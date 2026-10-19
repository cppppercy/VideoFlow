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
class TranscriptionDiagnostics:
    """一次本地识别的非敏感运行信息，用于判断长音频是否可能提前结束。"""

    media_duration: float | None
    speech_duration: float | None
    last_segment_end: float | None
    model_load_seconds: float
    inference_seconds: float
    total_seconds: float
    cpu_seconds: float
    peak_memory_mb: float | None
    pipeline: str
    coverage_status: str

    @property
    def realtime_factor(self) -> float | None:
        if not self.media_duration or self.media_duration <= 0:
            return None
        return self.inference_seconds / self.media_duration


@dataclass(frozen=True, slots=True)
class Transcript:
    segments: tuple[TranscriptSegment, ...]
    language: str | None = None
    language_probability: float | None = None
    diagnostics: TranscriptionDiagnostics | None = None

    @property
    def text(self) -> str:
        return "\n".join(segment.text for segment in self.segments if segment.text)
