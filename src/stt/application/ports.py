from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Protocol

from stt.domain.entities import Paragraph, Segment, TranscriptMeta


class SttError(Exception):
    """Lỗi có thông báo dành cho người dùng."""


@dataclass(frozen=True)
class Recognition:
    language: str
    duration: float
    segments: Iterator[Segment]


class AudioRecorder(Protocol):
    def record(self, output_path: Path) -> Iterator[bytes]: ...


class SpeechRecognizer(Protocol):
    model_name: str

    def transcribe(
        self, source: Path | BinaryIO, language: str | None, prompt: str | None
    ) -> Recognition: ...


class SegmentWriter(Protocol):
    def write(self, segment: Segment) -> None: ...

    def close(self, complete: bool) -> None: ...


class SegmentStore(Protocol):
    def open_writer(self, path: Path, meta: TranscriptMeta) -> SegmentWriter: ...

    def read(self, path: Path) -> tuple[TranscriptMeta, list[Segment], bool]: ...


class TranscriptWriter(Protocol):
    def write(self, path: Path, meta: TranscriptMeta, paragraphs: list[Paragraph]) -> None: ...
