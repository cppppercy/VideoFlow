from videoflow.sources.bilibili import BilibiliSubtitleError
from pathlib import Path

from videoflow.models import Transcript, TranscriptSegment, TranscriptionDiagnostics
from videoflow import ui
from videoflow.workflows import BatchTranscription, OnlineTranscript


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


def test_single_bilibili_audio_result_is_shown_in_common_result_area(monkeypatch, tmp_path: Path) -> None:
    transcript = Transcript((TranscriptSegment(0, 1, "单条结果"),), language="zh")
    result = BatchTranscription(
        (OnlineTranscript("课程", transcript, "https://www.bilibili.com/video/BV1test"),), ()
    )
    monkeypatch.setattr(ui, "transcribe_bilibili_batch", lambda *args, **kwargs: result)
    monkeypatch.setattr(
        ui,
        "write_exports",
        lambda *args, **kwargs: (tmp_path / "course.txt", tmp_path / "course.srt"),
    )

    output = ui.process_bilibili_audio_batch("url", "fast", "zh", "", "", True)

    assert "直接显示在页面底部" in output[0]
    assert output[2] is None
    assert output[3].startswith("B 站音频转录结束")
    assert output[4] == [["0.000", "1.000", "单条结果", "单条结果", "", ""]]
    assert output[5] == "单条结果\n"
    assert output[7] == str(tmp_path / "course.txt")
    assert output[8] == str(tmp_path / "course.srt")


def test_multiple_bilibili_audio_results_only_offer_zip(monkeypatch, tmp_path: Path) -> None:
    transcript = Transcript((TranscriptSegment(0, 1, "结果"),), language="zh")
    result = BatchTranscription(
        (
            OnlineTranscript("课程一", transcript, "https://www.bilibili.com/video/BV1one"),
            OnlineTranscript("课程二", transcript, "https://www.bilibili.com/video/BV1two"),
        ),
        (),
    )
    archive = tmp_path / "batch.zip"
    monkeypatch.setattr(ui, "transcribe_bilibili_batch", lambda *args, **kwargs: result)
    monkeypatch.setattr(ui, "write_batch_archive", lambda *args, **kwargs: archive)

    output = ui.process_bilibili_audio_batch("first\nsecond", "fast", "zh", "", "", True)

    assert "多个视频的 TXT/SRT 已打包" in output[0]
    assert output[2] == str(archive)
    assert output[3:] == ("", [], "", "", None, None)


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
