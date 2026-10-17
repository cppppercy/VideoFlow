from videoflow.sources.bilibili import BilibiliSubtitleError
from videoflow import ui


def test_bilibili_failure_is_shown_in_status(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise BilibiliSubtitleError("B 站要求登录后读取该视频字幕。")

    monkeypatch.setattr(ui, "fetch_bilibili_subtitles", unavailable)
    result = ui.process_bilibili_url("https://www.bilibili.com/video/BV1F64y1U7xM", "zh.*", "edge")

    assert result == ("错误：B 站要求登录后读取该视频字幕。", [], "", "", None, None)


def test_system_audio_requires_consent() -> None:
    assert ui.start_system_audio_recording(False).startswith("请先确认")


def test_online_audio_workflows_require_consent() -> None:
    assert ui.process_bilibili_audio_batch("url", "fast", "zh", "", "", False)[0].startswith(
        "请先确认"
    )
    assert ui.process_lms_replay("secret", "fast", "zh", "", False)[1].startswith("请先确认")
