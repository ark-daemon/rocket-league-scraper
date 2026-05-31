"""Drekt community spreadsheet fetcher."""

from __future__ import annotations

import asyncio
import io
import random
import re

import aiosqlite
import pandas as pd
from loguru import logger
from tqdm import tqdm

from ..config import Settings
from ..http_client import AsyncHttpClient
from ..storage import Storage
from ..utils import utc_now_iso


class DrektFetcher:
    def __init__(self, settings: Settings, storage: Storage):
        self.settings = settings
        self.storage = storage
        self.visited: set[str] = set()

    async def _init_db(self) -> None:
        async with aiosqlite.connect(self.storage.db_path, timeout=30.0) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS drekt_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sheet_id TEXT,
                    gid TEXT,
                    tab_name TEXT,
                    context_path TEXT,
                    data_json TEXT,
                    row_count INTEGER,
                    fetched_at TEXT,
                    UNIQUE(sheet_id, gid)
                )
            """)
            await db.commit()

    async def scrape(self) -> tuple[int, int]:
        run_id = await self.storage.run_started("drekt")
        
        await self._init_db()

        # Seed the queue with sheet IDs from config URLs
        queue_sheet_ids = set()
        for url in self.settings.drekt_csv_urls:
            match = re.search(r'docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)', str(url))
            if match:
                queue_sheet_ids.add(match.group(1))

        queue: list[tuple[str, str, str, str]] = [] # sheet_id, gid, tab_name, context_path
        
        total_spreadsheets_discovered = 0
        total_tabs_discovered = 0
        total_tabs_fetched = 0
        total_data_rows_stored = 0
        failed_or_skipped = []
        
        try:
            # We don't set a rate_limit_seconds because we will manually jitter sleep
            async with AsyncHttpClient(
                timeout=self.settings.http_timeout_seconds,
                user_agent=self.settings.user_agent,
                rate_limit_seconds=0, 
            ) as client:

                async def discover_tabs(sheet_id: str, context_path: str):
                    nonlocal total_spreadsheets_discovered, total_tabs_discovered
                    logger.debug(f"Discovering tabs for spreadsheet {sheet_id}")
                    try:
                        resp = await client.get(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
                        html = resp.text
                        
                        # Use regex to find (gid, tab_name) pairs
                        tabs = re.findall(r'\[[0-9]+,[0-9]+,\\?\"([0-9]+)\\?\",\[\{\\?\"1\\?\":\[\[[0-9]+,[0-9]+,\\?\"([^"]+?)\\?\"', html)
                        if not tabs:
                            # Fallback regex without escaped quotes, just in case Google changes something
                            tabs = re.findall(r'\[[0-9]+,[0-9]+,\x22([0-9]+)\x22,\[\{\x221\x22:\[\[[0-9]+,[0-9]+,\x22([^\x22]+?)\x22', html)
                        
                        if tabs:
                            total_spreadsheets_discovered += 1
                            total_tabs_discovered += len(set(tabs))
                            for gid, tab_name in set(tabs):
                                key = f"{sheet_id}:{gid}"
                                if key not in self.visited:
                                    queue.append((sheet_id, gid, tab_name, context_path))
                        else:
                            failed_or_skipped.append(f"No tabs found for sheet {sheet_id}")
                    except Exception as e:
                        failed_or_skipped.append(f"Error discovering tabs for {sheet_id}: {e}")

                # Initial discovery for all seeded IDs
                for sheet_id in queue_sheet_ids:
                    await discover_tabs(sheet_id, "Hub")
                
                # Setup tqdm progress bar
                pbar = tqdm(total=len(queue), desc="Crawling Drekt")
                
                while queue:
                    sheet_id, gid, tab_name, context_path = queue.pop(0)
                    key = f"{sheet_id}:{gid}"
                    
                    if key in self.visited:
                        pbar.update(1)
                        continue
                        
                    self.visited.add(key)
                    total_tabs_fetched += 1
                    
                    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
                    
                    try:
                        # Random delay to respect Google's limits
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                        resp = await client.get(csv_url)
                        csv_text = resp.text
                        
                        # Find other sheets recursively
                        new_sheet_ids = set(re.findall(r'docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)', csv_text))
                        for new_sid in new_sheet_ids:
                            # Random delay before discovering tabs of new sheet
                            await asyncio.sleep(random.uniform(1.0, 3.0))
                            await discover_tabs(new_sid, f"{context_path} > {tab_name}")
                            pbar.total = len(queue) + pbar.n
                            pbar.refresh()
                            
                        # Parse with pandas
                        try:
                            df = pd.read_csv(io.StringIO(csv_text), dtype=str, keep_default_na=False)
                            is_data_tab = False
                            row_count = len(df)
                            data_json = ""
                            
                            if row_count > 0:
                                is_data_tab = True
                                data_json = df.to_json(orient='records')
                                total_data_rows_stored += row_count
                                
                                fetched_at = utc_now_iso()
                                async with aiosqlite.connect(self.storage.db_path, timeout=30.0) as db:
                                    await db.execute(
                                        """
                                        INSERT OR REPLACE INTO drekt_stats 
                                        (sheet_id, gid, tab_name, context_path, data_json, row_count, fetched_at)
                                        VALUES (?, ?, ?, ?, ?, ?, ?)
                                        """,
                                        (sheet_id, gid, tab_name, context_path, data_json, row_count, fetched_at)
                                    )
                                    await db.commit()
                                
                            logger.info(f"Fetched tab {tab_name} ({csv_url}): is_data={is_data_tab}, index_links={len(new_sheet_ids)}, rows={row_count}")
                                
                        except Exception as e:
                            logger.error(f"Error parsing CSV for {csv_url}: {e}")
                            failed_or_skipped.append(f"CSV Parse Error {csv_url}: {e}")
                            
                    except Exception as e:
                        logger.error(f"Error fetching {csv_url}: {e}")
                        failed_or_skipped.append(f"Fetch Error {csv_url}: {e}")
                        
                    pbar.update(1)
                
                pbar.close()

            logger.info("Drekt Crawl Summary:")
            logger.info(f"Total Spreadsheets Discovered: {total_spreadsheets_discovered}")
            logger.info(f"Total Tabs Discovered: {total_tabs_discovered}")
            logger.info(f"Total Tabs Fetched: {total_tabs_fetched}")
            logger.info(f"Total Data Rows Stored: {total_data_rows_stored}")
            if failed_or_skipped:
                logger.info(f"Failed/Skipped: {len(failed_or_skipped)} items")
                for f in failed_or_skipped:
                    logger.debug(f)
                    
            await self.storage.run_finished(run_id, "ok", total_tabs_fetched, total_data_rows_stored)
            return total_tabs_fetched, total_data_rows_stored

        except Exception as exc:
            await self.storage.run_finished(run_id, "error", total_tabs_fetched, total_data_rows_stored, str(exc))
            raise
