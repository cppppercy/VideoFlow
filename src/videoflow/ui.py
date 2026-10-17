"""Gradio 界面；此模块只负责输入输出呈现。"""

import atexit
from pathlib import Path
from typing import Any

from .exporters import transcript_to_srt, transcript_to_txt, write_exports
from .runtime import make_temporary_directory
from .sources.bilibili import BilibiliSubtitleError, fetch_bilibili_subtitles
from .system_audio import SystemAudioCaptureError, SystemAudioRecorder
from .transcriber import MODEL_OPTIONS, TranscriptionError, transcribe_media

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
        gr.Markdown("# VideoFlow\n本地转录，或导入 B 站可访问的已有字幕。文件只在本机处理。")
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
                    "部分字幕需登录 B 站才能访问。课程平台链接不支持自动登录，请先按平台规则下载后使用本地模式。"
                )
                bilibili_url = gr.Textbox(label="B 站视频链接", placeholder="https://www.bilibili.com/video/BV...")
                with gr.Row():
                    bilibili_language = gr.Dropdown(BILIBILI_LANGUAGE_OPTIONS, value="zh.*", label="字幕语言")
                    browser = gr.Dropdown(BROWSER_OPTIONS, value="", label="本机登录会话（可选）")
                bilibili_button = gr.Button("导入已有字幕", variant="primary")
            with gr.Tab("播放中的网页/课程转录"):
                gr.Markdown(
                    "适用于 B 站没有可访问字幕，或只能在线播放、且你有权为个人学习记录的课程回放。"
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
        recording_start.click(start_system_audio_recording, [recording_consent], [status])
        recording_stop.click(
            stop_system_audio_and_transcribe,
            [recording_model, recording_language],
            [status, table, full_text, srt_text, txt_download, srt_download],
        )

    return demo
