# -*- coding: utf-8 -*-
"""
位置字段归一化（可复现）：
将 player / playoff 两张表的 pos 统一为三大类 G(后卫) / F(前锋) / C(中锋)。
原因：常规赛与 Kaggle 季后赛用 PG/SG/SF/PF/C，ESPN 季后赛用 Guard/Forward/Center、
G/F、Point Guard 等，口径不一导致同位置 TOP3、阵容分组匹配不全。
Guard 本就含 PG+SG、Forward 含 SF+PF，无法可靠细分，故统一三大类。
"""
import shutil
import sqlite3
import os

DB = os.path.join(os.path.dirname(__file__), "..", "database", "nba.db")
BAK = os.path.join(os.path.dirname(__file__), "..", "database", "nba.db.bak_pos")

POS_MAP = {
    "pg": "G", "sg": "G", "g": "G", "guard": "G",
    "point guard": "G", "shooting guard": "G",
    "sf": "F", "pf": "F", "f": "F", "forward": "F",
    "small forward": "F", "power forward": "F",
    "c": "C", "center": "C",
}


def norm_pos(raw):
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    # 混合位置（如 G-F / F-C / C-F）取首个主位置
    token = s.replace("/", "-").split("-")[0].strip()
    return POS_MAP.get(token) or POS_MAP.get(s)


def main():
    shutil.copy2(DB, BAK)
    print("已备份:", os.path.basename(BAK))
    conn = sqlite3.connect(DB)
    try:
        for table in ("player", "playoff"):
            rows = conn.execute(f"SELECT DISTINCT pos FROM {table}").fetchall()
            for (raw,) in rows:
                new = norm_pos(raw)
                conn.execute(f"UPDATE {table} SET pos=? WHERE pos IS ?", (new, raw))
            conn.commit()
            print(f"\n[{table}] 归一化后 pos 分布:")
            for r in conn.execute(f"SELECT pos, COUNT(*) c FROM {table} GROUP BY pos ORDER BY c DESC"):
                print(f"  {str(r[0]):6} {r[1]}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
