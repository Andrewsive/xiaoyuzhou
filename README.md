# Podcast Knowledge Pipeline

This repository now contains a local MVP pipeline for turning podcast feeds into a retrieval-ready knowledge base.

## Setup

1. Install dependencies:

```bash
C:\Users\yichen\miniconda3\python.exe -m pip install -r requirements.txt
```

2. Copy `.env.example` to `.env` and fill in:

- `DASHSCOPE_API_KEY`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `EMBEDDING_API_KEY`
- `EMBEDDING_BASE_URL`
- `EMBEDDING_MODEL`

3. Update `config.yaml`:

- For Xiaoyuzhou podcast URLs, the pipeline will try the public web page first
- Replace `rsshub.base_url` with your own RSSHub deployment for Xiaoyuzhou, or
- Set `podcasts[].rss_url` directly if you already have a working RSS URL
- If no cloud keys are configured, the pipeline falls back to:
  - local Whisper ASR
  - heuristic transcript cleaning
  - SQLite FTS search

If you only have an episode URL, resolve it first:

```bash
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline resolve-source https://www.xiaoyuzhoufm.com/episode/<episode-id>
```

## Commands

```bash
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline preflight
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline sync
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline download
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline transcribe
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline clean
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline index
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline download --limit 1
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline transcribe --limit 1
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline clean --limit 1
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline index --limit 1
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline run-once
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline retry-failed
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline stats
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline serve-agent --host 127.0.0.1 --port 8787
```

## Notes

- Public `rsshub.app` may return `403` for Xiaoyuzhou routes.
- Xiaoyuzhou public podcast pages often expose only the latest batch of episodes in `__NEXT_DATA__`; for full backfill, prefer your own RSSHub or a direct RSS URL.
- The new pipeline writes runtime data under `data/`.
- The old one-off scripts are still present, but the new entrypoint is `python -m podcast_pipeline`.

## Agent Mount

Run a local retrieval service for agents:

```bash
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline serve-agent --host 127.0.0.1 --port 8787
```

Endpoints:

- `GET /health`
- `GET /v1/search?q=年轻化&top_k=3`
- `POST /v1/retrieve` with JSON `{"query":"年轻化","top_k":3}`
