"""Defensive Liquipedia Rocket League parsers."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from selectolax.parser import HTMLParser

from ..utils import dump_json, parse_money, safe_column_name


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def table_rows(html: str) -> list[dict[str, str]]:
    tree = HTMLParser(html)
    rows: list[dict[str, str]] = []
    for table in tree.css("table"):
        headers = [clean_text(th.text()) or f"col_{i}" for i, th in enumerate(table.css("tr th"), start=1)]
        for tr in table.css("tr"):
            cells = tr.css("td")
            if not cells:
                continue
            if not headers or len(headers) < len(cells):
                headers = [f"col_{i}" for i in range(1, len(cells) + 1)]
            row = {}
            for key, cell in zip(headers, cells):
                row[safe_column_name(key)] = clean_text(cell.text()) or ""
            if row:
                rows.append(row)
    return rows


def parse_tournament_page(html: str, page_name: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text((soup.select_one("h1.firstHeading") or soup.select_one("h1") or soup.new_tag("h1")).get_text(" "))
    infobox = {}
    for row in soup.select(".fo-nttax-infobox .infobox-cell-2, .infobox tr, .fo-nttax-infobox-wrapper"):
        text = clean_text(row.get_text(" "))
        if text and ":" in text:
            key, value = text.split(":", 1)
            infobox[safe_column_name(key)] = clean_text(value) or ""
    joined = " ".join(infobox.values())
    return {
        "source": "liquipedia",
        "source_id": page_name,
        "name": title or page_name.replace("_", " "),
        "rlcs_season": infer_season(title or page_name),
        "region": infer_region(title, joined, page_name),
        "start_date": infobox.get("date") or infobox.get("start_date"),
        "end_date": infobox.get("end_date"),
        "prize_pool_total": parse_money(infobox.get("prize_pool")),
        "prize_pool_raw": infobox.get("prize_pool"),
        "stage_format": infer_stage_format(html),
        "raw_json": dump_json({"page": page_name, "infobox": infobox}),
    }


def parse_rosters(html: str, team_name: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = table_rows(html)
    roster_rows: list[dict[str, Any]] = []
    staff_rows: list[dict[str, Any]] = []
    transfer_rows: list[dict[str, Any]] = []
    for row in rows:
        lower_keys = set(row)
        name = row.get("id") or row.get("player") or row.get("ign") or row.get("name")
        team = team_name or row.get("team") or row.get("new_team") or row.get("to")
        if not name:
            continue
        raw = dump_json(row)
        if {"from", "to"} & lower_keys or "old_team" in lower_keys or "new_team" in lower_keys:
            transfer_rows.append(
                {
                    "source": "liquipedia",
                    "entity_type": "transfer",
                    "entity_name": name,
                    "event_name": f"{row.get('from') or row.get('old_team', '')} -> {row.get('to') or row.get('new_team', '')}".strip(),
                    "date": row.get("date"),
                    "raw_json": raw,
                }
            )
        elif any("coach" in (v or "").lower() for v in row.values()) or "role" in row and "coach" in row.get("role", "").lower():
            staff_rows.append(
                {
                    "source": "liquipedia",
                    "team_name": team,
                    "name": name,
                    "role": row.get("role") or row.get("position") or "coach",
                    "nationality": row.get("nationality") or row.get("country"),
                    "join_date": row.get("join_date") or row.get("joined"),
                    "raw_json": raw,
                }
            )
        else:
            roster_rows.append(
                {
                    "source": "liquipedia",
                    "team_name": team,
                    "player_ign": name,
                    "real_name": row.get("name") if row.get("name") != name else row.get("real_name"),
                    "nationality": row.get("nationality") or row.get("country"),
                    "role": row.get("role") or "player",
                    "status": row.get("status") or "active",
                    "car": row.get("car"),
                    "join_date": row.get("join_date") or row.get("joined"),
                    "raw_json": raw,
                }
            )
    return roster_rows, staff_rows, transfer_rows


def parse_earnings(html: str, page_name: str) -> list[dict[str, Any]]:
    earnings: list[dict[str, Any]] = []
    for row in table_rows(html):
        amount = row.get("prize") or row.get("prize_money") or row.get("earnings") or row.get("amount")
        entity = row.get("player") or row.get("team") or row.get("name")
        if not amount or not entity:
            continue
        earnings.append(
            {
                "source": "liquipedia",
                "entity_type": "player" if row.get("player") else "team",
                "entity_name": entity,
                "event_name": row.get("event") or row.get("tournament") or page_name.replace("_", " "),
                "placement": row.get("place") or row.get("placement"),
                "amount": parse_money(amount),
                "date": row.get("date"),
                "raw_json": dump_json(row),
            }
        )
    return earnings


def infer_region(*values: str | None) -> str | None:
    text = " ".join(v or "" for v in values).upper()
    for region in ("APAC", "MENA", "SAM", "OCE", "SSA", "NA", "EU"):
        if re.search(rf"\b{region}\b", text):
            return region
    return None


def infer_season(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"20\d{2}|Season\s*\d+", value, re.I)
    return match.group(0) if match else None


def infer_stage_format(html: str) -> str | None:
    text = html.lower()
    formats = []
    for candidate in ("swiss", "double elimination", "single elimination", "round robin", "bracket"):
        if candidate in text:
            formats.append(candidate)
    return ", ".join(formats) if formats else None
