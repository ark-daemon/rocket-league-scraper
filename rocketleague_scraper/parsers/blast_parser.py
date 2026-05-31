"""Parsers for BLAST Rocket League API payloads."""

from __future__ import annotations

from typing import Any

from ..reconciliation import build_match_key
from ..utils import dump_json, parse_duration_seconds, parse_money


def infer_region(*values: str | None) -> str | None:
    text = " ".join(v or "" for v in values).upper()
    for region in ("APAC", "MENA", "SAM", "OCE", "SSA", "NA", "EU"):
        if region in text:
            return region
    return None


def parse_team(team: dict[str, Any] | None) -> dict[str, Any] | None:
    if not team:
        return None
    return {
        "source": "blast",
        "source_id": team.get("id") or team.get("uuid"),
        "name": team.get("name") or team.get("displayName"),
        "short_name": team.get("shortName") or team.get("shorthand"),
        "nationality": team.get("nationality") or team.get("location"),
        "region": infer_region(team.get("nationality"), team.get("location")),
        "raw_json": dump_json(team),
    }


def parse_tournament(match_or_tournament: dict[str, Any]) -> dict[str, Any]:
    tournament = match_or_tournament.get("tournament", match_or_tournament)
    name = tournament.get("name") or tournament.get("parentTournamentName") or "Unknown BLAST Tournament"
    season = None
    circuit = match_or_tournament.get("circuit") or {}
    if isinstance(circuit, dict):
        season = circuit.get("name") or circuit.get("id")
    return {
        "source": "blast",
        "source_id": tournament.get("id") or tournament.get("tournamentUuid"),
        "name": name,
        "rlcs_season": season or tournament.get("circuitName"),
        "region": infer_region(name, tournament.get("region")),
        "start_date": tournament.get("startDate"),
        "end_date": tournament.get("endDate"),
        "prize_pool_total": parse_money(tournament.get("prizePool")),
        "prize_pool_raw": tournament.get("prizePool"),
        "location": tournament.get("location"),
        "stage_format": tournament.get("format") or match_or_tournament.get("parentTournamentFormat"),
        "raw_json": dump_json(tournament),
    }


def parse_match(match: dict[str, Any], tournament_id: int | None, team_a_id: int | None, team_b_id: int | None) -> dict[str, Any]:
    tournament = match.get("tournament") or {}
    stage = match.get("stage") or {}
    team_a = match.get("teamA") or {}
    team_b = match.get("teamB") or {}
    scheduled_at = match.get("scheduledAt") or match.get("timeOfSeries")
    row = {
        "source": "blast",
        "source_id": match.get("id") or match.get("uuid"),
        "tournament_id": tournament_id,
        "tournament_name": tournament.get("name") or match.get("parentTournamentName"),
        "event_name": tournament.get("name") or match.get("parentTournamentName"),
        "rlcs_season": (match.get("circuit") or {}).get("name") or match.get("circuitName"),
        "region": infer_region(tournament.get("name"), stage.get("name"), team_a.get("nationality"), team_b.get("nationality")),
        "stage": stage.get("name") or match.get("tournamentName") or match.get("name"),
        "series_format": match.get("type"),
        "scheduled_at": scheduled_at,
        "team_a_id": team_a_id,
        "team_b_id": team_b_id,
        "team_a_name": team_a.get("name"),
        "team_b_name": team_b.get("name"),
        "team_a_score": match.get("teamAScore"),
        "team_b_score": match.get("teamBScore"),
        "is_live": int(bool(match.get("isLive"))) if "isLive" in match else None,
        "is_completed": int(bool(match.get("isCompleted"))) if "isCompleted" in match else None,
        "raw_json": dump_json(match),
    }
    if row["team_a_score"] is not None and row["team_b_score"] is not None:
        if row["team_a_score"] > row["team_b_score"]:
            row["winner_team_id"] = team_a_id
            row["winner_name"] = row["team_a_name"]
        elif row["team_b_score"] > row["team_a_score"]:
            row["winner_team_id"] = team_b_id
            row["winner_name"] = row["team_b_name"]
    row["composite_key"] = build_match_key(row)
    return row


def parse_games(match: dict[str, Any], match_id: int) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    for index, game in enumerate(match.get("maps") or [], start=1):
        started = game.get("startedAt") or game.get("actualStartTime")
        ended = game.get("endedAt") or game.get("matchEndedTime")
        team_a_score = game.get("teamAScore")
        team_b_score = game.get("teamBScore")
        row = {
            "match_id": match_id,
            "source": "blast",
            "source_id": game.get("id") or game.get("uuid"),
            "game_number": index,
            "map_name": game.get("name"),
            "scheduled_at": game.get("scheduledAt") or game.get("scheduledStartTime"),
            "started_at": started,
            "ended_at": ended,
            "duration_seconds": parse_duration_seconds(started, ended),
            "team_a_score": team_a_score,
            "team_b_score": team_b_score,
            "overtime_flag": int(bool(game.get("overtime") or game.get("isOvertime"))) if ("overtime" in game or "isOvertime" in game) else None,
            "overtime_duration_seconds": game.get("overtimeDurationSeconds") or game.get("overtimeDuration"),
            "raw_json": dump_json(game),
        }
        team_a = match.get("teamA") or {}
        team_b = match.get("teamB") or {}
        if team_a_score is not None and team_b_score is not None:
            if team_a_score > team_b_score:
                row["winner_name"] = team_a.get("name")
            elif team_b_score > team_a_score:
                row["winner_name"] = team_b.get("name")
        games.append(row)
    return games


STAT_ALIASES = {
    "score": "score",
    "goals": "goals",
    "assists": "assists",
    "saves": "saves",
    "shots": "shots",
    "shotPercentage": "shot_percentage",
    "shot_percentage": "shot_percentage",
    "demosInflicted": "demos_inflicted",
    "demosTaken": "demos_taken",
    "mvp": "mvp_award",
    "isMvp": "mvp_award",
    "averageSpeed": "average_speed",
}

BOOST_ALIASES = {
    "boostPerMinute": "boost_per_minute",
    "timeZeroBoost": "time_zero_boost",
    "timeWithZeroBoost": "time_zero_boost",
    "timeFullBoost": "time_full_boost",
    "timeWithFullBoost": "time_full_boost",
    "averageBoostAmount": "average_boost_amount",
    "boostCollectedSmallPads": "boost_collected_small_pads",
    "boostCollectedLargePads": "boost_collected_large_pads",
    "boostStolenOpponentPads": "boost_stolen_opponent_pads",
}

POSITION_ALIASES = {
    "timeAttackingThird": "time_attacking_third",
    "timeNeutralThird": "time_neutral_third",
    "timeDefensiveThird": "time_defensive_third",
    "timeFrontOfBall": "time_front_of_ball",
    "timeBehindBall": "time_behind_ball",
    "timeSupersonicSpeed": "time_supersonic_speed",
    "timeOnGround": "time_on_ground",
    "timeLowAir": "time_low_air",
    "timeHighAir": "time_high_air",
}


def parse_player_stats_payload(payload: Any, game_id_lookup: dict[str, int]) -> list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]]:
    """Normalize optional BLAST player-stat payloads if an endpoint exposes them.

    BLAST changes these response shapes, so this walks common containers and keeps raw JSON.
    """
    candidates: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if any(key in value for key in ("player", "playerId", "playerName")) and any(key in value for key in STAT_ALIASES):
                candidates.append(value)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for item in candidates:
        map_id = item.get("mapId") or item.get("gameId") or item.get("matchId")
        game_id = game_id_lookup.get(str(map_id))
        if not game_id:
            continue
        player = item.get("player") if isinstance(item.get("player"), dict) else {}
        team = item.get("team") if isinstance(item.get("team"), dict) else {}
        base = {
            "game_id": game_id,
            "source": "blast",
            "source_id": item.get("id") or item.get("playerGameStatsId"),
            "player_name": item.get("playerName") or player.get("name") or player.get("nickname"),
            "team_name": item.get("teamName") or team.get("name"),
            "raw_json": dump_json(item),
        }
        for source_key, target_key in STAT_ALIASES.items():
            if source_key in item:
                base[target_key] = item.get(source_key)
        boost = {"raw_json": dump_json(item)}
        for source_key, target_key in BOOST_ALIASES.items():
            if source_key in item:
                boost[target_key] = item.get(source_key)
        pos = {"raw_json": dump_json(item)}
        for source_key, target_key in POSITION_ALIASES.items():
            if source_key in item:
                pos[target_key] = item.get(source_key)
        rows.append((base, boost, pos))
    return rows
