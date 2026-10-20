from pathlib import Path

from videoflow.models import TranscriptSegment
from videoflow import paraformer_review


def test_paraformer_candidate_with_more_glossary_hits_is_adopted(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "course.wav"
    media.touch()

    def fake_extract(source: Path, destination: Path, *, start: float, duration: float) -> None:
        assert source == media
        destination.touch()

    monkeypatch.setattr(paraformer_review, "_extract_clip", fake_extract)
    segments = (TranscriptSegment(1, 3, "这里讲REG系统", review_reason="低置信"),)

    result, reviewed = paraformer_review.review_uncertain_segments(
        media,
        segments,
        terms_text="RAG",
        runner=lambda path, hotwords: "这里讲RAG系统",
    )

    assert reviewed == 1
    assert result[0].text == "这里讲RAG系统"
    assert result[0].original_text == "这里讲REG系统"
    assert result[0].alternative_text == "这里讲RAG系统"
    assert "已采用" in (result[0].review_reason or "")


def test_paraformer_candidate_without_better_term_hit_is_review_only(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "course.wav"
    media.touch()
    monkeypatch.setattr(
        paraformer_review,
        "_extract_clip",
        lambda source, destination, **kwargs: destination.touch(),
    )
    segments = (TranscriptSegment(1, 3, "原始句子", review_reason="低置信"),)

    result, reviewed = paraformer_review.review_uncertain_segments(
        media,
        segments,
        terms_text="RAG",
        runner=lambda path, hotwords: "另一个句子",
    )

    assert reviewed == 1
    assert result[0].text == "原始句子"
    assert result[0].alternative_text == "另一个句子"
    assert "仅供人工比较" in (result[0].review_reason or "")


def test_clean_candidate_preserves_english_word_boundaries() -> None:
    cleaned = paraformer_review._clean_candidate("这 是 <|zh|> RAG retrieval system")

    assert cleaned == "这是 RAG retrieval system"


def test_cached_model_path_is_preferred(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(paraformer_review.Path, "home", lambda: tmp_path)
    model_dir = (
        tmp_path
        / ".cache"
        / "modelscope"
        / "models"
        / paraformer_review._PARAFORMER_REPOSITORY
        / "snapshots"
        / "master"
    )
    model_dir.mkdir(parents=True)
    (model_dir / "model.pt").touch()
    (model_dir / "config.yaml").touch()

    assert paraformer_review._resolve_model_source() == str(model_dir)
