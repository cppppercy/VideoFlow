"""Gradio 界面；此模块只负责输入输出呈现。"""

import atexit
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .exporters import transcript_to_srt, transcript_to_txt, write_exports
from .sources.bilibili import fetch_bilibili_subtitles
from .transcriber import MODEL_OPTIONS, transcribe_media

LANGUAGE_OPTIONS = [("自动识别", ""), ("中文", "zh"), ("English", "en"), ("日本語", "ja"), ("한국어", "ko")]
BILIBILI_LANGUAGE_OPTIONS = [("中文（优先）", "zh.*"), ("English", "en.*"), ("任意可用字幕", "all")]
BROWSER_OPTIONS = [("不使用登录（仅公开可访问字幕）", ""), ("Chrome（需你已登录 B 站）", "chrome"), ("Edge（需你已登录 B 站）", "edge")]


class _ExportStore:
    """Gradio 下载文件的临时目录；进程退出时删除，不保存用户媒体。"""

    def __init__(self) -> None:
        self._directory = TemporaryDirectory(prefix="videoflow-exports-")
        atexit.register(self._directory.cleanup)

    @property
    def path(self) -> str:
        return self._directory.name


_EXPORT_STORE = _ExportStore()


def _result_table(transcript: Any) -> list[list[str]]:
    return [[f"{item.start:.3f}", f"{item.end:.3f}", item.text] for item in transcript.segments]


def process_upload(
    media_path: str | None, model_name: str, language: str | None
) -> tuple[str, list[list[str]], str, str, str, str]:
    """UI 回调。导出文件只在进程的临时目录内保存。"""
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


def process_bilibili_url(
    video_url: str | None, language_pattern: str, browser: str | None
) -> tuple[str, list[list[str]], str, str, str, str]:
    """B 站已有字幕回调；不下载完整视频，也不持久化浏览器登录信息。"""
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

    return demo
