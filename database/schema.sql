-- =============================================================
-- NBA观赛辅助系统 - 数据库建表 SQL (SQLite)
-- 说明：表结构与 data/*.csv 字段对应，导入脚本负责填充数据
-- 注意：SQLite 下执行，无需安装数据库服务
-- =============================================================

-- 球队表：每行 = 某赛季的某支球队
CREATE TABLE IF NOT EXISTS team (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    season       TEXT,               -- 赛季，如 "2023-2024"
    lg           TEXT,               -- 联盟：NBA / ABA / BAA
    team         TEXT,               -- 球队全称
    abbreviation TEXT,               -- 球队简称，如 LAL
    playoffs     TEXT                -- 是否进入季后赛
);

-- 球员表：每行 = 某球员在某赛季（效力球队）的累计统计
-- 核心字段 pts/trb/ast/stl/blk/tov 用于雷达图、柱状图、下钻
-- 注意：player_id 是 basketball-reference 字符串 ID（如 curryst01），不是整数；
--       team 存的是球队缩写（如 LAL），球队全称在 team.team。
CREATE TABLE IF NOT EXISTS player (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id    TEXT,               -- 球员唯一标识（如 curryst01）
    season       TEXT,               -- 赛季（结束年份，如 2026 = 2025-26）
    lg           TEXT,               -- 联盟
    player       TEXT,               -- 球员姓名
    team         TEXT,               -- 球队缩写（如 LAL）
    pos          TEXT,               -- 场上位置（归一化 G/F/C）
    age          INTEGER,            -- 年龄
    g            INTEGER,            -- 出场数
    gs           INTEGER,            -- 首发数
    mp           REAL,               -- 出场时间
    fg_percent   REAL,               -- 命中率
    x3p_percent  REAL,               -- 三分命中率
    ft_percent   REAL,               -- 罚球命中率
    orb          REAL,               -- 前场篮板
    drb          REAL,               -- 后场篮板
    trb          REAL,               -- 总篮板
    ast          REAL,               -- 助攻
    stl          REAL,               -- 抢断
    blk          REAL,               -- 盖帽
    tov          REAL,               -- 失误
    pf           REAL,               -- 犯规
    pts          REAL                -- 得分
);

-- 赛程表：由 import_schedule.py 首次导入，update_recent_espn.py 只增量更新
-- season_type: preseason / regular / playoffs / playin / allstar / cup
-- game_status: Final / Final/OT / In Progress / Scheduled / Postponed
CREATE TABLE IF NOT EXISTS schedule (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      TEXT,               -- NBA gameId 或 espn-<id>
    game_date    TEXT,               -- 美东日期 YYYY-MM-DD（与 NBA 官网一致）
    home_team    TEXT,               -- 主队缩写
    away_team    TEXT,               -- 客队缩写
    home_score   INTEGER,
    away_score   INTEGER,
    game_status  TEXT,
    home_team_id INTEGER,
    away_team_id INTEGER,
    season_type  TEXT,               -- 见上方注释
    season       TEXT,               -- 2026-27
    tipoff_utc   TEXT,               -- ISO UTC，如 2026-10-24T02:00:00Z
    espn_id      TEXT,               -- ESPN event id
    updated_at   TEXT
);

-- 历届总冠军 / FMVP（1947–2026，数据文件 data/champions.csv）
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
);
CREATE INDEX IF NOT EXISTS idx_champions_season ON champions (season);
CREATE INDEX IF NOT EXISTS idx_champions_abbr ON champions (champion_abbr);

-- 用户偏好 / 观察名单 / 伤病（伤病目前为示例数据，未接实时源）
CREATE TABLE IF NOT EXISTS user_pref (
    id INTEGER PRIMARY KEY AUTOINCREMENT, pref_key TEXT UNIQUE, pref_value TEXT
);
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT UNIQUE,
    player_name TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS injuries (
    id INTEGER PRIMARY KEY AUTOINCREMENT, team TEXT, player TEXT,
    injury_type TEXT, status TEXT, return_date TEXT, note TEXT,
    source TEXT, updated_at TEXT, espn_id TEXT
);

-- 常用索引，加速筛选/下钻查询
CREATE INDEX IF NOT EXISTS idx_player_season ON player (season);
CREATE INDEX IF NOT EXISTS idx_player_playerid ON player (player_id);
CREATE INDEX IF NOT EXISTS idx_player_team    ON player (team);
CREATE INDEX IF NOT EXISTS idx_team_season    ON team (season);
CREATE INDEX IF NOT EXISTS idx_schedule_date  ON schedule (game_date);
CREATE INDEX IF NOT EXISTS idx_schedule_teams ON schedule (home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_schedule_espn  ON schedule (espn_id);
