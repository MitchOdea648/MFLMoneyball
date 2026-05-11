"""
MFL Moneyball - Test run with 5 players
"""

import os, time, requests
from supabase import create_client

BASE_URL     = "https://z519wdyajg.execute-api.us-east-1.amazonaws.com/prod"
ORIGIN       = "https://app.playmfl.com"

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]
REFRESH_TOKEN = os.environ["MFL_REFRESH_TOKEN"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Get access token
print("Refreshing access token...")
resp = requests.post(
    f"{BASE_URL}/auth/refresh",
    json={"refreshToken": REFRESH_TOKEN},
    headers={"origin": ORIGIN},
    timeout=10
)
resp.raise_for_status()
token = resp.json()["access"]["token"]
print(f"  Token obtained ✅")

hdrs = {"Authorization": f"Bearer {token}", "origin": ORIGIN}

# Fetch 5 known players with match history
test_ids = [826, 238838, 74230, 375384, 275271]
rows = []

for pid in test_ids:
    print(f"\nFetching player {pid}...")
    p = requests.get(f"{BASE_URL}/players/{pid}", headers=hdrs, timeout=10).json()["player"]
    m = p["metadata"]
    print(f"  {m['firstName']} {m['lastName']} | OVR:{m['overall']} | {m['positions']}")

    entries = requests.get(f"{BASE_URL}/players/{pid}/competitions", headers=hdrs, timeout=10).json()
    print(f"  {len(entries)} competition entries")

    totals = {
        "total_matches": 0, "total_minutes": 0, "total_goals": 0,
        "total_assists": 0, "total_shots": 0, "total_shots_on_target": 0,
        "total_xg": 0, "total_passes": 0, "total_passes_accurate": 0,
        "total_chances_created": 0, "total_dribbling": 0, "total_def_duels_won": 0,
        "total_clearances": 0, "total_yellow_cards": 0, "total_red_cards": 0,
        "total_wins": 0, "total_draws": 0, "total_losses": 0,
        "total_saves": 0, "total_goals_conceded": 0, "total_rating_sum": 0,
    }
    seen_seasons = set()
    seen_comps   = set()

    for entry in entries:
        s    = entry.get("stats", {})
        comp = entry.get("competition", {})
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
        seen_seasons.add(comp.get("season", {}).get("name", "unknown"))
        seen_comps.add(comp.get("id"))

    mins = totals["total_minutes"]
    p90  = mins / 90 if mins > 0 else None
    def per90(v): return round(v / p90, 2) if p90 else None
    def pct(n, d): return round(n / d * 100, 1) if d > 0 else None

    owner = p.get("ownedBy") or {}
    row = {
        "id": pid, "first_name": m.get("firstName"), "last_name": m.get("lastName"),
        "overall": m.get("overall"), "age": m.get("age"), "height": m.get("height"),
        "positions": m.get("positions", []), "primary_position": (m.get("positions") or [None])[0],
        "nationalities": m.get("nationalities", []), "preferred_foot": m.get("preferredFoot"),
        "pace": m.get("pace"), "shooting": m.get("shooting"), "passing": m.get("passing"),
        "dribbling": m.get("dribbling"), "defense": m.get("defense"),
        "physical": m.get("physical"), "goalkeeping": m.get("goalkeeping"),
        "owner_wallet": owner.get("walletAddress"), "owner_name": owner.get("name"),
        "energy": p.get("energy"), "has_pre_contract": p.get("hasPreContract", False),
        "offer_status": p.get("offerStatus", 0),
        **totals,
        "goals_p90": per90(totals["total_goals"]),
        "assists_p90": per90(totals["total_assists"]),
        "xg_p90": per90(totals["total_xg"]),
        "passes_p90": per90(totals["total_passes"]),
        "chances_p90": per90(totals["total_chances_created"]),
        "def_duels_p90": per90(totals["total_def_duels_won"]),
        "shots_p90": per90(totals["total_shots"]),
        "pass_acc_pct": pct(totals["total_passes_accurate"], totals["total_passes"]),
        "shot_acc_pct": pct(totals["total_shots_on_target"], totals["total_shots"]),
        "win_pct": pct(totals["total_wins"], totals["total_matches"]),
        "avg_rating": round(totals["total_rating_sum"] / totals["total_matches"], 2) if totals["total_matches"] > 0 else None,
        "seasons_played": len(seen_seasons),
        "competitions_played": len(seen_comps),
    }
    rows.append(row)
    print(f"  Aggregated: {totals['total_matches']} matches | {totals['total_minutes']} mins | {len(seen_comps)} comps")
    time.sleep(0.3)

# Upsert to Supabase
print(f"\nUpserting {len(rows)} rows to Supabase...")
result = supabase.table("mfl_players").upsert(rows, on_conflict="id").execute()
print(f"✅ Done! Check your Supabase table.")
