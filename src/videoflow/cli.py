"""命令行入口。"""

import argparse
from pathlib import Path

from .exporters import write_exports
from .transcriber import MODEL_OPTIONS, TRANSCRIPTION_PROFILES, TranscriptionError, transcribe_media


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="VideoFlow 本地媒体转录")
    parser.add_argument("media", help="本地音频或视频文件")
    parser.add_argument("--model", choices=MODEL_OPTIONS, default="base", help="Whisper 模型")
    parser.add_argument(
        "--profile",
        choices=tuple(TRANSCRIPTION_PROFILES),
        help="速度/准确度预设；设置后会覆盖 --model",
    )
    parser.add_argument("--language", help="ISO 语言代码，例如 zh、en；默认自动识别")
    parser.add_argument("--prompt", help="课程关键词或人名，用于提高专有词识别")
    parser.add_argument(
        "--corrections",
        help='明确纠错规则，多条用换行分隔，例如 "REG=>RAG"',
    )
    parser.add_argument(
        "--refine-low-confidence",
        action="store_true",
        help="仅用更高 beam 重试最多 12 个模型标记为可疑的片段",
    )
    parser.add_argument(
        "--paraformer-review",
        action="store_true",
        help="使用可选 Paraformer 复核最多 12 个可疑中文片段",
    )
    parser.add_argument("--output-dir", default="exports", help="TXT/SRT 输出目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        transcript = transcribe_media(
            args.media,
            model_name=args.model,
            language=args.language,
            profile_name=args.profile,
            initial_prompt=args.prompt,
            refine_low_confidence=args.refine_low_confidence,
            correction_rules=args.corrections,
            use_paraformer_review=args.paraformer_review,
        )
        txt_path, srt_path = write_exports(transcript, args.output_dir, Path(args.media).stem)
    except TranscriptionError as exc:
        print(f"转录失败：{exc}")
        return 1
    print(f"转录完成：{len(transcript.segments)} 个分段，语言：{transcript.language or '未知'}")
    if transcript.diagnostics is not None:
        diagnostics = transcript.diagnostics
        duration = f"{diagnostics.media_duration:.1f}" if diagnostics.media_duration is not None else "未知"
        last = f"{diagnostics.last_segment_end:.1f}" if diagnostics.last_segment_end is not None else "无"
        rtf = f"{diagnostics.realtime_factor:.3f}" if diagnostics.realtime_factor is not None else "未知"
        print(
            f"诊断：媒体 {duration} 秒，最后字幕 {last} 秒，"
            f"识别 {diagnostics.inference_seconds:.1f} 秒，RTF {rtf}，"
            f"覆盖状态 {diagnostics.coverage_status}"
        )
        if diagnostics.effective_batch_size is not None:
            print(f"批量大小：{diagnostics.effective_batch_size}")
        if diagnostics.gpu_name:
            gpu_memory = (
                f"，本进程峰值显存约 {diagnostics.peak_gpu_memory_mb:.0f} MB"
                if diagnostics.peak_gpu_memory_mb is not None
                else ""
            )
            print(f"GPU：{diagnostics.gpu_name}{gpu_memory}")
        if diagnostics.review_segment_count:
            print(f"需复核字幕段：{diagnostics.review_segment_count}（模型启发式提示）")
        if diagnostics.correction_count:
            print(f"已按显式规则修正：{diagnostics.correction_count} 处")
        if diagnostics.paraformer_review_count:
            print(f"Paraformer 已复核：{diagnostics.paraformer_review_count} 段")
    print(f"TXT：{txt_path}\nSRT：{srt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
