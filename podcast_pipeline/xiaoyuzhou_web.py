from __future__ import annotations

import json
import re
from dataclasses import dataclass

import requests

from .models import EpisodeCandidate, PodcastDefinition
from .utils import sha1_text


NEXT_DATA_PATTERN = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>')


@dataclass(slots=True)
class ResolvedPodcast:
    podcast_id: str
    title: str
    source_url: str
    author: str = ""
    description: str = ""


class XiaoyuzhouWebSource:
    def __init__(self, user_agent: str = "Mozilla/5.0"):
        self.user_agent = user_agent

    def resolve_url(self, url: str) -> ResolvedPodcast:
        if "/episode/" in url:
            payload = self._fetch_next_data(url)
            episode = payload.get("props", {}).get("pageProps", {}).get("episode")
            if not episode:
                raise RuntimeError(f"Could not resolve Xiaoyuzhou episode page: {url}")
            podcast_id = episode["pid"]
            podcast = episode.get("podcast", {})
            return ResolvedPodcast(
                podcast_id=podcast_id,
                title=podcast.get("title", ""),
                author=podcast.get("author", ""),
                description=podcast.get("description", ""),
                source_url=f"https://www.xiaoyuzhoufm.com/podcast/{podcast_id}",
            )

        if "/podcast/" in url:
            payload = self._fetch_next_data(url)
            podcast = payload.get("props", {}).get("pageProps", {}).get("podcast")
            if not podcast:
                raise RuntimeError(f"Could not resolve Xiaoyuzhou podcast page: {url}")
            podcast_id = podcast["pid"]
            return ResolvedPodcast(
                podcast_id=podcast_id,
                title=podcast.get("title", ""),
                author=podcast.get("author", ""),
                description=podcast.get("description", ""),
                source_url=f"https://www.xiaoyuzhoufm.com/podcast/{podcast_id}",
            )

        raise ValueError(f"Unsupported Xiaoyuzhou URL: {url}")

    def fetch_podcast(self, podcast: PodcastDefinition) -> tuple[str, list[EpisodeCandidate]]:
        resolved = self.resolve_url(podcast.source_url)
        payload = self._fetch_next_data(resolved.source_url)
        podcast_payload = payload.get("props", {}).get("pageProps", {}).get("podcast")
        if not podcast_payload:
            raise RuntimeError(f"Could not parse Xiaoyuzhou podcast payload from {resolved.source_url}")

        episodes: list[EpisodeCandidate] = []
        for episode in podcast_payload.get("episodes", []):
            audio_url = (
                episode.get("enclosure", {}).get("url")
                or episode.get("media", {}).get("source", {}).get("url", "")
            )
            episode_id = episode.get("eid")
            if not episode_id or not audio_url:
                continue
            canonical_podcast_id = podcast_payload.get("pid", resolved.podcast_id)
            source_url = f"https://www.xiaoyuzhoufm.com/episode/{episode_id}"
            summary = episode.get("description") or episode.get("shownotes") or ""
            episodes.append(
                EpisodeCandidate(
                    episode_id=sha1_text(f"{canonical_podcast_id}:{episode_id}"),
                    podcast_id=canonical_podcast_id,
                    podcast_title=podcast_payload.get("title", podcast.display_name),
                    guid=episode_id,
                    title=episode.get("title", episode_id),
                    source_url=source_url,
                    audio_url=audio_url,
                    published_at=episode.get("pubDate", ""),
                    summary=summary,
                    raw_feed_json=json.dumps(episode, ensure_ascii=False),
                )
            )
        return resolved.source_url, episodes

    def _fetch_next_data(self, url: str) -> dict:
        response = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=30)
        response.raise_for_status()
        match = NEXT_DATA_PATTERN.search(response.text)
        if not match:
            raise RuntimeError(f"Could not find __NEXT_DATA__ on page {url}")
        return json.loads(match.group(1))
