"""Parser for Drekt's community spreadsheet."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd

from ..utils import dump_json, safe_column_name


def parse_drekt_csv(csv_text: str, fetched_at: str) -> list[dict[str, Any]]:
    df = pd.read_csv(StringIO(csv_text), dtype=str, keep_default_na=False)
    rows: list[dict[str, Any]] = []
    original_columns = list(df.columns)
    normalized_columns = [safe_column_name(col, f"column_{idx}") for idx, col in enumerate(original_columns, start=1)]
    df.columns = normalized_columns
    for index, record in df.iterrows():
        raw = {original_columns[i]: record[normalized_columns[i]] for i in range(len(original_columns))}
        rows.append(
            {
                "spreadsheet_last_fetched": fetched_at,
                "row_index": int(index),
                "entity_type": infer_entity_type(record),
                "player_name": first_present(record, ("player", "player_name", "ign", "name")),
                "team_name": first_present(record, ("team", "team_name", "org", "organization")),
                "event_name": first_present(record, ("event", "tournament", "competition")),
                "rlcs_season": first_present(record, ("season", "rlcs_season")),
                "region": first_present(record, ("region",)),
                "stat_name": first_stat_name(record),
                "stat_value": first_stat_value(record),
                "source_columns_json": dump_json(original_columns),
                "row_json": dump_json(raw),
            }
        )
    return rows


def first_present(record: pd.Series, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if key in record and str(record[key]).strip():
            return str(record[key]).strip()
    return None


def infer_entity_type(record: pd.Series) -> str | None:
    if first_present(record, ("player", "player_name", "ign")):
        return "player"
    if first_present(record, ("team", "team_name", "org", "organization")):
        return "team"
    if first_present(record, ("event", "tournament", "competition")):
        return "event"
    return None


def first_stat_name(record: pd.Series) -> str | None:
    identity = {"player", "player_name", "ign", "name", "team", "team_name", "org", "organization", "event", "tournament", "season", "rlcs_season", "region"}
    for key, value in record.items():
        if key not in identity and str(value).strip():
            return key
    return None


def first_stat_value(record: pd.Series) -> str | None:
    stat = first_stat_name(record)
    if stat:
        value = str(record[stat]).strip()
        return value or None
    return None
