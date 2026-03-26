from __future__ import annotations

import json

import feedparser
import requests

from .config import AppConfig
from .models import EpisodeCandidate, PodcastDefinition
from .utils import ensure_directory, sha1_text


class RSSHubSource:
    def __init__(self, config: AppConfig):
        self.config = config

    def build_rss_url(self, podcast: PodcastDefinition) -> str:
        if podcast.rss_url:
            return podcast.rss_url
        return f"{self.config.rsshub.base_url.rstrip('/')}/xiaoyuzhou/podcast/{podcast.podcast_id}"

    def fetch_feed(self, podcast: PodcastDefinition) -> tuple[str, list[EpisodeCandidate]]:
        rss_url = self.build_rss_url(podcast)
        response = requests.get(
            rss_url,
            headers={"User-Agent": self.config.rsshub.user_agent},
            timeout=30,
        )
        if response.status_code == 403:
            raise RuntimeError(
                "RSSHub returned 403 for the Xiaoyuzhou route. Configure a self-hosted RSSHub instance "
                "with Xiaoyuzhou credentials/device id instead of relying on the public rsshub.app host."
            )
        response.raise_for_status()
        xml_text = response.text
        self._save_feed_snapshot(podcast.podcast_id, xml_text)

        parsed = feedparser.parse(xml_text)
        feed_title = parsed.feed.get("title", podcast.display_name)
        episodes: list[EpisodeCandidate] = []
        for entry in parsed.entries:
            audio_url = ""
            enclosures = entry.get("enclosures", [])
            if enclosures:
                audio_url = enclosures[0].get("href", "")
            guid = entry.get("id") or entry.get("guid") or entry.get("link") or audio_url
            if not guid or not audio_url:
                continue
            episode_id = sha1_text(f"{podcast.podcast_id}:{guid}")
            payload = {
                "title": entry.get("title", ""),
                "id": entry.get("id", ""),
                "guid": entry.get("guid", ""),
                "link": entry.get("link", ""),
                "audio_url": audio_url,
                "published": entry.get("published", ""),
                "summary": entry.get("summary", ""),
            }
            episodes.append(
                EpisodeCandidate(
                    episode_id=episode_id,
                    podcast_id=podcast.podcast_id,
                    podcast_title=feed_title,
                    guid=guid,
                    title=entry.get("title", episode_id),
                    source_url=entry.get("link", podcast.source_url),
                    audio_url=audio_url,
                    published_at=entry.get("published", "") or entry.get("updated", ""),
                    summary=entry.get("summary", ""),
                    raw_feed_json=json.dumps(payload, ensure_ascii=False),
                )
            )
        return rss_url, episodes

    def _save_feed_snapshot(self, podcast_id: str, xml_text: str) -> None:
        target_dir = ensure_directory(self.config.raw_rss_path / podcast_id)
        (target_dir / "latest.xml").write_text(xml_text, encoding="utf-8")
