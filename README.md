# Rocket League Esports Data Scraper

An async Python 3.11+ data extraction pipeline for Rocket League esports data. Built for resilient structural parsing, concurrent ingestion, and clean analytics-ready export.

## Overview

This tool provides a modular, configuration-driven architecture for automated extraction from structured esports data sources. It combines:

- **Asynchronous HTTP ingestion** with polite rate limiting, exponential back-off, and circuit-breaker-style retries.
- **Dynamic DOM parsing** that adapts to layout shifts and structural changes without hard-coding fragile selectors.
- **Resilient error handling** for transient network failures, anti-automation countermeasures, and malformed payloads.
- **Normalized SQLite staging** with atomic WAL transactions and concurrent write safety.
- **Efficient JSON/CSV pipeline** with sort-stable normalization and Parquet export for downstream analytics.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Config    │────▶│  Fetchers   │────▶│   Parsers   │
│   (.env)    │     │ (HTTP +     │     │ (DOM / JSON │
└─────────────┘     │  Browser)   │     │  / CSV)     │
                    └─────────────┘     └──────┬──────┘
                                               │
                    ┌─────────────┐     ┌──────▼──────┐
                    │   Export    │◄────│   SQLite    │
                    │  (Parquet)  │     │   (WAL)     │
                    └─────────────┘     └─────────────┘
```

## Features

- **Multi-Source Pipeline** — Ingests from tournament APIs, community wikis, and public spreadsheets through a unified interface.
- **Declarative Target Configuration** — All endpoints, seeds, and identity strings are externalized to environment variables. No hard-coded targets or credentials ship with the codebase.
- **Dual-Mode Fetching** — Prioritizes lightweight HTTP/JSON APIs and seamlessly falls back to browser-rendered content acquisition when dynamic pages are detected.
- **Anti-Fragile Parsing** — Parsers use structural inference and defensive normalization rather than brittle XPath, preserving raw payloads for backfill when schemas drift.
- **Concurrent Pipeline Workers** — Bounded async queues with graceful cancellation and back-pressure to respect upstream infrastructure.
- **Structured Logging & Observability** — JSON-serialized debug logs with automatic rotation, plus real-time CLI dashboards via Rich.

## Tech Stack

- Python 3.11+
- `httpx` — Async HTTP/2 client
- `aiosqlite` — Async SQLite with WAL mode
- `pandas` + `pyarrow` — In-memory transformation and Parquet serialization
- `typer` + `rich` — CLI interface and terminal UI
- `pydantic-settings` — Type-safe environment configuration
- `tenacity` — Resilient retry policies with exponential jitter

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

Copy the example configuration and populate your own targets:

```powershell
cp .env.example .env
# Edit .env with your endpoints, seeds, and user-agent string.
```

## Usage

List available commands:

```powershell
rl-scraper --help
```

Run all configured extraction pipelines:

```powershell
rl-scraper scrape all
```

Export the staging database to timestamped Parquet files:

```powershell
rl-scraper export
```

Check pipeline health and row counts:

```powershell
rl-scraper status
```

## Configuration

All runtime behavior is controlled via environment variables prefixed with `RL_`. See `.env.example` for the full schema, including:

- Source base URLs and API endpoints
- Discovery seeds (comma-separated)
- Rate-limit intervals and concurrency caps
- Request identity (`User-Agent`) and browser fingerprinting seeds
- Database, log, and export directory paths

## Data Pipeline

1. **Discovery** — Seed pages are crawled to discover tournament slugs, event links, or tab identifiers.
2. **Fetch** — Each resource is fetched with adaptive retries. Dynamic pages are rendered via a headless browser only when static APIs return non-structured responses.
3. **Parse** — Extracted entities (tournaments, teams, matches, rosters, earnings) are normalized into typed dictionaries.
4. **Persist** — SQLite acts as a transactional staging area with foreign-key constraints and WAL journaling for high-concurrency safety.
5. **Export** — Tables are dumped to sorted, compressed Parquet partitions suitable for Athena, Snowflake, or Pandas analysis.

## Compliance & Ethics

This tool is intended for lawful, ethical esports data research. Always:

- Respect `robots.txt` and Terms of Service of target domains.
- Keep rate limits conservative (default ≤ 2 req/s).
- Use an accurate, descriptive `User-Agent` string.
- Store credentials and target endpoints in `.env` — never commit them.

## License

MIT
