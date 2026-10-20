from pathlib import Path
from types import SimpleNamespace
import wave

import pytest

from videoflow import transcriber
from videoflow.transcriber import TranscriptionError, transcribe_media


class FakeModel:
    def transcribe(self, path: str, **kwargs: object):
        assert path.endswith("sample.wav")
        assert kwargs["language"] == "zh"
        return iter([
            SimpleNamespace(start=0.0, end=1.5, text="  第一段  "),
            SimpleNamespace(start=1.5, end=3.0, text="第二段"),
        ]), SimpleNamespace(language="zh", language_probability=0.99)


def test_transcribe_converts_model_segments(tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()
    seen = {}

    def factory(model_name: str, device: str, compute_type: str) -> FakeModel:
        seen.update(model_name=model_name, device=device, compute_type=compute_type)
        return FakeModel()

    result = transcribe_media(media, language="zh", model_factory=factory)

    assert result.text == "第一段\n第二段"
    assert result.language == "zh"
    assert seen == {"model_name": "base", "device": "cpu", "compute_type": "int8"}


def test_missing_file_is_reported_before_loading_model(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError, match="找不到本地文件"):
        transcribe_media(tmp_path / "missing.mp4")


def test_unsupported_extension_is_reported(tmp_path: Path) -> None:
    file = tmp_path / "notes.txt"
    file.touch()
    with pytest.raises(TranscriptionError, match="不支持的文件类型"):
        transcribe_media(file)


def test_unknown_model_is_reported(tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()
    with pytest.raises(TranscriptionError, match="不支持的模型"):
        transcribe_media(media, model_name="large")


def test_balanced_profile_uses_batched_base_model_and_prompt(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()
    seen: dict[str, object] = {}

    class BatchedFake:
        def transcribe(self, path: str, **kwargs: object):
            seen.update(kwargs)
            return iter([]), SimpleNamespace(language="zh", language_probability=1.0)

    def model_factory(model_name: str, device: str, compute_type: str) -> object:
        seen["model_name"] = model_name
        return object()

    monkeypatch.setattr(transcriber, "_default_model_factory", model_factory)
    monkeypatch.setattr(transcriber, "_default_batched_factory", lambda model: BatchedFake())

    transcribe_media(media, profile_name="balanced", language="zh", initial_prompt="特征值")

    assert seen["model_name"] == "base"
    assert seen["batch_size"] == 4
    assert seen["beam_size"] == 5
    assert seen["hotwords"] == "特征值"
    assert "initial_prompt" not in seen
    assert seen["word_timestamps"] is True
    assert seen["repetition_penalty"] == 1.1
    assert seen["no_repeat_ngram_size"] == 3


def test_gpu_turbo_profile_uses_cuda_float16(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()
    seen: dict[str, object] = {}

    class BatchedFake:
        def transcribe(self, path: str, **kwargs: object):
            seen.update(kwargs)
            return iter([]), SimpleNamespace(language="zh", language_probability=1.0)

    def model_factory(model_name: str, device: str, compute_type: str) -> object:
        seen.update(model_name=model_name, device=device, compute_type=compute_type)
        return object()

    monkeypatch.setattr(transcriber, "cuda_device_available", lambda: True)
    monkeypatch.setattr(transcriber, "_gpu_total_memory_mb", lambda: None)
    monkeypatch.setattr(transcriber, "_default_model_factory", model_factory)
    monkeypatch.setattr(transcriber, "_default_batched_factory", lambda model: BatchedFake())

    transcribe_media(media, profile_name="gpu_turbo", language="zh")

    assert seen["model_name"] == "turbo"
    assert seen["device"] == "cuda"
    assert seen["compute_type"] == "float16"
    assert seen["batch_size"] == 4
    assert seen["beam_size"] == 5


def test_gpu_batch_size_uses_eight_on_eight_gb_card(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOFLOW_GPU_BATCH_SIZE", raising=False)
    monkeypatch.setattr(transcriber, "_gpu_total_memory_mb", lambda: 8188)

    assert transcriber._recommended_gpu_batch_size(
        transcriber.TRANSCRIPTION_PROFILES["gpu_turbo"]
    ) == 8


def test_gpu_batch_size_respects_explicit_override(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOFLOW_GPU_BATCH_SIZE", "3")

    assert transcriber._recommended_gpu_batch_size(
        transcriber.TRANSCRIPTION_PROFILES["gpu_turbo"]
    ) == 3


def test_batched_gpu_out_of_memory_retries_smaller_batch() -> None:
    calls: list[int] = []

    class Engine:
        def transcribe(self, path: str, **kwargs: object):
            calls.append(int(kwargs["batch_size"]))
            if len(calls) == 1:
                raise RuntimeError("CUDA out of memory")
            return iter([]), SimpleNamespace(language="zh")

    segments, info, batch_size = transcriber._run_batched_transcription(
        Engine(),
        Path("sample.wav"),
        options={"language": "zh"},
        batch_size=8,
        allow_gpu_fallback=True,
    )

    assert segments == []
    assert info.language == "zh"
    assert batch_size == 4
    assert calls == [8, 4]


def test_hotwords_are_trimmed_and_deduplicated() -> None:
    assert transcriber.normalize_hotwords("高斯消去法， 残值;高斯消去法\nJordan 标准形") == (
        "高斯消去法, 残值, Jordan 标准形"
    )


def test_transcription_applies_explicit_course_corrections(tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()

    class Model:
        def transcribe(self, path: str, **kwargs: object):
            return iter([SimpleNamespace(start=0.0, end=1.0, text="REG作�业")]), SimpleNamespace(
                language="zh", language_probability=1.0
            )

    result = transcribe_media(
        media,
        language="zh",
        correction_rules="REG=>RAG",
        model_factory=lambda *args: Model(),
    )

    assert result.segments[0].text == "RAG作业"
    assert result.segments[0].original_text == "REG作�业"


def test_low_confidence_segment_is_marked_for_review() -> None:
    raw = [
        SimpleNamespace(
            start=0.0,
            end=1.0,
            text="不确定内容",
            words=None,
            avg_logprob=-1.2,
            compression_ratio=2.5,
            no_speech_prob=0.1,
        )
    ]

    result = transcriber._convert_model_segments(raw, split_words=False)

    assert result[0].review_reason == "低置信、疑似重复"


def test_refinement_keeps_only_higher_scoring_candidate() -> None:
    original = SimpleNamespace(
        start=0.0,
        end=1.0,
        text="原始结果",
        avg_logprob=-1.4,
        compression_ratio=2.5,
        no_speech_prob=0.1,
    )
    candidate = SimpleNamespace(
        start=0.0,
        end=1.0,
        text="精修结果",
        avg_logprob=-0.2,
        compression_ratio=1.1,
        no_speech_prob=0.1,
    )

    class Model:
        def transcribe(self, path: str, **kwargs: object):
            assert kwargs["beam_size"] == 8
            assert kwargs["clip_timestamps"] == [0.0, 1.0]
            return iter([candidate]), SimpleNamespace(language="zh")

    result, attempted = transcriber._refine_uncertain_segments(
        Model(),
        Path("sample.wav"),
        [original],
        options={"language": "zh", "beam_size": 5, "vad_filter": True},
        maximum=1,
        progress_callback=None,
    )

    assert attempted == 1
    assert result == [candidate]


def test_gpu_turbo_profile_reports_missing_cuda(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()
    monkeypatch.setattr(transcriber, "cuda_device_available", lambda: False)

    with pytest.raises(TranscriptionError, match="GPU 增强模式需要"):
        transcribe_media(media, profile_name="gpu_turbo", language="zh")


def test_batched_words_are_split_into_readable_subtitle_segments() -> None:
    words = [
        SimpleNamespace(start=0.0, end=1.0, word="这是"),
        SimpleNamespace(start=1.0, end=2.1, word="第一句。"),
        SimpleNamespace(start=2.2, end=3.0, word="第二句"),
        SimpleNamespace(start=4.0, end=5.0, word="有停顿"),
    ]
    raw = [SimpleNamespace(start=0.0, end=5.0, text="整段", words=words)]

    result = transcriber._convert_model_segments(raw, split_words=True)

    assert [item.text for item in result] == ["这是第一句。", "第二句", "有停顿"]
    assert [(item.start, item.end) for item in result] == [(0.0, 2.1), (2.2, 3.0), (4.0, 5.0)]


def test_batched_subtitle_group_does_not_grow_beyond_eight_seconds() -> None:
    words = [SimpleNamespace(start=float(i), end=float(i + 1), word=str(i)) for i in range(10)]
    raw = [SimpleNamespace(start=0.0, end=10.0, text="整段", words=words)]

    result = transcriber._convert_model_segments(raw, split_words=True)

    assert [item.text for item in result] == ["01234567", "89"]
    assert all(item.end - item.start <= 8.0 for item in result)


def test_non_chinese_transcript_skips_simplified_chinese_conversion() -> None:
    raw = [SimpleNamespace(start=0.0, end=1.0, text="後で確認します", words=None)]

    result = transcriber._convert_model_segments(
        raw,
        split_words=False,
        simplify_chinese=False,
    )

    assert [item.text for item in result] == ["後で確認します"]


def test_long_media_uses_incremental_pipeline_and_reports_coverage(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()
    seen: dict[str, object] = {}
    progress: list[tuple[str, float | None, float | None]] = []

    class LongMediaModel:
        def transcribe(self, path: str, **kwargs: object):
            seen.update(kwargs)
            return iter([
                SimpleNamespace(start=0.0, end=8.0, text="开头", words=None),
                SimpleNamespace(start=5390.0, end=5398.0, text="结尾。", words=None),
            ]), SimpleNamespace(
                language="zh",
                language_probability=1.0,
                duration=5400.0,
                duration_after_vad=5000.0,
            )

    monkeypatch.setattr(transcriber, "_probe_media_duration", lambda path: 5400.0)
    result = transcribe_media(
        media,
        profile_name="balanced",
        language="zh",
        model_factory=lambda *args: LongMediaModel(),
        progress_callback=lambda stage, current, total: progress.append((stage, current, total)),
    )

    assert "batch_size" not in seen
    assert seen["word_timestamps"] is True
    assert result.diagnostics is not None
    assert result.diagnostics.pipeline == "long-media"
    assert result.diagnostics.media_duration == 5400.0
    assert result.diagnostics.last_segment_end == 5398.0
    assert result.diagnostics.coverage_status == "appears_complete"
    assert any(current == 5398.0 and total == 5400.0 for _, current, total in progress)


def test_production_long_media_uses_overlapping_batched_chunks(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "sample.wav"
    media.touch()
    extracted: list[tuple[float, float]] = []
    calls: list[dict[str, object]] = []
    progress: list[tuple[str, float | None, float | None]] = []

    class BatchedFake:
        def transcribe(self, path: str, **kwargs: object):
            calls.append(kwargs)
            call_index = len(calls) - 1
            if call_index in (0, 1):
                # 同一边界语句会被两个带重叠的块识别，但只应保留到第二块。
                local_start = 598.0 if call_index == 0 else 1.0
                words = [
                    SimpleNamespace(start=local_start, end=local_start + 2.0, word="边界。")
                ]
                segments = [
                    SimpleNamespace(
                        start=local_start,
                        end=local_start + 2.0,
                        text="边界。",
                        words=words,
                    )
                ]
            else:
                segments = []
            return iter(segments), SimpleNamespace(
                language="zh",
                language_probability=0.99,
                duration_after_vad=100.0,
            )

    def fake_extract(source: Path, destination: Path, *, start: float, duration: float) -> None:
        extracted.append((start, duration))
        destination.touch()

    monkeypatch.setattr(transcriber, "LONG_MEDIA_CHUNK_SECONDS", 600)
    monkeypatch.setattr(transcriber, "_probe_media_duration", lambda path: 1300.0)
    monkeypatch.setattr(transcriber, "_default_model_factory", lambda *args: object())
    monkeypatch.setattr(transcriber, "_default_batched_factory", lambda model: BatchedFake())
    monkeypatch.setattr(transcriber, "_extract_audio_chunk", fake_extract)

    result = transcribe_media(
        media,
        profile_name="fast",
        language="zh",
        progress_callback=lambda stage, current, total: progress.append((stage, current, total)),
    )

    assert len(extracted) == 3
    assert extracted[0] == (0.0, 603.0)
    assert extracted[1] == (597.0, 606.0)
    assert [item.text for item in result.segments] == ["边界。"]
    assert (result.segments[0].start, result.segments[0].end) == (598.0, 600.0)
    assert all(call["batch_size"] == 8 for call in calls)
    assert all(call["temperature"] == 0.0 for call in calls)
    assert all(call["condition_on_previous_text"] is False for call in calls)
    assert result.diagnostics is not None
    assert result.diagnostics.pipeline == "chunked-batched"
    assert any(stage == "已完成第 3/3 段" for stage, _, _ in progress)


def test_recommended_cpu_threads_uses_eight_on_high_core_machine(monkeypatch) -> None:
    monkeypatch.delenv("VIDEOFLOW_CPU_THREADS", raising=False)
    monkeypatch.setattr(transcriber.os, "cpu_count", lambda: 24)

    assert transcriber._recommended_cpu_threads() == 8


def test_recommended_cpu_threads_validates_override(monkeypatch) -> None:
    monkeypatch.setenv("VIDEOFLOW_CPU_THREADS", "12")
    assert transcriber._recommended_cpu_threads() == 12

    monkeypatch.setenv("VIDEOFLOW_CPU_THREADS", "0")
    with pytest.raises(TranscriptionError, match="1–32"):
        transcriber._recommended_cpu_threads()


def test_large_unexplained_tail_is_marked_for_review() -> None:
    assert transcriber._coverage_status(5400.0, 4800.0, 1800.0) == "needs_review"
    assert transcriber._coverage_status(5400.0, 0.0, None) == "no_speech"


def test_media_duration_probe_reads_wav_seconds(tmp_path: Path) -> None:
    media = tmp_path / "one-second.wav"
    with wave.open(str(media), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x00\x00" * 16_000)

    assert transcriber._probe_media_duration(media) == pytest.approx(1.0, abs=0.01)
