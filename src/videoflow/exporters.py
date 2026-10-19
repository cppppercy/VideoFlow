"""TXT 与 SRT 导出。"""

from math import isfinite
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

from .models import Transcript

_SENTENCE_ENDINGS = frozenset("。！？!?；;")
_CLOSING_PUNCTUATION = frozenset("，。！？；：、,.!?;:%)]}”’》」』】〉")
_OPENING_PUNCTUATION = frozenset("([{（【《「『“‘〈")
_PARAGRAPH_PAUSE_SECONDS = 2.5
_FORCED_PARAGRAPH_PAUSE_SECONDS = 6.0
_TARGET_PARAGRAPH_CHARACTERS = 500


def format_srt_timestamp(seconds: float) -> str:
    """将秒转为 `HH:MM:SS,mmm`，按毫秒四舍五入。"""
    if not isfinite(seconds) or seconds < 0:
        raise ValueError("时间必须是有限的非负秒数。")
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{millis:03}"


def transcript_to_txt(transcript: Transcript) -> str:
    text = format_readable_text(transcript)
    return text + ("\n" if text else "")


def format_readable_text(transcript: Transcript) -> str:
    """把字幕片段排成连续阅读文本，不添加模型没有生成的标点。"""
    paragraphs: list[str] = []
    paragraph = ""
    previous = None
    for segment in transcript.segments:
        text = re.sub(r"\s+", " ", segment.text).strip()
        if not text:
            continue
        gap = max(0.0, segment.start - previous.end) if previous is not None else 0.0
        should_break = bool(
            paragraph
            and (
                gap >= _FORCED_PARAGRAPH_PAUSE_SECONDS
                or (
                    gap >= _PARAGRAPH_PAUSE_SECONDS
                    and paragraph[-1] in _SENTENCE_ENDINGS
                )
                or (
                    len(paragraph) >= _TARGET_PARAGRAPH_CHARACTERS
                    and paragraph[-1] in _SENTENCE_ENDINGS
                )
            )
        )
        if should_break:
            paragraphs.append(paragraph)
            paragraph = text
        else:
            paragraph = _join_text_fragments(paragraph, text)
        previous = segment
    if paragraph:
        paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def _join_text_fragments(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    last = left[-1]
    first = right[0]
    if first in _CLOSING_PUNCTUATION or last in _OPENING_PUNCTUATION:
        separator = ""
    elif last.isascii() and first.isascii() and last.isalnum() and first.isalnum():
        separator = " "
    elif last in ".,!?;:" and first.isascii() and first.isalnum():
        separator = " "
    else:
        separator = ""
    return f"{left}{separator}{right}"


def transcript_to_srt(transcript: Transcript) -> str:
    blocks = []
    for index, segment in enumerate(transcript.segments, start=1):
        blocks.append(
            f"{index}\n{format_srt_timestamp(segment.start)} --> "
            f"{format_srt_timestamp(segment.end)}\n{segment.text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def safe_export_stem(stem: str) -> str:
    """生成 Windows/macOS/Linux 都可用的非空导出文件名。"""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(stem)).strip(" ._")
    return cleaned[:120] or "transcript"


def write_exports(transcript: Transcript, output_dir: str | Path, stem: str) -> tuple[Path, Path]:
    """写入 UTF-8 TXT 和 SRT；调用方负责选择不会覆盖用户文件的目录。"""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    safe_stem = safe_export_stem(stem)
    txt_path = destination / f"{safe_stem}.txt"
    srt_path = destination / f"{safe_stem}.srt"
    txt_path.write_text(transcript_to_txt(transcript), encoding="utf-8")
    srt_path.write_text(transcript_to_srt(transcript), encoding="utf-8")
    return txt_path, srt_path


def write_batch_archive(
    items: list[tuple[str, Transcript]], output_dir: str | Path, stem: str = "videoflow-batch"
) -> Path:
    """将多个转录结果直接写入 ZIP，避免保留额外媒体或中间文件。"""
    if not items:
        raise ValueError("没有可导出的批量转录结果。")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    archive_path = destination / f"{safe_export_stem(stem)}.zip"
    used: set[str] = set()
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        for index, (title, transcript) in enumerate(items, start=1):
            base = safe_export_stem(title)
            if base in used:
                base = f"{base}-{index}"
            used.add(base)
            archive.writestr(f"{base}.txt", transcript_to_txt(transcript).encode("utf-8"))
            archive.writestr(f"{base}.srt", transcript_to_srt(transcript).encode("utf-8"))
    return archive_path
