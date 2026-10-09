from dataclasses import dataclass, replace
from typing import Iterable

from stt.domain.entities import Paragraph, Segment


@dataclass(frozen=True)
class CleaningRules:
    max_no_speech_prob: float = 0.6
    min_avg_logprob: float = -1.0
    max_compression_ratio: float = 2.4
    paragraph_pause: float = 2.0
    paragraph_max_words: int = 150


def _is_speech(segment: Segment, rules: CleaningRules) -> bool:
    silent = (
        segment.no_speech_prob > rules.max_no_speech_prob
        and segment.avg_logprob < rules.min_avg_logprob
    )
    return not silent and segment.compression_ratio <= rules.max_compression_ratio


def filter_segments(segments: Iterable[Segment], rules: CleaningRules) -> list[Segment]:
    kept: list[Segment] = []
    for segment in segments:
        text = " ".join(segment.text.split())
        if not text or not _is_speech(segment, rules):
            continue
        if kept and kept[-1].text.casefold() == text.casefold():
            continue
        kept.append(replace(segment, text=text))
    return kept


def to_paragraphs(segments: Iterable[Segment], rules: CleaningRules) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    words: list[str] = []
    start = last_end = 0.0
    for segment in segments:
        too_long = len(words) >= rules.paragraph_max_words
        if words and (segment.start - last_end > rules.paragraph_pause or too_long):
            paragraphs.append(Paragraph(start, " ".join(words)))
            words = []
        if not words:
            start = segment.start
        words.extend(segment.text.split())
        last_end = segment.end
    if words:
        paragraphs.append(Paragraph(start, " ".join(words)))
    return paragraphs


def clean(segments: Iterable[Segment], rules: CleaningRules = CleaningRules()) -> list[Paragraph]:
    return to_paragraphs(filter_segments(segments, rules), rules)
