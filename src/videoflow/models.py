"""转录领域数据，不依赖界面或模型库。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < 0:
            raise ValueError("字幕时间不能为负数。")
        if self.end < self.start:
            raise ValueError("字幕结束时间不能早于开始时间。")


@dataclass(frozen=True, slots=True)
class Transcript:
    segments: tuple[TranscriptSegment, ...]
    language: str | None = None
    language_probability: float | None = None

    @property
    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments if segment.text)
