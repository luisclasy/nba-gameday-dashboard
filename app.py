# -*- coding: utf-8 -*-
"""
NBA观赛辅助系统 - Flask 后端
技术栈：Flask + PyEcharts + SQLite (方案B)
所有图表数据实时从 SQLite 查询，前端通过 AJAX 获取图表配置(option)并渲染。
"""
import json
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, jsonify, render_template, request
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Radar

from cn_names import (
    TEAM_CN, PLAYER_CN, PLAYER_NICK, SURNAME_CN, cn_player, cn_team,
)

try:
    from database import update_recent_espn as espn_sync
    from database import update_injuries_espn as injury_sync
except Exception:  # 没装/没网时不影响主站启动
    espn_sync = None
    injury_sync = None

BASE = Path(__file__).resolve().parent
DB = BASE / "database" / "nba.db"

CN_TZ = ZoneInfo("Asia/Shanghai")
ET_TZ = ZoneInfo("America/New_York")

app = Flask(__name__)


def query(sql, args=()):
    """执行 SQL 查询，返回 dict 列表。"""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def chart_json(chart):
    """pyecharts 的 dump_options() 返回 JSON 字符串，直接以 application/json 返回。"""
    return app.response_class(chart.dump_options(), mimetype="application/json")


# ---------- 赛程表结构（增量迁移，旧库直接打开也能跑） ----------
SEASON_TYPE_BY_PREFIX = {
    "001": "preseason", "002": "regular", "003": "allstar",
    "004": "playoffs", "005": "playin", "006": "cup",
}


def season_from_date(game_date):
    """NBA 赛季按结束年份命名：2026-10 -> 2026-27，2027-03 -> 2026-27。"""
    try:
        dt = datetime.strptime((game_date or "")[:10], "%Y-%m-%d")
    except ValueError:
        return None
    start = dt.year if dt.month >= 9 else dt.year - 1
    return f"{start}-{str(start + 1)[2:]}"


def ensure_schedule_schema():
    """给 schedule 补齐赛季/赛制/开赛时间列；对旧库是幂等的。"""
    conn = sqlite3.connect(DB)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(schedule)")}
        if not cols:
            return
        for col, typ in (
            ("season_type", "TEXT"), ("season", "TEXT"),
            ("tipoff_utc", "TEXT"), ("espn_id", "TEXT"), ("updated_at", "TEXT"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE schedule ADD COLUMN {col} {typ}")
        for row in conn.execute(
            "SELECT id, game_date, game_id, season_type, season FROM schedule"
        ).fetchall():
            rid, game_date, game_id, st, season = row
            new_st = st or SEASON_TYPE_BY_PREFIX.get((game_id or "")[:3], "regular")
            new_season = season or season_from_date(game_date)
            if new_st != st or new_season != season:
                conn.execute(
                    "UPDATE schedule SET season_type=?, season=? WHERE id=?",
                    (new_st, new_season, rid),
                )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule(game_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_teams ON schedule(home_team, away_team)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_schedule_espn ON schedule(espn_id)")
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
    finally:
        conn.close()


ensure_schedule_schema()


def ensure_champions_schema():
    """champions 表由 import_champions.py 导入；旧库打开时也能自动建表。"""
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS champions ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, season TEXT UNIQUE, champion TEXT, "
            "champion_abbr TEXT, runner_up TEXT, series TEXT, fmvp TEXT, "
            "fmvp_team_abbr TEXT, source TEXT)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_champions_season ON champions (season)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_champions_abbr ON champions (champion_abbr)")
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
    finally:
        conn.close()


ensure_champions_schema()


def tipoff_parts(iso_utc):
    """ISO UTC -> (北京日期, 北京时间 HH:MM)。"""
    if not iso_utc:
        return None, None
    try:
        dt = datetime.fromisoformat(str(iso_utc).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cn = dt.astimezone(CN_TZ)
        return cn.strftime("%Y-%m-%d"), cn.strftime("%H:%M")
    except (ValueError, TypeError):
        return None, None


def tipoff_from_status(game_date, status):
    """旧数据没有 tipoff_utc 时，从 '7:00 pm ET' 推一个时间，方便展示。"""
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*([ap]m)\s*ET\s*$", status or "", re.I)
    if not m:
        return None
    try:
        h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
        dt = datetime.strptime((game_date or "")[:10], "%Y-%m-%d").replace(
            hour=h, minute=int(m.group(2)), tzinfo=ET_TZ
        )
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def game_state(row):
    status = (row.get("game_status") or "").strip()
    if status.startswith("Final"):
        return "final"
    if status.lower() in ("in progress", "halftime", "end of period", "status_in_progress"):
        return "live"
    return "scheduled"


# ---------- 今日比分自动刷新（后台线程，不阻塞页面请求） ----------
_ESPN_REFRESH_LOCK = threading.Lock()
_ESPN_LAST_REFRESH = 0.0
_ESPN_REFRESH_STATUS = "idle"


def _espn_refresh_worker():
    global _ESPN_LAST_REFRESH, _ESPN_REFRESH_STATUS
    try:
        if espn_sync is None:
            raise RuntimeError("ESPN 同步模块不可用")
        today = datetime.now(timezone.utc).astimezone(ET_TZ).date()
        conn = sqlite3.connect(DB)
        try:
            espn_sync.ensure_schema(conn)
            seen = set()
            # 今天 + 昨天：覆盖西海岸晚场比赛跨美东午夜的情况
            for delta in (-1, 0):
                day = today + timedelta(days=delta)
                data = espn_sync.get_json(day)
                espn_sync.sync_events(conn, data.get("events", []) or [], False, seen)
            conn.commit()
        finally:
            conn.close()
        _ESPN_REFRESH_STATUS = datetime.now(CN_TZ).strftime("ok %H:%M:%S")
    except Exception as e:
        _ESPN_REFRESH_STATUS = f"error: {e}"
    finally:
        _ESPN_LAST_REFRESH = time.time()
        _ESPN_REFRESH_LOCK.release()


def request_espn_refresh(min_interval=60):
    """前端轮询触发；同一时间只跑一个后台线程，失败也不会影响页面。"""
    if espn_sync is None:
        return False
    if time.time() - _ESPN_LAST_REFRESH < min_interval:
        return False
    if not _ESPN_REFRESH_LOCK.acquire(blocking=False):
        return False
    threading.Thread(target=_espn_refresh_worker, daemon=True).start()
    return True


# ---------- 伤病/出战成疑自动刷新（5 分钟节流，后台线程） ----------
_INJURY_REFRESH_LOCK = threading.Lock()
_INJURY_LAST_REFRESH = 0.0
_INJURY_REFRESH_STATUS = "idle"


def _injury_refresh_worker():
    global _INJURY_LAST_REFRESH, _INJURY_REFRESH_STATUS
    try:
        if injury_sync is None:
            raise RuntimeError("伤病同步模块不可用")
        conn = sqlite3.connect(DB)
        try:
            injury_sync.ensure_schema(conn)
            injury_sync.sync(conn)
        finally:
            conn.close()
        _INJURY_REFRESH_STATUS = datetime.now(CN_TZ).strftime("ok %H:%M:%S")
    except Exception as e:
        _INJURY_REFRESH_STATUS = f"error: {e}"
    finally:
        _INJURY_LAST_REFRESH = time.time()
        _INJURY_REFRESH_LOCK.release()


def request_injury_refresh(min_interval=300):
    if injury_sync is None:
        return False
    if time.time() - _INJURY_LAST_REFRESH < min_interval:
        return False
    if not _INJURY_REFRESH_LOCK.acquire(blocking=False):
        return False
    threading.Thread(target=_injury_refresh_worker, daemon=True).start()
    return True


# ---------- 名字归一化与跨表解析（常规赛 player_id <-> 季后赛球员名） ----------
def norm_name(s):
    """去重音/标点/大小写：Luka Dončić -> luka doncic；Doncic -> luka doncic"""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ")
    s = s.replace(" jr", "").replace(" sr", "").replace(" iii", "").replace(" ii", "")
    return " ".join(s.split())


# 位置归一化：PG/SG/Guard -> G(后卫)，SF/PF/Forward -> F(前锋)，C/Center -> C(中锋)
_POS_MAP = {
    "pg": "G", "sg": "G", "g": "G", "guard": "G", "point guard": "G", "shooting guard": "G",
    "sf": "F", "pf": "F", "f": "F", "forward": "F", "small forward": "F", "power forward": "F",
    "c": "C", "center": "C",
}


def norm_pos(raw):
    """把任意位置写法归一为 G/F/C；混合位置（G-F / F-C）取首个主位置；无法识别返回 None。"""
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if not s:
        return None
    token = s.replace("/", "-").split("-")[0].strip()
    return _POS_MAP.get(token) or _POS_MAP.get(s)


def surname_of(name):
    """取英文姓氏，去掉 Jr./Sr./II/III 后缀。"""
    s = re.sub(r"\s+(Jr\.?|Sr\.?|III|II|IV)\s*$", "", str(name or "").strip(), flags=re.I)
    parts = s.split()
    return parts[-1] if parts else ""


def _pick_by_name(rows, target, name_col="player"):
    """在 rows 中按归一化名字挑最匹配的行（先精确后包含，平局取出场数 g 多的）。"""
    t = norm_name(target)
    if not t:
        return None
    exact = [r for r in rows if norm_name(r[name_col]) == t]
    pool = exact
    if not pool:
        pool = [r for r in rows if t in norm_name(r[name_col]) or norm_name(r[name_col]) in t]
    if not pool:
        return None
    return max(pool, key=lambda r: r.get("g", 0) or 0)


def resolve_reg_pid(pid, season):
    """常规赛：player_id 精确匹配优先；否则按球员名（归一化）兜底解析。"""
    rows = query("SELECT player_id FROM player WHERE player_id=? AND season=? AND g>0", (pid, season))
    if rows:
        return rows[0]["player_id"]
    rows = query("SELECT player_id, player, g FROM player WHERE season=? AND g>0", (season,))
    hit = _pick_by_name(rows, pid)
    return hit["player_id"] if hit else None


def resolve_reg_pid_all(pid):
    """常规赛跨赛季解析（用于趋势接口）。"""
    rows = query("SELECT DISTINCT player_id FROM player WHERE player_id=? AND g>0", (pid,))
    if rows:
        return rows[0]["player_id"]
    rows = query("SELECT player_id, player, SUM(g) AS g FROM player WHERE g>0 GROUP BY player_id, player")
    hit = _pick_by_name(rows, pid)
    return hit["player_id"] if hit else None


def resolve_po_pid(pid, season):
    """季后赛：球员名精确匹配优先；否则归一化兜底；
    仍失败时（pid 可能是常规赛 player_id）先查常规赛姓名，再用姓名匹配季后赛。"""
    rows = query("SELECT player FROM playoff WHERE player=? AND season=? AND g>0", (pid, season))
    if rows:
        return rows[0]["player"]
    rows = query("SELECT player, g FROM playoff WHERE season=? AND g>0", (season,))
    hit = _pick_by_name(rows, pid)
    if hit:
        return hit["player"]
    # 经常规赛表反查姓名（id -> 名字 -> 季后赛）
    reg_real = resolve_reg_pid(pid, season)
    if reg_real:
        reg_rows = query(
            "SELECT player FROM player WHERE player_id=? AND season=? AND g>0 LIMIT 1",
            (reg_real, season),
        )
        if reg_rows:
            hit = _pick_by_name(rows, reg_rows[0]["player"])
            if hit:
                return hit["player"]
    return None


def resolve_po_pid_all(pid):
    """季后赛跨赛季解析。"""
    rows = query("SELECT DISTINCT player FROM playoff WHERE player=? AND g>0", (pid,))
    if rows:
        return rows[0]["player"]
    rows = query("SELECT player, SUM(g) AS g FROM playoff WHERE g>0 GROUP BY player")
    hit = _pick_by_name(rows, pid)
    return hit["player"] if hit else None


def stat_row(pid, season, stage):
    """统一取球员某赛季场均统计。
    stage=reg -> player 表（累计值 /g 得场均，pid=player_id 或球员名均可）
    stage=po  -> playoff 表（已是场均，pid=球员名）"""
    if stage == "po":
        real = resolve_po_pid(pid, season)
        if not real:
            return None
        rows = query(
            "SELECT player, team, pos, age, g, gs, mp, pts, trb, ast, stl, blk, tov, "
            "fg_pct, x3p_pct, ft_pct FROM playoff WHERE player=? AND season=?",
            (real, season),
        )
        if not rows:
            return None
        r = rows[0]
        return {
            "pid": r["player"], "name": r["player"], "team": fix_team(r["team"]), "pos": r["pos"],
            "age": r["age"], "season": season,
            "g": r["g"], "gs": r["gs"], "mp": round(r["mp"] or 0, 1),
            "pts": r["pts"] or 0, "reb": r["trb"] or 0, "ast": r["ast"] or 0,
            "stl": r["stl"] or 0, "blk": r["blk"] or 0, "tov": r["tov"] or 0,
            "fg": r["fg_pct"], "x3p": r["x3p_pct"], "ft": r["ft_pct"],
            "per": None, "ws": None, "vorp": None,
        }
    real = resolve_reg_pid(pid, season)
    if not real:
        return None
    rows = query(
        "SELECT player, player_id, team, pos, age, g, gs, mp, pts, trb, ast, stl, blk, tov, "
        "fg_percent, x3p_percent, ft_percent FROM player "
        "WHERE player_id=? AND season=? AND g>0 "
        "ORDER BY CASE WHEN team LIKE '%TM' THEN 0 ELSE 1 END, g DESC",
        (real, season),
    )
    if not rows:
        return None
    r = rows[0]
    g = r["g"]

    # 交易球员：优先使用 2TM/3TM 合计行，展示为“多队（球队列表）”
    team_disp = fix_team(r["team"])
    if (r["team"] or "").endswith("TM"):
        team_rows = query(
            "SELECT team FROM player WHERE player_id=? AND season=? AND g>0 "
            "AND team NOT LIKE '%TM' ORDER BY g DESC",
            (real, season),
        )
        names = [fix_team(t["team"]) for t in team_rows if t["team"]]
        team_disp = "多队（" + "/".join(names) + "）" if names else "多队"

    def per(v):
        return round(v / g, 2) if (v is not None and g) else None

    return {
        "pid": r["player_id"], "name": r["player"], "team": team_disp, "pos": r["pos"],
        "age": r["age"], "season": season,
        "g": g, "gs": r["gs"], "mp": round(r["mp"] / g, 1) if r["mp"] is not None else None,
        "pts": per(r["pts"]), "reb": per(r["trb"]), "ast": per(r["ast"]),
        "stl": per(r["stl"]), "blk": per(r["blk"]), "tov": per(r["tov"]),
        "fg": r["fg_percent"], "x3p": r["x3p_percent"], "ft": r["ft_percent"],
        "per": None, "ws": None, "vorp": None,
    }


def check_availability(pid, season, stage, cn=False):
    """查不到数据时给出区分性原因：
    po：球队未进季后赛 / 球队进了但球员未出场（伤病·未进入轮换）
    reg：该赛季无常规赛记录。cn=True 时人名/球队转中文。"""
    pn = (lambda s: cn_player(s) if cn else s)
    tn = (lambda s: team_label(s) if cn else fix_team(s))
    season_txt = f"{season} 赛季" if season else "该赛季"
    if stage == "po":
        # 先找该球员在该赛季常规赛的归属球队（交易球员可能有多支）
        reg_real = resolve_reg_pid(pid, season)
        if reg_real:
            reg = query(
                "SELECT player, team FROM player WHERE player_id=? AND season=? AND g>0 "
                "ORDER BY CASE WHEN team LIKE '%TM' THEN 1 ELSE 0 END, g DESC",
                (reg_real, season),
            )
            if reg:
                name = reg[0]["player"]
                teams = []
                for row in reg:
                    t = row["team"] or ""
                    if not t.endswith("TM") and t not in teams:
                        teams.append(t)
                if teams:
                    variants = sorted({v for t in teams for v in team_variants(t)})
                    in_po = query(
                        "SELECT 1 FROM playoff WHERE season=? AND team IN (%s) LIMIT 1"
                        % ",".join("?" * len(variants)),
                        [season, *variants],
                    )
                    teams_txt = "/".join(tn(t) for t in teams)
                    if in_po:
                        return {
                            "code": "player_inactive",
                            "message": f"{pn(name)} 所在的 {teams_txt} 进入了 {season} 季后赛，但本人未出场（可能因伤缺席或未进入轮换）",
                        }
                    return {
                        "code": "no_playoff_team",
                        "message": f"{pn(name)} 所在的 {teams_txt} 未进入 {season} 季后赛",
                    }
        # 常规赛表里没有该赛季记录：看该球员是否打过任意赛季季后赛
        po_all = resolve_po_pid_all(pid)
        if po_all:
            return {
                "code": "player_inactive",
                "message": f"{pn(po_all)} 在 {season_txt}季后赛未出场（可能因伤缺席、未进入轮换或当季未在 NBA）",
            }
        return {"code": "no_record", "message": f"{season_txt}未查询到 {pn(str(pid))} 的数据记录"}
    return {
        "code": "no_reg_record",
        "message": f"{pn(str(pid))} 在 {season_txt}无常规赛记录（可能尚未进入联盟、已退役或当季未出场）",
    }


def stats_table(stage):
    return "playoff" if stage == "po" else "player"


# 历史球队缩写 -> 现役标准缩写（与 import_playoffs 保持一致）
TEAM_ABBR_FIX = {
    "BRK": "BKN", "NJN": "BKN",
    "PHO": "PHX",
    "CHO": "CHA", "CHH": "CHA",
    "NOH": "NOP", "NOK": "NOP",
    "WSB": "WAS", "WSC": "WAS",
    "VAN": "MEM",
}


def fix_team(abbr):
    return TEAM_ABBR_FIX.get(abbr, abbr)


def team_variants(abbr):
    """双向别名组：无论传入现役缩写（BKN）还是历史写法（BRK/NJN），
    都返回同一组可能出现在 player/playoff 表里的球队缩写。"""
    if not abbr:
        return set()
    std = TEAM_ABBR_FIX.get(abbr, abbr)
    out = {abbr, std}
    for raw, std2 in TEAM_ABBR_FIX.items():
        if std2 == std:
            out.add(raw)
    return out


def team_label(abbr):
    """展示用队名：先修正历史/异写缩写，再转中文；未知队退回缩写。"""
    return cn_team(fix_team(abbr))


# ---------- 冠军 / FMVP / 当家球星 ----------
_TITLE_COUNTS_CACHE = None
_FMVP_COUNTS_CACHE = None
_STAR_CACHE = None


def team_title_counts():
    """现役球队的队史总冠军数（历史前身已合并，如 Minneapolis Lakers -> LAL）。"""
    global _TITLE_COUNTS_CACHE
    if _TITLE_COUNTS_CACHE is None:
        rows = query(
            "SELECT champion_abbr AS abbr, COUNT(*) AS n FROM champions "
            "WHERE champion_abbr IS NOT NULL AND champion_abbr != '' "
            "GROUP BY champion_abbr"
        )
        _TITLE_COUNTS_CACHE = {fix_team(r["abbr"]): r["n"] for r in rows}
    return _TITLE_COUNTS_CACHE


def team_title_count(abbr):
    return team_title_counts().get(fix_team(abbr), 0)


def fmvp_count_map():
    """归一化姓名 -> {name, count}，用于球员 FMVP 标签与冠军墙。"""
    global _FMVP_COUNTS_CACHE
    if _FMVP_COUNTS_CACHE is None:
        rows = query(
            "SELECT season, fmvp FROM champions "
            "WHERE fmvp IS NOT NULL AND TRIM(fmvp) != '' "
            "ORDER BY CAST(season AS INTEGER)"
        )
        out = {}
        for r in rows:
            name = (r["fmvp"] or "").replace("\xa0", " ").strip()
            key = norm_name(name)
            if not key:
                continue
            item = out.setdefault(key, {"name": name, "count": 0})
            item["name"] = name
            item["count"] += 1
        _FMVP_COUNTS_CACHE = out
    return _FMVP_COUNTS_CACHE


def fmvp_count_for(name):
    return fmvp_count_map().get(norm_name(name), {}).get("count", 0)


def franchise_stars():
    """按最近一个有统计的赛季，取每队场均得分最高的球员作为“当家球星”。"""
    global _STAR_CACHE
    if _STAR_CACHE is None:
        season_row = query("SELECT MAX(CAST(season AS INTEGER)) AS s FROM player")
        season = season_row[0]["s"] if season_row else None
        out = {}
        if season:
            rows = query(
                "SELECT player, player_id, team, g, pts FROM player "
                "WHERE season=? AND g>=20 AND team NOT LIKE '%TM' AND pts IS NOT NULL",
                (str(season),),
            )
            for r in rows:
                ppg = (r["pts"] or 0) / r["g"]
                key = fix_team(r["team"])
                cur = out.get(key)
                if not cur or ppg > cur["ppg"]:
                    out[key] = {
                        "player": r["player"],
                        "player_id": r["player_id"],
                        "team": key,
                        "ppg": round(ppg, 1),
                        "g": r["g"],
                        "season": str(season),
                    }
        _STAR_CACHE = out
    return _STAR_CACHE


def team_star(abbr):
    return franchise_stars().get(fix_team(abbr))


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# 筛选数据接口
# ---------------------------------------------------------------------------
@app.route("/api/seasons")
def api_seasons():
    """全部赛季列表（倒序）。stage=po 时用季后赛表（1950-2025）。"""
    stage = request.args.get("stage", "reg")
    tbl = stats_table(stage)
    rows = query(f"SELECT DISTINCT season FROM {tbl} ORDER BY CAST(season AS INTEGER) DESC")
    return jsonify([r["season"] for r in rows])


@app.route("/api/teams")
def api_teams():
    """某赛季的球队列表（含全称、中文名）。排除 2TM/3TM 等多队合计行。"""
    season = request.args.get("season", "")
    rows = query(
        "SELECT DISTINCT p.team AS abbr, COALESCE(t.team, p.team) AS name "
        "FROM player p LEFT JOIN team t ON t.abbreviation = p.team AND t.season = p.season "
        "WHERE p.season = ? AND p.team IS NOT NULL AND p.team NOT LIKE '%TM' ORDER BY name",
        (season,),
    )
    out, seen = [], set()
    for r in rows:
        abbr = r["abbr"]
        if not abbr or abbr in seen:
            continue
        seen.add(abbr)
        out.append({
            "abbr": abbr,
            "name": r["name"],
            "name_zh": team_label(abbr),
            "canonical": fix_team(abbr),
        })
    return jsonify(out)


@app.route("/api/players")
def api_players():
    """某赛季（可选球队）的球员列表，按得分降序。
    stage=po 时返回季后赛球员（pid 用球员名）。"""
    season = request.args.get("season", "")
    team = request.args.get("team", "")
    stage = request.args.get("stage", "reg")
    if stage == "po":
        sql = "SELECT player, team, pos, age, g, pts FROM playoff WHERE season = ? AND g > 0"
        args = [season]
        if team:
            vs = team_variants(team)
            sql += " AND team IN (%s)" % ",".join("?" * len(vs))
            args.extend(sorted(vs))
        sql += " ORDER BY pts DESC LIMIT 60"
        rows = query(sql, args)
        return jsonify(
            [{"player_id": r["player"], "player": r["player"], "team": fix_team(r["team"]),
              "pos": r["pos"], "age": r["age"], "g": r["g"], "pts": r["pts"]} for r in rows]
        )
    sql = "SELECT player_id, player, team, pos, age, g, pts FROM player WHERE season = ? AND g > 0 AND team NOT LIKE '%TM'"
    args = [season]
    if team:
        vs = team_variants(team)
        sql += " AND team IN (%s)" % ",".join("?" * len(vs))
        args.extend(sorted(vs))
    sql += " ORDER BY pts DESC LIMIT 60"
    rows = query(sql, args)
    out = []
    for r in rows:
        d = dict(r)
        d["team"] = fix_team(d["team"])
        out.append(d)
    return jsonify(out)


# ---------------------------------------------------------------------------
# 图表接口（返回 ECharts option JSON，前端 setOption 渲染）
# ---------------------------------------------------------------------------
@app.route("/api/bar")
def api_bar():
    """柱状图：某赛季各球队总得分 TOP15。
    stage=po 时用 SUM(pts*g)（球队季后赛总得分），不再用 AVG(球员场均)。"""
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    cn = request.args.get("cn") == "1"
    tn = (lambda r: team_label(r["abbr"]) if cn else (r["name"] or r["abbr"]))
    if stage == "po":
        rows = query(
            "SELECT team AS abbr, COALESCE((SELECT t.team FROM team t WHERE t.abbreviation=p.team "
            "AND t.season=p.season LIMIT 1), p.team) AS name, "
            "ROUND(SUM(pts * g), 0) AS total "
            "FROM playoff p WHERE season=? AND g>0 AND team NOT LIKE '%TM' "
            "GROUP BY team ORDER BY total DESC LIMIT 15",
            (season,),
        )
        names = [tn(r) for r in rows][::-1]
        values = [r["total"] for r in rows][::-1]
        bar = (
            Bar()
            .add_xaxis(names)
            .add_yaxis("季后赛总得分", values)
            .set_global_opts(
                title_opts=opts.TitleOpts(title=f"NBA {season} 季后赛 各队总得分 TOP15"),
                xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=10, rotate=40)),
            )
        )
        return chart_json(bar)
    rows = query(
        "SELECT p.team AS abbr, COALESCE(t.team, p.team) AS name, SUM(p.pts) AS total "
        "FROM player p LEFT JOIN team t ON t.abbreviation = p.team AND t.season = p.season "
        "WHERE p.season = ? AND p.team NOT LIKE '%TM' GROUP BY p.team ORDER BY total DESC LIMIT 15",
        (season,),
    )
    names = [tn(r) for r in rows][::-1]
    values = [round(r["total"]) for r in rows][::-1]
    bar = (
        Bar()
        .add_xaxis(names)
        .add_yaxis("赛季总得分", values)
        .set_global_opts(
            title_opts=opts.TitleOpts(title=f"NBA {season} 赛季 各球队总得分 TOP15"),
            xaxis_opts=opts.AxisOpts(axislabel_opts=opts.LabelOpts(font_size=10, rotate=40)),
        )
    )
    return chart_json(bar)


_RADAR_BASE_CACHE = {}


def radar_baseline(season, stage):
    """六维雷达的固定刻度：该赛季同类型球员的联盟最高场均（至少 1）。
    之前每个轴用“当前球员 × 1.4”，导致不同球员的雷达无法横向比较。"""
    key = (season, stage)
    if key in _RADAR_BASE_CACHE:
        return _RADAR_BASE_CACHE[key]
    base = [1, 1, 1, 1, 1, 1]
    try:
        if stage == "po":
            row = query(
                "SELECT MAX(pts) p, MAX(trb) r, MAX(ast) a, MAX(stl) s, "
                "MAX(blk) b, MAX(tov) t FROM playoff WHERE season=? AND g>=4",
                (season,),
            )
        else:
            row = query(
                "SELECT MAX(pts*1.0/g) p, MAX(trb*1.0/g) r, MAX(ast*1.0/g) a, "
                "MAX(stl*1.0/g) s, MAX(blk*1.0/g) b, MAX(tov*1.0/g) t "
                "FROM player WHERE season=? AND g>=20 AND team NOT LIKE '%TM'",
                (season,),
            )
        if row:
            vals = [row[0].get(k) for k in ("p", "r", "a", "s", "b", "t")]
            base = [max(round((v or 1) * 1.1, 2), 1) for v in vals]
    except sqlite3.Error:
        pass
    _RADAR_BASE_CACHE[key] = base
    return base


@app.route("/api/radar")
def api_radar():
    """雷达图：球员六维能力（得分/篮板/助攻/抢断/盖帽/失误，场均）。
    stage=reg / po 均支持；刻度用联盟同期最高值，便于横向比较。"""
    pid = request.args.get("player_id")
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    cn = request.args.get("cn") == "1"
    r = stat_row(pid, season, stage)
    if not r:
        return jsonify({})
    disp = cn_player(r["name"]) if cn else r["name"]
    names = ["得分", "篮板", "助攻", "抢断", "盖帽", "失误"]
    vals = [r["pts"] or 0, r["reb"] or 0, r["ast"] or 0,
            r["stl"] or 0, r["blk"] or 0, r["tov"] or 0]
    schema = [{"name": n, "max": m} for n, m in zip(names, radar_baseline(season, stage))]
    label = f"{disp} {season} {'季后赛' if stage=='po' else '常规赛'}"
    option = {
        "title": {"text": f"{disp} 六维能力雷达", "left": "center"},
        "tooltip": {},
        "legend": {"data": [label], "bottom": 0},
        "radar": {
            "indicator": schema,
            "radius": "65%",
            "splitNumber": 4,
        },
        "series": [
            {
                "type": "radar",
                "name": label,
                "data": [{"value": vals, "name": label}],
                "areaStyle": {"opacity": 0.25},
                "lineStyle": {"width": 2},
                "symbolSize": 6,
            }
        ],
    }
    return jsonify(option)


@app.route("/api/line")
def api_line():
    """折线图：球员生涯场均得分趋势。stage=po 时查季后赛表。"""
    pid = request.args.get("player_id")
    stage = request.args.get("stage", "reg")
    cn = request.args.get("cn") == "1"
    if stage == "po":
        rows = query(
            "SELECT player, season, pts FROM playoff "
            "WHERE player=? AND g>0 ORDER BY CAST(season AS INTEGER)",
            (pid,),
        )
        if not rows:
            return jsonify({})
        seasons = [r["season"] for r in rows]
        avg = [round(r["pts"], 1) for r in rows]
        disp = cn_player(rows[0]["player"]) if cn else rows[0]["player"]
        title = f"{disp} 季后赛生涯场均得分趋势"
    else:
        raw = query(
            "SELECT player, season, g, pts, team FROM player "
            "WHERE player_id = ? AND g > 0 "
            "ORDER BY CAST(season AS INTEGER), "
            "CASE WHEN team LIKE '%TM' THEN 0 ELSE 1 END, g DESC",
            (pid,),
        )
        if not raw:
            return jsonify({})
        # 每个赛季只取一行：优先 2TM/3TM 合计行，其次出场最多的球队行
        rows, seen = [], set()
        for row in raw:
            if row["season"] in seen:
                continue
            seen.add(row["season"])
            rows.append(row)
        seasons = [r["season"] for r in rows]
        avg = [round(r["pts"] / r["g"], 1) if r["g"] else None for r in rows]
        disp = cn_player(rows[0]["player"]) if cn else rows[0]["player"]
        title = f"{disp} 生涯场均得分趋势"
    line = (
        Line()
        .add_xaxis(seasons)
        .add_yaxis("场均得分", avg, is_smooth=True)
        .set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            xaxis_opts=opts.AxisOpts(type_="category"),
        )
    )
    return chart_json(line)


@app.route("/api/player_detail")
def api_player_detail():
    """下钻：球员某赛季完整统计（场均）。stage=reg / po 均支持。
    无数据时返回 reason（区分未进季后赛/伤病未参赛）。"""
    pid = request.args.get("player_id")
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    r = stat_row(pid, season, stage)
    if not r:
        return jsonify({"reason": check_availability(pid, season, stage, request.args.get("cn") == "1")})
    r["name_en"] = r["name"]
    r["fmvp_count"] = fmvp_count_for(r["name"])
    r["team_titles"] = team_title_count(r["team"])
    if request.args.get("cn") == "1" and r.get("name"):
        r["name"] = cn_player(r["name"])
    return jsonify(r)


# 全指标趋势的指标定义（顺序即展示顺序）
TREND_DIMS = [
    ("pts", "场均得分"), ("reb", "场均篮板"), ("ast", "场均助攻"),
    ("stl", "场均抢断"), ("blk", "场均盖帽"), ("tov", "场均失误"),
    ("mp", "场均时间(分钟)"), ("fg", "投篮命中率%"), ("x3p", "三分命中率%"), ("ft", "罚球命中率%"),
]


@app.route("/api/player_trends")
def api_player_trends():
    """单球员多赛季全指标趋势。
    range=5/10/all：近 N 个赛季 / 全部；stage=reg / po。"""
    pid = request.args.get("player_id")
    stage = request.args.get("stage", "reg")
    rng = request.args.get("range", "5")
    cn = request.args.get("cn") == "1"
    if stage == "po":
        real = resolve_po_pid_all(pid)
        if not real:
            return jsonify({"reason": check_availability(pid, "", "po", cn)})
        rows = query(
            "SELECT season, g, mp, pts, trb, ast, stl, blk, tov, fg_pct, x3p_pct, ft_pct "
            "FROM playoff WHERE player=? AND g>0 ORDER BY CAST(season AS INTEGER)",
            (real,),
        )
        name = real
        recs = []
        for r in rows:
            recs.append({
                "season": r["season"],
                "pts": r["pts"], "reb": r["trb"], "ast": r["ast"], "stl": r["stl"],
                "blk": r["blk"], "tov": r["tov"],
                "mp": round(r["mp"], 1) if r["mp"] is not None else None,
                "fg": round(r["fg_pct"] * 100, 1) if r["fg_pct"] is not None else None,
                "x3p": round(r["x3p_pct"] * 100, 1) if r["x3p_pct"] is not None else None,
                "ft": round(r["ft_pct"] * 100, 1) if r["ft_pct"] is not None else None,
            })
    else:
        real = resolve_reg_pid_all(pid)
        if not real:
            return jsonify({"reason": check_availability(pid, "", "reg", cn)})
        raw = query(
            "SELECT player, season, g, mp, pts, trb, ast, stl, blk, tov, "
            "fg_percent, x3p_percent, ft_percent, team FROM player "
            "WHERE player_id=? AND g>0 "
            "ORDER BY CAST(season AS INTEGER), "
            "CASE WHEN team LIKE '%TM' THEN 0 ELSE 1 END, g DESC",
            (real,),
        )
        # 每个赛季取一行：优先 2TM/3TM 合计行
        rows, seen = [], set()
        for row in raw:
            if row["season"] in seen:
                continue
            seen.add(row["season"])
            rows.append(row)
        name = rows[0]["player"] if rows else real
        recs = []

        def div(v, g):
            return round(v / g, 1) if (v is not None and g) else None

        for r in rows:
            g = r["g"]
            recs.append({
                "season": r["season"],
                "pts": div(r["pts"], g), "reb": div(r["trb"], g),
                "ast": div(r["ast"], g), "stl": div(r["stl"], g),
                "blk": div(r["blk"], g), "tov": div(r["tov"], g),
                "mp": div(r["mp"], g),
                "fg": round(r["fg_percent"] * 100, 1) if r["fg_percent"] is not None else None,
                "x3p": round(r["x3p_percent"] * 100, 1) if r["x3p_percent"] is not None else None,
                "ft": round(r["ft_percent"] * 100, 1) if r["ft_percent"] is not None else None,
            })
    # 补齐连续赛季轴：未参赛（伤停/未进季后赛）的年份各指标置 null，
    # 但仍保留该年的横轴刻度与数据点位置；range=5/10 按“年份个数”截取。
    have = {int(r["season"]): r for r in recs}
    if have:
        ys = sorted(have.keys())
        lo, hi = ys[0], ys[-1]
        if rng in ("5", "10"):
            lo = max(lo, hi - int(rng) + 1)
        dim_keys = [k for k, _ in TREND_DIMS]
        recs = [
            have[y] if y in have
            else dict({"season": str(y)}, **{k: None for k in dim_keys})
            for y in range(lo, hi + 1)
        ]
    seasons = [r["season"] for r in recs]
    series = [
        {"key": k, "label": label, "data": [r.get(k) for r in recs]}
        for k, label in TREND_DIMS
    ]
    disp_name = cn_player(name) if request.args.get("cn") == "1" else name
    return jsonify({"name": disp_name, "seasons": seasons, "series": series})


# ===========================================================================
# 主队关注 & 特色功能（第一梯队 + 对位对比 + 加分项）
# ===========================================================================

# ---------- 偏好存取（主队、观察名单共用） ----------
def get_pref(key):
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS user_pref ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, pref_key TEXT UNIQUE, pref_value TEXT)"
        )
        r = conn.execute("SELECT pref_value FROM user_pref WHERE pref_key=?", (key,)).fetchone()
        return r[0] if r else None
    finally:
        conn.close()


def set_pref(key, value):
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS user_pref ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, pref_key TEXT UNIQUE, pref_value TEXT)"
        )
        conn.execute("INSERT OR REPLACE INTO user_pref (pref_key, pref_value) VALUES (?,?)", (key, value))
        conn.commit()
    finally:
        conn.close()


# ---------- 主队关注（支持多支 + 默认主队 + 取消关注） ----------
@app.route("/api/fav_team", methods=["GET"])
def api_fav_team_get():
    teams = json.loads(get_pref("fav_teams") or "[]")
    # 兼容旧版单主队存储
    if not teams:
        old = get_pref("fav_team")
        if old:
            teams = [old]
            set_pref("fav_teams", json.dumps(teams))
    active = get_pref("fav_active") or (teams[0] if teams else None)
    if active not in teams:
        active = teams[0] if teams else None
    out = []
    for abbr in teams:
        row = query(
            "SELECT DISTINCT team FROM team WHERE abbreviation=? AND lg='NBA' "
            "ORDER BY CAST(season AS INTEGER) DESC LIMIT 1",
            (abbr,),
        )
        out.append({"team": abbr, "name": row[0]["team"] if row else abbr})
    return jsonify({"teams": out, "active": active})


@app.route("/api/fav_team", methods=["POST"])
def api_fav_team_add():
    data = request.get_json(silent=True) or {}
    team = data.get("team") or request.args.get("team", "")
    if not team:
        return jsonify({"ok": False, "msg": "缺少 team"})
    teams = json.loads(get_pref("fav_teams") or "[]")
    if team not in teams:
        if len(teams) >= 5:
            return jsonify({"ok": False, "msg": "最多关注 5 支主队"})
        teams.append(team)
        set_pref("fav_teams", json.dumps(teams))
    if not get_pref("fav_active"):
        set_pref("fav_active", team)
    return jsonify({"ok": True, "teams": teams})


@app.route("/api/fav_team/remove", methods=["POST"])
def api_fav_team_remove():
    data = request.get_json(silent=True) or {}
    team = data.get("team") or request.args.get("team", "")
    teams = json.loads(get_pref("fav_teams") or "[]")
    if team in teams:
        teams.remove(team)
        set_pref("fav_teams", json.dumps(teams))
    if get_pref("fav_active") == team:
        set_pref("fav_active", teams[0] if teams else "")
    return jsonify({"ok": True, "teams": teams})


@app.route("/api/fav_team/active", methods=["POST"])
def api_fav_team_active():
    data = request.get_json(silent=True) or {}
    team = data.get("team") or request.args.get("team", "")
    teams = json.loads(get_pref("fav_teams") or "[]")
    if team in teams:
        set_pref("fav_active", team)
    return jsonify({"ok": True, "active": team})


# ---------- 主队赛程看板 ----------
# 高强度对手：2025 赛季进入季后赛的球队（来自 Kaggle team 表 playoffs=1，真实数据）
STRONG_TEAMS = {"ATL", "BOS", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU",
                "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NYK", "OKC", "ORL", "SAC"}

# 球队分区映射（NBA 30 队）
EAST_TEAMS = {"ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA",
              "MIL", "NYK", "ORL", "PHI", "TOR", "WAS"}
WEST_TEAMS = {"DAL", "DEN", "GSW", "HOU", "LAC", "LAL", "MEM", "MIN", "NOP",
              "OKC", "PHX", "POR", "SAC", "SAS", "UTA"}


@app.route("/api/schedule")
def api_schedule():
    """主队赛程：已打/未打/进行中、主客场、胜负、北京时间、赛制标签。"""
    team = request.args.get("team", "")
    rows = query(
        "SELECT game_date, home_team, away_team, home_score, away_score, game_status, "
        "season_type, season, tipoff_utc, espn_id "
        "FROM schedule WHERE home_team=? OR away_team=? "
        "ORDER BY game_date, COALESCE(tipoff_utc, '')",
        (team, team),
    )
    out = []
    for r in rows:
        is_home = r["home_team"] == team
        opp = r["away_team"] if is_home else r["home_team"]
        iso = r["tipoff_utc"] or tipoff_from_status(r["game_date"], r["game_status"])
        date_cn, time_cn = tipoff_parts(iso)
        if not date_cn:
            date_cn, time_cn = (r["game_date"], None)
        state = game_state(r)
        played = state == "final"
        live = state == "live"
        my = r["home_score"] if is_home else r["away_score"]
        op = r["away_score"] if is_home else r["home_score"]
        has_score = my is not None and op is not None
        out.append(
            {
                "game_date": r["game_date"],
                "date_cn": date_cn,
                "time_cn": time_cn,
                "tipoff_utc": iso,
                "is_home": is_home,
                "opponent": fix_team(opp),
                "played": played,
                "live": live,
                "result": ("W" if my > op else "L") if (played and has_score) else None,
                "score": f"{my}-{op}" if ((played or live) and has_score) else None,
                "status": r["game_status"],
                "status_label": "终场" if played else ("进行中" if live else "未开赛"),
                "season_type": r["season_type"] or "regular",
                "season": r["season"],
                "is_preseason": (r["season_type"] or "") == "preseason",
            }
        )
    # 标签：背靠背 / 连续客场 / 高强度对手（只对常规赛/季后赛有意义）
    for i, g in enumerate(out):
        tags = []
        if g["season_type"] in ("regular", "playoffs") and i > 0:
            try:
                d1 = datetime.strptime(out[i - 1]["game_date"], "%Y-%m-%d")
                d2 = datetime.strptime(g["game_date"], "%Y-%m-%d")
                if (d2 - d1).days == 1:
                    tags.append("背靠背")
            except (ValueError, TypeError):
                pass
        away_run = 0
        j = i
        while j >= 0 and not out[j]["is_home"]:
            away_run += 1
            if j == 0:
                break
            try:
                d1 = datetime.strptime(out[j]["game_date"], "%Y-%m-%d")
                d2 = datetime.strptime(out[j - 1]["game_date"], "%Y-%m-%d")
            except (ValueError, TypeError):
                break
            if (d1 - d2).days != 1:
                break
            j -= 1
        if away_run >= 2 and g["season_type"] in ("regular", "playoffs"):
            tags.append("连续客场")
        if g["opponent"] in STRONG_TEAMS and g["season_type"] in ("regular", "playoffs"):
            tags.append("高强度")
        g["tags"] = tags
    return jsonify(out)


@app.route("/api/recent_games")
def api_recent_games():
    """最近/即将进行的比赛（默认最近 2 天 + 未来 2 天，北京时间，ESPN 更新）。
    refresh=1 时后台拉一次 ESPN（60 秒节流），本次请求先返回数据库缓存。"""
    if request.args.get("refresh") == "1":
        request_espn_refresh(60)
    try:
        back = int(request.args.get("days_back", 2))
        ahead = int(request.args.get("days_ahead", 2))
    except ValueError:
        back, ahead = 2, 2
    back = max(0, min(back, 30))
    ahead = max(0, min(ahead, 30))
    include_preseason = request.args.get("include_preseason") == "1"
    now = datetime.now(timezone.utc)
    lo = now - timedelta(days=back)
    hi = now + timedelta(days=ahead)
    rows = query(
        "SELECT game_date, home_team, away_team, home_score, away_score, game_status, "
        "season_type, season, tipoff_utc, espn_id "
        "FROM schedule"
    )
    items = []
    for r in rows:
        st = r["season_type"] or "regular"
        if st == "preseason" and not include_preseason:
            continue
        iso = r["tipoff_utc"] or tipoff_from_status(r["game_date"], r["game_status"])
        try:
            dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00")) if iso else None
            if dt is None:
                dt = datetime.strptime((r["game_date"] or "")[:10], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
        except (ValueError, TypeError):
            continue
        if not (lo <= dt <= hi):
            continue
        date_cn, time_cn = tipoff_parts(iso)
        if not date_cn:
            date_cn, time_cn = (r["game_date"], None)
        state = game_state(r)
        items.append(
            {
                "game_date": r["game_date"],
                "date_cn": date_cn,
                "time_cn": time_cn,
                "tipoff_utc": iso,
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "home_zh": team_label(r["home_team"]),
                "away_zh": team_label(r["away_team"]),
                "home_score": r["home_score"],
                "away_score": r["away_score"],
                "status": r["game_status"],
                "status_label": "终场" if state == "final" else ("进行中" if state == "live" else "未开赛"),
                "played": state == "final",
                "live": state == "live",
                "season_type": st,
                "season": r["season"],
                "espn_id": r["espn_id"],
            }
        )
    items.sort(key=lambda g: g["tipoff_utc"] or g["game_date"] or "")
    return jsonify({
        "games": items[:24],
        "updated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "source": "ESPN",
    })


# ---------- 战绩状态（近10场/主客场/东西部/连胜连败） ----------
@app.route("/api/team_form")
def api_team_form():
    team = request.args.get("team", "")
    rows = query(
        "SELECT game_date, home_team, away_team, home_score, away_score "
        "FROM schedule WHERE (home_team=? OR away_team=?) AND game_status LIKE 'Final%' "
        "AND (season_type='regular' OR (season_type IS NULL AND game_id LIKE '002%')) "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY game_date, COALESCE(tipoff_utc, '')",
        (team, team),
    )
    form = []
    for r in rows:
        is_home = r["home_team"] == team
        my = r["home_score"] if is_home else r["away_score"]
        op = r["away_score"] if is_home else r["home_score"]
        form.append("W" if my > op else "L")

    recent10 = form[-10:]
    recent5 = form[-5:]
    streak, streak_type = 0, None
    if form:
        streak_type = form[-1]
        for f in reversed(form):
            if f == streak_type:
                streak += 1
            else:
                break
    home_w = sum(1 for r in rows if r["home_team"] == team and r["home_score"] > r["away_score"])
    home_g = sum(1 for r in rows if r["home_team"] == team)
    away_w = sum(1 for r in rows if r["away_team"] == team and r["away_score"] > r["home_score"])
    away_g = sum(1 for r in rows if r["away_team"] == team)
    # 对阵东西部对手
    east_w = east_g = west_w = west_g = 0
    for r in rows:
        is_home = r["home_team"] == team
        opp = r["away_team"] if is_home else r["home_team"]
        my = r["home_score"] if is_home else r["away_score"]
        op = r["away_score"] if is_home else r["home_score"]
        win = my > op
        if opp in EAST_TEAMS:
            east_g += 1
            east_w += 1 if win else 0
        elif opp in WEST_TEAMS:
            west_g += 1
            west_w += 1 if win else 0
    return jsonify(
        {
            "total": len(form),
            "wins": form.count("W"),
            "recent10": recent10,
            "recent5": recent5,
            "recent10_wins": recent10.count("W"),
            "recent5_wins": recent5.count("W"),
            "streak": streak,
            "streak_type": streak_type,
            "home": {"w": home_w, "g": home_g},
            "away": {"w": away_w, "g": away_g},
            "east": {"w": east_w, "g": east_g},
            "west": {"w": west_w, "g": west_g},
            "titles": team_title_count(team),
            "star": team_star(team),
        }
    )


@app.route("/api/standings")
def api_standings():
    """当前赛季东西部排名（由 schedule 已完赛常规赛实时计算）。"""
    season_row = query(
        "SELECT season FROM schedule WHERE season_type='regular' "
        "ORDER BY game_date DESC LIMIT 1"
    )
    season_name = season_row[0]["season"] if season_row else ""
    rows = query(
        "SELECT game_date, home_team, away_team, home_score, away_score "
        "FROM schedule WHERE season_type='regular' AND game_status LIKE 'Final%' "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "AND season=? ORDER BY game_date, COALESCE(tipoff_utc, '')",
        (season_name,),
    )
    stats = {}
    for abbr in TEAM_CN:
        stats[abbr] = {"w": 0, "l": 0, "pf": 0, "pa": 0, "results": []}
    for r in rows:
        home, away = fix_team(r["home_team"]), fix_team(r["away_team"])
        hs, as_ = r["home_score"], r["away_score"]
        if home not in stats or away not in stats:
            continue
        for team, my, opp in ((home, hs, as_), (away, as_, hs)):
            s = stats[team]
            s["pf"] += my
            s["pa"] += opp
            win = my > opp
            s["w"] += 1 if win else 0
            s["l"] += 0 if win else 1
            s["results"].append("W" if win else "L")

    def build(team_abbr):
        s = stats[team_abbr]
        games = s["w"] + s["l"]
        last10 = s["results"][-10:]
        streak = 0
        streak_type = None
        if s["results"]:
            streak_type = s["results"][-1]
            for x in reversed(s["results"]):
                if x == streak_type:
                    streak += 1
                else:
                    break
        star = team_star(team_abbr)
        return {
            "team": team_abbr,
            "name": cn_team(team_abbr),
            "w": s["w"], "l": s["l"], "g": games,
            "pct": round(s["w"] / games, 3) if games else 0.0,
            "pf": s["pf"], "pa": s["pa"], "diff": s["pf"] - s["pa"],
            "last10": last10,
            "streak": streak, "streak_type": streak_type,
            "titles": team_title_count(team_abbr),
            "star": star,
        }

    def sort_conf(teams):
        arr = [build(t) for t in teams]
        arr.sort(key=lambda x: (-x["pct"], -x["w"], -x["diff"], x["name"]))
        leader = arr[0] if arr else None
        for i, item in enumerate(arr, 1):
            item["seed"] = i
            if leader and leader["w"] + leader["l"]:
                # GB = ((领先者胜场 - 本队胜场) + (本队负场 - 领先者负场)) / 2
                gb = ((leader["w"] - item["w"]) + (item["l"] - leader["l"])) / 2
                item["gb"] = round(gb, 1)
            else:
                item["gb"] = 0.0
        return arr

    return jsonify({
        "season": season_name,
        "as_of": datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "east": sort_conf([t for t in TEAM_CN if t in EAST_TEAMS]),
        "west": sort_conf([t for t in TEAM_CN if t in WEST_TEAMS]),
    })


@app.route("/api/champions")
def api_champions():
    """历届冠军 / FMVP 列表、球队冠军数、FMVP 次数。"""
    rows = query(
        "SELECT season, champion, champion_abbr, runner_up, series, fmvp, "
        "fmvp_team_abbr, source FROM champions ORDER BY CAST(season AS INTEGER) DESC"
    )
    titles = team_title_counts()
    fmvp_map = fmvp_count_map()
    for r in rows:
        r["titles"] = titles.get(fix_team(r["champion_abbr"]), 0)
        r["fmvp_count"] = fmvp_map.get(norm_name(r["fmvp"]), {}).get("count", 0)
    fmvp_list = [
        {"name": v["name"], "count": v["count"]}
        for v in sorted(fmvp_map.values(), key=lambda x: (-x["count"], x["name"]))
    ]
    return jsonify({
        "recent": rows[:8],
        "all": rows,
        "team_counts": titles,
        "fmvp_counts": fmvp_list,
        "latest": rows[0] if rows else None,
        "updated_at": datetime.now(CN_TZ).strftime("%Y-%m-%d"),
        "source": "ClutchTimes 1947–2026",
    })


# ---------- 主队球员出勤追踪 ----------
_SEASON_GAMES_CACHE = {}


def season_team_games(season):
    """该赛季每队常规赛场次：82/72/66/50（停摆/缩水赛季自动适配）。"""
    if season in _SEASON_GAMES_CACHE:
        return _SEASON_GAMES_CACHE[season]
    row = query("SELECT MAX(g) AS g FROM player WHERE season=? AND g>0", (season,))
    games = (row[0]["g"] if row else None) or 82
    # 防止交易球员 2TM 合计行之外出现异常值，限定合理范围
    games = max(1, min(int(games), 82))
    _SEASON_GAMES_CACHE[season] = games
    return games


@app.route("/api/attendance")
def api_attendance():
    """主队球员出勤率/首发率/轮换标签（基于赛季累计 g/gs，按该赛季场次）。"""
    team = request.args.get("team", "")
    season = request.args.get("season", "")
    team_games = season_team_games(season)
    vs = team_variants(team)
    rows = query(
        "SELECT player, player_id, pos, age, g, gs FROM player "
        "WHERE team IN (%s) AND season=? AND g>0 ORDER BY g DESC" % ",".join("?" * len(vs)),
        (*sorted(vs), season),
    )
    out = []
    for r in rows:
        rate = min(round(r["g"] / team_games * 100), 100)
        start_rate = round((r["gs"] or 0) / r["g"] * 100) if r["g"] else 0
        if r["g"] >= max(1, round(team_games * 0.878)):
            label = "铁人"
        elif start_rate >= 60:
            label = "稳定首发"
        elif rate >= 55:
            label = "主力轮换"
        else:
            label = "轮换边缘"
        out.append(
            {
                "player": r["player"],
                "player_id": r["player_id"],
                "pos": r["pos"],
                "age": r["age"],
                "g": r["g"],
                "gs": r["gs"],
                "attendance": rate,
                "start_rate": start_rate,
                "label": label,
                "team_games": team_games,
            }
        )
    return jsonify(out)


# ---------- 球员对位对比 ----------
@app.route("/api/compare")
def api_compare():
    """两球员基础数据对比（场均），前端标红优势项。stage=reg / po 均支持。
    任一方无数据时返回 missing 原因（未进季后赛/伤病等）。"""
    a, b = request.args.get("a"), request.args.get("b")
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    cn = request.args.get("cn") == "1"
    sa, sb = stat_row(a, season, stage), stat_row(b, season, stage)
    missing = []
    if not sa:
        missing.append({"side": "a", "reason": check_availability(a, season, stage, cn)})
    if not sb:
        missing.append({"side": "b", "reason": check_availability(b, season, stage, cn)})
    if missing:
        return jsonify({"missing": missing})

    def pct100(v):
        return round(v * 100, 1) if v is not None else None

    def nm(x):
        return cn_player(x["name"]) if cn else x["name"]

    def tm(x):
        return team_label(x["team"]) if cn else fix_team(x["team"])

    return jsonify(
        {
            "a": {"name": nm(sa), "pos": sa["pos"], "team": tm(sa),
                  "pts": sa["pts"], "reb": sa["reb"], "ast": sa["ast"],
                  "stl": sa["stl"], "blk": sa["blk"], "tov": sa["tov"],
                  "fg": pct100(sa["fg"]), "x3p": pct100(sa["x3p"]),
                  "fmvp_count": fmvp_count_for(sa["name"]),
                  "team_titles": team_title_count(sa["team"])},
            "b": {"name": nm(sb), "pos": sb["pos"], "team": tm(sb),
                  "pts": sb["pts"], "reb": sb["reb"], "ast": sb["ast"],
                  "stl": sb["stl"], "blk": sb["blk"], "tov": sb["tov"],
                  "fg": pct100(sb["fg"]), "x3p": pct100(sb["x3p"]),
                  "fmvp_count": fmvp_count_for(sb["name"]),
                  "team_titles": team_title_count(sb["team"])},
        }
    )


# ---------- 用户观察名单 ----------
@app.route("/api/watchlist", methods=["GET"])
def api_watchlist_get():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS watchlist ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT UNIQUE, player_name TEXT, created_at TEXT)"
        )
        rows = conn.execute("SELECT player_id, player_name FROM watchlist ORDER BY id DESC").fetchall()
        rows = [dict(r) for r in rows]
    finally:
        conn.close()
    for r in rows:
        d = query(
            "SELECT season, team, pos, pts, trb, ast, g FROM player "
            "WHERE player_id=? AND team NOT LIKE '%TM' ORDER BY CAST(season AS INTEGER) DESC LIMIT 1",
            (r["player_id"],),
        )
        if d:
            dd = dict(d[0])
            dd["team"] = fix_team(dd.get("team"))
            r.update(dd)
    return jsonify(rows)


@app.route("/api/watchlist/add")
def api_watchlist_add():
    pid = request.args.get("player_id", "")
    name = request.args.get("player_name", "")
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS watchlist ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, player_id TEXT UNIQUE, player_name TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (player_id, player_name, created_at) VALUES (?,?,datetime('now','localtime'))",
            (pid, name),
        )
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


@app.route("/api/watchlist/remove")
def api_watchlist_remove():
    pid = request.args.get("player_id", "")
    conn = sqlite3.connect(DB)
    try:
        conn.execute("DELETE FROM watchlist WHERE player_id=?", (pid,))
        conn.commit()
    finally:
        conn.close()
    return jsonify({"ok": True})


# ---------- 平行坐标图（加分项） ----------
@app.route("/api/parallel")
def api_parallel():
    """球队球员多指标平行坐标（场均）。stage=po 时查季后赛表。"""
    season = request.args.get("season", "")
    team = request.args.get("team", "")
    stage = request.args.get("stage", "reg")
    cn = request.args.get("cn") == "1"
    pn = (lambda s: cn_player(s) if cn else s)
    if stage == "po":
        sql = "SELECT player, g, pts, trb, ast, stl, blk, fg_pct FROM playoff WHERE season=? AND g>0"
        args = [season]
        if team:
            vs = team_variants(team)
            sql += " AND team IN (%s)" % ",".join("?" * len(vs))
            args.extend(sorted(vs))
        sql += " ORDER BY pts DESC LIMIT 15"
        rows = query(sql, args)
        data = [
            [
                pn(r["player"]), r["pts"] or 0, r["trb"] or 0, r["ast"] or 0,
                r["stl"] or 0, r["blk"] or 0,
                round((r["fg_pct"] or 0) * 100, 1),
            ]
            for r in rows
        ]
        return jsonify(
            {
                "dimensions": ["球员", "得分", "篮板", "助攻", "抢断", "盖帽", "命中率%"],
                "data": data,
            }
        )
    sql = "SELECT player, g, pts, trb, ast, stl, blk, fg_percent FROM player WHERE season=? AND g>0 AND team NOT LIKE '%TM'"
    args = [season]
    if team:
        vs = team_variants(team)
        sql += " AND team IN (%s)" % ",".join("?" * len(vs))
        args.extend(sorted(vs))
    sql += " ORDER BY pts DESC LIMIT 15"
    rows = query(sql, args)
    data = []
    for r in rows:
        g = r["g"]

        def div(v):
            return round(v / g, 1) if (v is not None and g) else None

        data.append(
            [
                pn(r["player"]),
                div(r["pts"]), div(r["trb"]), div(r["ast"]),
                div(r["stl"]), div(r["blk"]),
                round((r["fg_percent"] or 0) * 100, 1),
            ]
        )
    return jsonify(
        {
            "dimensions": ["球员", "得分", "篮板", "助攻", "抢断", "盖帽", "命中率%"],
            "data": data,
        }
    )


# ---------- 历史交手记录 ----------
@app.route("/api/h2h")
def api_h2h():
    """主队 vs 任意对手：本赛季交手记录 + 汇总（胜负、平均分差、近5场）。"""
    team = request.args.get("team", "")
    opp = request.args.get("opp", "")
    rows = query(
        "SELECT game_date, home_team, away_team, home_score, away_score "
        "FROM schedule WHERE ((home_team=? AND away_team=?) OR (home_team=? AND away_team=?)) "
        "AND game_status LIKE 'Final%' "
        "AND (season_type='regular' OR (season_type IS NULL AND game_id LIKE '002%')) "
        "AND home_score IS NOT NULL AND away_score IS NOT NULL "
        "ORDER BY game_date",
        (team, opp, opp, team),
    )
    games = []
    wins = losses = 0
    margins = []
    for r in rows:
        is_home = r["home_team"] == team
        my = r["home_score"] if is_home else r["away_score"]
        op = r["away_score"] if is_home else r["home_score"]
        margin = my - op
        w = my > op
        wins += 1 if w else 0
        losses += 0 if w else 1
        margins.append(margin)
        games.append(
            {
                "game_date": r["game_date"],
                "is_home": is_home,
                "result": "W" if w else "L",
                "score": f"{my}-{op}",
                "margin": margin,
            }
        )
    avg_margin = round(sum(margins) / len(margins), 1) if margins else 0
    last5 = games[-5:]
    last5_text = [{"date": g["game_date"], "result": g["result"], "margin": g["margin"]} for g in last5]
    return jsonify(
        {
            "team": team,
            "opp": opp,
            "total": len(games),
            "wins": wins,
            "losses": losses,
            "avg_margin": avg_margin,
            "last5": last5_text,
        }
    )


# ---------- 伤病轻量化看板（示例数据，可手动更新） ----------
INJURY_SAMPLE = [
    ("LAL", "Jarred Vanderbilt", "膝盖", "每日观察", "", "示例数据"),
    ("LAL", "Christian Wood", "右膝", "缺席", "2027-01-15", "示例数据"),
    ("BOS", "Kristaps Porzingis", "小腿", "每周复查", "", "示例数据"),
    ("GSW", "Jonathan Kuminga", "脚踝", "每日观察", "", "示例数据"),
]


def ensure_injuries():
    conn = sqlite3.connect(DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS injuries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, team TEXT, player TEXT, "
            "injury_type TEXT, status TEXT, return_date TEXT, note TEXT)"
        )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(injuries)")}
        for col, typ in (("source", "TEXT"), ("updated_at", "TEXT"), ("espn_id", "TEXT")):
            if col not in cols:
                conn.execute(f"ALTER TABLE injuries ADD COLUMN {col} {typ}")
        n = conn.execute("SELECT COUNT(*) FROM injuries").fetchone()[0]
        if n == 0:
            conn.executemany(
                "INSERT INTO injuries (team, player, injury_type, status, return_date, note) VALUES (?,?,?,?,?,?)",
                INJURY_SAMPLE,
            )
            conn.commit()
        conn.commit()
    finally:
        conn.close()


@app.route("/api/injuries")
def api_injuries():
    team = request.args.get("team", "")
    if request.args.get("refresh") == "1":
        request_injury_refresh(300)
    ensure_injuries()
    vs = team_variants(team) or {team}
    rows = query(
        "SELECT player, injury_type, status, return_date, note, source, updated_at "
        "FROM injuries WHERE team IN (%s) "
        "ORDER BY CASE status WHEN '缺席' THEN 0 WHEN '大概率缺阵' THEN 1 "
        "WHEN '出战成疑' THEN 2 WHEN '每日观察' THEN 3 ELSE 4 END, id"
        % ",".join("?" * len(vs)),
        tuple(sorted(vs)),
    )
    for r in rows:
        r["is_sample"] = (r.get("note") or "") == "示例数据" or (r.get("source") or "") == "示例"
    return jsonify(rows)


# ---------- 阵容结构总览 ----------
@app.route("/api/roster")
def api_roster():
    """主队阵容：按位置分组卡片 + 平均年龄 + 新秀/老将/核心/角色统计。"""
    team = request.args.get("team", "")
    season = request.args.get("season", "")
    team_games = season_team_games(season)
    core_min = max(1, round(team_games * 0.6))
    role_min = max(1, round(team_games * 0.35))
    vs = team_variants(team)
    rows = query(
        "SELECT player, player_id, pos, age, g, gs, pts FROM player "
        "WHERE team IN (%s) AND season=? AND g>0 ORDER BY pos, pts DESC" % ",".join("?" * len(vs)),
        (*sorted(vs), season),
    )
    if not rows:
        return jsonify({"groups": [], "stats": {}})

    def is_core(r):
        gs = r["gs"] or 0
        return r["g"] >= core_min and (gs / r["g"] >= 0.7)

    groups = {}
    for r in rows:
        pos = r["pos"] or "未知"
        groups.setdefault(pos, []).append(
            {
                "player": r["player"],
                "player_id": r["player_id"],
                "age": r["age"],
                "g": r["g"],
                "gs": r["gs"],
                "pts": round(r["pts"] / r["g"], 1) if r["pts"] is not None else None,
                "tag": "核心" if is_core(r) else ("轮换" if r["g"] >= role_min else "边缘"),
            }
        )
    ages = [r["age"] for r in rows if r["age"]]
    avg_age = round(sum(ages) / len(ages), 1) if ages else 0
    stats = {
        "count": len(rows),
        "avg_age": avg_age,
        "rookie": sum(1 for a in ages if a <= 21),
        "veteran": sum(1 for a in ages if a >= 32),
        "young": sum(1 for a in ages if 22 <= a <= 26),
        "core": sum(1 for r in rows if is_core(r)),
        "role": sum(1 for r in rows if not is_core(r)),
        "team_games": team_games,
    }
    return jsonify({"groups": groups, "stats": stats})


# ---------- 多球员雷达对比（加分项） ----------
@app.route("/api/radar_multi")
def api_radar_multi():
    """多个球员六维能力叠加雷达（逗号分隔 player_id）。stage=reg / po 均支持。"""
    ids = [x for x in request.args.get("ids", "").split(",") if x]
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    cn = request.args.get("cn") == "1"
    if not ids:
        return jsonify({})
    rows = []
    for pid in ids:
        r = stat_row(pid, season, stage)
        if r:
            rows.append(r)
    if not rows:
        return jsonify({})
    names = ["得分", "篮板", "助攻", "抢断", "盖帽", "失误"]
    series_data = []
    for r in rows:
        vals = [r["pts"] or 0, r["reb"] or 0, r["ast"] or 0,
                r["stl"] or 0, r["blk"] or 0, r["tov"] or 0]
        disp = cn_player(r["name"]) if cn else r["name"]
        label = f"{disp} {season}"
        series_data.append({"name": label, "value": vals})
    schema = [{"name": n, "max": m} for n, m in zip(names, radar_baseline(season, stage))]
    option = {
        "title": {"text": f"{len(rows)} 名球员六维能力对比（{'季后赛' if stage=='po' else '常规赛'}）", "left": "center"},
        "tooltip": {},
        "legend": {"bottom": 0, "type": "scroll"},
        "radar": {"indicator": schema, "radius": "62%", "splitNumber": 4},
        "series": [
            {
                "type": "radar",
                "data": series_data,
                "areaStyle": {"opacity": 0.12},
                "lineStyle": {"width": 2},
                "symbolSize": 5,
            }
        ],
    }
    return jsonify(option)


@app.route("/api/multi_bar")
def api_multi_bar():
    """多球员六维场均分组柱状图数据（与雷达同源）。stage=reg / po 均支持。"""
    ids = [x for x in request.args.get("ids", "").split(",") if x]
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    cn = request.args.get("cn") == "1"
    if not ids:
        return jsonify({"players": [], "dims": []})
    rows = []
    for pid in ids:
        r = stat_row(pid, season, stage)
        if r:
            rows.append(r)
    if not rows:
        return jsonify({"players": [], "dims": []})
    dims = ["得分", "篮板", "助攻", "抢断", "盖帽", "失误"]
    return jsonify(
        {
            "players": [(cn_player(r["name"]) if cn else r["name"]) for r in rows],
            "dims": dims,
            "data": [
                [r["pts"] or 0, r["reb"] or 0, r["ast"] or 0,
                 r["stl"] or 0, r["blk"] or 0, r["tov"] or 0]
                for r in rows
            ],
        }
    )


# ---------- 搜索（球员 + 球队 + 中文别名） ----------
@app.route("/api/cn_map")
def api_cn_map():
    """中文翻译开关数据：球队中文名 + 历史队名 + 球星昵称 + 球员姓氏表。"""
    return jsonify(
        {
            "teams": TEAM_CN,
            "team_names": {abbr: full for abbr, (full, _cn) in team_index().items()},
            "nicks": [{"m": m, "cn": cn} for m, cn in PLAYER_NICK],
            "surnames": SURNAME_CN,
        }
    )


@app.route("/api/pos_trend")
def api_pos_trend():
    """同位置当赛季场均得分 TOP3 球员的多赛季趋势对比（折线）。
    stage=reg / po 均支持；返回原始数据由前端渲染。"""
    pos = norm_pos(request.args.get("pos", ""))
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    if not pos:
        return jsonify({})
    if stage == "po":
        top = query(
            "SELECT player FROM playoff WHERE pos=? AND season=? AND g>0 ORDER BY pts DESC LIMIT 3",
            (pos, season),
        )
        series = []
        for t in top:
            rows = query(
                "SELECT season, pts FROM playoff WHERE player=? AND g>0 "
                "ORDER BY CAST(season AS INTEGER)",
                (t["player"],),
            )
            series.append({"name": t["player"], "values": {r["season"]: round(r["pts"], 1) for r in rows}})
    else:
        top = query(
            "SELECT player_id, player FROM player WHERE pos=? AND season=? AND g>=20 "
            "AND team NOT LIKE '%TM' ORDER BY pts*1.0/g DESC LIMIT 3",
            (pos, season),
        )
        series = []
        for t in top:
            rows = query(
                "SELECT season, g, pts FROM player WHERE player_id=? AND g>0 "
                "ORDER BY CAST(season AS INTEGER)",
                (t["player_id"],),
            )
            series.append(
                {
                    "name": t["player"],
                    "values": {r["season"]: round(r["pts"] / r["g"], 1) for r in rows if r["g"]},
                }
            )
    if not series:
        return jsonify({})
    seasons = sorted(set(s for p in series for s in p["values"]), key=int)
    data = [[p["values"].get(s) for s in seasons] for p in series]
    return jsonify(
        {
            "pos": pos,
            "season": season,
            "stage": stage,
            "seasons": seasons,
            "players": [p["name"] for p in series],
            "data": data,
        }
    )


_TEAM_INDEX_CACHE = None
_CN_SURNAME_INDEX = None


def team_index():
    """abbr -> (英文全称, 中文名) 的全量索引（含历史球队），只查一次。"""
    global _TEAM_INDEX_CACHE
    if _TEAM_INDEX_CACHE is not None:
        return _TEAM_INDEX_CACHE
    names = {}
    for r in query(
        "SELECT DISTINCT abbreviation AS abbr, team FROM team "
        "WHERE abbreviation IS NOT NULL AND abbreviation != '' AND lg='NBA' "
        "ORDER BY CAST(season AS INTEGER) DESC"
    ):
        names.setdefault(r["abbr"], r["team"])
    out = {}
    for abbr, full in names.items():
        out[abbr] = (full, TEAM_CN.get(fix_team(abbr)) or TEAM_CN.get(abbr))
    _TEAM_INDEX_CACHE = out
    return out


def cn_surname_index():
    """中文姓 -> 英文姓集合，用于“威廉姆斯”这类反向搜索。"""
    global _CN_SURNAME_INDEX
    if _CN_SURNAME_INDEX is None:
        idx = {}
        for en, zh in SURNAME_CN.items():
            idx.setdefault(zh, set()).add(en)
        _CN_SURNAME_INDEX = idx
    return _CN_SURNAME_INDEX


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    season = request.args.get("season", "")
    stage = request.args.get("stage", "reg")
    if not q:
        return jsonify([])
    qn = q.casefold()
    out = []
    seen = set()

    if stage == "po":
        base_sql = (
            "SELECT player AS player_id, player, team, pos, g, pts "
            "FROM playoff WHERE LOWER(player) LIKE ? AND season=? AND g>0"
        )
    else:
        base_sql = (
            "SELECT player_id, player, team, pos, g, pts FROM player "
            "WHERE LOWER(player) LIKE ? AND season=? AND g>0 AND team NOT LIKE '%TM'"
        )

    def add_player(p, score, cn_label=None):
        pid = p["player_id"]
        if pid in seen:
            return
        seen.add(pid)
        item = {"type": "player", **p, "_score": score}
        if cn_label:
            item["cn"] = cn_label
        out.append(item)

    # 1) 英文名：完全匹配 > 前缀 > 子串（子串只用于 2 个字符以上）
    if len(qn) >= 2:
        for p in query(
            base_sql + " ORDER BY pts DESC, player LIMIT 30",
            (f"%{qn}%", season),
        ):
            nm = norm_name(p["player"])
            score = 100 if nm == norm_name(qn) else (85 if nm.startswith(norm_name(qn)) else 50)
            add_player(p, score)

    # 2) 中文别名/昵称（大小写不敏感）
    for alias, match, cn in PLAYER_CN:
        if qn and qn in alias.casefold():
            for p in query(
                base_sql + " ORDER BY pts DESC, player LIMIT 8",
                (f"%{match.casefold()}%", season),
            ):
                add_player(p, 95 if qn == alias.casefold() else 90, cn)

    # 3) 中文姓反查：输入“威廉姆斯”能找到所有 Williams
    if qn:
        for zh, ens in cn_surname_index().items():
            if qn in zh.casefold() or zh.casefold() in qn:
                for en in sorted(ens):
                    for p in query(
                        base_sql + " ORDER BY pts DESC, player LIMIT 16",
                        (f"%{en.casefold()}%", season),
                    ):
                        # LIKE '%Williams%' 会命中 Williamson，必须比对完整姓氏
                        if norm_name(surname_of(p["player"])) != norm_name(en):
                            continue
                        add_player(p, 80, zh)

    # 4) 球队：缩写 / 英文全称 / 中文名；精确与前缀优先，避免 “ad” 命中 Philadelphia
    seen_team = set()
    for abbr, (full, cn) in team_index().items():
        abbr_l, full_l = abbr.casefold(), (full or "").casefold()
        cn_l = (cn or "").casefold()
        if qn in (abbr_l, full_l, cn_l):
            score = 100
        elif abbr_l.startswith(qn) or full_l.startswith(qn) or (cn and cn_l.startswith(qn)):
            score = 80
        elif len(qn) >= 3 and (qn in full_l or (cn and qn in cn_l)):
            score = 60
        elif len(qn) >= 2 and qn in abbr_l:
            score = 55
        else:
            continue
        canon = fix_team(abbr)
        if canon in seen_team:
            continue
        seen_team.add(canon)
        label = f"{full}（{cn}）" if cn else (full or abbr)
        out.append({
            "type": "team", "player_id": abbr, "player": label,
            "team": abbr, "pos": "球队", "_score": score,
        })

    # 分数优先；同分时球队略优先，然后按赛季得分排序
    out.sort(key=lambda x: (
        -x.get("_score", 0),
        0 if x.get("type") == "team" else 1,
        -(x.get("pts") or 0),
        x.get("player", ""),
    ))
    for it in out:
        it.pop("_score", None)
        if it.get("type") == "player":
            it["team"] = fix_team(it.get("team"))
    return jsonify(out[:15])


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
