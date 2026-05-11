"""
MFL Moneyball Sync
Fetches all players + their full competition history,
aggregates everything into career totals, upserts one row per player.
"""

import os, time, requests
from supabase import create_client

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL     = "https://z519wdyajg.execute-api.us-east-1.amazonaws.com/prod"
ORIGIN       = "https://app.playmfl.com"
PLAYER_LIMIT = 1000
RATE_DELAY   = 0.3  # seconds between requests

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]
REFRESH_TOKEN = os.environ["MFL_REFRESH_TOKEN"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_access_token(refresh_token: str) -> str:
    print("Refreshing access token...")
    resp = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refreshToken": refresh_token},
        headers={"origin": ORIGIN},
        timeout=10
    )
    resp.raise_for_status()
    token = resp.json()["access"]["token"]
    print("  Access token obtained.")
    return token

def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "origin": ORIGIN}

# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch_players(token: str) -> list:
    print(f"Fetching players (limit={PLAYER_LIMIT})...")
    resp = requests.get(
        f"{BASE_URL}/players",
        params={"limit": PLAYER_LIMIT},
        headers=headers(token),
        timeout=15
    )
    resp.raise_for_status()
    players = resp.json()
    print(f"  Got {len(players)} players")
    return players

def fetch_competitions(player_id: int, token: str) -> list:
    resp = requests.get(
        f"{BASE_URL}/players/{player_id}/competitions",
        headers=headers(token),
        timeout=10
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()

# ── Aggregate ─────────────────────────────────────────────────────────────────
def aggregate(player: dict, competition_entries: list) -> dict:
    """Combine player metadata + all competition entries into one flat row."""
    m     = player["metadata"]
    owner = player.get("ownedBy") or {}

    totals = {
        "total_matches":         0,
        "total_minutes":         0,
        "total_goals":           0,
        "total_assists":         0,
        "total_shots":           0,
        "total_shots_on_target": 0,
        "total_xg":              0,
        "total_passes":          0,
        "total_passes_accurate": 0,
        "total_chances_created": 0,
        "total_dribbling":       0,
        "total_def_duels_won":   0,
        "total_clearances":      0,
        "total_yellow_cards":    0,
        "total_red_cards":       0,
        "total_wins":            0,
        "total_draws":           0,
        "total_losses":          0,
        "total_saves":           0,
        "total_goals_conceded":  0,
        "total_rating_sum":      0,
    }

    seen_seasons      = set()
    seen_competitions = set()

    for entry in competition_entries:
        s    = entry.get("stats", {})
        comp = entry.get("competition", {})
        season = comp.get("season", {})

        totals["total_matches"]         += s.get("nbMatches", 0)
        totals["total_minutes"]         += s.get("time", 0) // 60
        totals["total_goals"]           += s.get("goals", 0)
        totals["total_assists"]         += s.get("assists", 0)
        totals["total_shots"]           += s.get("shots", 0)
        totals["total_shots_on_target"] += s.get("shotsOnTarget", 0)
        totals["total_xg"]              += s.get("xG", 0)
        totals["total_passes"]          += s.get("passes", 0)
        totals["total_passes_accurate"] += s.get("passesAccurate", 0)
        totals["total_chances_created"] += s.get("chancesCreated", 0)
        totals["total_dribbling"]       += s.get("dribblingSuccess", 0)
        totals["total_def_duels_won"]   += s.get("defensiveDuelsWon", 0)
        totals["total_clearances"]      += s.get("clearances", 0)
        totals["total_yellow_cards"]    += s.get("yellowCards", 0)
        totals["total_red_cards"]       += s.get("redCards", 0)
        totals["total_wins"]            += s.get("wins", 0)
        totals["total_draws"]           += s.get("draws", 0)
        totals["total_losses"]          += s.get("losses", 0)
        totals["total_saves"]           += s.get("saves", 0)
        totals["total_goals_conceded"]  += s.get("goalsConceded", 0)
        totals["total_rating_sum"]      += s.get("rating", 0)

        seen_seasons.add(season.get("name", "unknown"))
        seen_competitions.add(comp.get("id"))

    mins = totals["total_minutes"]
    p90  = mins / 90 if mins > 0 else None

    def per90(val):
        return round(val / p90, 2) if p90 else None

    def pct(num, denom):
        return round(num / denom * 100, 1) if denom > 0 else None

    return {
        # Identity
        "id":               player["id"],
        "first_name":       m.get("firstName"),
        "last_name":        m.get("lastName"),

        # Attributes
        "overall":          m.get("overall"),
        "age":              m.get("age"),
        "height":           m.get("height"),
        "positions":        m.get("positions", []),
        "primary_position": (m.get("positions") or [None])[0],
        "nationalities":    m.get("nationalities", []),
        "preferred_foot":   m.get("preferredFoot"),
        "pace":             m.get("pace"),
        "shooting":         m.get("shooting"),
        "passing":          m.get("passing"),
        "dribbling":        m.get("dribbling"),
        "defense":          m.get("defense"),
        "physical":         m.get("physical"),
        "goalkeeping":      m.get("goalkeeping"),

        # Ownership
        "owner_wallet":     owner.get("walletAddress"),
        "owner_name":       owner.get("name"),
        "energy":           player.get("energy"),
        "has_pre_contract": player.get("hasPreContract", False),
        "offer_status":     player.get("offerStatus", 0),

        # Career totals
        **totals,

        # Per-90
        "goals_p90":     per90(totals["total_goals"]),
        "assists_p90":   per90(totals["total_assists"]),
        "xg_p90":        per90(totals["total_xg"]),
        "passes_p90":    per90(totals["total_passes"]),
        "chances_p90":   per90(totals["total_chances_created"]),
        "def_duels_p90": per90(totals["total_def_duels_won"]),
        "shots_p90":     per90(totals["total_shots"]),

        # Percentages
        "pass_acc_pct": pct(totals["total_passes_accurate"], totals["total_passes"]),
        "shot_acc_pct": pct(totals["total_shots_on_target"], totals["total_shots"]),
        "win_pct":      pct(totals["total_wins"], totals["total_matches"]),
        "avg_rating":   round(totals["total_rating_sum"] / totals["total_matches"], 2)
                        if totals["total_matches"] > 0 else None,

        # Context
        "seasons_played":      len(seen_seasons),
        "competitions_played": len(seen_competitions),
    }

# ── Upsert ────────────────────────────────────────────────────────────────────
def upsert_batch(rows: list):
    for i in range(0, len(rows), 200):
        chunk = rows[i:i+200]
        supabase.table("mfl_players").upsert(chunk, on_conflict="id").execute()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    access_token = get_access_token(REFRESH_TOKEN)
    players      = fetch_players(access_token)

    print(f"\nAggregating career stats for {len(players)} players...")
    rows   = []
    errors = []

    for i, p in enumerate(players):
        pid = p["id"]
        try:
            entries = fetch_competitions(pid, access_token)
            row     = aggregate(p, entries)
            rows.append(row)

            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(players)} — {row['first_name']} {row['last_name']} "
                      f"| {row['total_matches']} matches across {row['competitions_played']} comps")

            time.sleep(RATE_DELAY)

        except Exception as e:
            print(f"  ERROR player {pid}: {e}")
            errors.append(pid)
            time.sleep(1)

    print(f"\nUpserting {len(rows)} rows to Supabase...")
    upsert_batch(rows)

    if errors:
        print(f"\nRetrying {len(errors)} failed players...")
        retry_rows = []
        for pid in errors:
            try:
                p_resp  = requests.get(f"{BASE_URL}/players/{pid}", headers=headers(access_token), timeout=10)
                p       = p_resp.json()["player"]
                entries = fetch_competitions(pid, access_token)
                retry_rows.append(aggregate(p, entries))
                print(f"  Retry OK: {pid}")
                time.sleep(1)
            except Exception as e:
                print(f"  Retry FAILED {pid}: {e}")
        if retry_rows:
            upsert_batch(retry_rows)

    print(f"\n✅ Done. {len(rows)} players synced, {len(errors)} errors.")

if __name__ == "__main__":
    main()
