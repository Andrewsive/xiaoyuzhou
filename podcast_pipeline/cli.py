from __future__ import annotations

import json
from pathlib import Path

import typer

from .agent_service import create_agent_app
from .config import load_config
from .pipeline import PipelineRunner
from .xiaoyuzhou_web import XiaoyuzhouWebSource

app = typer.Typer(help="Podcast knowledge base pipeline")


def _runner(config_path: Path) -> PipelineRunner:
    return PipelineRunner(load_config(config_path))


@app.command("preflight")
def preflight(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(runner.dump_json(runner.preflight()))
    finally:
        runner.close()


@app.command("sync")
def sync(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(runner.dump_json(runner.sync()))
    finally:
        runner.close()


@app.command("download")
def download(
    config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False),
    limit: int | None = typer.Option(None, min=1),
    episode_id: str | None = typer.Option(None),
) -> None:
    runner = _runner(config)
    try:
        typer.echo(
            json.dumps(
                {"downloaded": runner.download_pending(limit=limit, episode_id=episode_id)},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        runner.close()


@app.command("transcribe")
def transcribe(
    config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False),
    limit: int | None = typer.Option(None, min=1),
    episode_id: str | None = typer.Option(None),
) -> None:
    runner = _runner(config)
    try:
        typer.echo(
            json.dumps(
                {"transcribed": runner.transcribe_pending(limit=limit, episode_id=episode_id)},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        runner.close()


@app.command("clean")
def clean(
    config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False),
    limit: int | None = typer.Option(None, min=1),
    episode_id: str | None = typer.Option(None),
) -> None:
    runner = _runner(config)
    try:
        typer.echo(
            json.dumps(
                {"cleaned": runner.clean_pending(limit=limit, episode_id=episode_id)},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        runner.close()


@app.command("index")
def index(
    config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False),
    limit: int | None = typer.Option(None, min=1),
    episode_id: str | None = typer.Option(None),
) -> None:
    runner = _runner(config)
    try:
        typer.echo(
            json.dumps(
                {"indexed": runner.index_pending(limit=limit, episode_id=episode_id)},
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        runner.close()


@app.command("run-once")
def run_once(
    config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False),
    limit: int | None = typer.Option(None, min=1),
) -> None:
    runner = _runner(config)
    try:
        typer.echo(runner.dump_json(runner.run_once(limit=limit)))
    finally:
        runner.close()


@app.command("retry-failed")
def retry_failed(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(json.dumps({"reset": runner.retry_failed()}, ensure_ascii=False, indent=2))
    finally:
        runner.close()


@app.command("stats")
def stats(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(runner.dump_json(runner.stats()))
    finally:
        runner.close()


@app.command("search")
def search(
    query: str = typer.Argument(...),
    top_k: int = typer.Option(5, min=1, max=20),
    config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False),
) -> None:
    runner = _runner(config)
    try:
        typer.echo(json.dumps(runner.search(query=query, top_k=top_k), ensure_ascii=False, indent=2))
    finally:
        runner.close()


@app.command("resolve-source")
def resolve_source(url: str = typer.Argument(..., help="Xiaoyuzhou episode or podcast URL")) -> None:
    source = XiaoyuzhouWebSource()
    resolved = source.resolve_url(url)
    typer.echo(
        json.dumps(
            {
                "podcast_id": resolved.podcast_id,
                "title": resolved.title,
                "author": resolved.author,
                "description": resolved.description,
                "source_url": resolved.source_url,
                "config_snippet": {
                    "display_name": resolved.title,
                    "source_url": resolved.source_url,
                    "enabled": True,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("serve-agent")
def serve_agent(
    config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8787, min=1, max=65535),
) -> None:
    flask_app = create_agent_app(config)
    flask_app.run(host=host, port=port)
