"""Liquipedia Rocket League fetcher."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urljoin

from loguru import logger
from tqdm.asyncio import tqdm

from ..config import Settings
from ..http_client import AsyncHttpClient
from ..parsers.liquipedia_parser import parse_earnings, parse_rosters, parse_tournament_page
from ..pipeline import QueuePipeline
from ..storage import Storage


class LiquipediaFetcher:
    def __init__(self, settings: Settings, storage: Storage):
        self.settings = settings
        self.storage = storage

    async def scrape(self) -> tuple[int, int]:
        run_id = await self.storage.run_started("liquipedia")
        seen = written = 0
        try:
            async with AsyncHttpClient(
                timeout=self.settings.http_timeout_seconds,
                user_agent=self.settings.user_agent,
                rate_limit_seconds=self.settings.liquipedia_rate_limit_seconds,
            ) as client:
                pages = await self.discover_pages(client)
                logger.info("Liquipedia pages queued: {}", len(pages))
                pipeline = QueuePipeline[tuple[str, str]](
                    workers=min(self.settings.max_concurrency, 3),
                    handler=self._store_page,
                )
                for page_name in tqdm(pages, desc="Liquipedia pages"):
                    html = await self.fetch_page(client, page_name)
                    await pipeline.put((page_name, html))
                await pipeline.run()
                seen = pipeline.result.seen
                written = pipeline.result.written
            await self.storage.run_finished(run_id, "ok", seen, written)
            return seen, written
        except Exception as exc:
            await self.storage.run_finished(run_id, "error", seen, written, str(exc))
            raise

    async def discover_pages(self, client: AsyncHttpClient) -> list[str]:
        seeds = list(self.settings.liquipedia_seed_pages)
        discovered: set[str] = set(seeds)
        for seed in seeds[:2]:
            try:
                html = (await client.get(self.page_url(seed))).text
            except Exception as exc:
                logger.warning("Could not discover Liquipedia links from {}: {}", seed, exc)
                continue
            for link in re.findall(r'href="/rocketleague/([^"]+)"', html):
                if any(token in link for token in ("Rocket_League_Championship_Series", "RLCS")):
                    if ":" not in link and "#" not in link:
                        discovered.add(link.split("?")[0])
        return sorted(discovered)

    async def fetch_page(self, client: AsyncHttpClient, page_name: str) -> str:
        return (await client.get(self.page_url(page_name))).text

    def page_url(self, page_name: str) -> str:
        base = str(self.settings.liquipedia_base_url).rstrip("/") + "/"
        return urljoin(base, quote(page_name, safe="/()_-"))

    async def _store_page(self, item: tuple[str, str]) -> int:
        page_name, html = item
        count = 0
        tournament = parse_tournament_page(html, page_name)
        tournament_id = await self.storage.upsert_tournament(tournament)
        count += 1

        roster_rows, staff_rows, transfer_rows = parse_rosters(html)
        count += await self.storage.insert_many("rosters", roster_rows)
        count += await self.storage.insert_many("staff", staff_rows)
        count += await self.storage.insert_many("earnings", transfer_rows)

        earnings = parse_earnings(html, page_name)
        for row in earnings:
            row["tournament_id"] = tournament_id
        count += await self.storage.insert_many("earnings", earnings)
        return count
