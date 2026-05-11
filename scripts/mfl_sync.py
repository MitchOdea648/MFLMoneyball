"""
MFL Moneyball - Full Database Sync with Checkpoint
Runs daily via schedule, picks up where it left off.
Covers all ~377,000 player IDs over ~7 days.
"""

import os, time, requests
from datetime import datetime, timezone
from supabase import create_client

BASE_URL      = "https://z519wdyajg.execute-api.us-east-1.amazonaws.com/prod"
ORIGIN        = "https://app.playmfl.com"
MAX_PLAYER_ID = 377200
RATE_DELAY    = 0.5
MAX_RUNTIME   = 5.5 * 3600  # 5.5 hours in seconds

SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]
REFRESH_TOKEN = os.environ["MFL_REFRESH_TOKEN"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Auth ──────────────────────────────────────────────────────────────────────
def get_access_token() -> str:
    print("Refreshing access token...")
    resp = requests.post(
        f"{BASE_URL}/auth/refresh",
        json={"refreshToken": REFRESH_TOKEN},
        headers={"origin": ORIGIN},
        timeout=10
    )
    resp.raise_for_status()
    token = resp.json()["access"]["token"]
    print("  Token obtained ✅")
    return token

def make_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "origin": ORIGIN}

# ── Checkpoint ────────────────────────────────────────────────────────────────
def get_checkpoint() -> dict:
    result = supabase.table("mfl_sync_checkpoint").select("*").eq("id", 1).execute()
    return result.data[0]

def save_checkpoint(last_id: int, total_processed: int, total_found: int, completed: bool = False):
    supabase.table("mfl_sync_checkpoint").update({
        "last_id":         last_id,
        "total_processed": total_processed,
        "total_found":     total_found,
        "completed":       completed,
        "updated_at":      datetime.now(timezone.utc).isoformat()
    }).eq("id", 1).execute()

# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch_player(player_id: int, token: str) -> dict | None:
    resp = requests.get(
        f"{BASE_URL}/players/{player_id}",
        headers=make_headers(token),
        timeout=10
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("player")

def fetch_competitions(player_id: int, token: str) -> list:
    resp = requests.get(
        f"{BASE_URL}/players/{player_id}/competitions",
        headers=make_headers(token),
        timeout=10
    )
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    return resp.json()

# ── Aggregate ─────────────────────────────────────────────────────────────────
def aggregate(player: dict, entries: list) -> dict:
    m     = player["metadata"]
    owner = player.get("ownedBy") or {}

    totals = {
        "total_matches": 0, "total_minutes": 0, "total_goals": 0,
        "total_assists": 0, "total_shots": 0, "total_shots_on_target": 0,
        "total_xg": 0, "total_passes": 0, "total_passes_accurate": 0,
        "total_chances_created": 0, "total_dribbling": 0,
        "total_def_duels_won": 0, "total_clearances": 0,
        "total_yellow_cards": 0, "total_red_cards": 0,
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

    return {
        "id":               player["id"],
        "first_name":       m.get("firstName"),
        "last_name":        m.get("lastName"),
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
        "owner_wallet":     owner.get("walletAddress"),
        "owner_name":       owner.get("name"),
        "energy":           player.get("energy"),
        "has_pre_contract": player.get("hasPreContract", False),
        "offer_status":     player.get("offerStatus", 0),
        **totals,
        "goals_p90":     per90(totals["total_goals"]),
        "assists_p90":   per90(totals["total_assists"]),
        "xg_p90":        per90(totals["total_xg"]),
        "passes_p90":    per90(totals["total_passes"]),
        "chances_p90":   per90(totals["total_chances_created"]),
        "def_duels_p90": per90(totals["total_def_duels_won"]),
        "shots_p90":     per90(totals["total_shots"]),
        "pass_acc_pct":  pct(totals["total_passes_accurate"], totals["total_passes"]),
        "shot_acc_pct":  pct(totals["total_shots_on_target"], totals["total_shots"]),
        "win_pct":       pct(totals["total_wins"], totals["total_matches"]),
        "avg_rating":    round(totals["total_rating_sum"] / totals["total_matches"], 2)
                         if totals["total_matches"] > 0 else None,
        "seasons_played":      len(seen_seasons),
        "competitions_played": len(seen_comps),
    }

# ── Upsert ────────────────────────────────────────────────────────────────────
def upsert_batch(rows: list):
    for i in range(0, len(rows), 200):
        supabase.table("mfl_players").upsert(
            rows[i:i+200], on_conflict="id"
        ).execute()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    start_time = time.time()

    # Check checkpoint
    checkpoint = get_checkpoint()
    if checkpoint["completed"]:
        print("✅ Full sync already completed! Reset checkpoint to re-run.")
        return

    start_id        = checkpoint["last_id"] + 1
    total_processed = checkpoint["total_processed"]
    total_found     = checkpoint["total_found"]

    print(f"Resuming from ID {start_id:,} (processed so far: {total_processed:,}, found: {total_found:,})")

    token      = get_access_token()
    batch      = []
    last_id    = start_id - 1
    token_time = time.time()

    for player_id in range(start_id, MAX_PLAYER_ID + 1):

        # Refresh token every 90 minutes
        if time.time() - token_time > 90 * 60:
            token      = get_access_token()
            token_time = time.time()

        # Check runtime limit
        elapsed = time.time() - start_time
        if elapsed > MAX_RUNTIME:
            print(f"\n⏱ Time limit reached after {elapsed/3600:.1f}hrs")
            break

        try:
            player = fetch_player(player_id, token)
            total_processed += 1
            last_id = player_id

            if player is None:
                # 404 — player doesn't exist, short delay and move on
                time.sleep(0.1)
                continue

            entries = fetch_competitions(player_id, token)
            row     = aggregate(player, entries)
            batch.append(row)
            total_found += 1

            # Upsert and save checkpoint every 200 found players
            if len(batch) >= 200:
                upsert_batch(batch)
                save_checkpoint(last_id, total_processed, total_found)
                print(f"  ID {player_id:,} | found {total_found:,} | processed {total_processed:,} | {elapsed/3600:.1f}hrs elapsed")
                batch = []

            time.sleep(RATE_DELAY)

        except Exception as e:
            err = str(e)
            if "403" in err:
                # Rate limited — back off and retry same ID
                time.sleep(15)
                try:
                    player = fetch_player(player_id, token)
                    if player:
                        entries = fetch_competitions(player_id, token)
                        row     = aggregate(player, entries)
                        batch.append(row)
                        total_found += 1
                    total_processed += 1
                    last_id = player_id
                except Exception as e2:
                    print(f"  RETRY FAILED at ID {player_id}: {e2}")
                    time.sleep(5)
            elif "timeout" in err.lower():
                print(f"  TIMEOUT at ID {player_id} — skipping")
                time.sleep(5)
            else:
                print(f"  ERROR at ID {player_id}: {e}")
                time.sleep(2)

    # Upsert any remaining rows
    if batch:
        upsert_batch(batch)

    # Save final checkpoint
    completed = last_id >= MAX_PLAYER_ID
    save_checkpoint(last_id, total_processed, total_found, completed)

    print(f"\n{'✅ FULL SYNC COMPLETE' if completed else '⏸ Paused — will resume tomorrow'}")
    print(f"  Last ID processed: {last_id:,}")
    print(f"  Total processed:   {total_processed:,}")
    print(f"  Total found:       {total_found:,}")
    print(f"  Runtime:           {(time.time()-start_time)/3600:.1f}hrs")

if __name__ == "__main__":
    main()
