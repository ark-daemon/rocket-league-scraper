"""Small parsing helpers shared by fetchers and parsers."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def dump_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip().casefold()


def parse_int(value: object) -> int | None:
    if value in (None, "", "-"):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_float(value: object) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def parse_money(value: object) -> float | None:
    if value in (None, "", "-"):
        return None
    text = re.sub(r"[^0-9.-]", "", str(value))
    return parse_float(text)


def parse_duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
        return max(0.0, (end_dt - start_dt).total_seconds())
    except ValueError:
        return None


def composite_match_key(tournament: str | None, team_a: str | None, team_b: str | None, date: str | None) -> str:
    teams = sorted([normalize_name(team_a), normalize_name(team_b)])
    day = (date or "")[:10]
    raw = "|".join([normalize_name(tournament), *teams, day])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def safe_column_name(value: str, fallback: str = "column") -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
    return cleaned or fallback


def infer_region(*values: str | None) -> str | None:
    text = " ".join(v or "" for v in values).upper()
    for region in ("APAC", "MENA", "SAM", "OCE", "SSA", "NA", "EU"):
        if re.search(rf"\b{region}\b", text):
            return region
    return None
