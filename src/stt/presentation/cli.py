import argparse
import sys
import time
from datetime import date
from pathlib import Path

from stt.application.dto import CleanRequest, RecordRequest, TranscribeRequest
from stt.application.ports import SttError
from stt.application.use_cases import CleanTranscript, RecordAudio, TranscribeMedia
from stt.infrastructure.jsonl_store import JsonlStore
from stt.infrastructure.markdown_writer import MarkdownWriter

OUT_ROOT = Path("out")


def _out_dir(source: Path) -> Path:
    if OUT_ROOT.resolve() in source.resolve().parents:
        return source.parent
    return OUT_ROOT / f"{date.today().isoformat()}-{source.stem}"


def _transcribe(args: argparse.Namespace) -> Path:
    from stt.infrastructure.whisper_recognizer import WhisperRecognizer

    def progress(done: float, total: float) -> None:
        percent = 100 * done / total if total else 100
        print(f"\r{percent:5.1f}%  {done:.0f}/{total:.0f} giây", end="", flush=True)

    print(f"Đang chép lời bằng model {args.model}. Lần đầu sẽ tải model về máy.")
    started = time.monotonic()
    result = TranscribeMedia(WhisperRecognizer(args.model), JsonlStore()).execute(
        TranscribeRequest(args.file, _out_dir(args.file), args.language, args.prompt), progress
    )
    elapsed = time.monotonic() - started
    speed = f", gấp {elapsed / result.duration:.1f} lần thời lượng" if result.duration else ""
    print(f"\nĐã chép {result.segment_count} đoạn ({result.language}) trong {elapsed:.0f} giây{speed}.")
    print(f"File thô: {result.raw_path}")
    return result.raw_path


def _clean(raw_path: Path) -> None:
    result = CleanTranscript(JsonlStore(), MarkdownWriter()).execute(CleanRequest(raw_path))
    if not result.complete:
        print("Cảnh báo: lượt chép lời này bị ngắt giữa chừng, transcript chưa đầy đủ.", file=sys.stderr)
    print(f"Giữ {result.kept} đoạn, bỏ {result.dropped} đoạn. Transcript: {result.transcript_path}")


def _record(args: argparse.Namespace) -> None:
    from stt.infrastructure.wasapi_recorder import WasapiRecorder

    live = None
    if args.live:
        from stt.infrastructure.whisper_recognizer import WhisperRecognizer

        live = WhisperRecognizer("small")
    print("Đang thu âm thanh máy tính. Nhấn Ctrl+C để dừng.")
    result = RecordAudio(WasapiRecorder(), live).execute(
        RecordRequest(args.name, OUT_ROOT, args.live), print
    )
    print(f"\nĐã thu {result.seconds:.0f} giây vào {result.audio_path}")
    print(f"Chép lời bằng: stt run \"{result.audio_path}\"")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stt", description="Chép lời âm thanh máy tính hoặc video, chạy local.")
    commands = parser.add_subparsers(dest="command", required=True)

    def add_source_command(name: str, help_text: str) -> None:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("file", type=Path, help="file wav hoặc video")
        command.add_argument("--model", default="large-v3")
        command.add_argument("--language", choices=["en", "vi"], help="mặc định: tự nhận")
        command.add_argument("--prompt", help="tên riêng, thuật ngữ để model nghe đúng")

    add_source_command("transcribe", "chép lời ra raw.jsonl")
    add_source_command("run", "chép lời rồi làm sạch")
    clean = commands.add_parser("clean", help="làm sạch raw.jsonl thành transcript.md")
    clean.add_argument("raw", type=Path)
    record = commands.add_parser("record", help="thu âm thanh máy tính, Ctrl+C để dừng")
    record.add_argument("name", help="tên buổi ghi, dùng làm tên thư mục")
    record.add_argument("--live", action="store_true", help="in bản chép nháp trong lúc thu")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "record":
            _record(args)
        elif args.command == "clean":
            _clean(args.raw)
        else:
            raw_path = _transcribe(args)
            if args.command == "run":
                _clean(raw_path)
    except SttError as error:
        print(f"Lỗi: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nĐã dừng. Phần đã xong vẫn được giữ trên đĩa.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
