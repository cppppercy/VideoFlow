import pytest
from contextlib import contextmanager
from pathlib import Path

from videoflow.models import Transcript
from videoflow import workflows
from videoflow.sources.remote_audio import ExtractedAudio, RemoteAudioError
from videoflow.sources.xjtu_lms import XjtuReplay


def test_bilibili_batch_deduplicates_and_keeps_individual_failures(monkeypatch) -> None:
    seen: list[str] = []

    def fake_transcribe(url: str, **kwargs: object) -> workflows.OnlineTranscript:
        seen.append(url)
        if "bad" in url:
            raise RuntimeError("测试失败")
        return workflows.OnlineTranscript(url.rsplit("/", 1)[-1], Transcript(()), url)

    monkeypatch.setattr(workflows, "transcribe_bilibili_audio", fake_transcribe)
    result = workflows.transcribe_bilibili_batch(
        "https://good/1\nhttps://bad/2\nhttps://good/1",
        model_name="tiny",
        language="zh",
        browser=None,
    )

    assert seen == ["https://good/1", "https://bad/2"]
    assert len(result.successes) == 1
    assert result.failures == (("https://bad/2", "测试失败"),)


def test_bilibili_batch_limits_workload() -> None:
    with pytest.raises(ValueError, match="最多"):
        workflows.transcribe_bilibili_batch(
            "\n".join(f"https://example/{index}" for index in range(11)),
            model_name="tiny",
            language="zh",
            browser=None,
        )


def test_lms_workflow_retries_authorized_fallback_stream(monkeypatch, tmp_path: Path) -> None:
    replay = XjtuReplay(
        activity_id=1288517,
        title="第一讲",
        stream_url="https://cdn.example.edu/primary.mp4",
        fallback_urls=("https://cdn.example.edu/fallback.m3u8",),
        label="INSTRUCTOR",
        request_headers=(("Origin", "https://lms.xjtu.edu.cn"),),
    )
    audio_path = tmp_path / "stream.wav"
    audio_path.touch()
    seen: list[str] = []

    @contextmanager
    def fake_extract(url: str, title: str, **kwargs: object):
        seen.append(url)
        assert kwargs["request_headers"] == replay.request_headers
        if "primary" in url:
            raise RemoteAudioError("HTTP 403")
        yield ExtractedAudio(audio_path, title)

    monkeypatch.setattr(workflows, "resolve_lms_replay", lambda payload: replay)
    monkeypatch.setattr(workflows, "extract_stream_audio", fake_extract)
    monkeypatch.setattr(workflows, "transcribe_media", lambda *args, **kwargs: Transcript(()))

    result = workflows.transcribe_lms_payload("payload", model_name="base", language="zh")

    assert result.title == "第一讲"
    assert seen == [replay.stream_url, replay.fallback_urls[0]]
