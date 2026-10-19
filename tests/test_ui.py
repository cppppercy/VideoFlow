from videoflow.sources.bilibili import BilibiliSubtitleError
from videoflow.models import Transcript, TranscriptSegment, TranscriptionDiagnostics
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


def test_cuda_profile_is_declared_for_ui() -> None:
    assert ("GPU 增强（turbo / RTX，推荐本机）", "gpu_turbo") in ui.PROFILE_OPTIONS


def test_diagnostic_status_does_not_call_large_tail_complete() -> None:
    transcript = Transcript(
        (TranscriptSegment(0, 1800, "部分结果"),),
        diagnostics=TranscriptionDiagnostics(
            media_duration=5400,
            speech_duration=4800,
            last_segment_end=1800,
            model_load_seconds=1,
            inference_seconds=100,
            total_seconds=101,
            cpu_seconds=90,
            peak_memory_mb=800,
            pipeline="long-media",
            coverage_status="needs_review",
        ),
    )

    status = ui._diagnostic_status("转录结束。", transcript)

    assert "01:30:00" in status
    assert "00:30:00" in status
    assert "未标记为完整成功" in status
