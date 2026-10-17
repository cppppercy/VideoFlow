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
        )
        txt_path, srt_path = write_exports(transcript, args.output_dir, Path(args.media).stem)
    except TranscriptionError as exc:
        print(f"转录失败：{exc}")
        return 1
    print(f"转录完成：{len(transcript.segments)} 个分段，语言：{transcript.language or '未知'}")
    print(f"TXT：{txt_path}\nSRT：{srt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
