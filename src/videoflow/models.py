"""转录领域数据，不依赖界面或模型库。"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str
    # 模型提供的启发式质量提示。它只用于提醒人工抽查，不能替代人工参考稿 CER。
    review_reason: str | None = None
    # 发生术语纠错或采用第二模型候选时保留 Whisper/来源原文，便于人工对照。
    original_text: str | None = None
    # 第二模型候选始终单独保留；未采用时也可在页面中人工比较。
    alternative_text: str | None = None

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
    effective_batch_size: int | None = None
    gpu_name: str | None = None
    peak_gpu_memory_mb: float | None = None
    review_segment_count: int = 0
    correction_count: int = 0
    paraformer_review_count: int = 0

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
