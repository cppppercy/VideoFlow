"""Gradio 界面；此模块只负责输入输出呈现。"""

import atexit
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .exporters import transcript_to_srt, transcript_to_txt, write_exports
from .transcriber import MODEL_OPTIONS, TranscriptionError, transcribe_media

LANGUAGE_OPTIONS = [("自动识别", ""), ("中文", "zh"), ("English", "en"), ("日本語", "ja"), ("한국어", "ko")]


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


def create_app() -> Any:
    try:
        import gradio as gr
    except ImportError as exc:
        raise RuntimeError("未安装 Gradio。请执行：python -m pip install -e \".[dev]\"") from exc

    with gr.Blocks(title="VideoFlow") as demo:
        gr.Markdown("# VideoFlow\n本地音视频转文字；文件仅在本机处理。")
        with gr.Row():
            media = gr.File(label="音频或视频", type="filepath")
            with gr.Column():
                model = gr.Dropdown(MODEL_OPTIONS, value="base", label="模型")
                language = gr.Dropdown(LANGUAGE_OPTIONS, value="", label="语言")
                run_button = gr.Button("开始转录", variant="primary")
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

    return demo
