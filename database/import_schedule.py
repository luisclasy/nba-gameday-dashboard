# -*- coding: utf-8 -*-
"""
赛程数据导入脚本：从 NBA 官网公开 JSON 拉取当前赛季赛程，写入 SQLite。
运行方式：venv\Scripts\python.exe database\import_schedule.py
特点：一次导入，赛季中途轻量重跑即可更新比分。
"""
import json
import sqlite3
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "database" / "nba.db"

SCHEDULE_URL = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nba.com/schedule",
    "Origin": "https://www.nba.com",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Connection": "keep-alive",
}


def fetch_schedule():
    """拉取并解析 NBA 官网赛程 JSON。"""
    req = urllib.request.Request(SCHEDULE_URL, headers=HEADERS)
    data = json.load(urllib.request.urlopen(req, timeout=60))
    lg = data["leagueSchedule"]
    rows = []
    for gd in lg.get("gameDates", []):
        for g in gd.get("games", []):
            h, a = g.get("homeTeam", {}), g.get("awayTeam", {})
            rows.append(
                (
                    g.get("gameId"),
                    (g.get("gameDateEst") or "")[:10],   # YYYY-MM-DD
                    h.get("teamTricode"),
                    a.get("teamTricode"),
                    h.get("score"),
                    a.get("score"),
                    g.get("gameStatusText"),
                    h.get("teamId"),
                    a.get("teamId"),
                )
            )
    return rows


def main():
    rows = fetch_schedule()
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT,
                game_date TEXT,
                home_team TEXT,
                away_team TEXT,
                home_score INTEGER,
                away_score INTEGER,
                game_status TEXT,
                home_team_id INTEGER,
                away_team_id INTEGER
            )"""
        )
        conn.execute("DELETE FROM schedule")
        conn.executemany(
            "INSERT INTO schedule (game_id, game_date, home_team, away_team, "
            "home_score, away_score, game_status, home_team_id, away_team_id) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        cur = conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
        done = cur.execute("SELECT COUNT(*) FROM schedule WHERE game_status='Final'").fetchone()[0]
        print(f"✅ 赛程导入完成：共 {total} 场，已完赛 {done} 场")
        print("赛程日期范围:", cur.execute(
            "SELECT MIN(game_date), MAX(game_date) FROM schedule").fetchone())
        print("示例(主队视角 湖人):")
        for r in cur.execute(
            "SELECT game_date, home_team, away_team, home_score, away_score, game_status "
            "FROM schedule WHERE home_team='LAL' OR away_team='LAL' ORDER BY game_date LIMIT 5"
        ).fetchall():
            print("  ", r)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
