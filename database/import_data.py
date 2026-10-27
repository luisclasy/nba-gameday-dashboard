# -*- coding: utf-8 -*-
"""
数据导入脚本：读取 data/*.csv，筛选 NBA 联盟数据，写入 SQLite 数据库。
运行方式：venv\Scripts\python.exe database\import_data.py
数据库输出：database\nba.db
"""
import sqlite3
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent   # 项目根目录
DATA = BASE / "data"
DB   = BASE / "database" / "nba.db"
SCHEMA = BASE / "database" / "schema.sql"

# player_totals.csv 中需要保留到 player 表的列
PLAYER_COLS = [
    "player_id", "season", "lg", "player", "team", "pos", "age",
    "g", "gs", "mp", "fg_percent", "x3p_percent", "ft_percent",
    "orb", "drb", "trb", "ast", "stl", "blk", "tov", "pf", "pts",
]


def load_data():
    """读取并筛选 NBA 联盟的球队与球员数据。"""
    team = pd.read_csv(DATA / "teams.csv", encoding="utf-8")
    team = team[team["lg"] == "NBA"]

    player = pd.read_csv(DATA / "player_totals.csv", encoding="utf-8")
    player = player[player["lg"] == "NBA"]
    player = player[PLAYER_COLS]
    return team, player


def main():
    team, player = load_data()
    conn = sqlite3.connect(DB)
    try:
        # 1. 执行建表 SQL
        conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        # 2. 清空旧数据，避免重复导入
        conn.execute("DELETE FROM player")
        conn.execute("DELETE FROM team")
        # 3. 写入数据
        team.to_sql("team", conn, if_exists="append", index=False)
        player.to_sql("player", conn, if_exists="append", index=False)
        conn.commit()

        cur = conn.cursor()
        print("✅ 导入完成")
        print("team   行数:", cur.execute("SELECT COUNT(*) FROM team").fetchone()[0])
        print("player 行数:", cur.execute("SELECT COUNT(*) FROM player").fetchone()[0])
        print("赛季范围:", cur.execute("SELECT MIN(season), MAX(season) FROM player").fetchone())
        print("近赛季得分榜示例:")
        for row in cur.execute(
            "SELECT player, season, team, pts FROM player "
            "WHERE season LIKE '2023%' ORDER BY pts DESC LIMIT 3"
        ).fetchall():
            print("  ", row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
