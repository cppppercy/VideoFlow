"""faster-whisper 适配层。"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
from threading import Event, Lock, Thread
from time import perf_counter, process_time
from typing import Any

from .models import Transcript, TranscriptSegment, TranscriptionDiagnostics
from .runtime import make_temporary_directory
from .text_processing import clean_transcription_text

SUPPORTED_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4",
    ".mpeg", ".mpg", ".oga", ".ogg", ".opus", ".wav", ".webm", ".wma",
}
MODEL_OPTIONS = ("tiny", "base", "small")
_SENTENCE_ENDINGS = ("。", "！", "？", "!", "?", ";", "；")
LONG_MEDIA_THRESHOLD_SECONDS = 20 * 60
LONG_MEDIA_CHUNK_SECONDS = 5 * 60
LONG_MEDIA_OVERLAP_SECONDS = 3.0
ProgressCallback = Callable[[str, float | None, float | None], None]


@dataclass(frozen=True, slots=True)
class TranscriptionProfile:
    model_name: str
    beam_size: int
    batch_size: int
    min_silence_duration_ms: int
    device: str = "cpu"
    compute_type: str = "int8"


TRANSCRIPTION_PROFILES = {
    "fast": TranscriptionProfile("base", beam_size=1, batch_size=8, min_silence_duration_ms=500),
    "balanced": TranscriptionProfile("base", beam_size=5, batch_size=4, min_silence_duration_ms=800),
    "gpu_turbo": TranscriptionProfile(
        "turbo",
        beam_size=5,
        batch_size=4,
        min_silence_duration_ms=800,
        device="cuda",
        compute_type="float16",
    ),
    "accurate": TranscriptionProfile("small", beam_size=5, batch_size=4, min_silence_duration_ms=1200),
}
PROFILE_OPTIONS = (
    ("快速（base / beam 1）", "fast"),
    ("均衡（base / beam 5，推荐课程）", "balanced"),
    ("GPU 增强（turbo / RTX，推荐本机）", "gpu_turbo"),
    ("高精度（small，较慢）", "accurate"),
)


class TranscriptionError(RuntimeError):
    """向 CLI 和界面呈现的可读转录错误。"""


_MODEL_RUNTIME_LOCK = Lock()
_CUDA_DLL_DIRECTORY_HANDLES: list[Any] = []


@dataclass(frozen=True, slots=True)
class _CombinedTranscriptionInfo:
    language: str | None
    language_probability: float | None
    duration: float
    duration_after_vad: float | None


class _ResourceMonitor:
    """用标准库/系统 API 低频采样当前进程 RSS。"""

    def __init__(self) -> None:
        self._stop = Event()
        self._thread: Thread | None = None
        self.peak_memory_mb: float | None = None

    def __enter__(self) -> "_ResourceMonitor":
        if _current_rss_mb() is None:
            return self

        def sample() -> None:
            while not self._stop.wait(0.25):
                rss = _current_rss_mb()
                if rss is None:
                    return
                self.peak_memory_mb = max(self.peak_memory_mb or 0.0, rss)

        try:
            self.peak_memory_mb = _current_rss_mb()
            self._thread = Thread(target=sample, name="videoflow-resource-monitor", daemon=True)
            self._thread.start()
        except (OSError, RuntimeError):
            self._thread = None
        return self

    def __exit__(self, *args: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)


def _current_rss_mb() -> float | None:
    """返回当前进程常驻内存；不引入额外运行依赖。"""
    try:
        if os.name == "nt":
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            get_current_process = ctypes.windll.kernel32.GetCurrentProcess
            get_current_process.restype = wintypes.HANDLE
            get_process_memory = ctypes.windll.psapi.GetProcessMemoryInfo
            get_process_memory.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(ProcessMemoryCounters),
                wintypes.DWORD,
            ]
            get_process_memory.restype = wintypes.BOOL
            if not get_process_memory(
                get_current_process(), ctypes.byref(counters), counters.cb
            ):
                return None
            return counters.WorkingSetSize / (1024 * 1024)

        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return float(rss) / divisor
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def _notify(
    callback: ProgressCallback | None,
    stage: str,
    current: float | None = None,
    total: float | None = None,
) -> None:
    if callback is not None:
        callback(stage, current, total)


def _probe_media_duration(path: Path) -> float | None:
    """只读取媒体容器元数据，不解码内容；失败时交给识别引擎继续尝试。"""
    try:
        import av

        with av.open(str(path), metadata_errors="ignore") as container:
            if container.duration is not None:
                # container.duration 以 AV_TIME_BASE（微秒）计数；av.time_base 是每秒刻度。
                return max(0.0, float(container.duration / av.time_base))
            durations = []
            for stream in container.streams:
                if stream.duration is not None and stream.time_base is not None:
                    durations.append(float(stream.duration * stream.time_base))
            return max(durations) if durations else None
    except Exception:
        return None


def _coverage_status(
    media_duration: float | None,
    speech_duration: float | None,
    last_segment_end: float | None,
) -> str:
    """保守标记明显的尾部缺口；无法区分长静音时只要求复核，不宣称截断。"""
    if media_duration is None or media_duration <= 0:
        return "unknown"
    if last_segment_end is None:
        return "no_speech" if not speech_duration else "needs_review"
    tail_gap = max(0.0, media_duration - last_segment_end)
    if tail_gap > max(120.0, media_duration * 0.20):
        return "needs_review"
    return "appears_complete"


def _validate_media_path(media_path: str | Path) -> Path:
    path = Path(media_path).expanduser()
    if not path.is_file():
        raise TranscriptionError(f"找不到本地文件：{path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise TranscriptionError(f"不支持的文件类型 {path.suffix or '（无扩展名）'}；支持：{supported}")
    return path


@lru_cache(maxsize=1)
def _default_model_factory(model_name: str, device: str, compute_type: str) -> Any:
    """缓存最近使用的一个模型，批量任务无需为每个视频重复加载。"""
    if device == "cuda":
        _configure_cuda_dll_directories()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "未安装 faster-whisper。请执行：python -m pip install -e \".[dev]\""
        ) from exc
    try:
        model_options: dict[str, Any] = {}
        if device == "cpu":
            # CTranslate2 默认为 4 个 CPU 线程。在常见的移动工作站 CPU 上会明显
            # 未充分利用处理器；8 线程也是 faster-whisper 官方 CPU 基准采用的配置。
            model_options["cpu_threads"] = _recommended_cpu_threads()
        return WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            **model_options,
        )
    except Exception as exc:  # 模型下载、硬件或运行库错误均需对用户可见
        raise TranscriptionError(f"模型“{model_name}”无法加载：{exc}") from exc


def _recommended_cpu_threads() -> int:
    """为 CPU 推理选择保守线程数，可用 VIDEOFLOW_CPU_THREADS 覆盖。"""
    configured = os.environ.get("VIDEOFLOW_CPU_THREADS")
    if configured:
        try:
            value = int(configured)
        except ValueError as exc:
            raise TranscriptionError("VIDEOFLOW_CPU_THREADS 必须是 1–32 的整数。") from exc
        if not 1 <= value <= 32:
            raise TranscriptionError("VIDEOFLOW_CPU_THREADS 必须是 1–32 的整数。")
        return value
    logical_processors = os.cpu_count() or 4
    return max(1, min(8, logical_processors // 2 if logical_processors > 4 else logical_processors))


def cuda_device_available() -> bool:
    """检查 CTranslate2、显卡和 Windows CUDA 运行库是否同时可用。"""
    try:
        _configure_cuda_dll_directories()
        import ctranslate2

        if ctranslate2.get_cuda_device_count() <= 0:
            return False
        if os.name == "nt":
            import ctypes

            ctypes.WinDLL("cublas64_12.dll")
            ctypes.WinDLL("cudnn64_9.dll")
        return True
    except (ImportError, OSError, RuntimeError):
        return False


def _configure_cuda_dll_directories() -> None:
    """让 CTranslate2 能找到可选 NVIDIA Python 包中的 Windows DLL。"""
    if os.name != "nt" or _CUDA_DLL_DIRECTORY_HANDLES:
        return
    for package_name in ("nvidia.cublas", "nvidia.cudnn"):
        try:
            spec = importlib.util.find_spec(package_name)
        except ImportError:
            continue
        if spec is None or not spec.submodule_search_locations:
            continue
        for package_directory in spec.submodule_search_locations:
            dll_directory = Path(package_directory) / "bin"
            if dll_directory.is_dir():
                _CUDA_DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(dll_directory)))


def _default_batched_factory(model: Any) -> Any:
    try:
        from faster_whisper import BatchedInferencePipeline

        return BatchedInferencePipeline(model=model)
    except ImportError as exc:
        raise TranscriptionError("当前 faster-whisper 不支持批量推理，请重新安装依赖。") from exc


def _extract_audio_chunk(
    source: Path,
    destination: Path,
    *,
    start: float,
    duration: float,
) -> None:
    """将本地媒体的一小段转换为 16 kHz 单声道 WAV，避免长音频整段特征常驻内存。"""
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(destination),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(120.0, duration),
            check=False,
        )
    except FileNotFoundError as exc:
        raise TranscriptionError("找不到 FFmpeg。请安装 FFmpeg 并确保命令行可以执行 ffmpeg。") from exc
    except subprocess.TimeoutExpired as exc:
        raise TranscriptionError("准备长媒体分块时 FFmpeg 超时。请确认文件可正常播放。") from exc
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or "未知 FFmpeg 错误").strip().splitlines()[-1]
        raise TranscriptionError(f"无法准备长媒体音频分块：{detail}")


def _transcribe_long_media_chunked(
    model: Any,
    path: Path,
    *,
    media_duration: float,
    options: dict[str, Any],
    profile: TranscriptionProfile,
    progress_callback: ProgressCallback | None,
) -> tuple[tuple[TranscriptSegment, ...], _CombinedTranscriptionInfo]:
    """分块后顺序批量识别，兼顾长课程的内存上限与 CPU 吞吐。"""
    engine = _default_batched_factory(model)
    converted_items: list[TranscriptSegment] = []
    detected_language = options.get("language")
    language_probability: float | None = None
    speech_duration = 0.0
    has_speech_duration = False
    last_reported = 0.0
    chunk_count = max(
        1,
        int((media_duration + LONG_MEDIA_CHUNK_SECONDS - 1) // LONG_MEDIA_CHUNK_SECONDS),
    )

    with make_temporary_directory(prefix="videoflow-long-media-") as temporary_directory:
        chunk_path = Path(temporary_directory) / "chunk.wav"
        for chunk_index in range(chunk_count):
            keep_start = chunk_index * LONG_MEDIA_CHUNK_SECONDS
            keep_end = min(media_duration, keep_start + LONG_MEDIA_CHUNK_SECONDS)
            extract_start = max(0.0, keep_start - LONG_MEDIA_OVERLAP_SECONDS)
            extract_end = min(media_duration, keep_end + LONG_MEDIA_OVERLAP_SECONDS)
            _notify(
                progress_callback,
                f"正在准备第 {chunk_index + 1}/{chunk_count} 段音频",
                keep_start,
                media_duration,
            )
            _extract_audio_chunk(
                path,
                chunk_path,
                start=extract_start,
                duration=extract_end - extract_start,
            )

            chunk_options = dict(options)
            chunk_options["language"] = detected_language
            chunk_options["batch_size"] = profile.batch_size
            chunk_options["word_timestamps"] = True
            chunk_options["vad_parameters"] = {
                "min_silence_duration_ms": profile.min_silence_duration_ms
            }
            raw_segments, info = engine.transcribe(str(chunk_path), **chunk_options)
            if detected_language is None:
                detected_language = getattr(info, "language", None)
                language_probability = getattr(info, "language_probability", None)
            elif language_probability is None:
                language_probability = getattr(info, "language_probability", None)
            chunk_speech_duration = getattr(info, "duration_after_vad", None)
            if chunk_speech_duration is not None:
                speech_duration += float(chunk_speech_duration)
                has_speech_duration = True

            for segment in _convert_model_segments_iter(
                raw_segments,
                split_words=True,
                simplify_chinese=bool(
                    detected_language and str(detected_language).lower().startswith("zh")
                ),
            ):
                global_start = max(0.0, extract_start + segment.start)
                global_end = min(media_duration, extract_start + segment.end)
                midpoint = (global_start + global_end) / 2
                # 相邻块各保留 3 秒上下文；用中点归属消除重叠区重复字幕。
                if midpoint < keep_start or (
                    midpoint >= keep_end and chunk_index + 1 < chunk_count
                ):
                    continue
                converted = TranscriptSegment(global_start, global_end, segment.text)
                converted_items.append(converted)
                last_reported = max(last_reported, converted.end)
                _notify(
                    progress_callback,
                    f"正在识别第 {chunk_index + 1}/{chunk_count} 段",
                    last_reported,
                    media_duration,
                )
            last_reported = max(last_reported, keep_end)
            _notify(
                progress_callback,
                f"已完成第 {chunk_index + 1}/{chunk_count} 段",
                last_reported,
                media_duration,
            )

    converted_items.sort(key=lambda item: (item.start, item.end))
    return tuple(converted_items), _CombinedTranscriptionInfo(
        language=detected_language,
        language_probability=language_probability,
        duration=media_duration,
        duration_after_vad=min(speech_duration, media_duration) if has_speech_duration else None,
    )


def _convert_model_segments(
    segments: Any,
    *,
    split_words: bool,
    simplify_chinese: bool = True,
) -> tuple[TranscriptSegment, ...]:
    """将模型输出转为统一分段；批量推理按词时间戳重新切成可读字幕。"""
    return tuple(
        _convert_model_segments_iter(
            segments,
            split_words=split_words,
            simplify_chinese=simplify_chinese,
        )
    )


def _append_word_group(
    converted: list[TranscriptSegment],
    words: list[Any],
    *,
    simplify_chinese: bool,
) -> None:
    if not words:
        return
    raw_text = "".join(str(word.word) for word in words).strip()
    text = clean_transcription_text(raw_text) if simplify_chinese else raw_text
    if text:
        converted.append(
            TranscriptSegment(start=float(words[0].start), end=float(words[-1].end), text=text)
        )


def transcribe_media(
    media_path: str | Path,
    *,
    model_name: str = "base",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
    profile_name: str | None = None,
    initial_prompt: str | None = None,
    model_factory: Callable[[str, str, str], Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> Transcript:
    """转录一个本地媒体文件，返回不依赖 faster-whisper 的结构化结果。"""
    path = _validate_media_path(media_path)
    profile = None
    if profile_name is not None:
        profile = TRANSCRIPTION_PROFILES.get(profile_name)
        if profile is None:
            raise TranscriptionError(
                f"不支持的转录模式“{profile_name}”；可选：{', '.join(TRANSCRIPTION_PROFILES)}"
            )
        model_name = profile.model_name
        device = profile.device
        compute_type = profile.compute_type
        if device == "cuda" and not cuda_device_available():
            raise TranscriptionError(
                "GPU 增强模式需要可用的 NVIDIA CUDA 环境。请改用均衡模式，"
                "或执行 .\\.venv\\Scripts\\python.exe -m pip install -e \".[gpu]\" "
                "安装项目声明的 Windows CUDA 12 / cuDNN 9 运行库。"
            )
    if model_name not in MODEL_OPTIONS and profile is None:
        raise TranscriptionError(f"不支持的模型“{model_name}”；可选：{', '.join(MODEL_OPTIONS)}")

    factory = model_factory or _default_model_factory
    started_at = perf_counter()
    cpu_started_at = process_time()
    media_duration = _probe_media_duration(path)
    use_long_media_pipeline = bool(
        profile is not None
        and media_duration is not None
        and media_duration >= LONG_MEDIA_THRESHOLD_SECONDS
    )
    model_load_seconds = 0.0
    inference_seconds = 0.0
    pipeline = "standard"
    _notify(progress_callback, "正在检查媒体时长", 0.0, media_duration)
    try:
        # 模型加载与推理共用一把锁，避免两个网页任务同时首次加载模型而瞬间占满内存。
        with _MODEL_RUNTIME_LOCK, _ResourceMonitor() as resources:
            model_started_at = perf_counter()
            _notify(progress_callback, "正在加载模型", 0.0, media_duration)
            model = factory(model_name, device, compute_type)
            model_load_seconds = perf_counter() - model_started_at
            engine = model
            options: dict[str, Any] = {
                "language": language or None,
                "vad_filter": True,
                "beam_size": profile.beam_size if profile else 5,
            }
            if profile is not None and profile.beam_size == 1:
                # 快速档不执行多温度回退；困难片段以少量准确率换取可预测的耗时。
                options["temperature"] = 0.0
                options["condition_on_previous_text"] = False
            if profile is not None:
                options["repetition_penalty"] = 1.1
                options["no_repeat_ngram_size"] = 3
                options["hallucination_silence_threshold"] = 2.0
            if initial_prompt and initial_prompt.strip():
                # hotwords 专门用于给识别器提供术语提示；相比 initial_prompt，
                # 它不会把整段提示当成第一窗口之前已经说过的正文。
                options["hotwords"] = initial_prompt.strip()[:2000]
            split_words = profile is not None
            if profile is not None and model_factory is None and use_long_media_pipeline:
                pipeline = "chunked-batched"
                inference_started_at = perf_counter()
                _notify(progress_callback, "正在分块识别长媒体", 0.0, media_duration)
                converted_segments, info = _transcribe_long_media_chunked(
                    model,
                    path,
                    media_duration=media_duration,
                    options=options,
                    profile=profile,
                    progress_callback=progress_callback,
                )
                inference_seconds = perf_counter() - inference_started_at
            elif profile is not None and model_factory is None:
                engine = _default_batched_factory(model)
                pipeline = "batched"
                options["batch_size"] = profile.batch_size
                options["word_timestamps"] = True
                options["vad_parameters"] = {
                    "min_silence_duration_ms": profile.min_silence_duration_ms
                }
            elif profile is not None:
                # 注入测试模型时保留标准引擎，避免单元测试依赖 FFmpeg 和真实批量管线。
                # 生产环境的长课程已在上面的 chunked-batched 分支处理。
                pipeline = "long-media" if use_long_media_pipeline else "standard"
                options["word_timestamps"] = True
                options["vad_parameters"] = {
                    "min_silence_duration_ms": profile.min_silence_duration_ms
                }
            if pipeline != "chunked-batched":
                inference_started_at = perf_counter()
                _notify(progress_callback, "正在识别语音", 0.0, media_duration)
                segments, info = engine.transcribe(str(path), **options)
                converted_items: list[TranscriptSegment] = []
                detected_language = language or getattr(info, "language", None)
                for converted in _convert_model_segments_iter(
                    segments,
                    split_words=split_words,
                    simplify_chinese=bool(
                        detected_language
                        and str(detected_language).lower().startswith("zh")
                    ),
                ):
                    converted_items.append(converted)
                    _notify(
                        progress_callback,
                        "正在识别语音",
                        converted.end,
                        media_duration or getattr(info, "duration", None),
                    )
                converted_segments = tuple(converted_items)
                inference_seconds = perf_counter() - inference_started_at
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError(
            f"无法解码或转录“{path.name}”。请确认文件可播放、FFmpeg 可用且模型运行正常：{exc}"
        ) from exc

    measured_duration = media_duration or getattr(info, "duration", None)
    speech_duration = getattr(info, "duration_after_vad", None)
    last_segment_end = converted_segments[-1].end if converted_segments else None
    diagnostics = TranscriptionDiagnostics(
        media_duration=float(measured_duration) if measured_duration is not None else None,
        speech_duration=float(speech_duration) if speech_duration is not None else None,
        last_segment_end=last_segment_end,
        model_load_seconds=model_load_seconds,
        inference_seconds=inference_seconds,
        total_seconds=perf_counter() - started_at,
        cpu_seconds=process_time() - cpu_started_at,
        peak_memory_mb=resources.peak_memory_mb,
        pipeline=pipeline,
        coverage_status=_coverage_status(measured_duration, speech_duration, last_segment_end),
    )
    _notify(progress_callback, "识别结束，正在生成结果", measured_duration, measured_duration)
    return Transcript(
        segments=converted_segments,
        language=getattr(info, "language", None),
        language_probability=getattr(info, "language_probability", None),
        diagnostics=diagnostics,
    )


def _convert_model_segments_iter(
    segments: Any,
    *,
    split_words: bool,
    simplify_chinese: bool = True,
) -> Any:
    """逐个输出转换后的字幕段，使长音频可以持续报告实际识别位置。"""
    for item in segments:
        words = getattr(item, "words", None) if split_words else None
        if not words:
            raw_text = str(item.text).strip()
            text = clean_transcription_text(raw_text) if simplify_chinese else raw_text
            if text:
                yield TranscriptSegment(start=float(item.start), end=float(item.end), text=text)
            continue

        converted: list[TranscriptSegment] = []
        group: list[Any] = []
        for word in words:
            if group and float(word.start) - float(group[-1].end) >= 0.8:
                _append_word_group(converted, group, simplify_chinese=simplify_chinese)
                group = []
            if group and float(word.end) - float(group[0].start) > 8.0:
                _append_word_group(converted, group, simplify_chinese=simplify_chinese)
                group = []
            group.append(word)
            duration = float(group[-1].end) - float(group[0].start)
            text = "".join(str(part.word) for part in group).strip()
            if duration >= 2.0 and text.endswith(_SENTENCE_ENDINGS):
                _append_word_group(converted, group, simplify_chinese=simplify_chinese)
                group = []
        _append_word_group(converted, group, simplify_chinese=simplify_chinese)
        yield from converted
