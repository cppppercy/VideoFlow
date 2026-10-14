"""faster-whisper 适配层。"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .models import Transcript, TranscriptSegment

SUPPORTED_EXTENSIONS = {
    ".aac", ".avi", ".flac", ".m4a", ".mkv", ".mov", ".mp3", ".mp4",
    ".mpeg", ".mpg", ".oga", ".ogg", ".opus", ".wav", ".webm", ".wma",
}
MODEL_OPTIONS = ("tiny", "base", "small")


class TranscriptionError(RuntimeError):
    """向 CLI 和界面呈现的可读转录错误。"""


def _validate_media_path(media_path: str | Path) -> Path:
    path = Path(media_path).expanduser()
    if not path.is_file():
        raise TranscriptionError(f"找不到本地文件：{path}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise TranscriptionError(f"不支持的文件类型 {path.suffix or '（无扩展名）'}；支持：{supported}")
    return path


def _default_model_factory(model_name: str, device: str, compute_type: str) -> Any:
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


def transcribe_media(
    media_path: str | Path,
    *,
    model_name: str = "base",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
    model_factory: Callable[[str, str, str], Any] | None = None,
) -> Transcript:
    """转录一个本地媒体文件，返回不依赖 faster-whisper 的结构化结果。"""
    path = _validate_media_path(media_path)
    if model_name not in MODEL_OPTIONS:
        raise TranscriptionError(f"不支持的模型“{model_name}”；可选：{', '.join(MODEL_OPTIONS)}")

    factory = model_factory or _default_model_factory
    model = factory(model_name, device, compute_type)
    try:
        segments, info = model.transcribe(
            str(path), language=language or None, vad_filter=True, beam_size=5
        )
        converted = tuple(
            TranscriptSegment(start=float(item.start), end=float(item.end), text=str(item.text).strip())
            for item in segments
            if str(item.text).strip()
        )
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
