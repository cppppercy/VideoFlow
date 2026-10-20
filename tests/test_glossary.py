from pathlib import Path

import pytest

from videoflow.glossary import (
    apply_course_glossary,
    delete_course_glossary,
    glossary_hotwords,
    list_course_glossaries,
    load_course_glossary,
    parse_correction_rules,
    save_course_glossary,
)
from videoflow.models import Transcript, TranscriptSegment, TranscriptionDiagnostics


def _diagnostics() -> TranscriptionDiagnostics:
    return TranscriptionDiagnostics(
        media_duration=1,
        speech_duration=1,
        last_segment_end=1,
        model_load_seconds=0,
        inference_seconds=0,
        total_seconds=0,
        cpu_seconds=0,
        peak_memory_mb=None,
        pipeline="standard",
        coverage_status="appears_complete",
    )


def test_explicit_rules_correct_text_and_preserve_original() -> None:
    transcript = Transcript(
        (TranscriptSegment(0, 1, "这个REG作�业讲向量检凿"),),
        language="zh",
        diagnostics=_diagnostics(),
    )

    result = apply_course_glossary(
        transcript,
        terms_text="RAG，向量检索",
        rules_text="REG=>RAG\n检凿=>检索",
    )

    segment = result.segments[0]
    assert segment.text == "这个RAG作业讲向量检索"
    assert segment.original_text == "这个REG作�业讲向量检凿"
    assert "REG→RAG" in (segment.review_reason or "")
    assert "乱码" in (segment.review_reason or "")
    assert result.diagnostics is not None
    assert result.diagnostics.correction_count == 2


def test_phonetic_term_candidate_is_only_suggested() -> None:
    transcript = Transcript((TranscriptSegment(0, 1, "这里讲向量检凿方法"),), language="zh")

    result = apply_course_glossary(transcript, terms_text="向量检索")

    assert result.segments[0].text == "这里讲向量检凿方法"
    assert "疑似术语" in (result.segments[0].review_reason or "")


def test_correction_rules_reject_ambiguous_source() -> None:
    with pytest.raises(ValueError, match="两个不同"):
        parse_correction_rules("REG=>RAG\nREG=>正则")


def test_rule_targets_are_added_to_hotwords() -> None:
    assert glossary_hotwords("Embedding", "REG=>RAG\n作严=>作业") == "Embedding, RAG, 作业"


def test_course_glossary_can_be_saved_loaded_and_deleted(tmp_path: Path) -> None:
    store = tmp_path / "glossaries.json"

    save_course_glossary("软件工程", "RAG，Embedding", "REG=>RAG", store)

    assert list_course_glossaries(store) == ("软件工程",)
    loaded = load_course_glossary("软件工程", store)
    assert loaded.terms == "RAG，Embedding"
    assert loaded.corrections == "REG=>RAG"

    delete_course_glossary("软件工程", store)
    assert list_course_glossaries(store) == ()
