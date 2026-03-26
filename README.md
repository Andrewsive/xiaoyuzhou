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

- Replace `rsshub.base_url` with your own RSSHub deployment for Xiaoyuzhou, or
- Set `podcasts[].rss_url` directly if you already have a working RSS URL

## Commands

```bash
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline preflight
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline sync
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline download
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline transcribe
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline clean
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline index
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline run-once
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline retry-failed
C:\Users\yichen\miniconda3\python.exe -m podcast_pipeline stats
```

## Notes

- Public `rsshub.app` may return `403` for Xiaoyuzhou routes.
- The new pipeline writes runtime data under `data/`.
- The old one-off scripts are still present, but the new entrypoint is `python -m podcast_pipeline`.
