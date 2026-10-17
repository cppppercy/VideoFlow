import pytest

from videoflow.models import Transcript
from videoflow import workflows


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
