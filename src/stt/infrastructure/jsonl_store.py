import json
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

from stt.application.ports import SttError
from stt.domain.entities import Segment, TranscriptMeta


class _JsonlWriter:
    def __init__(self, file: TextIO):
        self._file = file

    def write(self, segment: Segment) -> None:
        self.write_row({"type": "segment", **asdict(segment)})

    def close(self, complete: bool) -> None:
        if complete:
            self.write_row({"type": "end"})
        self._file.close()

    def write_row(self, row: dict) -> None:
        self._file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self._file.flush()


class JsonlStore:
    def open_writer(self, path: Path, meta: TranscriptMeta) -> _JsonlWriter:
        writer = _JsonlWriter(path.open("w", encoding="utf-8"))
        writer.write_row({"type": "meta", **asdict(meta)})
        return writer

    def read(self, path: Path) -> tuple[TranscriptMeta, list[Segment], bool]:
        meta = None
        segments: list[Segment] = []
        complete = False
        try:
            with path.open(encoding="utf-8") as file:
                for line in file:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        break  # dòng cuối bị cắt dở khi tiến trình chết giữa chừng
                    kind = row.pop("type", None)
                    if kind == "meta":
                        meta = TranscriptMeta(**row)
                    elif kind == "segment":
                        segments.append(Segment(**row))
                    elif kind == "end":
                        complete = True
        except (TypeError, AttributeError, UnicodeDecodeError) as error:
            raise SttError(f"{path} không đúng định dạng raw.jsonl: {error}") from error
        if meta is None:
            raise SttError(f"{path} không đúng định dạng raw.jsonl: thiếu dòng meta")
        return meta, segments, complete
