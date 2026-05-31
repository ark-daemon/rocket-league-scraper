"""SQLite persistence and Parquet export."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import aiosqlite
import pandas as pd
from loguru import logger

from .utils import dump_json, utc_now_iso


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT,
    name TEXT NOT NULL,
    rlcs_season TEXT,
    region TEXT,
    start_date TEXT,
    end_date TEXT,
    prize_pool_total REAL,
    prize_pool_raw TEXT,
    location TEXT,
    stage_format TEXT,
    world_championship_qualification_status TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id),
    UNIQUE(source, name, rlcs_season, region)
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT,
    name TEXT NOT NULL,
    short_name TEXT,
    region TEXT,
    nationality TEXT,
    standings_points INTEGER,
    wins INTEGER,
    losses INTEGER,
    overtime_losses INTEGER,
    goal_differential INTEGER,
    recent_form_5 TEXT,
    recent_form_10 TEXT,
    home_region_record TEXT,
    international_record TEXT,
    bo3_win_rate REAL,
    bo5_win_rate REAL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id),
    UNIQUE(source, name)
);

CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT,
    ign TEXT NOT NULL,
    real_name TEXT,
    nationality TEXT,
    car TEXT,
    settings_json TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id),
    UNIQUE(source, ign)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT,
    composite_key TEXT NOT NULL,
    tournament_id INTEGER,
    tournament_name TEXT,
    event_name TEXT,
    rlcs_season TEXT,
    region TEXT,
    stage TEXT,
    series_format TEXT,
    scheduled_at TEXT,
    team_a_id INTEGER,
    team_b_id INTEGER,
    team_a_name TEXT,
    team_b_name TEXT,
    team_a_score INTEGER,
    team_b_score INTEGER,
    winner_team_id INTEGER,
    winner_name TEXT,
    h2h_all_time TEXT,
    h2h_season TEXT,
    game_version TEXT,
    is_live INTEGER,
    is_completed INTEGER,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(tournament_id) REFERENCES tournaments(id),
    FOREIGN KEY(team_a_id) REFERENCES teams(id),
    FOREIGN KEY(team_b_id) REFERENCES teams(id),
    UNIQUE(source, source_id),
    UNIQUE(composite_key)
);

CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT,
    game_number INTEGER,
    map_name TEXT,
    scheduled_at TEXT,
    started_at TEXT,
    ended_at TEXT,
    duration_seconds REAL,
    team_a_score INTEGER,
    team_b_score INTEGER,
    winner_team_id INTEGER,
    winner_name TEXT,
    overtime_flag INTEGER,
    overtime_duration_seconds REAL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(match_id) REFERENCES matches(id) ON DELETE CASCADE,
    UNIQUE(source, source_id),
    UNIQUE(match_id, game_number)
);

CREATE TABLE IF NOT EXISTS player_game_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    player_id INTEGER,
    team_id INTEGER,
    source TEXT NOT NULL,
    source_id TEXT,
    player_name TEXT,
    team_name TEXT,
    score INTEGER,
    goals INTEGER,
    assists INTEGER,
    saves INTEGER,
    shots INTEGER,
    shot_percentage REAL,
    demos_inflicted INTEGER,
    demos_taken INTEGER,
    mvp_award INTEGER,
    average_speed REAL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY(player_id) REFERENCES players(id),
    FOREIGN KEY(team_id) REFERENCES teams(id),
    UNIQUE(game_id, source, source_id),
    UNIQUE(game_id, player_name, team_name)
);

CREATE TABLE IF NOT EXISTS boost_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_game_stats_id INTEGER NOT NULL,
    boost_per_minute REAL,
    time_zero_boost REAL,
    time_full_boost REAL,
    average_boost_amount REAL,
    boost_collected_small_pads REAL,
    boost_collected_large_pads REAL,
    boost_stolen_opponent_pads REAL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(player_game_stats_id) REFERENCES player_game_stats(id) ON DELETE CASCADE,
    UNIQUE(player_game_stats_id)
);

CREATE TABLE IF NOT EXISTS positioning_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_game_stats_id INTEGER NOT NULL,
    time_attacking_third REAL,
    time_neutral_third REAL,
    time_defensive_third REAL,
    time_front_of_ball REAL,
    time_behind_ball REAL,
    time_supersonic_speed REAL,
    time_on_ground REAL,
    time_low_air REAL,
    time_high_air REAL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(player_game_stats_id) REFERENCES player_game_stats(id) ON DELETE CASCADE,
    UNIQUE(player_game_stats_id)
);

CREATE TABLE IF NOT EXISTS rosters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    team_id INTEGER,
    player_id INTEGER,
    team_name TEXT,
    player_ign TEXT,
    real_name TEXT,
    nationality TEXT,
    role TEXT,
    status TEXT,
    car TEXT,
    settings_json TEXT,
    join_date TEXT,
    leave_date TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(team_id) REFERENCES teams(id),
    FOREIGN KEY(player_id) REFERENCES players(id),
    UNIQUE(source, team_name, player_ign, role, join_date)
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    team_id INTEGER,
    team_name TEXT,
    name TEXT NOT NULL,
    role TEXT,
    nationality TEXT,
    join_date TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(team_id) REFERENCES teams(id),
    UNIQUE(source, team_name, name, role)
);

CREATE TABLE IF NOT EXISTS earnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    player_id INTEGER,
    team_id INTEGER,
    event_name TEXT,
    tournament_id INTEGER,
    placement TEXT,
    amount REAL,
    currency TEXT DEFAULT 'USD',
    date TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(player_id) REFERENCES players(id),
    FOREIGN KEY(team_id) REFERENCES teams(id),
    FOREIGN KEY(tournament_id) REFERENCES tournaments(id),
    UNIQUE(source, entity_type, entity_name, event_name, placement, date)
);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    items_seen INTEGER DEFAULT 0,
    items_written INTEGER DEFAULT 0,
    error TEXT
);
"""


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            await db.executescript(SCHEMA)
            await db.commit()
        logger.debug("SQLite schema ready at {}", self.db_path)

    async def run_started(self, source: str) -> int:
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            cur = await db.execute(
                "INSERT INTO scrape_runs(source, started_at, status) VALUES (?, ?, ?)",
                (source, utc_now_iso(), "running"),
            )
            await db.commit()
            return int(cur.lastrowid)

    async def run_finished(
        self, run_id: int, status: str, items_seen: int, items_written: int, error: str | None = None
    ) -> None:
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            await db.execute(
                """
                UPDATE scrape_runs
                SET finished_at=?, status=?, items_seen=?, items_written=?, error=?
                WHERE id=?
                """,
                (utc_now_iso(), status, items_seen, items_written, error, run_id),
            )
            await db.commit()

    async def upsert_team(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id(
            "teams",
            row,
            ["source", "source_id"],
            fallback_where="source=? AND name=?",
            fallback_params=(row.get("source"), row.get("name")),
        )

    async def upsert_player(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id(
            "players",
            row,
            ["source", "source_id"],
            fallback_where="source=? AND ign=?",
            fallback_params=(row.get("source"), row.get("ign")),
        )

    async def upsert_tournament(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id(
            "tournaments",
            row,
            ["source", "source_id"],
            fallback_where="source=? AND name=? AND COALESCE(rlcs_season, '')=COALESCE(?, '') AND COALESCE(region, '')=COALESCE(?, '')",
            fallback_params=(row.get("source"), row.get("name"), row.get("rlcs_season"), row.get("region")),
        )

    async def upsert_match(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id(
            "matches",
            row,
            ["source", "source_id"],
            fallback_where="composite_key=?",
            fallback_params=(row.get("composite_key"),),
        )

    async def upsert_game(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id(
            "games",
            row,
            ["source", "source_id"],
            fallback_where="match_id=? AND game_number=?",
            fallback_params=(row.get("match_id"), row.get("game_number")),
        )

    async def upsert_player_game_stats(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id(
            "player_game_stats",
            row,
            ["game_id", "source", "source_id"],
            fallback_where="game_id=? AND player_name=? AND COALESCE(team_name, '')=COALESCE(?, '')",
            fallback_params=(row.get("game_id"), row.get("player_name"), row.get("team_name")),
        )

    async def upsert_boost_stats(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id("boost_stats", row, ["player_game_stats_id"])

    async def upsert_positioning_stats(self, row: dict[str, Any]) -> int:
        return await self._upsert_returning_id("positioning_stats", row, ["player_game_stats_id"])

    async def insert_many(self, table: str, rows: Iterable[dict[str, Any]]) -> int:
        cleaned: list[dict[str, Any]] = []
        for row in rows:
            clean = {k: self._normalize_value(v) for k, v in row.items() if v is not None}
            if clean:
                cleaned.append(clean)
        if not cleaned:
            return 0
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for clean in cleaned:
            key = tuple(sorted(clean))
            grouped.setdefault(key, []).append(clean)
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            total = 0
            for columns_tuple, group in grouped.items():
                columns = list(columns_tuple)
                placeholders = ", ".join("?" for _ in columns)
                sql = f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
                values = [tuple(r[c] for c in columns) for r in group]
                await db.executemany(sql, values)
                total += len(group)
            await db.commit()
            return total

    async def counts(self) -> dict[str, int]:
        tables = [
            "tournaments", "matches", "games", "player_game_stats", "boost_stats",
            "positioning_stats", "teams", "players", "rosters", "staff", "earnings", "drekt_stats",
        ]
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            result = {}
            for table in tables:
                cur = await db.execute(f"SELECT COUNT(*) FROM {table}")
                result[table] = int((await cur.fetchone())[0])
            return result

    async def export_parquet(self, export_dir: Path) -> list[Path]:
        export_dir.mkdir(parents=True, exist_ok=True)
        tables = [
            "matches", "games", "player_game_stats", "boost_stats", "positioning_stats",
            "teams", "players", "rosters", "staff", "tournaments", "earnings", "drekt_stats",
        ]
        written: list[Path] = []
        db_conn = self._sync_connection()
        try:
            for table in tables:
                df = pd.read_sql_query(f"SELECT * FROM {table}", db_conn)
                out = export_dir / f"{table}.parquet"
                df.to_parquet(out, index=False)
                written.append(out)
        finally:
            db_conn.close()
        return written

    async def _upsert_returning_id(
        self,
        table: str,
        row: dict[str, Any],
        conflict_columns: list[str],
        fallback_where: str | None = None,
        fallback_params: tuple[Any, ...] = (),
    ) -> int:
        clean = {k: self._normalize_value(v) for k, v in row.items() if v is not None}
        clean["updated_at"] = utc_now_iso()
        columns = list(clean)
        assignments = ", ".join(
            f"{col}=excluded.{col}" for col in columns if col not in conflict_columns and col != "created_at"
        )
        placeholders = ", ".join("?" for _ in columns)
        conflict = ", ".join(conflict_columns)
        sql = (
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {assignments} RETURNING id"
        )
        try:
            async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
                cur = await db.execute(sql, tuple(clean[c] for c in columns))
                row_id = (await cur.fetchone())[0]
                await db.commit()
                return int(row_id)
        except aiosqlite.IntegrityError:
            if not fallback_where:
                raise
            async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
                set_clause = ", ".join(f"{col}=?" for col in columns if col != "created_at")
                values = [clean[col] for col in columns if col != "created_at"]
                await db.execute(
                    f"UPDATE {table} SET {set_clause} WHERE {fallback_where}",
                    (*values, *fallback_params),
                )
                cur = await db.execute(f"SELECT id FROM {table} WHERE {fallback_where}", fallback_params)
                found = await cur.fetchone()
                await db.commit()
                if not found:
                    raise
                return int(found[0])

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if isinstance(value, (dict, list, tuple)):
            return dump_json(value)
        return value

    def _sync_connection(self):
        import sqlite3
        return sqlite3.connect(self.db_path)
