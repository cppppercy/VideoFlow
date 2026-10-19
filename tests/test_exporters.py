from zipfile import ZipFile

from videoflow.exporters import (
    format_readable_text,
    format_srt_timestamp,
    safe_export_stem,
    transcript_to_srt,
    transcript_to_txt,
    write_batch_archive,
)
from videoflow.models import Transcript, TranscriptSegment


def sample_transcript() -> Transcript:
    return Transcript((
        TranscriptSegment(0, 1.2344, "你好"),
        TranscriptSegment(61.9996, 3661.2, "世界"),
    ), language="zh")


def test_srt_timestamp_rounds_and_carries() -> None:
    assert format_srt_timestamp(1.9996) == "00:00:02,000"
    assert format_srt_timestamp(3661.2) == "01:01:01,200"


def test_exported_txt_is_plain_utf8_text() -> None:
    assert transcript_to_txt(sample_transcript()) == "你好\n\n世界\n"


def test_readable_txt_joins_subtitle_fragments_without_inventing_punctuation() -> None:
    transcript = Transcript((
        TranscriptSegment(0, 1, "今天我们来讲"),
        TranscriptSegment(1, 2, "机器学习。"),
        TranscriptSegment(2.1, 3, "首先，理解"),
        TranscriptSegment(3, 4, "监督学习"),
    ))

    assert format_readable_text(transcript) == "今天我们来讲机器学习。首先，理解监督学习"


def test_readable_txt_uses_long_pause_only_at_reliable_paragraph_boundary() -> None:
    transcript = Transcript((
        TranscriptSegment(0, 1, "第一句。"),
        TranscriptSegment(4, 5, "第二句！"),
        TranscriptSegment(12, 13, "没有标点的第三部分"),
    ))

    assert format_readable_text(transcript) == "第一句。\n\n第二句！\n\n没有标点的第三部分"


def test_readable_txt_handles_english_numbers_and_mixed_chinese() -> None:
    transcript = Transcript((
        TranscriptSegment(0, 1, "VideoFlow"),
        TranscriptSegment(1, 2, "version"),
        TranscriptSegment(2, 3, "0.4.2"),
        TranscriptSegment(3, 4, "支持CPU"),
        TranscriptSegment(4, 5, "INT8。"),
    ))

    assert format_readable_text(transcript) == "VideoFlow version 0.4.2支持CPU INT8。"


def test_readable_txt_empty_transcript() -> None:
    assert format_readable_text(Transcript(())) == ""


def test_exported_srt_has_standard_blocks() -> None:
    assert transcript_to_srt(sample_transcript()) == (
        "1\n00:00:00,000 --> 00:00:01,234\n你好\n\n"
        "2\n00:01:02,000 --> 01:01:01,200\n世界\n"
    )


def test_export_stem_removes_cross_platform_invalid_characters() -> None:
    assert safe_export_stem('课程: 第一讲?/\\') == "课程_ 第一讲"


def test_batch_archive_contains_txt_and_srt_for_each_item(tmp_path) -> None:
    archive = write_batch_archive(
        [("第一讲", sample_transcript()), ("第一讲", sample_transcript())], tmp_path
    )
    with ZipFile(archive) as opened:
        assert opened.namelist() == ["第一讲.txt", "第一讲.srt", "第一讲-2.txt", "第一讲-2.srt"]
