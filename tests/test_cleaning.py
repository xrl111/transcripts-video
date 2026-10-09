from stt.domain.cleaning import CleaningRules, clean, filter_segments, to_paragraphs
from stt.domain.entities import Paragraph, Segment

RULES = CleaningRules()


def seg(start, end, text, logprob=-0.2, no_speech=0.01, ratio=1.2):
    return Segment(start, end, text, logprob, no_speech, ratio)


def texts(segments):
    return [s.text for s in segments]


def test_drops_hallucination_on_silence():
    segments = [
        seg(0, 2, "Hello everyone."),
        seg(2, 4, "Thanks for watching!", logprob=-1.5, no_speech=0.9),
    ]
    assert texts(filter_segments(segments, RULES)) == ["Hello everyone."]


def test_keeps_segment_when_only_one_silence_signal_fires():
    segments = [
        seg(0, 2, "Quiet but clear.", logprob=-0.3, no_speech=0.9),
        seg(2, 4, "Mumbled speech.", logprob=-1.5, no_speech=0.1),
    ]
    assert len(filter_segments(segments, RULES)) == 2


def test_drops_repetition_loop():
    segments = [seg(0, 2, "ok ok ok ok ok ok ok ok", ratio=3.1), seg(2, 4, "Next topic.")]
    assert texts(filter_segments(segments, RULES)) == ["Next topic."]


def test_collapses_consecutive_duplicates_ignoring_case_and_spacing():
    segments = [
        seg(0, 2, "Thank you."),
        seg(2, 4, "  thank   you. "),
        seg(4, 6, "Thank you."),
        seg(6, 8, "Moving on."),
    ]
    assert texts(filter_segments(segments, RULES)) == ["Thank you.", "Moving on."]


def test_drops_blank_text_and_normalizes_whitespace():
    segments = [seg(0, 2, "   "), seg(2, 4, " two   spaces\n here ")]
    assert texts(filter_segments(segments, RULES)) == ["two spaces here"]


def test_new_paragraph_after_long_pause():
    segments = [seg(0, 2, "First point."), seg(2.5, 4, "Still first."), seg(7, 9, "Second point.")]
    assert to_paragraphs(segments, RULES) == [
        Paragraph(0, "First point. Still first."),
        Paragraph(7, "Second point."),
    ]


def test_new_paragraph_when_too_long():
    rules = CleaningRules(paragraph_max_words=4)
    segments = [seg(0, 1, "one two three"), seg(1, 2, "four five"), seg(2, 3, "six")]
    assert to_paragraphs(segments, rules) == [
        Paragraph(0, "one two three four five"),
        Paragraph(2, "six"),
    ]


def test_empty_input():
    assert clean([], RULES) == []


def test_clean_filters_then_groups():
    segments = [
        seg(0, 2, "Welcome."),
        seg(2, 3, "you", logprob=-1.4, no_speech=0.8),
        seg(3, 5, "Let's begin."),
    ]
    assert clean(segments, RULES) == [Paragraph(0, "Welcome. Let's begin.")]
