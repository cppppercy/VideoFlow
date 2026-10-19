"""Gradio 界面；此模块只负责输入输出呈现。"""

import atexit
from pathlib import Path
from typing import Any, Callable

from .exporters import transcript_to_srt, transcript_to_txt, write_batch_archive, write_exports
from .runtime import make_temporary_directory
from .sources.bilibili import BilibiliSubtitleError, fetch_bilibili_subtitles
from .sources.remote_audio import RemoteAudioError
from .sources.xjtu_lms import XjtuLmsError
from .system_audio import SystemAudioCaptureError, SystemAudioRecorder
from .transcriber import (
    PROFILE_OPTIONS,
    TranscriptionError,
    cuda_device_available,
    transcribe_media,
)
from .workflows import transcribe_bilibili_batch, transcribe_lms_payload

LANGUAGE_OPTIONS = [("自动识别", ""), ("中文", "zh"), ("English", "en"), ("日本語", "ja"), ("한국어", "ko")]
BILIBILI_LANGUAGE_OPTIONS = [("中文（优先）", "zh.*"), ("English", "en.*"), ("任意可用字幕", "all")]
BROWSER_OPTIONS = [("不使用登录（仅公开可访问字幕）", ""), ("Chrome（需你已登录 B 站）", "chrome"), ("Edge（需你已登录 B 站）", "edge")]


class _ExportStore:
    """Gradio 下载文件的临时目录；进程退出时删除，不保存用户媒体。"""

    def __init__(self) -> None:
        self._directory = make_temporary_directory(prefix="videoflow-exports-")
        atexit.register(self._directory.cleanup)

    @property
    def path(self) -> str:
        return self._directory.name


_EXPORT_STORE = _ExportStore()
_SYSTEM_AUDIO_RECORDER = SystemAudioRecorder(_EXPORT_STORE.path)


def _result_table(transcript: Any) -> list[list[str]]:
    return [
        [f"{item.start:.3f}", f"{item.end:.3f}", item.text, item.review_reason or ""]
        for item in transcript.segments
    ]


def _failure_result(error: Exception) -> tuple[str, list[list[str]], str, str, None, None]:
    """将预期错误显示在页面状态框中，避免 Gradio 只显示无信息的“错误”。"""
    return (f"错误：{error}", [], "", "", None, None)


def _format_clock(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    rounded = max(0, round(seconds))
    hours, remainder = divmod(rounded, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _diagnostic_status(prefix: str, transcript: Any) -> str:
    diagnostics = transcript.diagnostics
    if diagnostics is None:
        return prefix
    details = (
        f"媒体时长 {_format_clock(diagnostics.media_duration)}，"
        f"最后字幕 {_format_clock(diagnostics.last_segment_end)}，"
        f"识别耗时 {diagnostics.inference_seconds:.1f} 秒"
    )
    if diagnostics.realtime_factor is not None:
        details += f"，RTF {diagnostics.realtime_factor:.3f}"
    pipeline_labels = {
        "batched": "批量推理",
        "chunked-batched": "长媒体分块批量推理",
        "long-media": "逐窗口推理",
        "standard": "标准推理",
    }
    details += f"，处理方式 {pipeline_labels.get(diagnostics.pipeline, diagnostics.pipeline)}"
    if diagnostics.peak_memory_mb is not None:
        details += f"，进程峰值内存约 {diagnostics.peak_memory_mb:.0f} MB"
    if diagnostics.effective_batch_size is not None:
        details += f"，批量大小 {diagnostics.effective_batch_size}"
    if diagnostics.gpu_name:
        details += f"，GPU {diagnostics.gpu_name}"
        if diagnostics.peak_gpu_memory_mb is not None:
            details += f"，本进程峰值显存约 {diagnostics.peak_gpu_memory_mb:.0f} MB"
    if diagnostics.review_segment_count:
        details += f"，已标记 {diagnostics.review_segment_count} 段需复核"
    if diagnostics.coverage_status == "needs_review":
        suffix = "。最后字幕与媒体末尾相差较大，请检查尾部是否为静音或发生遗漏；本次结果未标记为完整成功。"
    elif diagnostics.coverage_status == "no_speech":
        suffix = "。媒体中未识别到语音，请检查音轨、音量和语言设置。"
    elif diagnostics.coverage_status == "unknown":
        suffix = "。无法读取媒体总时长，请按最后字幕位置人工确认完整性。"
    else:
        suffix = "。覆盖检查未发现明显提前结束。"
    return f"{prefix}{details}{suffix}"


def _gradio_progress_callback(progress: Any) -> Callable[[str, float | None, float | None], None]:
    def report(stage: str, current: float | None, total: float | None) -> None:
        if current is not None and total is not None and total > 0:
            progress(min(max(current / total, 0.0), 1.0), desc=stage)
        elif current is not None:
            progress((max(0, round(current)), None), desc=stage, unit="秒")
        else:
            progress(0, desc=stage)

    return report


def process_upload(
    media_path: str | None,
    profile_name: str,
    language: str | None,
    initial_prompt: str | None,
    refine_low_confidence: bool = False,
    progress_callback: Callable[[str, float | None, float | None], None] | None = None,
) -> tuple[str, list[list[str]], str, str, str | None, str | None]:
    """UI 回调。导出文件只在进程的临时目录内保存。"""
    try:
        if not media_path:
            raise ValueError("请先选择一个本地音频或视频文件。")
        transcript = transcribe_media(
            media_path,
            profile_name=profile_name,
            language=language or None,
            initial_prompt=initial_prompt,
            refine_low_confidence=refine_low_confidence,
            progress_callback=progress_callback,
        )
        language_label = transcript.language or "未知"
        status = _diagnostic_status(
            f"转录结束：{len(transcript.segments)} 个分段，识别语言：{language_label}。",
            transcript,
        )
        txt_path, srt_path = write_exports(transcript, _EXPORT_STORE.path, Path(media_path).stem)
        return (
            status,
            _result_table(transcript),
            transcript_to_txt(transcript),
            transcript_to_srt(transcript),
            str(txt_path),
            str(srt_path),
        )
    except (ValueError, TranscriptionError, OSError) as exc:
        return _failure_result(exc)


def process_bilibili_url(
    video_url: str | None, language_pattern: str, browser: str | None
) -> tuple[str, list[list[str]], str, str, str | None, str | None]:
    """B 站已有字幕回调；不下载完整视频，也不持久化浏览器登录信息。"""
    try:
        if not video_url or not video_url.strip():
            raise ValueError("请粘贴完整的 B 站 BV 视频链接。")
        result = fetch_bilibili_subtitles(
            video_url, language_pattern=language_pattern, browser=browser or None
        )
        transcript = result.transcript
        txt_path, srt_path = write_exports(transcript, _EXPORT_STORE.path, result.title)
        language_label = transcript.language or "自动"
        status = (
            f"已导入 B 站已有字幕：{len(transcript.segments)} 个分段，语言：{language_label}。"
            "未下载完整视频。"
        )
        return (
            status,
            _result_table(transcript),
            transcript_to_txt(transcript),
            transcript_to_srt(transcript),
            str(txt_path),
            str(srt_path),
        )
    except (ValueError, BilibiliSubtitleError, OSError) as exc:
        return _failure_result(exc)


def process_bilibili_audio_batch(
    raw_urls: str | None,
    profile_name: str,
    language: str | None,
    browser: str | None,
    initial_prompt: str | None,
    confirmed: bool,
    refine_low_confidence: bool = False,
    progress_callback: Callable[[str, float | None, float | None], None] | None = None,
) -> tuple[str, str, str | None]:
    """批量提取 B 站独立音频流并转录，完整视频不会作为回退格式下载。"""
    if not confirmed:
        return "请先确认你有权处理这些视频，仅用于个人学习。", "", None
    try:
        result = transcribe_bilibili_batch(
            raw_urls or "",
            model_name="base",
            language=language or None,
            browser=browser or None,
            profile_name=profile_name,
            initial_prompt=initial_prompt,
            refine_low_confidence=refine_low_confidence,
            progress_callback=progress_callback,
        )
        report_lines = [
            *(f"成功：{item.source}" for item in result.successes),
            *(f"失败：{source}\n  {message}" for source, message in result.failures),
        ]
        if not result.successes:
            return f"处理完成：0 个成功，{len(result.failures)} 个失败。", "\n".join(report_lines), None
        archive = write_batch_archive(
            [(item.title, item.transcript) for item in result.successes],
            _EXPORT_STORE.path,
            "videoflow-bilibili-batch",
        )
        status = (
            f"处理完成：{len(result.successes)} 个成功，{len(result.failures)} 个失败。"
            "每个视频的 TXT/SRT 已打包；临时音频已删除。"
        )
        return status, "\n".join(report_lines), str(archive)
    except (ValueError, BilibiliSubtitleError, RemoteAudioError, TranscriptionError, OSError) as exc:
        return f"错误：{exc}", "", None


def process_lms_replay(
    payload: str | None,
    profile_name: str,
    language: str | None,
    initial_prompt: str | None,
    confirmed: bool,
    refine_low_confidence: bool = False,
    progress_callback: Callable[[str, float | None, float | None], None] | None = None,
) -> tuple[str, str, list[list[str]], str, str, str | None, str | None]:
    """使用浏览器助手提供的一次性任务提取课程音频并转录；首项用于清空任务框。"""
    if not confirmed:
        return "", "请先确认你有权为个人学习处理该课程回放。", [], "", "", None, None
    try:
        result = transcribe_lms_payload(
            payload or "",
            model_name="base",
            language=language or None,
            profile_name=profile_name,
            initial_prompt=initial_prompt,
            refine_low_confidence=refine_low_confidence,
            progress_callback=progress_callback,
        )
        transcript = result.transcript
        txt_path, srt_path = write_exports(transcript, _EXPORT_STORE.path, result.title)
        status = _diagnostic_status(
            f"课程回放转录结束：{len(transcript.segments)} 个分段。"
            "短期任务和临时音频未持久化；输入框已清空。",
            transcript,
        )
        return (
            "",
            status,
            _result_table(transcript),
            transcript_to_txt(transcript),
            transcript_to_srt(transcript),
            str(txt_path),
            str(srt_path),
        )
    except (XjtuLmsError, RemoteAudioError, TranscriptionError, ValueError, OSError) as exc:
        return "", f"错误：{exc}", [], "", "", None, None


def start_system_audio_recording(confirmed: bool) -> str:
    """开始本机扬声器回环录音，不接触网页内容或登录信息。"""
    if not confirmed:
        return "请先确认你有权为个人学习目的记录当前播放内容。"
    try:
        _SYSTEM_AUDIO_RECORDER.start()
        return "正在录制电脑声音。请在课程页面正常播放；结束后回到这里点击“停止录制并转录”。"
    except SystemAudioCaptureError as exc:
        return f"错误：{exc}"


def stop_system_audio_and_transcribe(
    profile_name: str,
    language: str | None,
    initial_prompt: str | None,
    refine_low_confidence: bool = False,
    progress_callback: Callable[[str, float | None, float | None], None] | None = None,
) -> tuple[str, list[list[str]], str, str, str | None, str | None]:
    """停止录音后立即使用既有本地转录链路；原始 WAV 随后删除。"""
    try:
        captured = _SYSTEM_AUDIO_RECORDER.stop()
        transcript = transcribe_media(
            captured.path,
            profile_name=profile_name,
            language=language or None,
            initial_prompt=initial_prompt,
            refine_low_confidence=refine_low_confidence,
            progress_callback=progress_callback,
        )
        txt_path, srt_path = write_exports(transcript, _EXPORT_STORE.path, "system-audio-transcript")
        status = _diagnostic_status(
            f"转录结束：已录制 {captured.seconds:.1f} 秒电脑声音并生成 {len(transcript.segments)} 个分段。"
            "原始临时录音已删除。",
            transcript,
        )
        return (
            status,
            _result_table(transcript),
            transcript_to_txt(transcript),
            transcript_to_srt(transcript),
            str(txt_path),
            str(srt_path),
        )
    except (SystemAudioCaptureError, TranscriptionError, OSError) as exc:
        return _failure_result(exc)
    finally:
        _SYSTEM_AUDIO_RECORDER.cleanup()


def create_app() -> Any:
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError("未安装 Gradio。请执行：python -m pip install -e \".[dev]\"") from exc

    has_cuda = cuda_device_available()
    runtime_profile_options = tuple(
        option for option in PROFILE_OPTIONS if has_cuda or option[1] != "gpu_turbo"
    )
    default_profile = "gpu_turbo" if has_cuda else "balanced"

    def upload_with_progress(
        media_path: str | None,
        profile_name: str,
        language: str | None,
        initial_prompt: str | None,
        refine_low_confidence: bool,
        progress: Any = gr.Progress(),
    ) -> tuple[str, list[list[str]], str, str, str | None, str | None]:
        return process_upload(
            media_path,
            profile_name,
            language,
            initial_prompt,
            refine_low_confidence,
            progress_callback=_gradio_progress_callback(progress),
        )

    def bilibili_batch_with_progress(
        raw_urls: str | None,
        profile_name: str,
        language: str | None,
        browser: str | None,
        initial_prompt: str | None,
        refine_low_confidence: bool,
        confirmed: bool,
        progress: Any = gr.Progress(),
    ) -> tuple[str, str, str | None]:
        return process_bilibili_audio_batch(
            raw_urls,
            profile_name,
            language,
            browser,
            initial_prompt,
            confirmed,
            refine_low_confidence,
            progress_callback=_gradio_progress_callback(progress),
        )

    def lms_with_progress(
        payload: str | None,
        profile_name: str,
        language: str | None,
        initial_prompt: str | None,
        refine_low_confidence: bool,
        confirmed: bool,
        progress: Any = gr.Progress(),
    ) -> tuple[str, str, list[list[str]], str, str, str | None, str | None]:
        return process_lms_replay(
            payload,
            profile_name,
            language,
            initial_prompt,
            confirmed,
            refine_low_confidence,
            progress_callback=_gradio_progress_callback(progress),
        )

    def recording_with_progress(
        profile_name: str,
        language: str | None,
        initial_prompt: str | None,
        refine_low_confidence: bool,
        progress: Any = gr.Progress(),
    ) -> tuple[str, list[list[str]], str, str, str | None, str | None]:
        return stop_system_audio_and_transcribe(
            profile_name,
            language,
            initial_prompt,
            refine_low_confidence,
            progress_callback=_gradio_progress_callback(progress),
        )

    with gr.Blocks(title="VideoFlow") as demo:
        gr.Markdown(
            "# VideoFlow\n"
            "本机完成音视频转字幕：选择来源 → 设置转录模式 → 下载 TXT/SRT。"
            "在线来源只处理当前账号有权访问的内容，临时音频在完成后删除。"
        )
        with gr.Accordion("转录设置（本地文件、B 站音频、LMS 和兼容录音共用）", open=True):
            with gr.Row():
                profile = gr.Dropdown(
                    runtime_profile_options,
                    value=default_profile,
                    label="速度 / 准确度",
                )
                language = gr.Dropdown(LANGUAGE_OPTIONS, value="zh", label="语音语言")
            initial_prompt = gr.Textbox(
                label="课程术语热词（推荐填写，用逗号分隔）",
                placeholder="例如：数值计算，线性方程组，高斯消去法，残值，舍入误差",
                lines=2,
            )
            refine_low_confidence = gr.Checkbox(
                label="精修可疑片段（可选：最多 12 段，以更高 beam 重试）",
                value=False,
            )
            gpu_note = (
                "已检测到 NVIDIA CUDA：可选择“GPU 增强”，使用 turbo 提高准确度且避免 CPU small 的慢速。"
                if has_cuda
                else "未检测到完整 CUDA 运行库；网页会隐藏 GPU 增强，请选择快速或均衡。"
            )
            gr.Markdown(
                "快速使用 base/beam 1；均衡使用 base/beam 5，适合普通课程；高精度使用 small。"
                "GPU 增强使用 turbo/beam 5 和 CUDA FP16；其他模式使用 CPU INT8。"
                "短音频使用批量推理，超过 20 分钟时自动按 5 分钟"
                "分块批量识别。中文结果会统一转换为简体，并压缩明显的重复幻觉。"
                "术语热词会通过专用 hotwords 参数提示模型，不会作为正文前缀。"
                "勾选精修后，程序只会重试模型标记为低置信或异常重复的少量片段；"
                "它是启发式优化，不替代人工抽查。"
                f"首次使用对应模型时需要下载。{gpu_note}"
            )

        with gr.Tabs():
            with gr.Tab("本地文件"):
                media = gr.File(label="选择音频或视频", type="filepath")
                run_button = gr.Button("开始转录本地文件", variant="primary")

            with gr.Tab("在线内容"):
                with gr.Tabs():
                    with gr.Tab("B 站"):
                        with gr.Accordion("已有字幕：直接导入（最快）", open=True):
                            gr.Markdown("只读取单个 BV 视频的字幕 JSON，不下载视频或音频。")
                            bilibili_url = gr.Textbox(
                                label="B 站视频链接",
                                placeholder="https://www.bilibili.com/video/BV...",
                            )
                            with gr.Row():
                                bilibili_language = gr.Dropdown(
                                    BILIBILI_LANGUAGE_OPTIONS, value="zh.*", label="字幕语言"
                                )
                                browser = gr.Dropdown(
                                    BROWSER_OPTIONS, value="", label="登录会话（可选）"
                                )
                            bilibili_button = gr.Button("导入已有字幕")

                        with gr.Accordion("没有字幕：提取音频并识别", open=False):
                            gr.Markdown(
                                "每行一个 BV 链接，最多 10 个。只选择独立音频流，不实时播放，"
                                "不会混入电脑其他声音；结果打包为 ZIP。"
                            )
                            bilibili_audio_urls = gr.Textbox(
                                label="B 站链接（每行一个）",
                                placeholder="https://www.bilibili.com/video/BV...",
                                lines=5,
                            )
                            bilibili_audio_browser = gr.Dropdown(
                                BROWSER_OPTIONS, value="", label="登录会话（可选）"
                            )
                            bilibili_audio_consent = gr.Checkbox(
                                label="我确认有权处理这些视频，仅用于个人学习", value=False
                            )
                            bilibili_audio_button = gr.Button("批量转录 B 站音频", variant="primary")
                            bilibili_batch_status = gr.Textbox(label="批量状态", interactive=False)
                            bilibili_batch_report = gr.Textbox(
                                label="逐项结果", lines=6, interactive=False
                            )
                            bilibili_batch_zip = gr.File(
                                label="下载批量 TXT/SRT（ZIP）", interactive=False
                            )

                    with gr.Tab("西交 LMS"):
                        gr.Markdown(
                            "在已登录的课程活动页点击浏览器助手右下角“复制到 VideoFlow”，"
                            "粘贴后即可直接提取授权回放，不需要把课程实时播放一遍。"
                        )
                        lms_payload = gr.Textbox(
                            label="LMS 助手任务（一次性信息，处理后自动清空）",
                            type="password",
                        )
                        lms_consent = gr.Checkbox(
                            label="我确认当前账号有观看权限，并仅为个人学习转录", value=False
                        )
                        lms_button = gr.Button("提取 LMS 音频并转录", variant="primary")
                        gr.Markdown(
                            "助手目录：`D:\\application\\VideoFlow\\browser-extension`。"
                            "新版会优先使用 LMS 的授权直链、附带平台要求的同源请求头，并在失败时尝试备用机位。"
                        )

            with gr.Tab("兼容录音"):
                gr.Markdown(
                    "仅在在线直连确实失败时使用。它会实时录制 Windows 默认扬声器，"
                    "因此必须完整播放，且会录入通知和其他声音。"
                )
                recording_consent = gr.Checkbox(
                    label="我确认有权记录当前播放内容，仅用于个人学习", value=False
                )
                with gr.Row():
                    recording_start = gr.Button("开始录制电脑声音")
                    recording_stop = gr.Button("停止录制并转录", variant="primary")
        status = gr.Textbox(label="处理状态", interactive=False)
        table = gr.Dataframe(
            headers=["开始（秒）", "结束（秒）", "文本", "复核提示"],
            label="字幕分段",
            interactive=False,
        )
        full_text = gr.Textbox(label="全文（可复制）", lines=12)
        srt_text = gr.Textbox(label="SRT 内容（可复制）", lines=12)
        with gr.Row():
            txt_download = gr.File(label="下载 TXT", interactive=False)
            srt_download = gr.File(label="下载 SRT", interactive=False)
        run_button.click(
            upload_with_progress,
            [media, profile, language, initial_prompt, refine_low_confidence],
            [status, table, full_text, srt_text, txt_download, srt_download],
        )
        bilibili_button.click(
            process_bilibili_url,
            [bilibili_url, bilibili_language, browser],
            [status, table, full_text, srt_text, txt_download, srt_download],
        )
        bilibili_audio_button.click(
            bilibili_batch_with_progress,
            [
                bilibili_audio_urls,
                profile,
                language,
                bilibili_audio_browser,
                initial_prompt,
                refine_low_confidence,
                bilibili_audio_consent,
            ],
            [bilibili_batch_status, bilibili_batch_report, bilibili_batch_zip],
        )
        lms_button.click(
            lms_with_progress,
            [lms_payload, profile, language, initial_prompt, refine_low_confidence, lms_consent],
            [lms_payload, status, table, full_text, srt_text, txt_download, srt_download],
        )
        recording_start.click(start_system_audio_recording, [recording_consent], [status])
        recording_stop.click(
            recording_with_progress,
            [profile, language, initial_prompt, refine_low_confidence],
            [status, table, full_text, srt_text, txt_download, srt_download],
        )

    return demo
