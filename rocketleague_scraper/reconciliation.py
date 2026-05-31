"""Cross-source reconciliation helpers."""

from __future__ import annotations

from .utils import composite_match_key


def build_match_key(row: dict) -> str:
    return composite_match_key(
        row.get("tournament_name") or row.get("event_name"),
        row.get("team_a_name"),
        row.get("team_b_name"),
        row.get("scheduled_at"),
    )
