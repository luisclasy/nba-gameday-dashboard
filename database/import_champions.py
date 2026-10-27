# -*- coding: utf-8 -*-
"""
导入历届 NBA 总冠军 / FMVP（1947–2026）。

数据文件：data/champions.csv
字段：season, champion, champion_abbr, runner_up, series, fmvp, fmvp_team_abbr, source
用法：
    venv\\Scripts\\python.exe database\\import_champions.py
"""
import csv
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "database" / "nba.db"
CSV = BASE / "data" / "champions.csv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS champions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    season          TEXT UNIQUE,
    champion        TEXT,
    champion_abbr   TEXT,
    runner_up       TEXT,
    series          TEXT,
    fmvp            TEXT,
    fmvp_team_abbr  TEXT,
    source          TEXT
)
"""


def main():
    with CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    conn = sqlite3.connect(DB)
    try:
        conn.execute(SCHEMA)
        conn.execute("DELETE FROM champions")
        conn.executemany(
            "INSERT INTO champions (season, champion, champion_abbr, runner_up, series, "
            "fmvp, fmvp_team_abbr, source) VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    r["season"], r["champion"], r["champion_abbr"], r["runner_up"],
                    r["series"], r["fmvp"], r["fmvp_team_abbr"], r["source"],
                )
                for r in rows
            ],
        )
        conn.commit()
        print(f"✅ 已导入 champions: {len(rows)} 条")
        for row in conn.execute(
            "SELECT season, champion, fmvp FROM champions ORDER BY CAST(season AS INTEGER) DESC LIMIT 5"
        ):
            print("  ", row)
        print("球队冠军数 TOP8:")
        for row in conn.execute(
            "SELECT champion_abbr, COUNT(*) n FROM champions "
            "GROUP BY champion_abbr ORDER BY n DESC LIMIT 8"
        ):
            print("  ", row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
