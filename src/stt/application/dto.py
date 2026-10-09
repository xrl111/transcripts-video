from dataclasses import dataclass
from pathlib import Path

from stt.domain.cleaning import CleaningRules


@dataclass(frozen=True)
class RecordRequest:
    name: str
    out_root: Path
    live: bool = False


@dataclass(frozen=True)
class RecordResult:
    audio_path: Path
    seconds: float


@dataclass(frozen=True)
class TranscribeRequest:
    source: Path
    out_dir: Path
    language: str | None = None
    prompt: str | None = None


@dataclass(frozen=True)
class TranscribeResult:
    raw_path: Path
    language: str
    duration: float
    segment_count: int


@dataclass(frozen=True)
class CleanRequest:
    raw_path: Path
    rules: CleaningRules = CleaningRules()


@dataclass(frozen=True)
class CleanResult:
    transcript_path: Path
    kept: int
    dropped: int
    complete: bool
