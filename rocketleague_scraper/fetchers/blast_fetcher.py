"""BLAST.tv Rocket League fetcher."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from loguru import logger
from tqdm.asyncio import tqdm

from ..config import Settings
from ..http_client import AsyncHttpClient
from ..parsers.blast_parser import (
    parse_games,
    parse_match,
    parse_player_stats_payload,
    parse_team,
    parse_tournament,
)
from ..pipeline import QueuePipeline
from ..storage import Storage


class BlastFetcher:
    def __init__(self, settings: Settings, storage: Storage):
        self.settings = settings
        self.storage = storage

    async def scrape(self) -> tuple[int, int]:
        run_id = await self.storage.run_started("blast")
        seen = written = 0
        try:
            async with AsyncHttpClient(
                timeout=self.settings.http_timeout_seconds,
                user_agent=self.settings.user_agent,
                rate_limit_seconds=self.settings.blast_rate_limit_seconds,
            ) as client:
                slugs = await self.discover_tournament_slugs(client)
                logger.info("BLAST tournament slugs: {}", ", ".join(slugs))

                pipeline = QueuePipeline[dict[str, Any]](
                    workers=min(self.settings.max_concurrency, 4),
                    handler=self._store_match_payload,
                )
                for slug in tqdm(slugs, desc="BLAST tournaments"):
                    payloads = await self.fetch_tournament_matches(client, slug)
                    for payload in payloads:
                        await pipeline.put(payload)
                await pipeline.run()
                seen = pipeline.result.seen
                written = pipeline.result.written
            await self.storage.run_finished(run_id, "ok", seen, written)
            return seen, written
        except Exception as exc:
            await self.storage.run_finished(run_id, "error", seen, written, str(exc))
            raise

    async def discover_tournament_slugs(self, client: AsyncHttpClient) -> list[str]:
        configured = list(self.settings.blast_tournament_slugs)
        try:
            response = await client.get(str(self.settings.blast_base_url).rstrip("/") + "/tournaments")
            found = sorted(set(re.findall(r"/rl/tournaments/([a-z0-9-]+)", response.text)))
            # Keep RLCS regional events and majors/worlds; ignore generic or duplicated nav links.
            filtered = [slug for slug in found if slug.startswith("rlcs-")]
            preferred = [slug for slug in filtered if "2026" in slug]
            limited = preferred[: self.settings.blast_max_discovered_tournaments]
            return sorted(set(configured + limited))
        except Exception as exc:
            logger.warning("BLAST tournament discovery failed; using configured slugs: {}", exc)
            return configured

    async def fetch_tournament_matches(self, client: AsyncHttpClient, slug: str) -> list[dict[str, Any]]:
        api_base = str(self.settings.blast_api_base_url).rstrip("/")
        url = f"{api_base}/v2/games/rl/tournaments/{slug}/matches"
        try:
            data = await client.get_json(url)
            if isinstance(data, list):
                return data
        except Exception as exc:
            logger.warning("BLAST matches API failed for {}: {}", slug, exc)
        html = await self.fetch_rendered_page(urljoin(str(self.settings.blast_base_url), f"tournaments/{slug}"))
        logger.warning("No JSON parsed from BLAST fallback HTML for {}; stored zero matches", slug)
        _ = html
        return []

    async def _store_match_payload(self, match: dict[str, Any]) -> int:
        tournament_id = await self.storage.upsert_tournament(parse_tournament(match))
        team_a = parse_team(match.get("teamA"))
        team_b = parse_team(match.get("teamB"))
        team_a_id = await self.storage.upsert_team(team_a) if team_a else None
        team_b_id = await self.storage.upsert_team(team_b) if team_b else None
        match_id = await self.storage.upsert_match(parse_match(match, tournament_id, team_a_id, team_b_id))
        game_ids: dict[str, int] = {}
        count = 1
        for game_row in parse_games(match, match_id):
            game_id = await self.storage.upsert_game(game_row)
            if game_row.get("source_id"):
                game_ids[str(game_row["source_id"])] = game_id
            count += 1

        stats_payload = await self.fetch_optional_stats_for_match(match) if self.settings.blast_probe_deep_stats else []
        if stats_payload:
            for stat_row, boost_row, pos_row in parse_player_stats_payload(stats_payload, game_ids):
                pgs_id = await self.storage.upsert_player_game_stats(stat_row)
                boost_row["player_game_stats_id"] = pgs_id
                pos_row["player_game_stats_id"] = pgs_id
                await self.storage.upsert_boost_stats(boost_row)
                await self.storage.upsert_positioning_stats(pos_row)
                count += 3
        return count

    async def fetch_optional_stats_for_match(self, match: dict[str, Any]) -> list[Any]:
        """Try known/likely BLAST stats endpoints without making them mandatory.

        Match and map APIs are public but not all events expose deep telemetry. Missing endpoints are
        normal, so 404s are swallowed and raw payloads are normalized when available.
        """
        api_base = str(self.settings.blast_api_base_url).rstrip("/")
        match_id = match.get("id") or match.get("uuid")
        candidates = [
            f"{api_base}/v1/statistics/rl/matches/{match_id}",
            f"{api_base}/v2/games/rl/matches/{match_id}",
        ]
        for game in match.get("maps") or []:
            game_id = game.get("id") or game.get("uuid")
            external = game.get("externalId")
            candidates.extend(
                [
                    f"{api_base}/v1/statistics/rl/maps/{game_id}",
                    f"{api_base}/v1/statistics/rl/games/{game_id}",
                    f"{api_base}/v1/statistics/rl/maps/{external}",
                ]
            )
        results: list[Any] = []
        async with httpx.AsyncClient(timeout=self.settings.http_timeout_seconds, follow_redirects=True) as client:
            for url in candidates:
                try:
                    response = await client.get(url, headers={"User-Agent": self.settings.user_agent})
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    results.append(response.json())
                    await asyncio.sleep(self.settings.blast_rate_limit_seconds)
                except Exception:
                    continue
        return results

    async def fetch_rendered_page(self, url: str) -> str:
        from cloakbrowser import launch_async

        browser = await launch_async(args=[f"--fingerprint={self.settings.blast_fingerprint_seed}"])
        try:
            page = await browser.new_page()
            await page.goto(url)
            await asyncio.sleep(3)
            return await page.content()
        finally:
            await browser.close()
