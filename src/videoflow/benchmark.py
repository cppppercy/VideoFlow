"""在本机用同一媒体公平比较 VideoFlow 转录配置。"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import unicodedata

from .exporters import format_readable_text
from .transcriber import (
    MODEL_OPTIONS,
    TRANSCRIPTION_PROFILES,
    TranscriptionError,
    _default_model_factory,
    transcribe_media,
)


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    configuration: str
    model: str
    pipeline: str | None
    media_seconds: float | None
    model_load_seconds: float | None
    inference_seconds: float | None
    realtime_factor: float | None
    peak_memory_mb: float | None
    peak_gpu_memory_mb: float | None
    effective_batch_size: int | None
    last_segment_end: float | None
    coverage_status: str | None
    review_segment_count: int
    cer: float | None
    characters: int
    error: str | None = None


def normalize_cer_text(text: str) -> str:
    """CER 默认忽略排版空白，但保留标点和原有字符。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def character_error_rate(reference: str, hypothesis: str) -> float:
    expected = normalize_cer_text(reference)
    actual = normalize_cer_text(hypothesis)
    if not expected:
        return 0.0 if not actual else 1.0
    previous = list(range(len(actual) + 1))
    for row, expected_character in enumerate(expected, start=1):
        current = [row]
        for column, actual_character in enumerate(actual, start=1):
            substitution = previous[column - 1] + (expected_character != actual_character)
            current.append(min(current[-1] + 1, previous[column] + 1, substitution))
        previous = current
    return previous[-1] / len(expected)


def run_benchmark(
    media_path: str | Path,
    configurations: list[tuple[str, str, str | None]],
    *,
    language: str | None = None,
    initial_prompt: str | None = None,
    reference: str | None = None,
    cold_start: bool = True,
    refine_low_confidence: bool = False,
) -> list[BenchmarkResult]:
    results: list[BenchmarkResult] = []
    for label, model_name, profile_name in configurations:
        if cold_start:
            _default_model_factory.cache_clear()
        try:
            transcript = transcribe_media(
                media_path,
                model_name=model_name,
                profile_name=profile_name,
                language=language,
                initial_prompt=initial_prompt,
                refine_low_confidence=refine_low_confidence,
            )
            diagnostics = transcript.diagnostics
            text = format_readable_text(transcript)
            results.append(
                BenchmarkResult(
                    configuration=label,
                    model=model_name,
                    pipeline=diagnostics.pipeline if diagnostics else None,
                    media_seconds=diagnostics.media_duration if diagnostics else None,
                    model_load_seconds=diagnostics.model_load_seconds if diagnostics else None,
                    inference_seconds=diagnostics.inference_seconds if diagnostics else None,
                    realtime_factor=diagnostics.realtime_factor if diagnostics else None,
                    peak_memory_mb=diagnostics.peak_memory_mb if diagnostics else None,
                    peak_gpu_memory_mb=diagnostics.peak_gpu_memory_mb if diagnostics else None,
                    effective_batch_size=diagnostics.effective_batch_size if diagnostics else None,
                    last_segment_end=diagnostics.last_segment_end if diagnostics else None,
                    coverage_status=diagnostics.coverage_status if diagnostics else None,
                    review_segment_count=diagnostics.review_segment_count if diagnostics else 0,
                    cer=character_error_rate(reference, text) if reference is not None else None,
                    characters=len(normalize_cer_text(text)),
                )
            )
        except (TranscriptionError, OSError, ValueError) as exc:
            results.append(
                BenchmarkResult(
                    configuration=label,
                    model=model_name,
                    pipeline=None,
                    media_seconds=None,
                    model_load_seconds=None,
                    inference_seconds=None,
                    realtime_factor=None,
                    peak_memory_mb=None,
                    peak_gpu_memory_mb=None,
                    effective_batch_size=None,
                    last_segment_end=None,
                    coverage_status=None,
                    review_segment_count=0,
                    cer=None,
                    characters=0,
                    error=str(exc),
                )
            )
    return results


def results_to_markdown(results: list[BenchmarkResult]) -> str:
    def number(value: float | None, digits: int = 2) -> str:
        return "未测" if value is None else f"{value:.{digits}f}"

    lines = [
        "| 配置 | 模型 | 管线 | 媒体秒数 | 加载秒数 | 识别秒数 | RTF | 峰值内存 MB | 峰值显存 MB | 批量 | 需复核段 | 末条字幕秒数 | 覆盖状态 | CER |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for item in results:
        coverage = f"失败：{item.error}" if item.error else (item.coverage_status or "未知")
        lines.append(
            f"| {item.configuration} | {item.model} | {item.pipeline or '未知'} | "
            f"{number(item.media_seconds, 1)} | "
            f"{number(item.model_load_seconds)} | {number(item.inference_seconds)} | "
            f"{number(item.realtime_factor, 3)} | {number(item.peak_memory_mb, 1)} | "
            f"{number(item.peak_gpu_memory_mb, 1)} | "
            f"{item.effective_batch_size if item.effective_batch_size is not None else '未测'} | "
            f"{item.review_segment_count} | {number(item.last_segment_end, 1)} | "
            f"{coverage} | {number(item.cer, 4)} |"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoFlow 本机 ASR 质量/速度基准")
    parser.add_argument("media", help="有权使用的本地音频或视频")
    parser.add_argument(
        "--profiles",
        default="fast,balanced,accurate",
        help="逗号分隔的预设，默认 fast,balanced,accurate",
    )
    parser.add_argument("--models", default="", help="额外比较的原始 Whisper 模型，如 base,small")
    parser.add_argument("--language", default="zh", help="语言代码；留空表示自动识别")
    parser.add_argument("--prompt", help="课程关键词")
    parser.add_argument("--reference", help="人工核对的 UTF-8 参考稿；提供后计算 CER")
    parser.add_argument(
        "--refine-low-confidence",
        action="store_true",
        help="启用可疑片段二次识别，便于与默认结果比较",
    )
    parser.add_argument("--reuse-model", action="store_true", help="允许复用进程内模型缓存")
    parser.add_argument("--json", dest="json_path", help="可选 JSON 结果路径")
    return parser


def _parse_configurations(profiles: str, models: str) -> list[tuple[str, str, str | None]]:
    configurations: list[tuple[str, str, str | None]] = []
    for profile_name in (item.strip() for item in profiles.split(",") if item.strip()):
        if profile_name not in TRANSCRIPTION_PROFILES:
            raise ValueError(f"未知预设：{profile_name}")
        configurations.append(
            (profile_name, TRANSCRIPTION_PROFILES[profile_name].model_name, profile_name)
        )
    for model_name in (item.strip() for item in models.split(",") if item.strip()):
        if model_name not in MODEL_OPTIONS:
            raise ValueError(f"未知模型：{model_name}")
        configurations.append((f"model-{model_name}", model_name, None))
    if not configurations:
        raise ValueError("至少选择一个预设或模型。")
    return configurations


def main() -> int:
    args = build_parser().parse_args()
    try:
        configurations = _parse_configurations(args.profiles, args.models)
        reference = Path(args.reference).read_text(encoding="utf-8") if args.reference else None
        results = run_benchmark(
            args.media,
            configurations,
            language=args.language or None,
            initial_prompt=args.prompt,
            reference=reference,
            cold_start=not args.reuse_model,
            refine_low_confidence=args.refine_low_confidence,
        )
    except (OSError, ValueError) as exc:
        print(f"基准配置失败：{exc}")
        return 2
    print(results_to_markdown(results))
    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return 1 if any(item.error for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
