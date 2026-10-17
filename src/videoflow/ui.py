"""Gradio 界面；此模块只负责输入输出呈现。"""

import atexit
from pathlib import Path
from typing import Any

from .exporters import transcript_to_srt, transcript_to_txt, write_batch_archive, write_exports
from .runtime import make_temporary_directory
from .sources.bilibili import BilibiliSubtitleError, fetch_bilibili_subtitles
from .sources.remote_audio import RemoteAudioError
from .sources.xjtu_lms import XjtuLmsError
from .system_audio import SystemAudioCaptureError, SystemAudioRecorder
from .transcriber import MODEL_OPTIONS, TranscriptionError, transcribe_media
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
    return [[f"{item.start:.3f}", f"{item.end:.3f}", item.text] for item in transcript.segments]


def _failure_result(error: Exception) -> tuple[str, list[list[str]], str, str, None, None]:
    """将预期错误显示在页面状态框中，避免 Gradio 只显示无信息的“错误”。"""
    return (f"错误：{error}", [], "", "", None, None)


def process_upload(
    media_path: str | None, model_name: str, language: str | None
) -> tuple[str, list[list[str]], str, str, str | None, str | None]:
    """UI 回调。导出文件只在进程的临时目录内保存。"""
    try:
        if not media_path:
            raise ValueError("请先选择一个本地音频或视频文件。")
        transcript = transcribe_media(media_path, model_name=model_name, language=language or None)
        language_label = transcript.language or "未知"
        status = f"完成：{len(transcript.segments)} 个分段，识别语言：{language_label}。"
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
    model_name: str,
    language: str | None,
    browser: str | None,
    confirmed: bool,
) -> tuple[str, str, str | None]:
    """批量提取 B 站独立音频流并转录，完整视频不会作为回退格式下载。"""
    if not confirmed:
        return "请先确认你有权处理这些视频，仅用于个人学习。", "", None
    try:
        result = transcribe_bilibili_batch(
            raw_urls or "",
            model_name=model_name,
            language=language or None,
            browser=browser or None,
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
    model_name: str,
    language: str | None,
    confirmed: bool,
) -> tuple[str, str, list[list[str]], str, str, str | None, str | None]:
    """使用浏览器助手提供的一次性任务提取课程音频并转录；首项用于清空任务框。"""
    if not confirmed:
        return "", "请先确认你有权为个人学习处理该课程回放。", [], "", "", None, None
    try:
        result = transcribe_lms_payload(
            payload or "",
            model_name=model_name,
            language=language or None,
        )
        transcript = result.transcript
        txt_path, srt_path = write_exports(transcript, _EXPORT_STORE.path, result.title)
        status = (
            f"课程回放转录完成：{len(transcript.segments)} 个分段。"
            "短期任务和临时音频未持久化；输入框已清空。"
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
    model_name: str, language: str | None
) -> tuple[str, list[list[str]], str, str, str | None, str | None]:
    """停止录音后立即使用既有本地转录链路；原始 WAV 随后删除。"""
    try:
        captured = _SYSTEM_AUDIO_RECORDER.stop()
        transcript = transcribe_media(captured.path, model_name=model_name, language=language or None)
        txt_path, srt_path = write_exports(transcript, _EXPORT_STORE.path, "system-audio-transcript")
        status = (
            f"完成：已录制 {captured.seconds:.1f} 秒电脑声音并生成 {len(transcript.segments)} 个分段。"
            "原始临时录音已删除。"
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

    with gr.Blocks(title="VideoFlow") as demo:
        gr.Markdown(
            "# VideoFlow\n本地文件、B 站独立音频流或已授权课程回放均在本机转录。"
            "不上传媒体，临时音频在处理后删除。"
        )
        with gr.Tabs():
            with gr.Tab("本地文件转录"):
                with gr.Row():
                    media = gr.File(label="音频或视频", type="filepath")
                    with gr.Column():
                        model = gr.Dropdown(MODEL_OPTIONS, value="base", label="模型")
                        language = gr.Dropdown(LANGUAGE_OPTIONS, value="", label="语言")
                        run_button = gr.Button("开始本地转录", variant="primary")
            with gr.Tab("B 站已有字幕"):
                gr.Markdown(
                    "仅支持单个 BV 视频链接；只下载字幕 JSON，不下载完整视频。"
                    "部分字幕需登录 B 站才能访问。没有已有字幕时，请改用“B 站音频转录”。"
                )
                bilibili_url = gr.Textbox(label="B 站视频链接", placeholder="https://www.bilibili.com/video/BV...")
                with gr.Row():
                    bilibili_language = gr.Dropdown(BILIBILI_LANGUAGE_OPTIONS, value="zh.*", label="字幕语言")
                    browser = gr.Dropdown(BROWSER_OPTIONS, value="", label="本机登录会话（可选）")
                bilibili_button = gr.Button("导入已有字幕", variant="primary")
            with gr.Tab("B 站音频转录"):
                gr.Markdown(
                    "每行粘贴一个完整 BV 链接（单次最多 10 个）。VideoFlow 只选择 B 站独立音频流，"
                    "不会用完整视频格式兜底；下载后离线转录，因此不必实时播放，也不会混入电脑其他声音。"
                )
                bilibili_audio_urls = gr.Textbox(
                    label="B 站链接（每行一个）",
                    placeholder="https://www.bilibili.com/video/BV...",
                    lines=6,
                )
                with gr.Row():
                    bilibili_audio_model = gr.Dropdown(MODEL_OPTIONS, value="base", label="模型")
                    bilibili_audio_language = gr.Dropdown(LANGUAGE_OPTIONS, value="zh", label="语音语言")
                    bilibili_audio_browser = gr.Dropdown(
                        BROWSER_OPTIONS, value="", label="本机登录会话（可选）"
                    )
                bilibili_audio_consent = gr.Checkbox(
                    label="我确认有权处理这些视频，仅用于个人学习", value=False
                )
                bilibili_audio_button = gr.Button("提取音频并批量转录", variant="primary")
                bilibili_batch_status = gr.Textbox(label="批量状态", interactive=False)
                bilibili_batch_report = gr.Textbox(label="逐项结果", lines=8, interactive=False)
                bilibili_batch_zip = gr.File(label="下载批量 TXT/SRT（ZIP）", interactive=False)
            with gr.Tab("西交 LMS 课程回放"):
                gr.Markdown(
                    "无需播放完整课程。先在 Edge/Chrome 扩展页加载仓库中的 `browser-extension` 文件夹；"
                    "登录 LMS 并打开具体学习活动后，点击右下角“复制到 VideoFlow”，再把任务粘贴到下面。"
                    "助手不导出 Cookie、账号或密码；短期任务仅在本次本机处理期间使用。"
                )
                lms_payload = gr.Textbox(
                    label="LMS 助手任务（一次性短期信息，处理后自动清空）", type="password"
                )
                with gr.Row():
                    lms_model = gr.Dropdown(MODEL_OPTIONS, value="base", label="模型")
                    lms_language = gr.Dropdown(LANGUAGE_OPTIONS, value="zh", label="语音语言")
                lms_consent = gr.Checkbox(
                    label="我确认当前账号有观看权限，并仅为个人学习转录", value=False
                )
                lms_button = gr.Button("提取课程音频并转录", variant="primary")
            with gr.Tab("播放中的网页/课程转录"):
                gr.Markdown(
                    "兼容性兜底：适用于链接音频提取失败但可以正常播放的内容。"
                    "请自行在课程网页正常播放；VideoFlow 只在本机录制当前 Windows 默认扬声器的声音，"
                    "不会读取课程链接、账号或浏览器 Cookie，也不会下载课程视频。"
                )
                recording_consent = gr.Checkbox(label="我确认有权记录当前播放内容，仅用于个人学习", value=False)
                with gr.Row():
                    recording_model = gr.Dropdown(MODEL_OPTIONS, value="base", label="模型")
                    recording_language = gr.Dropdown(LANGUAGE_OPTIONS, value="zh", label="语言")
                with gr.Row():
                    recording_start = gr.Button("开始录制电脑声音", variant="primary")
                    recording_stop = gr.Button("停止录制并转录")
        status = gr.Textbox(label="处理状态", interactive=False)
        table = gr.Dataframe(headers=["开始（秒）", "结束（秒）", "文本"], label="字幕分段", interactive=False)
        full_text = gr.Textbox(label="全文（可复制）", lines=12)
        srt_text = gr.Textbox(label="SRT 内容（可复制）", lines=12)
        with gr.Row():
            txt_download = gr.File(label="下载 TXT", interactive=False)
            srt_download = gr.File(label="下载 SRT", interactive=False)
        run_button.click(
            process_upload,
            [media, model, language],
            [status, table, full_text, srt_text, txt_download, srt_download],
        )
        bilibili_button.click(
            process_bilibili_url,
            [bilibili_url, bilibili_language, browser],
            [status, table, full_text, srt_text, txt_download, srt_download],
        )
        bilibili_audio_button.click(
            process_bilibili_audio_batch,
            [
                bilibili_audio_urls,
                bilibili_audio_model,
                bilibili_audio_language,
                bilibili_audio_browser,
                bilibili_audio_consent,
            ],
            [bilibili_batch_status, bilibili_batch_report, bilibili_batch_zip],
        )
        lms_button.click(
            process_lms_replay,
            [lms_payload, lms_model, lms_language, lms_consent],
            [lms_payload, status, table, full_text, srt_text, txt_download, srt_download],
        )
        recording_start.click(start_system_audio_recording, [recording_consent], [status])
        recording_stop.click(
            stop_system_audio_and_transcribe,
            [recording_model, recording_language],
            [status, table, full_text, srt_text, txt_download, srt_download],
        )

    return demo
