"""TXT 与 SRT 导出。"""

from math import isfinite
from pathlib import Path

from .models import Transcript


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
    return transcript.text + ("\n" if transcript.text else "")


def transcript_to_srt(transcript: Transcript) -> str:
    blocks = []
    for index, segment in enumerate(transcript.segments, start=1):
        blocks.append(
            f"{index}\n{format_srt_timestamp(segment.start)} --> "
            f"{format_srt_timestamp(segment.end)}\n{segment.text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def write_exports(transcript: Transcript, output_dir: str | Path, stem: str) -> tuple[Path, Path]:
    """写入 UTF-8 TXT 和 SRT；调用方负责选择不会覆盖用户文件的目录。"""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    safe_stem = Path(stem).stem or "transcript"
    txt_path = destination / f"{safe_stem}.txt"
    srt_path = destination / f"{safe_stem}.srt"
    txt_path.write_text(transcript_to_txt(transcript), encoding="utf-8")
    srt_path.write_text(transcript_to_srt(transcript), encoding="utf-8")
    return txt_path, srt_path
