from pathlib import Path
from types import SimpleNamespace

import pytest

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
