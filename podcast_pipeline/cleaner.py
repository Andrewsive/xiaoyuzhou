from __future__ import annotations

import json
from pathlib import Path

from .config import AppConfig
from .http_clients import OpenAICompatibleClient, parse_json_response
from .models import CleanSegment, TranscriptSegment
from .utils import getenv_required, sha1_text


SYSTEM_PROMPT = """You clean podcast transcripts for retrieval.
Return strict JSON with this shape:
{
  "text": "cleaned paragraph",
  "summary": "one-sentence summary",
  "keywords": ["kw1", "kw2", "kw3"]
}
Requirements:
- Remove filler words and obvious ASR glitches.
- Keep facts, names, and intent faithful to the source.
- Write in Simplified Chinese when the source is Chinese.
- Do not invent details.
- Return JSON only.
"""


def load_segments_from_transcript_payload(transcript_path: Path) -> list[TranscriptSegment]:
    payload = json.loads(transcript_path.read_text(encoding="utf-8"))
    segments: list[TranscriptSegment] = []
    for file_item in payload.get("files", []):
        transcript_payload = file_item.get("payload", {})
        for transcript in transcript_payload.get("transcripts", []):
            for sentence in transcript.get("sentences", []):
                text = (sentence.get("text") or "").strip()
                if not text:
                    continue
                speaker = str(sentence.get("speaker_id", "unknown"))
                segment_id = sha1_text(
                    f"{sentence.get('sentence_id', '')}:{sentence.get('begin_time', 0)}:{sentence.get('end_time', 0)}:{text}"
                )
                segments.append(
                    TranscriptSegment(
                        segment_id=segment_id,
                        text=text,
                        start_ms=int(sentence.get("begin_time", 0)),
                        end_ms=int(sentence.get("end_time", 0)),
                        speaker=speaker,
                    )
                )
    return segments


def group_segments(segments: list[TranscriptSegment], *, max_chars: int) -> list[list[TranscriptSegment]]:
    groups: list[list[TranscriptSegment]] = []
    current: list[TranscriptSegment] = []
    current_chars = 0
    for segment in segments:
        segment_len = len(segment.text)
        if current and current_chars + segment_len > max_chars:
            groups.append(current)
            current = []
            current_chars = 0
        current.append(segment)
        current_chars += segment_len
    if current:
        groups.append(current)
    return groups


class TranscriptCleaner:
    def __init__(self, config: AppConfig):
        self.config = config
        self.client = OpenAICompatibleClient(
            api_key=getenv_required(config.cleaner.api_key_env),
            base_url=config.cleaner_base_url(),
        )

    def clean_to_files(self, *, transcript_path: Path, jsonl_output_path: Path, md_output_path: Path) -> tuple[Path, Path]:
        segments = load_segments_from_transcript_payload(transcript_path)
        grouped = group_segments(segments, max_chars=self.config.cleaner.max_input_chars)
        cleaned_segments: list[CleanSegment] = []
        for group in grouped:
            cleaned_segments.append(self._clean_group(group))

        with jsonl_output_path.open("w", encoding="utf-8") as handle:
            for item in cleaned_segments:
                handle.write(
                    json.dumps(
                        {
                            "chunk_id": item.chunk_id,
                            "text": item.text,
                            "start_ms": item.start_ms,
                            "end_ms": item.end_ms,
                            "speaker": item.speaker,
                            "keywords": item.keywords,
                            "summary": item.summary,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        md_output_path.write_text(self._render_episode_markdown(cleaned_segments), encoding="utf-8")
        return jsonl_output_path, md_output_path

    def _clean_group(self, group: list[TranscriptSegment]) -> CleanSegment:
        raw_text = "\n".join(f"[{seg.start_ms}-{seg.end_ms}] (speaker={seg.speaker}) {seg.text}" for seg in group)
        response = self.client.chat(
            model=self.config.cleaner_model(),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_text},
            ],
            temperature=self.config.cleaner.temperature,
        )
        parsed = parse_json_response(response)
        speakers = sorted({segment.speaker for segment in group})
        return CleanSegment(
            chunk_id=sha1_text("|".join(segment.segment_id for segment in group)),
            text=parsed["text"].strip(),
            start_ms=group[0].start_ms,
            end_ms=group[-1].end_ms,
            speaker=",".join(speakers),
            keywords=[str(item).strip() for item in parsed.get("keywords", []) if str(item).strip()],
            summary=parsed.get("summary", "").strip(),
        )

    def _render_episode_markdown(self, segments: list[CleanSegment]) -> str:
        lines = ["# Episode Summary", "", "## Cleaned Segments", ""]
        for item in segments:
            lines.append(f"### {item.start_ms} - {item.end_ms}")
            lines.append("")
            lines.append(item.text)
            lines.append("")
            if item.summary:
                lines.append(f"Summary: {item.summary}")
                lines.append("")
            if item.keywords:
                lines.append(f"Keywords: {', '.join(item.keywords)}")
                lines.append("")
        return "\n".join(lines).strip() + "\n"
