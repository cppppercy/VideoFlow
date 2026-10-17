"""faster-whisper 适配层。"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

from .models import Transcript, TranscriptSegment

SUPPORTED_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4",
    ".mpeg", ".mpg", ".oga", ".ogg", ".opus", ".wav", ".webm", ".wma",
}
MODEL_OPTIONS = ("tiny", "base", "small")
_SENTENCE_ENDINGS = ("。", "！", "？", "!", "?", ";", "；")


@dataclass(frozen=True, slots=True)
class TranscriptionProfile:
    model_name: str
    beam_size: int
    batch_size: int
    min_silence_duration_ms: int


TRANSCRIPTION_PROFILES = {
    "fast": TranscriptionProfile("tiny", beam_size=1, batch_size=8, min_silence_duration_ms=500),
    "balanced": TranscriptionProfile("base", beam_size=5, batch_size=4, min_silence_duration_ms=800),
    "accurate": TranscriptionProfile("small", beam_size=5, batch_size=4, min_silence_duration_ms=1200),
}
PROFILE_OPTIONS = (
    ("快速（tiny，低占用）", "fast"),
    ("均衡（base，推荐）", "balanced"),
    ("高精度（small，较慢）", "accurate"),
)


class TranscriptionError(RuntimeError):
    """向 CLI 和界面呈现的可读转录错误。"""


_MODEL_RUNTIME_LOCK = Lock()


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
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError(
            "未安装 faster-whisper。请执行：python -m pip install -e \".[dev]\""
        ) from exc
    try:
        return WhisperModel(model_name, device=device, compute_type=compute_type)
    except Exception as exc:  # 模型下载、硬件或运行库错误均需对用户可见
        raise TranscriptionError(f"模型“{model_name}”无法加载：{exc}") from exc


def _default_batched_factory(model: Any) -> Any:
    try:
        from faster_whisper import BatchedInferencePipeline

        return BatchedInferencePipeline(model=model)
    except ImportError as exc:
        raise TranscriptionError("当前 faster-whisper 不支持批量推理，请重新安装依赖。") from exc


def _convert_model_segments(segments: Any, *, split_words: bool) -> tuple[TranscriptSegment, ...]:
    """将模型输出转为统一分段；批量推理按词时间戳重新切成可读字幕。"""
    converted: list[TranscriptSegment] = []
    for item in segments:
        words = getattr(item, "words", None) if split_words else None
        if not words:
            text = str(item.text).strip()
            if text:
                converted.append(
                    TranscriptSegment(start=float(item.start), end=float(item.end), text=text)
                )
            continue

        group: list[Any] = []
        for word in words:
            if group and float(word.start) - float(group[-1].end) >= 0.8:
                _append_word_group(converted, group)
                group = []
            if group and float(word.end) - float(group[0].start) > 8.0:
                _append_word_group(converted, group)
                group = []
            group.append(word)
            duration = float(group[-1].end) - float(group[0].start)
            text = "".join(str(part.word) for part in group).strip()
            if duration >= 2.0 and text.endswith(_SENTENCE_ENDINGS):
                _append_word_group(converted, group)
                group = []
        _append_word_group(converted, group)
    return tuple(converted)


def _append_word_group(converted: list[TranscriptSegment], words: list[Any]) -> None:
    if not words:
        return
    text = "".join(str(word.word) for word in words).strip()
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
    if model_name not in MODEL_OPTIONS:
        raise TranscriptionError(f"不支持的模型“{model_name}”；可选：{', '.join(MODEL_OPTIONS)}")

    factory = model_factory or _default_model_factory
    try:
        # 模型加载与推理共用一把锁，避免两个网页任务同时首次加载模型而瞬间占满内存。
        with _MODEL_RUNTIME_LOCK:
            model = factory(model_name, device, compute_type)
            engine = model
            options: dict[str, Any] = {
                "language": language or None,
                "vad_filter": True,
                "beam_size": profile.beam_size if profile else 5,
            }
            if initial_prompt and initial_prompt.strip():
                options["initial_prompt"] = initial_prompt.strip()[:2000]
            if profile is not None and model_factory is None:
                engine = _default_batched_factory(model)
                options["batch_size"] = profile.batch_size
                options["word_timestamps"] = True
                options["vad_parameters"] = {
                    "min_silence_duration_ms": profile.min_silence_duration_ms
                }
            segments, info = engine.transcribe(str(path), **options)
            converted = _convert_model_segments(segments, split_words=profile is not None)
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError(
            f"无法解码或转录“{path.name}”。请确认文件可播放、FFmpeg 可用且模型运行正常：{exc}"
        ) from exc

    return Transcript(
        segments=converted,
        language=getattr(info, "language", None),
        language_probability=getattr(info, "language_probability", None),
    )
