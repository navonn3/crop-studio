"""Export MediaHub's scanned games (moments + HLS link) for Crop Studio's game mode.

Reads MediaHub/pbp_moments.json (+ pbp_project.json offsets for manually synced games) and writes plaintext
JSON to data/games/ (git-ignored). `node build.mjs` then encrypts them into docs/g/*.bin.

Video time of a moment (same as MediaHub addToPL): mp = t + offset + shift, where scorebug-mapped games
(`exact`) carry the true action second (shift 0) and VidSwap-tag games are offset-synced with shift +4.
Only games listed in tools/broadcast_games.txt (the user's own broadcasts) are exported, and only if they
have an HLS link and either `exact` or a sync offset.

Usage:  python tools/export_games.py [path/to/MediaHub]
"""
import json
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
MH = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "My-IBBA-Dash" / "MediaHub"
OUT = HERE / "data" / "games"
WHITELIST = HERE / "tools" / "broadcast_games.txt"


def whitelist():
    gids = set()
    for line in WHITELIST.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            gids.add(int(line))
    return gids


def score(sc):
    try:
        h, a = sc.split("-")
        return int(h), int(a)
    except Exception:
        return None


def reachable(url):
    """Some streams get pulled from the CDN (403) - those games are skipped, the tool can't cut from them."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False


def player_sides(moms):
    """home/away per player, from which side's score moved on their made shots."""
    votes = defaultdict(Counter)
    prev = (0, 0)
    for m in sorted(moms, key=lambda m: m["t"]):
        s = score(m.get("sc") or "")
        if s is None:
            continue
        if m["k"] == "shot" and m.get("res") == "made" and m.get("p"):
            dh, da = s[0] - prev[0], s[1] - prev[1]
            if dh > 0 and da == 0:
                votes[m["p"]]["h"] += 1
            elif da > 0 and dh == 0:
                votes[m["p"]]["a"] += 1
        prev = s
    return {p: c.most_common(1)[0][0] for p, c in votes.items()}


def main():
    data = json.loads((MH / "pbp_moments.json").read_text(encoding="utf-8"))
    proj = json.loads((MH / "pbp_project.json").read_text(encoding="utf-8"))
    offsets = {int(k): v for k, v in (proj.get("offsets") or {}).items()}
    scores_p = MH / "moment_scores.json"
    scores = json.loads(scores_p.read_text(encoding="utf-8")) if scores_p.exists() else {}
    # venue recordings move to cloud_hls a day or two after the game, trimmed at the start:
    # hls_moves.json maps gid -> {m3u8, shift}, shift (s) added to every moment time
    moves_p = MH / "hls_moves.json"
    moves = {int(k): v for k, v in json.loads(moves_p.read_text(encoding="utf-8")).items()
             if not k.startswith("_")} if moves_p.exists() else {}

    by_gid = defaultdict(list)
    for m in data["moments"]:
        by_gid[m["gid"]].append(m)

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()
    wanted = whitelist()
    index = []
    for g in data["games"]:
        gid = g["gid"]
        if gid not in wanted:
            continue
        moms = by_gid.get(gid)
        if not g.get("m3u8") or not moms:
            continue
        exact = bool(g.get("exact"))
        if not exact and gid not in offsets:
            continue
        off = 0 if exact else offsets[gid]
        shift = (0 if exact else 4) + moves.get(gid, {}).get("shift", 0.0)
        url = moves.get(gid, {}).get("m3u8") or g["m3u8"]
        sides = player_sides(moms)
        rows = []
        for m in sorted(moms, key=lambda m: m["t"]):
            r = {"t": round(m["t"] + off + shift, 2), "k": m["k"], "p": m.get("p") or "", "sc": m.get("sc") or "",
                 "q": str(m.get("q") or "")}
            for f in ("val", "res", "type", "side"):
                if m.get(f) is not None:
                    r[f] = m[f]
            sd = sides.get(m.get("p"))
            if sd:
                r["s"] = sd
            hs = scores.get(f"{gid}:{m['t']}:{m.get('num')}:{m['k']}")
            if hs and hs > 1:
                r["h"] = hs
            rows.append(r)
        (OUT / f"{gid}.json").write_text(json.dumps({"gid": gid, "m": rows}, ensure_ascii=False, separators=(",", ":")),
                                         encoding="utf-8")
        index.append({"gid": gid, "date": g.get("date") or "", "home": g.get("home") or "", "away": g.get("away") or "",
                      "url": url, "n": len(rows)})
    with ThreadPoolExecutor(8) as ex:
        ok = list(ex.map(lambda g: reachable(g["url"]), index))
    dead = [g for g, o in zip(index, ok) if not o]
    for g in dead:
        (OUT / f"{g['gid']}.json").unlink()
        print(f"  skip {g['gid']} {g['date']} {g['home']} - {g['away']}: stream unreachable")
    index = [g for g, o in zip(index, ok) if o]
    index.sort(key=lambda x: (x["date"], x["gid"]), reverse=True)
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"exported {len(index)} games, {sum(x['n'] for x in index)} moments -> {OUT}")


if __name__ == "__main__":
    main()
