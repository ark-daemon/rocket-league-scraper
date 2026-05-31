"""Typer CLI for the Rocket League scraper."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import Settings, get_settings
from .fetchers.blast_fetcher import BlastFetcher
from .fetchers.drekt_fetcher import DrektFetcher
from .fetchers.liquipedia_fetcher import LiquipediaFetcher
from .logging_config import configure_logging
from .storage import Storage

app = typer.Typer(help="Async structural data extraction CLI")
scrape_app = typer.Typer(help="Run one or more configured extraction jobs")
app.add_typer(scrape_app, name="scrape")
console = Console()


def bootstrap() -> tuple[Settings, Storage]:
    settings = get_settings()
    configure_logging(settings.log_dir)
    return settings, Storage(settings.db_path)


async def run_source(source: str) -> tuple[int, int]:
    settings, storage = bootstrap()
    await storage.init()
    if source == "blast":
        return await BlastFetcher(settings, storage).scrape()
    if source == "liquipedia":
        return await LiquipediaFetcher(settings, storage).scrape()
    if source == "drekt":
        return await DrektFetcher(settings, storage).scrape()
    raise typer.BadParameter(f"Unknown source: {source}")


@scrape_app.command("blast")
def scrape_blast() -> None:
    """Run the primary configured extraction pipeline."""
    seen, written = asyncio.run(run_source("blast"))
    console.print(f"Primary scrape complete: {seen} items seen, {written} rows written.")


@scrape_app.command("liquipedia")
def scrape_liquipedia() -> None:
    """Run the secondary configured extraction pipeline."""
    seen, written = asyncio.run(run_source("liquipedia"))
    console.print(f"Secondary scrape complete: {seen} pages seen, {written} rows written.")


@scrape_app.command("drekt")
def scrape_drekt() -> None:
    """Run the tertiary configured extraction pipeline."""
    seen, written = asyncio.run(run_source("drekt"))
    console.print(f"Tertiary scrape complete: {seen} rows seen, {written} rows written.")


@scrape_app.command("all")
def scrape_all() -> None:
    """Run all configured extraction pipelines sequentially."""
    async def _run() -> list[tuple[str, int, int]]:
        results = []
        for source in ("blast", "liquipedia", "drekt"):
            seen, written = await run_source(source)
            results.append((source, seen, written))
        return results

    results = asyncio.run(_run())
    table = Table(title="Scrape complete")
    table.add_column("Source")
    table.add_column("Seen", justify="right")
    table.add_column("Rows written", justify="right")
    for source, seen, written in results:
        table.add_row(source, str(seen), str(written))
    console.print(table)


@app.command("export")
def export(output_dir: Path | None = typer.Option(None, "--output-dir", "-o")) -> None:
    """Export SQLite tables to Parquet files."""
    async def _run() -> list[Path]:
        settings, storage = bootstrap()
        await storage.init()
        return await storage.export_parquet(output_dir or settings.export_dir)

    paths = asyncio.run(_run())
    for path in paths:
        console.print(str(path))


@app.command("status")
def status() -> None:
    """Show row counts for the scraper database."""
    async def _run() -> dict[str, int]:
        _, storage = bootstrap()
        await storage.init()
        return await storage.counts()

    counts = asyncio.run(_run())
    table = Table(title="Extraction pipeline status")
    table.add_column("Table")
    table.add_column("Rows", justify="right")
    for table_name, count in counts.items():
        table.add_row(table_name, str(count))
    console.print(table)


if __name__ == "__main__":
    app()
