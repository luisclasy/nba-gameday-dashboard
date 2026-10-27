# -*- coding: utf-8 -*-
"""
从 ESPN 拉取 NBA 伤病/出战成疑名单，写入 injuries 表。

用法：
    venv\\Scripts\\python.exe database\\update_injuries_espn.py
    venv\\Scripts\\python.exe database\\update_injuries_espn.py --dry-run

说明：
- 这是“当前快照”，每次运行会替换 injuries 表内容；
- 状态统一为：缺席 / 每日观察 / 出战成疑 / 大概率缺阵 / 大概率出战；
- 伤病部位尽量翻译成中文，短评保留 ESPN 原文（前端用小字展示）。
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent
DEFAULT_DB = BASE / "database" / "nba.db"
URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries"

STATUS_CN = {
    "Out": "缺席",
    "Day-To-Day": "每日观察",
    "Questionable": "出战成疑",
    "Doubtful": "大概率缺阵",
    "Probable": "大概率出战",
    "Available": "可出战",
}
TYPE_CN = {
    "Ankle": "脚踝", "Knee": "膝盖", "Hamstring": "腿筋", "Foot": "脚部",
    "Leg": "腿部", "Back": "背部", "Illness": "疾病", "Concussion": "脑震荡",
    "Hip": "髋部", "Groin": "腹股沟", "Calf": "小腿", "Thigh": "大腿",
    "Hand": "手部", "Wrist": "手腕", "Shoulder": "肩膀", "Elbow": "肘部",
    "Eye": "眼部", "Neck": "颈部", "Quadriceps": "股四头肌", "Achilles": "跟腱",
    "Toe": "脚趾", "Finger": "手指", "Ribs": "肋骨", "Abdomen": "腹部",
    "Oblique": "腹斜肌", "Head": "头部", "Face": "面部", "Personal": "个人原因",
}
SIDE_CN = {"Right": "右侧", "Left": "左侧", "Both": "双侧", "Not Specified": "未说明"}
DETAIL_CN = {
    "Fracture": "骨折", "Strain": "拉伤", "Sprain": "扭伤", "Tear": "撕裂",
    "Inflammation": "炎症", "Soreness": "酸痛", "Contusion": "挫伤",
    "Surgery": "手术", "Not Specified": "未说明", "Stiffness": "僵硬",
}
NAME_ALIASES = {
    "LA Clippers": "LAC",
}


def get_team_map(conn):
    """球队全称 -> 缩写（优先最新赛季）。"""
    rows = conn.execute(
        "SELECT team, abbreviation FROM team WHERE lg='NBA' AND abbreviation IS NOT NULL "
        "ORDER BY CAST(season AS INTEGER) DESC"
    ).fetchall()
    out = {}
    for full, abbr in rows:
        if full and abbr:
            out.setdefault(full, abbr)
    out.update(NAME_ALIASES)
    return out


def ensure_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(injuries)")}
    if not cols:
        conn.execute(
            "CREATE TABLE injuries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, team TEXT, player TEXT, "
            "injury_type TEXT, status TEXT, return_date TEXT, note TEXT)"
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(injuries)")}
    for col, typ in (("source", "TEXT"), ("updated_at", "TEXT"), ("espn_id", "TEXT")):
        if col not in cols:
            conn.execute(f"ALTER TABLE injuries ADD COLUMN {col} {typ}")


def fetch():
    req = urllib.request.Request(URL, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def injury_type_cn(details):
    details = details or {}
    parts = []
    t = details.get("type")
    if t:
        parts.append(TYPE_CN.get(t, t))
    side = details.get("side")
    if side:
        parts.append(SIDE_CN.get(side, side))
    detail = details.get("detail")
    if detail:
        parts.append(DETAIL_CN.get(detail, detail))
    return " · ".join(parts) or "伤病"


def sync(conn, dry_run=False):
    """拉取并替换 injuries 表；返回 (球队数, 行数, 未映射球队)。供 CLI 和 Flask 自动刷新共用。"""
    data = fetch()
    teams = {t.get("displayName"): t for t in data.get("injuries", [])}
    team_map = get_team_map(conn)
    updated_at = data.get("timestamp") or datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, skipped = [], []
    for team_name, team in teams.items():
        abbr = team_map.get(team_name)
        if not abbr:
            skipped.append(team_name)
            continue
        for item in team.get("injuries", []):
            athlete = item.get("athlete") or {}
            player = athlete.get("displayName") or athlete.get("shortName")
            if not player:
                continue
            details = item.get("details") or {}
            status_en = item.get("status") or "Out"
            rows.append((
                abbr,
                player,
                injury_type_cn(details),
                STATUS_CN.get(status_en, status_en),
                details.get("returnDate") or "",
                (item.get("shortComment") or "")[:300],
                "ESPN",
                updated_at,
                str(item.get("id") or ""),
            ))
    rows.sort(key=lambda r: (r[0], r[3], r[1]))
    if not dry_run and rows:
        conn.execute("DELETE FROM injuries")
        conn.executemany(
            "INSERT INTO injuries (team, player, injury_type, status, return_date, note, "
            "source, updated_at, espn_id) VALUES (?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    return len(teams), rows, skipped


def main():
    parser = argparse.ArgumentParser(description="从 ESPN 更新当前 NBA 伤病名单")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(Path(args.db))
    try:
        ensure_schema(conn)
        team_count, rows, skipped = sync(conn, args.dry_run)
        print(f"ESPN 球队: {team_count}，伤病记录: {len(rows)}，未映射球队: {len(skipped)}")
        if skipped:
            print("  未映射:", ", ".join(skipped))
        for r in rows[:8]:
            print(f"  {r[0]:3} {r[1]:22} {r[3]:5} {r[2]:18} {r[4] or '待定'}")
        if args.dry_run:
            print("DRY-RUN：未写库")
        else:
            print(f"已写入 injuries: {len(rows)} 条")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
