from pathlib import Path
from types import SimpleNamespace

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
    assert seen["initial_prompt"] == "特征值"
    assert seen["word_timestamps"] is True


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
