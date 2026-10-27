# -*- coding: utf-8 -*-
"""
从 ESPN scoreboard 拉取最近/即将进行的 NBA 比赛，增量更新 schedule 表。

特点：
- 只更新/补充，不删除原有赛程；
- 自动给 schedule 增加 season_type / season / tipoff_utc / espn_id / updated_at 列；
- 用“美东日期 + 主队 + 客队”匹配原 NBA 赛程，避免 UTC 日期跨天导致错位；
- 已完赛写 Final / Final-OT，进行中写 In Progress，未开赛写 Scheduled；
- 未开赛比分写 NULL，不再用 0-0 伪装成已完赛。

用法：
    venv\\Scripts\\python.exe database\\update_recent_espn.py
    venv\\Scripts\\python.exe database\\update_recent_espn.py --days-back 21 --days-ahead 7
    venv\\Scripts\\python.exe database\\update_recent_espn.py --start 2026-10-03 --end 2026-10-31
    venv\\Scripts\\python.exe database\\update_recent_espn.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE / "database" / "nba.db"
ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={day}"
ET = ZoneInfo("America/New_York")

# ESPN 缩写 -> 数据库/NBA 官方缩写（其余原样保留）
ESPN_TEAM = {
    "UTAH": "UTA", "NO": "NOP", "NY": "NYK", "GS": "GSW",
    "SA": "SAS", "WSH": "WAS", "PHX": "PHX", "BKN": "BKN",
}
SEASON_TYPE = {1: "preseason", 2: "regular", 3: "playoffs", 4: "allstar", 5: "playin", 6: "cup"}


def season_from_year(year: int) -> str:
    return f"{year - 1}-{str(year)[2:]}"


def season_from_date(game_date: str) -> str:
    dt = datetime.strptime((game_date or "")[:10], "%Y-%m-%d")
    start = dt.year if dt.month >= 9 else dt.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def ensure_schema(conn: sqlite3.Connection):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(schedule)")}
    if not cols:
        raise RuntimeError("schedule 表不存在，请先运行 database/import_schedule.py")
    for col, typ in (
        ("season_type", "TEXT"), ("season", "TEXT"),
        ("tipoff_utc", "TEXT"), ("espn_id", "TEXT"), ("updated_at", "TEXT"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE schedule ADD COLUMN {col} {typ}")
    # 旧数据补赛季/赛制（001=季前赛，002=常规赛，003=全明星，004=季后赛，005=附加赛，006=杯赛）
    prefix_type = {"001": "preseason", "002": "regular", "003": "allstar",
                   "004": "playoffs", "005": "playin", "006": "cup"}
    for rid, game_date, game_id, st, season in conn.execute(
        "SELECT id, game_date, game_id, season_type, season FROM schedule"
    ).fetchall():
        new_st = st or prefix_type.get((game_id or "")[:3], "regular")
        new_season = season or season_from_date(game_date)
        if new_st != st or new_season != season:
            conn.execute(
                "UPDATE schedule SET season_type=?, season=? WHERE id=?",
                (new_st, new_season, rid),
            )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule(game_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_teams ON schedule(home_team, away_team)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_espn ON schedule(espn_id)")


def get_json(day: date, retries: int = 2):
    url = ESPN_URL.format(day=day.strftime("%Y%m%d"))
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(1 + attempt)
    raise RuntimeError(f"{day} 拉取失败: {last_err}")


def normalize_event(event: dict):
    """解析一个 ESPN event；返回 (home, away, game_date_et, tipoff_utc, ...)。"""
    comp = (event.get("competitions") or [{}])[0]
    status = comp.get("status") or event.get("status") or {}
    stype = (status.get("type") or {})
    status_name = stype.get("name", "")
    competitors = {c.get("homeAway"): c for c in (comp.get("competitors") or [])}
    home_c = competitors.get("home")
    away_c = competitors.get("away")
    if not home_c or not away_c:
        return None
    home = ESPN_TEAM.get(home_c["team"].get("abbreviation", ""), home_c["team"].get("abbreviation", ""))
    away = ESPN_TEAM.get(away_c["team"].get("abbreviation", ""), away_c["team"].get("abbreviation", ""))
    if not home or not away:
        return None

    tip = event.get("date") or comp.get("date")
    try:
        tip_dt = datetime.fromisoformat(str(tip).replace("Z", "+00:00"))
        if tip_dt.tzinfo is None:
            tip_dt = tip_dt.replace(tzinfo=timezone.utc)
        game_date_et = tip_dt.astimezone(ET).date().isoformat()
        tipoff_utc = tip_dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, TypeError):
        return None

    season = event.get("season") or {}
    season_year = season.get("year")
    season_name = season_from_year(int(season_year)) if season_year else season_from_date(game_date_et)
    stype_id = season.get("type")
    stype_name = SEASON_TYPE.get(stype_id)
    if not stype_name:
        # 1=季前赛 2=常规赛 3=季后赛；缺省按日期推断
        stype_name = "regular"

    period = (comp.get("status") or {}).get("period") or (event.get("status") or {}).get("period") or 0
    if status_name == "STATUS_FINAL":
        game_status = "Final/OT" if int(period or 0) > 4 else "Final"
    elif status_name == "STATUS_IN_PROGRESS":
        game_status = "In Progress"
    elif status_name == "STATUS_POSTPONED":
        game_status = "Postponed"
    elif status_name == "STATUS_CANCELED":
        game_status = "Canceled"
    else:
        game_status = "Scheduled"

    def score(c):
        v = c.get("score")
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    hs = score(home_c)
    as_ = score(away_c)
    if status_name not in ("STATUS_FINAL", "STATUS_IN_PROGRESS"):
        hs = as_ = None
    return {
        "home": home, "away": away,
        "home_score": hs, "away_score": as_,
        "game_date": game_date_et, "tipoff_utc": tipoff_utc,
        "game_status": game_status, "status_name": status_name,
        "season_type": stype_name, "season": season_name,
        "espn_id": str(event.get("id") or ""),
        "home_team_id": home_c.get("team", {}).get("id"),
        "away_team_id": away_c.get("team", {}).get("id"),
    }


def sync_events(conn, events, dry_run=False, seen=None):
    """把一个 ESPN scoreboard 的 events 列表同步进 schedule。供 CLI 和 Flask 自动刷新共用。"""
    seen = seen if seen is not None else set()
    stats = {"fetched": 0, "matched": 0, "inserted": 0, "updated": 0, "skipped": 0}
    latest = []
    for ev in events:
        eid = str(ev.get("id") or "")
        if eid in seen:
            continue
        seen.add(eid)
        info = normalize_event(ev)
        if not info:
            stats["skipped"] += 1
            continue
        stats["fetched"] += 1
        row = conn.execute(
            "SELECT id, game_id FROM schedule WHERE game_date=? AND home_team=? AND away_team=?",
            (info["game_date"], info["home"], info["away"]),
        ).fetchone()
        if not row:
            # ESPN 的 UTC 日期和 ET 日期可能差一天，容忍 ±1 天
            for delta in (-1, 1):
                d = (date.fromisoformat(info["game_date"]) + timedelta(days=delta)).isoformat()
                row = conn.execute(
                    "SELECT id, game_id FROM schedule WHERE game_date=? AND home_team=? AND away_team=?",
                    (d, info["home"], info["away"]),
                ).fetchone()
                if row:
                    break
        if row:
            if not dry_run:
                conn.execute(
                    "UPDATE schedule SET game_date=?, home_score=?, away_score=?, game_status=?, "
                    "season_type=?, season=?, tipoff_utc=?, espn_id=?, updated_at=? WHERE id=?",
                    (info["game_date"], info["home_score"], info["away_score"], info["game_status"],
                     info["season_type"], info["season"], info["tipoff_utc"], info["espn_id"],
                     datetime.now(timezone.utc).isoformat(timespec="seconds"), row[0]),
                )
            stats["matched"] += 1
            if info["game_status"].startswith("Final"):
                stats["updated"] += 1
                latest.append((info["game_date"], info["away"], info["away_score"],
                               info["home"], info["home_score"]))
        else:
            if not dry_run:
                conn.execute(
                    "INSERT INTO schedule (game_id, game_date, home_team, away_team, home_score, "
                    "away_score, game_status, home_team_id, away_team_id, season_type, season, "
                    "tipoff_utc, espn_id, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (f"espn-{info['espn_id']}", info["game_date"], info["home"], info["away"],
                     info["home_score"], info["away_score"], info["game_status"],
                     info["home_team_id"], info["away_team_id"], info["season_type"],
                     info["season"], info["tipoff_utc"], info["espn_id"],
                     datetime.now(timezone.utc).isoformat(timespec="seconds")),
                )
            stats["inserted"] += 1
    return stats, latest


def main():
    parser = argparse.ArgumentParser(description="从 ESPN 更新最近 NBA 赛程")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite 路径")
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD（默认今天-21天）")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD（默认今天+7天）")
    parser.add_argument("--days-back", type=int, default=21)
    parser.add_argument("--days-ahead", type=int, default=7)
    parser.add_argument("--dry-run", action="store_true", help="只拉取和对比，不写库")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).astimezone(ET).date()
    start = date.fromisoformat(args.start) if args.start else today - timedelta(days=args.days_back)
    end = date.fromisoformat(args.end) if args.end else today + timedelta(days=args.days_ahead)
    if end < start:
        raise SystemExit("--end 不能早于 --start")

    db = Path(args.db)
    conn = sqlite3.connect(db)
    try:
        # dry-run 只读：不建列、不写行，避免把“预览”变成写库
        if not args.dry_run:
            ensure_schema(conn)
        seen = set()
        stats = {"fetched": 0, "matched": 0, "inserted": 0, "updated": 0, "skipped": 0}
        latest = []
        day = start
        while day <= end:
            try:
                data = get_json(day)
            except RuntimeError as e:
                print(f"⚠️ {e}")
                day += timedelta(days=1)
                continue
            events = data.get("events", []) or []
            print(f"{day}: ESPN {len(events)} 场")
            s, l = sync_events(conn, events, args.dry_run, seen)
            for k in stats:
                stats[k] += s[k]
            latest.extend(l)
            day += timedelta(days=1)
            time.sleep(0.15)

        if not args.dry_run:
            conn.commit()
        cur = conn.cursor()
        print("\n=== 更新汇总 ===")
        print(f"ESPN 事件: {stats['fetched']}；匹配原赛程: {stats['matched']}；"
              f"新增: {stats['inserted']}；完赛更新: {stats['updated']}；跳过: {stats['skipped']}")
        print("最近完赛（客队 比分 @ 主队）:")
        for r in sorted(latest)[-8:]:
            print(f"  {r[0]}  {r[1]} {r[2]} @ {r[3]} {r[4]}")
        total = cur.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
        finals = cur.execute("SELECT COUNT(*) FROM schedule WHERE game_status LIKE 'Final%'").fetchone()[0]
        print(f"schedule 总场次: {total}，已完赛: {finals}")
        print("2026-27 常规赛 LAL 最近 5 场:")
        for r in cur.execute(
            "SELECT game_date, away_team, away_score, home_team, home_score, game_status, tipoff_utc "
            "FROM schedule WHERE season_type='regular' AND (home_team='LAL' OR away_team='LAL') "
            "ORDER BY game_date LIMIT 5"
        ):
            print("  ", r)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
