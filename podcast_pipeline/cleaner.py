from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .config import AppConfig
from .http_clients import OpenAICompatibleClient, parse_json_response
from .models import CleanSegment, TranscriptSegment
from .utils import getenv_required, sha1_text

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover - optional dependency fallback
    OpenCC = None


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
- Preserve the speaker's meaning instead of rewriting the content.
- Do not invent details.
- Return JSON only.
"""

_OPENCC = OpenCC("t2s") if OpenCC else None


def to_simplified(text: str) -> str:
    if not text:
        return text
    if _OPENCC is None:
        return text
    return _OPENCC.convert(text)


def _default_model_for_base_url(base_url: str) -> str | None:
    normalized = base_url.strip().lower()
    if "dashscope.aliyuncs.com/compatible-mode/v1" in normalized:
        return "qwen-plus"
    if "api.openai.com/v1" in normalized:
        return "gpt-4o-mini"
    return None


def _resolve_cleaner_settings(config: AppConfig) -> tuple[str, str, str] | None:
    api_key = os.getenv(config.cleaner.api_key_env, "").strip()
    base_url = os.getenv(config.cleaner.base_url_env, "").strip()
    model = os.getenv(config.cleaner.model_env, "").strip()
    if api_key and base_url and model:
        return api_key, base_url.rstrip("/"), model

    embedding_api_key = os.getenv(config.embedding.api_key_env, "").strip()
    embedding_base_url = os.getenv(config.embedding.base_url_env, "").strip()
    if not embedding_api_key:
        return None

    api_key = api_key or embedding_api_key
    base_url = (base_url or embedding_base_url).rstrip("/")
    model = model or _default_model_for_base_url(base_url) or config.cleaner.default_model
    if api_key and base_url and model:
        return api_key, base_url, model
    return None


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
        provider = config.cleaner.provider.lower()
        cleaner_settings = _resolve_cleaner_settings(config)
        self.mode = "heuristic" if provider == "heuristic" or (provider == "auto" and not cleaner_settings) else "llm"
        self.client = None
        self.model = None
        if self.mode == "llm":
            if cleaner_settings is None:
                raise RuntimeError("Cleaner is configured for LLM mode but no compatible API settings were found")
            api_key, base_url, model = cleaner_settings
            self.client = OpenAICompatibleClient(api_key=api_key, base_url=base_url)
            self.model = model

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
        if self.mode == "llm":
            if self.client is None or self.model is None:
                raise RuntimeError("LLM cleaner is not initialized correctly")
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                temperature=self.config.cleaner.temperature,
            )
            parsed = parse_json_response(response)
        else:
            parsed = self._heuristic_clean(raw_text)

        speakers = sorted({segment.speaker for segment in group})
        text = to_simplified(str(parsed["text"]).strip())
        summary = to_simplified(str(parsed.get("summary", "")).strip())
        keywords = [to_simplified(str(item).strip()) for item in parsed.get("keywords", []) if str(item).strip()]
        return CleanSegment(
            chunk_id=sha1_text("|".join(segment.segment_id for segment in group)),
            text=text,
            start_ms=group[0].start_ms,
            end_ms=group[-1].end_ms,
            speaker=",".join(speakers),
            keywords=keywords,
            summary=summary,
        )

    def _heuristic_clean(self, text: str) -> dict[str, object]:
        cleaned = re.sub(r"\[(\d+)-(\d+)\]\s+\(speaker=.*?\)\s*", "", text)
        cleaned = to_simplified(cleaned)
        filler_pattern = r"\b(那个|就是说|然后|就是|其实|可能|你知道|呃|嗯|啊)\b"
        cleaned = re.sub(filler_pattern, " ", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)
        cleaned = cleaned.strip()
        summary = cleaned.split("。")[0].strip() if "。" in cleaned else cleaned[:80]
        return {
            "text": cleaned,
            "summary": summary[:120],
            "keywords": [],
        }

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
