"""可选 Paraformer 中文复核；默认 Whisper 路径不依赖此模块的重型依赖。"""

from __future__ import annotations

from dataclasses import replace
from importlib.util import find_spec
import os
from pathlib import Path
import re
import subprocess
from threading import Lock
from typing import Callable

from .glossary import parse_glossary_terms
from .models import TranscriptSegment
from .runtime import make_temporary_directory
from .text_processing import clean_transcription_text


ParaformerRunner = Callable[[Path, str | None], str]
MAX_PARAFORMER_REVIEWS = 12
_MODEL = None
_MODEL_LOCK = Lock()
_TAG = re.compile(r"<\|[^|]+\|>")
_PARAFORMER_REPOSITORY = "iic--speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"


class ParaformerReviewError(RuntimeError):
    pass


def paraformer_available() -> bool:
    # 这里只探测包，不在网页启动时导入 PyTorch/FunASR；重型模块到首次复核再加载。
    return find_spec("funasr") is not None


def review_uncertain_segments(
    media_path: str | Path,
    segments: tuple[TranscriptSegment, ...],
    *,
    terms_text: str | None,
    maximum: int = MAX_PARAFORMER_REVIEWS,
    runner: ParaformerRunner | None = None,
    progress_callback: Callable[[str, float | None, float | None], None] | None = None,
) -> tuple[tuple[TranscriptSegment, ...], int]:
    """用 Paraformer 复核可疑段；仅在术语命中更好时自动采用候选。"""
    if runner is None and not paraformer_available():
        raise ParaformerReviewError(
            "尚未安装 Paraformer 可选依赖。请先执行 "
            '.\\.venv\\Scripts\\python.exe -m pip install -e ".[chinese-review]"，然后重启 VideoFlow。'
        )
    run = runner or _default_runner
    terms = parse_glossary_terms(terms_text)
    reviewed = 0
    output: list[TranscriptSegment] = []
    with make_temporary_directory(prefix="videoflow-paraformer-") as temporary_directory:
        clip_path = Path(temporary_directory) / "review.wav"
        for segment in segments:
            if not segment.review_reason or reviewed >= maximum:
                output.append(segment)
                continue
            reviewed += 1
            if progress_callback is not None:
                progress_callback(
                    f"正在用 Paraformer 复核可疑片段 {reviewed}/{maximum}",
                    segment.start,
                    None,
                )
            start = max(0.0, segment.start - 0.35)
            end = max(start + 0.1, segment.end + 0.35)
            try:
                _extract_clip(Path(media_path), clip_path, start=start, duration=end - start)
                candidate = _clean_candidate(run(clip_path, ", ".join(terms) or None))
            except Exception as exc:
                failure = " ".join(str(exc).split())[:160] or type(exc).__name__
                output.append(
                    replace(
                        segment,
                        review_reason=_append_reason(
                            segment.review_reason,
                            f"Paraformer 复核失败：{failure}",
                        ),
                    )
                )
                continue
            if not candidate or candidate == segment.text:
                output.append(segment)
                continue
            current_hits = _term_hits(segment.text, terms)
            candidate_hits = _term_hits(candidate, terms)
            adopt = candidate_hits > current_hits or ("\ufffd" in segment.text and "\ufffd" not in candidate)
            if adopt:
                output.append(
                    replace(
                        segment,
                        text=candidate,
                        original_text=segment.original_text or segment.text,
                        alternative_text=candidate,
                        review_reason=_append_reason(
                            segment.review_reason,
                            "已采用 Paraformer 候选（课程术语命中更好）",
                        ),
                    )
                )
            else:
                output.append(
                    replace(
                        segment,
                        alternative_text=candidate,
                        review_reason=_append_reason(
                            segment.review_reason,
                            "Paraformer 候选仅供人工比较",
                        ),
                    )
                )
    return tuple(output), reviewed


def _default_runner(audio_path: Path, hotwords: str | None) -> str:
    model = _load_model()
    options: dict[str, object] = {
        "input": str(audio_path),
        "language": "zh",
        "use_itn": True,
        "batch_size_s": 60,
    }
    if hotwords:
        options["hotword"] = hotwords.replace(",", " ")
    results = model.generate(**options)
    if not results or not isinstance(results[0], dict):
        return ""
    return str(results[0].get("text", ""))


def _load_model():
    global _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise ParaformerReviewError("缺少 FunASR，可选中文复核不可用。") from exc
        device = os.getenv("VIDEOFLOW_PARAFORMER_DEVICE", "cpu").strip() or "cpu"
        _MODEL = AutoModel(model=_resolve_model_source(), device=device, disable_update=True)
        return _MODEL


def _resolve_model_source() -> str:
    configured = os.getenv("VIDEOFLOW_PARAFORMER_MODEL", "").strip()
    if configured:
        return configured
    cache_root = Path.home() / ".cache" / "modelscope"
    candidates = (
        cache_root / "models" / _PARAFORMER_REPOSITORY / "snapshots" / "master",
        cache_root
        / "hub"
        / "models"
        / "iic"
        / "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
    )
    for candidate in candidates:
        if (candidate / "model.pt").is_file() and (candidate / "config.yaml").is_file():
            return str(candidate)
    return "paraformer-zh"


def _extract_clip(source: Path, destination: Path, *, start: float, duration: float) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-y",
        str(destination),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(60.0, duration * 2),
            check=False,
        )
    except FileNotFoundError as exc:
        raise ParaformerReviewError("找不到 FFmpeg。") from exc
    if completed.returncode != 0 or not destination.is_file():
        raise ParaformerReviewError("无法准备待复核音频片段。")


def _clean_candidate(value: str) -> str:
    without_tags = _TAG.sub("", value).strip()
    # FunASR 有时会在每个汉字间插入空格；只移除汉字之间的空格，保留英文词界。
    without_cjk_spaces = re.sub(r"(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])", "", without_tags)
    return clean_transcription_text(re.sub(r"\s+", " ", without_cjk_spaces))


def _term_hits(text: str, terms: tuple[str, ...]) -> int:
    lowered = text.casefold()
    return sum(1 for term in terms if term.casefold() in lowered)


def _append_reason(existing: str | None, addition: str) -> str:
    return "；".join(dict.fromkeys(part for part in (existing, addition) if part))
