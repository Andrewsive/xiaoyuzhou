from __future__ import annotations

import json
from pathlib import Path

import typer

from .config import load_config
from .pipeline import PipelineRunner

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
def download(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(json.dumps({"downloaded": runner.download_pending()}, ensure_ascii=False, indent=2))
    finally:
        runner.close()


@app.command("transcribe")
def transcribe(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(json.dumps({"transcribed": runner.transcribe_pending()}, ensure_ascii=False, indent=2))
    finally:
        runner.close()


@app.command("clean")
def clean(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(json.dumps({"cleaned": runner.clean_pending()}, ensure_ascii=False, indent=2))
    finally:
        runner.close()


@app.command("index")
def index(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(json.dumps({"indexed": runner.index_pending()}, ensure_ascii=False, indent=2))
    finally:
        runner.close()


@app.command("run-once")
def run_once(config: Path = typer.Option(Path("config.yaml"), exists=True, dir_okay=False)) -> None:
    runner = _runner(config)
    try:
        typer.echo(runner.dump_json(runner.run_once()))
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
