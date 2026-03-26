from podcast_pipeline.cleaner import group_segments
from podcast_pipeline.models import TranscriptSegment
from podcast_pipeline.utils import extract_podcast_id, guess_extension_from_url


def test_extract_podcast_id() -> None:
    url = "https://www.xiaoyuzhoufm.com/podcast/5e280faf418a84a0461fa1eb"
    assert extract_podcast_id(url) == "5e280faf418a84a0461fa1eb"


def test_guess_extension_from_url() -> None:
    url = "https://cdn.example.com/audio/demo.m4a?token=abc"
    assert guess_extension_from_url(url) == ".m4a"


def test_group_segments_respects_limit() -> None:
    segments = [
        TranscriptSegment(segment_id="1", text="hello", start_ms=0, end_ms=1000, speaker="a"),
        TranscriptSegment(segment_id="2", text="world", start_ms=1000, end_ms=2000, speaker="a"),
        TranscriptSegment(segment_id="3", text="python", start_ms=2000, end_ms=3000, speaker="b"),
    ]
    groups = group_segments(segments, max_chars=8)
    assert len(groups) == 3
    assert groups[0][0].start_ms == 0
    assert groups[-1][0].speaker == "b"
