from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: float


@dataclass(frozen=True)
class Paragraph:
    start: float
    text: str


@dataclass(frozen=True)
class TranscriptMeta:
    source: str
    created: str
    duration: float
    language: str
    model: str
