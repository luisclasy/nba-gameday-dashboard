/* =============================================================
   NBA观赛辅助系统 - 前端交互（v5）
   功能：筛选联动（常规赛/季后赛双分支）、主队管理（多主队）、
         赛程看板、战绩状态、出勤追踪、伤病、阵容、历史交锋、
         对位对比（年份切换）、多球员雷达+柱状图（年份切换）、
         同位置TOP3多赛季趋势、观察名单（即时查看）、搜索、提醒
   ============================================================= */

let barChart = null;
let radarChart = null;
let lineChart = null;
let parallelChart = null;
let posTrendChart = null;
let multiRadarChart = null;
let multiBarChart = null;
let detailTrendChart = null;
let currentPlayerId = null;   // 当前选中球员（reg=player_id / po=球员名）
let currentPlayerName = null; // 当前选中球员姓名（跨 stage 匹配用）
let favTeams = [];            // 关注的主队 [{team, name}]
let favActive = null;         // 当前展示的主队
let attData = [];             // 出勤原始数据（用于筛选）
let attFilter = "all";        // all / core / edge
let lastInjuries = [];        // 最近一次伤病数据（自动刷新 hero 时复用）
let lastTeamForm = null;
let lastTeamSched = null;
let multiSel = [];            // 多雷达已选球员 [{pid, name}]
let searchTimer = null;
let stageMode = "reg";        // 主界面：reg=常规赛 / po=季后赛
// 弹窗独立状态（不跟随主界面）
let detailStage = "reg";
let detailRange = "5";
let detailPid = null;         // 详情当前球员（reg=player_id / po=名字）
let detailName = null;        // 详情球员姓名（跨 stage 匹配）
let compareStage = "reg";
let multiStage = "reg";
let watchStage = "reg";
let cnOn = false;             // 中文翻译开关（localStorage 记忆）
let cnMap = { teams: {}, team_names: {}, nicks: [], surnames: {} };

// 历史/异写缩写 -> 现役标准缩写（和后端 TEAM_ABBR_FIX 保持一致）
const TEAM_ALIAS = {
    BRK: "BKN", NJN: "BKN", PHO: "PHX", CHO: "CHA", CHH: "CHA",
    NOH: "NOP", NOK: "NOP", WSB: "WAS", WSC: "WAS", VAN: "MEM",
};

// 球队主色（用于队标/卡片强调色，纯前端视觉映射）
const TEAM_COLORS = {
    ATL: "#e03a3e", BOS: "#007a33", BKN: "#6b7280", CHA: "#1d1160", CHI: "#ce1141",
    CLE: "#860038", DAL: "#00538c", DEN: "#0e2240", DET: "#c8102e", GSW: "#1d428a",
    HOU: "#ce1141", IND: "#002d62", LAC: "#c8102e", LAL: "#552583", MEM: "#5d76a9",
    MIA: "#98002e", MIL: "#00471b", MIN: "#0c2340", NOP: "#0c2340", NYK: "#006bb6",
    OKC: "#007ac1", ORL: "#0077c0", PHI: "#006bb6", PHX: "#e56020", POR: "#e03a3e",
    SAC: "#5a2d81", SAS: "#8a8d8f", TOR: "#ce1141", UTA: "#002b5c", WAS: "#002b5c",
};

const TEAM_SHORT_EN = {
    ATL: "Hawks", BOS: "Celtics", BKN: "Nets", CHA: "Hornets", CHI: "Bulls",
    CLE: "Cavs", DAL: "Mavs", DEN: "Nuggets", DET: "Pistons", GSW: "Warriors",
    HOU: "Rockets", IND: "Pacers", LAC: "Clippers", LAL: "Lakers", MEM: "Grizzlies",
    MIA: "Heat", MIL: "Bucks", MIN: "Wolves", NOP: "Pelicans", NYK: "Knicks",
    OKC: "Thunder", ORL: "Magic", PHI: "76ers", PHX: "Suns", POR: "Blazers",
    SAC: "Kings", SAS: "Spurs", TOR: "Raptors", UTA: "Jazz", WAS: "Wizards",
};

const TEAM_CONFERENCE = {
    ATL: "东部", BOS: "东部", BKN: "东部", CHA: "东部", CHI: "东部", CLE: "东部",
    DET: "东部", IND: "东部", MIA: "东部", MIL: "东部", NYK: "东部", ORL: "东部",
    PHI: "东部", TOR: "东部", WAS: "东部",
    DAL: "西部", DEN: "西部", GSW: "西部", HOU: "西部", LAC: "西部", LAL: "西部",
    MEM: "西部", MIN: "西部", NOP: "西部", OKC: "西部", PHX: "西部", POR: "西部",
    SAC: "西部", SAS: "西部", UTA: "西部",
};

function teamColor(abbr) {
    const key = TEAM_ALIAS[abbr] || abbr;
    return TEAM_COLORS[key] || "#5c7bd9";
}

function teamMark(abbr, size = "") {
    if (!abbr || String(abbr).length > 4) return "";
    return `<span class="team-mark ${size}" style="--team-color:${teamColor(abbr)}">${abbr}</span>`;
}

function hideOptionTitle(option) {
    if (!option || !option.title) return;
    const titles = Array.isArray(option.title) ? option.title : [option.title];
    titles.forEach((t) => { if (t) t.show = false; });
}

function teamDisplay(abbr, short = false) {
    if (!abbr) return "";
    if (cnOn) return teamCN(abbr);
    if (String(abbr).length > 4) return abbr;
    const key = TEAM_ALIAS[abbr] || abbr;
    if (short && TEAM_SHORT_EN[key]) return TEAM_SHORT_EN[key];
    return (cnMap.team_names && cnMap.team_names[abbr]) || abbr;
}

// ECharts 深色主题：统一标题/轴/图例/提示框，避免默认 #464646 叠在深色卡片上
echarts.registerTheme("nbaDark", {
    color: ["#5c7bd9", "#f0a500", "#38bdf8", "#e879f9", "#4ade80", "#f87171"],
    backgroundColor: "transparent",
    textStyle: { color: "#c7d6f0" },
    title: { textStyle: { color: "#e6edf7" }, subtextStyle: { color: "#93c5fd" } },
    legend: { textStyle: { color: "#c7d6f0" } },
    tooltip: {
        backgroundColor: "rgba(15,26,51,0.96)",
        borderColor: "rgba(96,165,250,0.4)",
        textStyle: { color: "#e6edf7" },
    },
    categoryAxis: {
        axisLine: { lineStyle: { color: "rgba(96,165,250,0.35)" } },
        axisLabel: { color: "#a8b8d8" },
        splitLine: { lineStyle: { color: "rgba(96,165,250,0.08)" } },
    },
    valueAxis: {
        axisLine: { lineStyle: { color: "rgba(96,165,250,0.35)" } },
        axisLabel: { color: "#a8b8d8" },
        splitLine: { lineStyle: { color: "rgba(96,165,250,0.08)" } },
    },
    radar: {
        axisName: { color: "#c7d6f0" },
        splitLine: { lineStyle: { color: "rgba(96,165,250,0.18)" } },
        splitArea: { areaStyle: { color: ["rgba(96,165,250,0.03)", "rgba(96,165,250,0.07)"] } },
    },
});

// ---------- 工具 ----------
async function fetchJSON(url, method = "GET", body = null) {
    // GET 请求自动携带中文翻译开关，后端图表/数据接口据此输出中文名
    if (method === "GET" && url.includes("/api/")) {
        url += (url.includes("?") ? "&" : "?") + "cn=" + (cnOn ? "1" : "0");
    }
    const opt = { method };
    if (body) {
        opt.headers = { "Content-Type": "application/json" };
        opt.body = JSON.stringify(body);
    }
    const resp = await fetch(url, opt);
    if (!resp.ok) throw new Error("请求失败: " + url);
    return resp.json();
}

function $(id) {
    return document.getElementById(id);
}

let toastTimer = null;
function showToast(message, type = "ok", duration = 2400) {
    const el = $("appToast");
    if (!el) return;
    el.textContent = message;
    el.className = "app-toast show" + (type === "error" ? " error" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
        el.className = "app-toast" + (type === "error" ? " error" : "");
    }, duration);
}

// 位置归一化 + 中文展示（后端统一 G/F/C，兼容旧写法）
const POS_CN = { G: "后卫", F: "前锋", C: "中锋",
    PG: "后卫", SG: "后卫", SF: "前锋", PF: "前锋",
    Guard: "后卫", Forward: "前锋", Center: "中锋" };
function normPos(p) {
    if (!p) return "";
    const s = String(p).trim();
    const head = s.replace(/\//g, "-").split("-")[0].trim();
    return ({ PG: "G", SG: "G", SF: "F", PF: "F", C: "C",
        Guard: "G", G: "G", Forward: "F", F: "F", Center: "C" })[head] || "";
}
function posLabel(p) {
    const g = normPos(p);
    return POS_CN[g] || p || "-";
}

function stageParam() {
    return `stage=${stageMode}`;
}

// 球员姓名归一化（跨常规赛/季后赛名字差异：重音、Jr. 等）
function normName(s) {
    if (!s) return "";
    return s
        .normalize("NFKD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[.\']/g, "")
        .replace(/-/g, " ")
        .replace(/\s+(jr|sr|iii|ii)\b/g, "")
        .replace(/\s+/g, " ")
        .trim();
}

// 从选项文本 "Name (TEAM)" 取球员姓名
function optName(text) {
    return (text || "").split(" (")[0].trim();
}

// ---------- 中文翻译（开关：球队全中文；球员昵称>中文姓氏>英文姓氏） ----------
function teamCN(abbr) {
    if (!cnOn || !abbr) return abbr || "";
    const key = TEAM_ALIAS[abbr] || abbr;
    return cnMap.teams[key] || (cnMap.team_names && cnMap.team_names[abbr]) || abbr;
}
function rawSurname(name) {
    const s = String(name || "").trim().replace(/\s+(Jr\.?|Sr\.?|III|II|IV)\s*$/i, "");
    const p = s.split(/\s+/);
    return p.length ? p[p.length - 1] : s;
}
function playerCN(name) {
    if (!name) return "";
    if (!cnOn) return name;
    const nn = normName(name);
    for (const it of cnMap.nicks) {
        if (nn.includes(it.m)) return it.cn;
    }
    const sur = rawSurname(name);
    const hit = cnMap.surnamesNorm ? cnMap.surnamesNorm[normName(sur)] : null;
    return hit || sur;
}
async function loadCnMap() {
    cnMap = await fetchJSON("/api/cn_map");
    cnMap.surnamesNorm = {};
    Object.entries(cnMap.surnames || {}).forEach(([k, v]) => {
        cnMap.surnamesNorm[normName(k)] = v;
    });
    cnMap.nameToAbbr = {};
    Object.entries(cnMap.team_names || {}).forEach(([abbr, name]) => {
        if (name) cnMap.nameToAbbr[name] = abbr;
    });
    // 历史缩写（如 DNN/BRK）可能覆盖现役缩写，这里用现役 30 队再覆盖一次
    Object.keys(TEAM_SHORT_EN).forEach((abbr) => {
        const name = cnMap.team_names && cnMap.team_names[abbr];
        if (name) cnMap.nameToAbbr[name] = abbr;
    });
    cnMap.cnToAbbr = {};
    Object.entries(cnMap.teams || {}).forEach(([abbr, cn]) => {
        if (cn) cnMap.cnToAbbr[cn] = abbr;
    });
}

function abbrForLabel(label) {
    if (!label) return null;
    return (cnMap.nameToAbbr && cnMap.nameToAbbr[label])
        || (cnMap.cnToAbbr && cnMap.cnToAbbr[label])
        || null;
}
// 切换中文翻译后整体重渲染（重刷下拉/图表与各区块）
async function toggleCn(on) {
    cnOn = on;
    localStorage.setItem("nba_cn", on ? "1" : "0");
    const cb = $("cnToggle");
    if (cb) cb.checked = on;
    // 重绘主筛选下拉（保留已选；loadPlayers 会顺带重绘雷达/折线/同位置图）
    await loadTeams();
    await loadPlayers();
    await loadBar();
    await loadParallel();
    await loadFavTeam();
    await loadRecentGames(true);
}

// ---------- 弹窗统一管理（修复遮罩残留导致页面变暗） ----------
function showModal(id) {
    bootstrap.Modal.getOrCreateInstance($(id)).show();
}

function hideModal(id) {
    bootstrap.Modal.getOrCreateInstance($(id)).hide();
}

// 所有弹窗彻底关闭后，兜底清理残留遮罩与 body 锁定
document.addEventListener("hidden.bs.modal", () => {
    setTimeout(() => {
        if (!document.querySelector(".modal.show")) {
            document.querySelectorAll(".modal-backdrop").forEach((el) => el.remove());
            document.body.classList.remove("modal-open");
            document.body.style.overflow = "";
            document.body.style.paddingRight = "";
        }
    }, 80);
});

// ---------- 初始化 ----------
async function init() {
    // 中文翻译开关：先恢复记忆并加载译名表，再渲染任何数据；?cn=1 / ?cn=0 可强制覆盖
    const cnParam = new URLSearchParams(location.search).get("cn");
    cnOn = cnParam === "1" || (cnParam !== "0" && localStorage.getItem("nba_cn") === "1");
    const cnToggle = $("cnToggle");
    if (cnToggle) {
        cnToggle.checked = cnOn;
        cnToggle.addEventListener("change", () => toggleCn(cnToggle.checked));
    }
    await loadCnMap();

    barChart = echarts.init($("barChart"), "nbaDark");
    radarChart = echarts.init($("radarChart"), "nbaDark");
    lineChart = echarts.init($("lineChart"), "nbaDark");
    parallelChart = echarts.init($("parallelChart"), "nbaDark");
    posTrendChart = echarts.init($("posTrendChart"), "nbaDark");
    multiRadarChart = echarts.init($("multiRadar"), "nbaDark");
    multiBarChart = echarts.init($("multiBar"), "nbaDark");
    detailTrendChart = echarts.init($("detailTrendChart"), "nbaDark");

    window.addEventListener("resize", () => {
        [barChart, radarChart, lineChart, parallelChart, posTrendChart, multiRadarChart, multiBarChart, detailTrendChart].forEach((c) => c && c.resize());
    });
    // 弹窗动画结束后图表需重新计算尺寸
    $("radarMultiModal").addEventListener("shown.bs.modal", () => {
        multiRadarChart.resize();
        multiBarChart.resize();
    });
    $("detailModal").addEventListener("shown.bs.modal", () => {
        detailTrendChart.resize();
    });

    await reloadSeasons();
    await loadParallel();
    await loadFavTeam();
    await loadRecentGames(true);
    await loadStandings();
    await loadChampions();

    // 事件绑定
    $("stageToggle").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-stage]");
        if (!btn || btn.dataset.stage === stageMode) return;
        stageMode = btn.dataset.stage;
        $("stageToggle").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        await reloadSeasons();
        await loadParallel();
        await loadFavTeam();
    });
    $("seasonSelect").addEventListener("change", async () => {
        await refreshAll();
        await loadParallel();
        await loadFavTeam();
    });
    $("teamSelect").addEventListener("change", async () => {
        await loadPlayers();
        await loadParallel();
    });
    $("playerSelect").addEventListener("change", loadPlayerCharts);
    $("detailBtn").addEventListener("click", () => showDetail());
    $("watchAddBtn").addEventListener("click", addWatch);
    $("resetBtn").addEventListener("click", async () => {
        $("teamSelect").value = "";
        $("playerSelect").value = "";
        currentPlayerId = null;
        currentPlayerName = null;
        await loadPlayers();
        await loadParallel();
        showToast("已重置球队和球员筛选");
    });
    $("recentRefreshBtn").addEventListener("click", async () => {
        const btn = $("recentRefreshBtn");
        const ico = btn.querySelector(".refresh-ico");
        if (btn.disabled) return;
        btn.disabled = true;
        ico.classList.add("is-spinning");
        await loadRecentGames(true);
        setTimeout(async () => {
            await loadRecentGames(false);
            await refreshMainTeamLive();
            await loadStandings();
            ico.classList.remove("is-spinning");
            btn.disabled = false;
            showToast("最近比赛已刷新");
        }, 3000);
    });
    $("favTeamBtn").addEventListener("click", openFavTeamModal);
    $("favAddBtn").addEventListener("click", openFavTeamModal);
    $("teamHeroBtn").addEventListener("click", openFavTeamModal);
    $("watchlistBtn").addEventListener("click", openWatchlist);
    $("compareBtn").addEventListener("click", openCompare);
    $("helpBtn").addEventListener("click", () => showModal("helpModal"));
    $("allChampionsBtn").addEventListener("click", () => {
        renderAllChampions();
        showModal("championsModal");
    });
    $("compareA").addEventListener("change", renderCompare);
    $("compareB").addEventListener("change", renderCompare);
    $("compareSwapBtn").addEventListener("click", () => {
        const a = $("compareA").value;
        const b = $("compareB").value;
        if (!a || !b) return;
        $("compareA").value = b;
        $("compareB").value = a;
        renderCompare();
        showToast("已交换对位双方");
    });
    // 对位对比：独立数据类型 / 赛季切换（不重置已选球员）
    $("compareStageToggle").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-stage]");
        if (!btn || btn.dataset.stage === compareStage) return;
        compareStage = btn.dataset.stage;
        $("compareStageToggle").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        await loadCompareSeasons();
        await loadComparePlayers();
        await renderCompare();
    });
    $("compareSeason").addEventListener("change", async () => {
        await loadComparePlayers();
        await renderCompare();
    });
    $("radarMultiBtn").addEventListener("click", openRadarMulti);
    $("multiAddBtn").addEventListener("click", multiAddPlayer);
    $("multiAdd").addEventListener("change", () => {
        const addBtn = $("multiAddBtn");
        if (addBtn) addBtn.disabled = !$("multiAdd").value;
    });
    $("multiClearBtn").addEventListener("click", () => {
        multiSel = [];
        $("multiAdd").value = "";
        $("multiAddBtn").disabled = true;
        renderMultiChips();
        renderMultiRadar();
        showToast("已清空多人对比");
    });
    // 多球员对比：独立数据类型 / 赛季切换（保留已选球员）
    $("multiStageToggle").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-stage]");
        if (!btn || btn.dataset.stage === multiStage) return;
        multiStage = btn.dataset.stage;
        $("multiStageToggle").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        await loadMultiSeasons();
        await loadMultiPlayers();
        renderMultiChips();
        renderMultiRadar();
    });
    $("multiSeason").addEventListener("change", async () => {
        await loadMultiPlayers();
        renderMultiChips();
        renderMultiRadar();
    });
    // 详情弹窗：独立数据类型 / 赛季 / 趋势范围
    $("detailStageToggle").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-stage]");
        if (!btn || btn.dataset.stage === detailStage) return;
        detailStage = btn.dataset.stage;
        $("detailStageToggle").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        await loadDetailSeasons();
        await loadDetail();
    });
    $("detailSeason").addEventListener("change", loadDetail);
    $("detailRangeToggle").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-range]");
        if (!btn || btn.dataset.range === detailRange) return;
        detailRange = btn.dataset.range;
        $("detailRangeToggle").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        loadDetailTrend();
    });
    // 观察名单弹窗：独立数据类型 / 赛季
    $("watchStageToggle").addEventListener("click", async (e) => {
        const btn = e.target.closest("button[data-stage]");
        if (!btn || btn.dataset.stage === watchStage) return;
        watchStage = btn.dataset.stage;
        $("watchStageToggle").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        await loadWatchSeasons();
    });
    // 出勤筛选按钮
    $("attFilter").addEventListener("click", (e) => {
        const btn = e.target.closest("button[data-f]");
        if (!btn) return;
        $("attFilter").querySelectorAll("button").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        attFilter = btn.dataset.f;
        applyAttFilter();
    });
    bindSearch();
    bindShortcuts();
    bindRemindToggle();

    // 今日比分自动刷新：每分钟触发一次后台 ESPN 同步，并刷新最近比赛/主队战绩
    setInterval(async () => {
        if (document.hidden) return;
        await loadRecentGames(true);
        setTimeout(refreshMainTeamLive, 3000);
        await loadStandings();
    }, 60000);
}

// 按当前 stage 加载赛季列表（默认取最新赛季）
async function reloadSeasons() {
    const seasons = await fetchJSON(`/api/seasons?${stageParam()}`);
    $("seasonSelect").innerHTML = seasons
        .map((s) => `<option value="${s}">${s} 赛季</option>`)
        .join("");
    if (seasons.length) {
        $("seasonSelect").value = seasons[0];
        await refreshAll();
    }
}

// ---------- 筛选联动 ----------
async function refreshAll() {
    await loadTeams();
    await loadPlayers();
    await loadBar();
}

async function loadTeams() {
    const season = $("seasonSelect").value;
    const prevTeam = $("teamSelect").value;
    const teams = await fetchJSON(`/api/teams?season=${encodeURIComponent(season)}`);
    $("teamSelect").innerHTML =
        '<option value="">全部球队</option>' +
        teams.map((t) => {
            const label = cnOn ? (t.name_zh || teamCN(t.abbr)) : teamDisplay(t.abbr, true);
            return `<option value="${t.abbr}" title="${t.name || t.abbr}">${label}</option>`;
        }).join("");
    // 切换年份 / 常规赛·季后赛时保留已选球队（仅当该视图中存在；季后赛仅16队）
    $("teamSelect").value =
        prevTeam && teams.some((t) => t.abbr === prevTeam) ? prevTeam : "";
}

async function loadPlayers() {
    const season = $("seasonSelect").value;
    const team = $("teamSelect").value;
    const prevPid = $("playerSelect").value;
    const prevName = currentPlayerName;
    const players = await fetchJSON(
        `/api/players?season=${encodeURIComponent(season)}&team=${encodeURIComponent(team)}&${stageParam()}`
    );
    $("playerSelect").innerHTML =
        '<option value="">请选择球员</option>' +
        players
            .map((p) => `<option value="${p.player_id}" data-en="${p.player}">${playerCN(p.player)} (${teamCN(p.team)})</option>`)
            .join("");
    // 切换年份 / 常规赛·季后赛时保留已选球员：先按 id 精确匹配，再按归一化姓名跨视图匹配
    let hit = null;
    if (prevPid) hit = players.find((p) => String(p.player_id) === String(prevPid));
    if (!hit && prevName) {
        const nm = normName(prevName);
        hit = players.find((p) => normName(p.player) === nm);
    }
    // 数据看板默认展示当前筛选下的第一名球员，避免雷达/趋势一开始是空白
    if (!hit && players.length) hit = players[0];
    if (hit) {
        $("playerSelect").value = hit.player_id;
        await loadPlayerCharts();
    } else {
        $("playerSelect").value = "";
        currentPlayerId = null;
        currentPlayerName = null;
        radarChart.clear();
        lineChart.clear();
        posTrendChart.clear();
        renderPlayerSummary(null);
        renderPlayerKpis(null);
        setPlayerActions(false);
    }
}

function renderPlayerSummary(info) {
    const box = $("playerInfo");
    if (!box) return;
    if (!info) {
        box.innerHTML = '<span class="text-muted">选择一名球员，查看赛季概览</span>';
        return;
    }
    const mark = info.team && String(info.team).length <= 4 ? teamMark(info.team) : "";
    box.innerHTML = `
        <div class="player-summary-main">
            ${mark}
            <strong>${info.name}</strong>
            <span class="psub">${posLabel(info.pos)} · ${teamDisplay(info.team, true)} · ${info.age ?? "?"} 岁</span>
            <span class="pstage">${stageMode === "po" ? "季后赛" : "常规赛"} · ${info.season}</span>
            ${info.fmvp_count ? `<span class="fmvp-tag">FMVP ×${info.fmvp_count}</span>` : ""}
            ${info.team_titles ? `<span class="title-tag">队史 ${info.team_titles} 冠</span>` : ""}
        </div>`;
}

function setPlayerActions(enabled) {
    const detail = $("detailBtn");
    const watch = $("watchAddBtn");
    if (detail) detail.disabled = !enabled;
    if (watch) watch.disabled = !enabled;
}

function renderPlayerKpis(info) {
    const box = $("playerKpis");
    if (!box) return;
    if (!info) {
        box.innerHTML = "";
        return;
    }
    const pct = (v) => (v == null ? "--" : `${(v * 100).toFixed(1)}%`);
    const items = [
        ["得分", info.pts ?? "--"],
        ["篮板", info.reb ?? "--"],
        ["助攻", info.ast ?? "--"],
        ["抢断", info.stl ?? "--"],
        ["盖帽", info.blk ?? "--"],
        ["命中率", pct(info.fg)],
    ];
    box.innerHTML = items
        .map(([k, v]) => `<div class="kpi"><span>${k}</span><strong>${v}</strong></div>`)
        .join("");
}

async function loadBar() {
    const season = $("seasonSelect").value;
    const option = await fetchJSON(`/api/bar?season=${encodeURIComponent(season)}&${stageParam()}`);
    hideOptionTitle(option);
    option.legend = { show: false };
    option.grid = { top: 18, left: 58, right: 70, bottom: 66, containLabel: true };
    // 英文模式把完整队名缩成 Cavs / Mavs / Blazers，避免 x 轴拥挤
    const axes = Array.isArray(option.xAxis) ? option.xAxis : [option.xAxis];
    let axisAbbrs = [];
    axes.forEach((axis) => {
        if (!axis) return;
        axis.axisLabel = axis.axisLabel || {};
        axis.axisLabel.margin = 10;
        if (!Array.isArray(axis.data)) return;
        axisAbbrs = axis.data.map((label) => abbrForLabel(label));
        axis.data = axis.data.map((label, i) => {
            const abbr = axisAbbrs[i];
            if (!abbr) return label;
            const key = TEAM_ALIAS[abbr] || abbr;
            return cnOn ? teamCN(abbr) : (TEAM_SHORT_EN[key] || label);
        });
    });
    const barSeries = Array.isArray(option.series) ? option.series[0] : option.series;
    if (barSeries) {
        barSeries.itemStyle = Object.assign({}, barSeries.itemStyle, {
            borderRadius: [4, 4, 0, 0],
            borderColor: "rgba(255,255,255,0.18)",
            borderWidth: 1,
            color: (p) => {
                const abbr = axisAbbrs[p.dataIndex];
                return abbr ? teamColor(abbr) : "#5c7bd9";
            },
        });
    }
    barChart.setOption(option, true);
}

async function loadParallel() {
    const season = $("seasonSelect").value;
    const team = $("teamSelect").value;
    const par = await fetchJSON(
        `/api/parallel?season=${encodeURIComponent(season)}&team=${encodeURIComponent(team)}&${stageParam()}`
    );
    if (!par || !par.data || !par.data.length) {
        parallelChart.clear();
        return;
    }
    const dims = par.dimensions;
    const option = {
        title: { show: false },
        tooltip: {},
        parallelAxis: dims.map((d, i) =>
            i === 0 ? { dim: i, name: d, type: "category" } : { dim: i, name: d }
        ),
        parallel: { left: "6%", right: "8%", bottom: 28, top: 28 },
        series: [{ type: "parallel", lineStyle: { width: 2, opacity: 0.6 }, data: par.data }],
    };
    parallelChart.setOption(option, true);
}

// 选中球员 -> 雷达 + 折线 + 同位置TOP3趋势
async function loadPlayerCharts() {
    const pid = $("playerSelect").value;
    if (!pid) {
        radarChart.clear();
        lineChart.clear();
        posTrendChart.clear();
        renderPlayerSummary(null);
        renderPlayerKpis(null);
        setPlayerActions(false);
        currentPlayerId = null;
        currentPlayerName = null;
        return;
    }
    const season = $("seasonSelect").value;
    currentPlayerId = pid;
    const sel = $("playerSelect").selectedOptions[0];
    currentPlayerName = sel ? (sel.dataset.en || optName(sel.textContent)) : null;

    let radarOpt, lineOpt, info;
    try {
        [radarOpt, lineOpt, info] = await Promise.all([
            fetchJSON(`/api/radar?player_id=${encodeURIComponent(pid)}&season=${encodeURIComponent(season)}&${stageParam()}`),
            fetchJSON(`/api/line?player_id=${encodeURIComponent(pid)}&${stageParam()}`),
            fetchJSON(`/api/player_detail?player_id=${encodeURIComponent(pid)}&season=${encodeURIComponent(season)}&${stageParam()}`),
        ]);
    } catch (err) {
        console.error(err);
        radarChart.clear();
        lineChart.clear();
        posTrendChart.clear();
        renderPlayerKpis(null);
        setPlayerActions(false);
        $("playerInfo").innerHTML = '<span class="text-danger">数据加载失败，请稍后重试</span>';
        return;
    }

    if (radarOpt && radarOpt.series) {
        hideOptionTitle(radarOpt);
        radarChart.setOption(radarOpt, true);
    } else radarChart.clear();
    if (lineOpt && lineOpt.series) {
        hideOptionTitle(lineOpt);
        lineOpt.legend = { show: false };
        lineOpt.grid = { top: 18, left: 45, right: 18, bottom: 34, containLabel: true };
        if (Array.isArray(lineOpt.series)) {
            lineOpt.series.forEach((s) => { s.label = { show: false }; });
        }
        lineChart.setOption(lineOpt, true);
    } else lineChart.clear();
    if (info && info.name) {
        renderPlayerSummary(info);
        renderPlayerKpis(info);
        setPlayerActions(true);
        loadPosTrend(info.pos, season, stageMode);
    } else {
        renderPlayerSummary(null);
        renderPlayerKpis(null);
        setPlayerActions(false);
        posTrendChart.clear();
    }
}

// 同位置 TOP3 多赛季趋势折线
async function loadPosTrend(pos, season, stage) {
    if (!pos) {
        posTrendChart.clear();
        return;
    }
    let d;
    try {
        d = await fetchJSON(`/api/pos_trend?pos=${encodeURIComponent(pos)}&season=${encodeURIComponent(season)}&stage=${stage}`);
    } catch (err) {
        console.error(err);
        posTrendChart.clear();
        return;
    }
    if (!d || !d.seasons || !d.seasons.length) {
        posTrendChart.clear();
        return;
    }
    const colors = ["#f0a500", "#38bdf8", "#e879f9"];
    const option = {
        title: { show: false },
        tooltip: { trigger: "axis" },
        legend: { bottom: 0, type: "scroll" },
        grid: { left: 42, right: 24, bottom: 44, top: 18 },
        xAxis: { type: "category", data: d.seasons, name: "赛季" },
        yAxis: { type: "value", name: "场均得分" },
        series: d.players.map((name, i) => ({
            name: playerCN(name),
            type: "line",
            smooth: true,
            connectNulls: true,
            data: d.data[i],
            lineStyle: { width: 2.5, color: colors[i % 3] },
            itemStyle: { color: colors[i % 3] },
            symbolSize: 6,
        })),
    };
    posTrendChart.setOption(option, true);
}

// ---------- 球员详情弹窗（独立赛季/数据类型 + 全指标多赛季趋势） ----------
function setStageToggle(containerId, stage) {
    $(containerId).querySelectorAll("button[data-stage]").forEach((b) => {
        b.classList.toggle("active", b.dataset.stage === stage);
    });
}

async function showDetail(pid, name, stage, season) {
    if (!pid && !currentPlayerId) {
        showToast("请先在「球员」下拉框中选择一名球员", "error");
        return;
    }
    if (pid) {
        detailPid = pid;
        detailName = name || pid;
    } else {
        detailPid = currentPlayerId;
        detailName = currentPlayerName || currentPlayerId;
    }
    detailStage = stage || stageMode;
    setStageToggle("detailStageToggle", detailStage);
    // 范围按钮保持当前选择
    $("detailRangeToggle").querySelectorAll("button[data-range]").forEach((b) => {
        b.classList.toggle("active", b.dataset.range === detailRange);
    });
    await loadDetailSeasons(season);
    await loadDetail();
    showModal("detailModal");
}

async function loadDetailSeasons(preferSeason) {
    const seasons = await fetchJSON(`/api/seasons?stage=${detailStage}`);
    $("detailSeason").innerHTML = seasons
        .map((s) => `<option value="${s}">${s} 赛季</option>`)
        .join("");
    const cur = preferSeason || $("seasonSelect").value;
    $("detailSeason").value = seasons.includes(cur) ? cur : seasons[0];
}

async function loadDetail() {
    if (!detailPid) return;
    const season = $("detailSeason").value;
    const reqPid = detailStage === "po" ? detailName || detailPid : detailPid;
    const d = await fetchJSON(
        `/api/player_detail?player_id=${encodeURIComponent(reqPid)}&season=${encodeURIComponent(season)}&stage=${detailStage}`
    );
    const alertBox = $("detailAlert");
    if (!d || !d.name) {
        $("detailBody").innerHTML = '<tr><td class="text-muted">该赛季无数据</td></tr>';
        alertBox.style.display = "";
        alertBox.textContent = "⚠️ " + (d && d.reason ? d.reason.message : "未查询到该球员数据");
        loadDetailTrend();
        return;
    }
    alertBox.style.display = "none";
    detailPid = d.pid;
    detailName = d.name_en || d.name;
    const fmt = (v, tail = "") => (v == null ? "--" : v + tail);
    const rows = [
        ["球员", d.name], ["赛季", `${d.season}（${detailStage === "po" ? "季后赛" : "常规赛"}）`],
        ["球队", teamCN(d.team)], ["位置", posLabel(d.pos)], ["年龄", d.age],
        ["出场 / 首发", `${d.g} 场 / ${d.gs ?? "-"} 场`],
        ["场均时间", fmt(d.mp, " 分钟")],
        ["场均得分", fmt(d.pts)], ["场均篮板", fmt(d.reb)], ["场均助攻", fmt(d.ast)],
        ["场均抢断", fmt(d.stl)], ["场均盖帽", fmt(d.blk)], ["场均失误", fmt(d.tov)],
        ["投篮命中率", d.fg == null ? "--" : (d.fg * 100).toFixed(1) + " %"],
        ["三分命中率", d.x3p == null ? "--" : (d.x3p * 100).toFixed(1) + " %"],
        ["罚球命中率", d.ft == null ? "--" : (d.ft * 100).toFixed(1) + " %"],
    ];
    $("detailBody").innerHTML = rows
        .map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`)
        .join("");
    loadDetailTrend();
}

// 全指标多赛季趋势：10 个指标，5 列 × 2 行多 grid 一屏展示
async function loadDetailTrend() {
    const reqPid = detailStage === "po" ? detailName || detailPid : detailPid;
    if (!reqPid) {
        detailTrendChart.clear();
        return;
    }
    const d = await fetchJSON(
        `/api/player_trends?player_id=${encodeURIComponent(reqPid)}&stage=${detailStage}&range=${detailRange}`
    );
    if (!d || !d.series || !d.seasons || !d.seasons.length) {
        detailTrendChart.clear();
        return;
    }
    const COLS = 5;
    const n = d.series.length;
    // 横轴每年都有刻度与数据点（缺赛年为空断点）；标签按年份密度隔年显示
    const ny = d.seasons.length;
    let labelInterval = 0;
    if (ny > 15) labelInterval = 3;
    else if (ny > 9) labelInterval = 2;
    else if (ny > 6) labelInterval = 1;
    const grids = [];
    const titles = [];
    const xAxes = [];
    const yAxes = [];
    const series = [];
    const cellW = 18.8;
    const gapX = 0.9;
    for (let i = 0; i < n; i++) {
        const col = i % COLS;
        const row = Math.floor(i / COLS);
        const left = 1.5 + col * (cellW + gapX);
        const top = row === 0 ? 9 : 57;
        grids.push({
            left: `${left}%`, width: `${cellW}%`,
            top: `${top}%`, height: "36%",
            containLabel: true,
        });
        titles.push({
            text: d.series[i].label,
            left: `${left}%`,
            top: `${top - 5}%`,
            textStyle: { fontSize: 12, color: "#93c5fd", fontWeight: 600 },
        });
        const isPct = d.series[i].key === "fg" || d.series[i].key === "x3p" || d.series[i].key === "ft";
        xAxes.push({
            gridIndex: i, type: "category", data: d.seasons,
            boundaryGap: false,
            axisLabel: { fontSize: 9, color: "#7a8ab0", interval: labelInterval, rotate: 35 },
            axisLine: { lineStyle: { color: "rgba(96,165,250,0.3)" } },
        });
        yAxes.push({
            gridIndex: i, type: "value", scale: true,
            axisLabel: { fontSize: 9, color: "#7a8ab0" },
            splitLine: { lineStyle: { color: "rgba(96,165,250,0.08)" } },
        });
        series.push({
            name: d.series[i].label,
            type: "line",
            smooth: true,
            connectNulls: true,
            xAxisIndex: i,
            yAxisIndex: i,
            data: d.series[i].data,
            lineStyle: { width: 2, color: isPct ? "#f0a500" : "#38bdf8" },
            itemStyle: { color: isPct ? "#f0a500" : "#38bdf8" },
            areaStyle: { color: isPct ? "rgba(240,165,0,0.12)" : "rgba(56,189,248,0.12)" },
            symbolSize: 6,
            showSymbol: true,
        });
    }
    const option = {
        title: titles,
        tooltip: { trigger: "axis", formatter: (p) => {
            const it = p[0];
            return `${it.axisValue} 赛季<br/>${it.seriesName}：<b>${it.data ?? "--"}</b>`;
        } },
        grid: grids,
        xAxis: xAxes,
        yAxis: yAxes,
        series,
    };
    detailTrendChart.setOption(option, true);
}

// =====================================================================
// 最近比赛（ESPN 更新，北京时间）
// =====================================================================
async function loadRecentGames(refresh = false) {
    const box = $("recentGamesBox");
    if (!box) return;
    try {
        const qs = new URLSearchParams({ days_back: "2", days_ahead: "3" });
        if (refresh) qs.set("refresh", "1");
        const d = await fetchJSON(`/api/recent_games?${qs.toString()}`);
        const games = d.games || [];
        if (!games.length) {
            box.innerHTML = '<div class="text-muted small p-2">最近两天暂无比赛</div>';
            $("recentUpdated").textContent = "";
            return;
        }
        box.innerHTML = games.map((g) => {
            const cls = g.live ? "live" : (g.played ? "final" : "upcoming");
            const hasScore = (g.played || g.live) && g.away_score != null && g.home_score != null;
            const score = hasScore
                ? `<span>${g.away_score}</span><span class="dim">–</span><span>${g.home_score}</span>`
                : '<span class="rg-vs">@</span>';
            const when = g.time_cn ? `${(g.date_cn || g.game_date || "").slice(5)} ${g.time_cn}` : (g.date_cn || g.game_date || "");
            const pre = g.season_type === "preseason"
                ? '<span class="badge tag-badge tag-pre">季前赛</span>' : "";
            const status = g.live ? "进行中" : (g.played ? "终场" : "未开赛");
            return `<article class="recent-game ${cls}"
                        style="--away-color:${teamColor(g.away_team)};--home-color:${teamColor(g.home_team)}"
                        title="${g.away_zh} @ ${g.home_zh} · ${when} 北京">
                <div class="rg-top">
                    <span class="rg-time">${when} <span class="rg-tz">北京</span>${pre}</span>
                    <span class="rg-status ${cls}">${status}</span>
                </div>
                <div class="rg-match">
                    <div class="rg-side">
                        ${teamMark(g.away_team)}
                        <span class="rg-name">${cnOn ? g.away_zh : teamDisplay(g.away_team, true)}</span>
                    </div>
                    <div class="rg-score">${score}</div>
                    <div class="rg-side home">
                        <span class="rg-name">${cnOn ? g.home_zh : teamDisplay(g.home_team, true)}</span>
                        ${teamMark(g.home_team)}
                    </div>
                </div>
            </article>`;
        }).join("");
        $("recentUpdated").textContent = `更新 ${d.updated_at || ""} · ESPN`;
    } catch (err) {
        console.error(err);
        box.innerHTML = '<div class="text-muted small p-2">最近比赛加载失败</div>';
    }
}

// =====================================================================
// 东西部排名 / 冠军墙
// =====================================================================
let standingsData = null;
let championsData = null;

function pctText(v) {
    if (v == null) return "-";
    return v.toFixed(3).replace(/^0/, "");
}

function renderStandingsTable(el, rows) {
    if (!el) return;
    if (!rows || !rows.length) {
        el.innerHTML = '<div class="text-muted small p-2">暂无排名数据</div>';
        return;
    }
    const body = rows.map((r) => {
        const cls = r.seed <= 6 ? "seed-playoff" : (r.seed <= 10 ? "seed-playin" : "");
        const starName = r.star
            ? (cnOn ? playerCN(r.star.player) : r.star.player.split(" ").pop())
            : null;
        const star = starName ? `★ ${starName} ${r.star.ppg}` : "★ 暂无";
        const titleTag = r.titles
            ? `<span class="titles-mini" title="${r.titles} 次总冠军">🏆${r.titles}</span>`
            : "";
        return `<tr class="${cls}">
            <td class="seed">${r.seed}</td>
            <td>
                <div class="standings-team" title="${r.star ? r.star.player : ""}">
                    ${teamMark(r.team)}
                    <span class="st-name">${teamDisplay(r.team, true)}</span>
                    ${titleTag}
                </div>
                <div class="standings-star">${star}</div>
            </td>
            <td class="standings-record">${r.w}-${r.l}</td>
            <td class="standings-pct">${pctText(r.pct)}</td>
            <td class="standings-gb gb-col">${r.gb ? r.gb.toFixed(1) : "-"}</td>
        </tr>`;
    }).join("");
    el.innerHTML = `<table class="standings-table">
        <thead><tr><th>#</th><th>球队 / 当家球星</th><th>胜-负</th><th>胜率</th><th class="gb-col">差</th></tr></thead>
        <tbody>${body}</tbody>
    </table>`;
}

async function loadStandings() {
    try {
        const d = await fetchJSON("/api/standings");
        standingsData = d;
        renderStandingsTable($("eastStandings"), d.east);
        renderStandingsTable($("westStandings"), d.west);
        $("standingsUpdated").textContent = `${d.season || ""} · ${d.as_of || ""} 北京`;
    } catch (err) {
        console.error(err);
        $("eastStandings").innerHTML = '<div class="text-muted small p-2">排名加载失败</div>';
        $("westStandings").innerHTML = '<div class="text-muted small p-2">排名加载失败</div>';
    }
}

function renderChampionWall(rows) {
    const box = $("championWall");
    if (!box) return;
    if (!rows || !rows.length) {
        box.innerHTML = '<div class="text-muted small p-2">暂无冠军数据</div>';
        return;
    }
    box.innerHTML = rows.map((c) => {
        const fmvp = c.fmvp
            ? `${c.fmvp}${c.fmvp_count > 1 ? ` ×${c.fmvp_count}` : ""}`
            : "—";
        const titleTag = c.titles ? `<span class="title-tag">🏆 ${c.titles}</span>` : "";
        const fmvpTag = c.fmvp_count > 1 ? `<span class="fmvp-tag">×${c.fmvp_count}</span>` : "";
        return `<div class="champion-row" title="${c.champion} def. ${c.runner_up} · ${c.series}">
            <span class="champion-year">${c.season}</span>
            ${teamMark(c.champion_abbr)}
            <div class="champion-body">
                <div class="champion-name">${c.champion} ${titleTag}</div>
                <div class="champion-fmvp">FMVP：<b>${fmvp}</b></div>
            </div>
            <div class="champion-tags">${fmvpTag}</div>
        </div>`;
    }).join("");
}

function renderFmvpBoard(items) {
    const box = $("fmvpLeaderboard");
    if (!box) return;
    if (!items.length) {
        box.innerHTML = "";
        return;
    }
    const top = items.slice(0, 6);
    box.innerHTML = `<div class="fmvp-board-head"><span>FMVP 榜</span><small>历史次数</small></div>
        <div class="fmvp-board-list">${top.map((x, i) => `<div class="fmvp-board-row">
            <span class="fmvp-rank">${i + 1}</span>
            <span class="fmvp-name">${x.name}</span>
            <span class="fmvp-count">×${x.count}</span>
        </div>`).join("")}</div>`;
}

function renderAllChampions() {
    const box = $("championsTable");
    if (!box || !championsData) return;
    const rows = championsData.all || [];
    box.innerHTML = `<table class="champ-table">
        <thead><tr><th>年份</th><th>冠军</th><th>亚军</th><th>FMVP</th><th class="tags-cell">标签</th></tr></thead>
        <tbody>${rows.map((c) => `<tr>
            <td class="year">${c.season}</td>
            <td><span class="team-cell">${teamMark(c.champion_abbr)}<span>${c.champion}</span></span></td>
            <td>${c.runner_up || "—"}</td>
            <td class="fmvp-cell"><b>${c.fmvp || "—"}</b>${c.fmvp_count > 1 ? ` ×${c.fmvp_count}` : ""}</td>
            <td class="tags-cell">${c.titles ? `<span class="title-tag">🏆 ${c.titles}</span>` : ""} ${c.fmvp ? `<span class="fmvp-tag">FMVP${c.fmvp_count > 1 ? " ×" + c.fmvp_count : ""}</span>` : ""}</td>
        </tr>`).join("")}</tbody>
    </table>`;
}

async function loadChampions() {
    try {
        championsData = await fetchJSON("/api/champions");
        renderChampionWall((championsData.recent || []).slice(0, 6));
        renderFmvpBoard(championsData.fmvp_counts || []);
        renderAllChampions();
        if (favActive && lastTeamForm) {
            renderTeamHero(lastTeamForm, lastTeamSched, lastInjuries, favActive);
        }
    } catch (err) {
        console.error(err);
        $("championWall").innerHTML = '<div class="text-muted small p-2">冠军数据加载失败</div>';
    }
}

function fmvpCountForName(name) {
    if (!championsData || !name) return 0;
    const key = normName(name);
    const item = (championsData.fmvp_counts || []).find((x) => normName(x.name) === key);
    return item ? item.count : 0;
}

// =====================================================================
// 主队管理（多主队）
// =====================================================================
async function loadFavTeam() {
    const f = await fetchJSON("/api/fav_team");
    favTeams = f.teams || [];
    favActive = f.active;
    renderFavChips();
    if (favActive) {
        await loadMainTeam(favActive);
    } else {
        renderTeamHero(null);
        ["teamFormBox", "scheduleBox", "attendanceBox", "injuryBox", "rosterBox"].forEach((id) => {
            $(id).innerHTML = '<div class="text-muted">添加主队后显示</div>';
        });
    }
    checkRemind();
}

function renderFavChips() {
    const labelOf = (t) =>
        cnOn
            ? teamCN(t.team)
            : t.name.replace(/^(Los Angeles |New York |Oklahoma City |San Antonio |Golden State |Portland |Toronto |Washington |Charlotte |Sacramento )/, "");
    $("favChips").innerHTML = favTeams.length
        ? favTeams
              .map(
                  (t) => `<span class="fav-chip ${t.team === favActive ? "active" : ""}" data-abbr="${t.team}">
                      ${teamMark(t.team)}
                      ${labelOf(t)}
                      <b class="chip-x" data-del="${t.team}">✕</b>
                  </span>`
              )
              .join("")
        : '<span class="text-muted">暂无，点「＋ 添加主队」</span>';
}

function renderTeamHero(form, sched = null, inj = null, team = null) {
    const hero = $("teamHero");
    const badge = $("teamHeroBadge");
    if (!hero || !badge) return;

    if (!team) {
        hero.style.setProperty("--team-color", "#f59e0b");
        badge.className = "team-mark lg";
        badge.style.setProperty("--team-color", "#5c7bd9");
        badge.textContent = "NBA";
        $("favTeamName").textContent = "未设置主队";
        $("teamHeroMeta").textContent = "选择一支主队，查看赛程、伤病与阵容";
        $("teamNextGame").innerHTML = '<span class="next-empty">设置主队后显示下一场比赛</span>';
        $("teamStar").textContent = "选择主队后显示当家球星";
        $("teamHeroBtn").textContent = "选择";
        return;
    }

    const color = teamColor(team);
    const key = TEAM_ALIAS[team] || team;
    hero.style.setProperty("--team-color", color);
    badge.className = "team-mark lg";
    badge.style.setProperty("--team-color", color);
    badge.textContent = team;
    $("favTeamName").textContent = teamDisplay(team, true);
    $("teamHeroBtn").textContent = "切换";

    const conf = TEAM_CONFERENCE[key] || "NBA";
    const record = form ? `${form.wins} 胜 ${form.total - form.wins} 负` : "暂无战绩";
    const injuryCount = Array.isArray(inj) ? inj.length : 0;
    const titles = form && form.titles ? ` · ${form.titles} 冠` : "";
    $("teamHeroMeta").textContent = `${conf} · ${record}${titles}${injuryCount ? ` · ${injuryCount} 人伤病` : ""}`;

    if (form && form.star) {
        const star = form.star;
        const fmvp = fmvpCountForName(star.player);
        $("teamStar").innerHTML = `★ 当家球星 <b>${playerCN(star.player)}</b> ` +
            `<span>${star.ppg} 分 / ${star.season || "上赛季"}</span>` +
            (fmvp ? ` <span class="fmvp-tag">FMVP ×${fmvp}</span>` : "");
    } else {
        $("teamStar").textContent = "★ 暂无当家球星数据";
    }

    const next = (sched || []).find((g) => g.live) || (sched || []).find((g) => !g.played);
    if (!next) {
        $("teamNextGame").innerHTML = '<span class="next-empty">暂无后续赛程</span>';
        return;
    }
    const live = !!next.live;
    const when = next.date_cn || next.game_date || "";
    const time = next.time_cn || "";
    const pre = next.season_type === "preseason" ? " · 季前赛" : "";
    const score = (live && next.score) ? `<span class="next-score">${next.score}</span>` : "";
    $("teamNextGame").innerHTML = `
        <div class="next-label">${live ? "LIVE NOW" : "NEXT GAME"} · 北京时间</div>
        <div class="next-main">
            ${teamMark(next.opponent)}
            <span>${teamDisplay(next.opponent, true)}</span>
            <span class="next-at">${next.is_home ? "主场" : "客场"}</span>
            ${live ? '<span class="next-live">进行中</span>' : ""}
            ${score}
        </div>
        <div class="next-time">${when} ${time}${pre}</div>`;
}

async function loadMainTeam(team) {
    const season = $("seasonSelect").value;
    const [form, sched, att, inj, rost] = await Promise.all([
        fetchJSON(`/api/team_form?team=${encodeURIComponent(team)}`),
        fetchJSON(`/api/schedule?team=${encodeURIComponent(team)}`),
        fetchJSON(`/api/attendance?team=${encodeURIComponent(team)}&season=${encodeURIComponent(season)}`),
        fetchJSON(`/api/injuries?team=${encodeURIComponent(team)}&refresh=1`),
        fetchJSON(`/api/roster?team=${encodeURIComponent(team)}&season=${encodeURIComponent(season)}`),
    ]);
    lastInjuries = Array.isArray(inj) ? inj : [];
    lastTeamForm = form;
    lastTeamSched = sched;
    renderTeamHero(form, sched, lastInjuries, team);
    renderForm(form);
    renderSchedule(sched);
    renderAttendance(att);
    renderInjury(inj);
    renderRoster(rost);
}

async function refreshMainTeamLive() {
    if (!favActive) return;
    try {
        const [form, sched] = await Promise.all([
            fetchJSON(`/api/team_form?team=${encodeURIComponent(favActive)}`),
            fetchJSON(`/api/schedule?team=${encodeURIComponent(favActive)}`),
        ]);
        lastTeamForm = form;
        lastTeamSched = sched;
        renderTeamHero(form, sched, lastInjuries, favActive);
        renderForm(form);
        renderSchedule(sched);
    } catch (err) {
        console.error(err);
    }
}

function renderBlocks(arr) {
    return arr
        .map((r) => `<span class="block ${r === "W" ? "block-win" : "block-loss"}">${r}</span>`)
        .join("");
}

function renderForm(f) {
    const streakText = f.streak
        ? `<b class="${f.streak_type === "W" ? "text-success" : "text-danger"}">${f.streak_type === "W" ? "🔥 " + f.streak + " 连胜" : "💧 " + f.streak + " 连败"}</b>`
        : "—";
    $("teamFormBox").innerHTML = `
        <div class="big-num">${f.wins}<small>/</small>${f.total - f.wins}</div>
        <div class="small text-muted">常规赛战绩 (胜-负)</div>
        <div class="mt-2">${streakText}</div>
        <div class="mt-3 small">近 10 场</div>
        <div class="mt-1">${renderBlocks(f.recent10)}</div>
        <div class="mt-3 small">主客场 / 东西部</div>
        <div class="mt-1">
            <span class="mini-label">主 ${f.home.w}-${f.home.g - f.home.w}</span>
            <span class="mini-label ms-1">客 ${f.away.w}-${f.away.g - f.away.w}</span>
        </div>
        <div class="mt-1">
            <span class="mini-label">东 ${f.east.w}-${f.east.g - f.east.w}</span>
            <span class="mini-label ms-1">西 ${f.west.w}-${f.west.g - f.west.w}</span>
        </div>
    `;
}

function renderSchedule(s) {
    if (!s.length) {
        $("scheduleBox").innerHTML = '<div class="text-muted">暂无赛程</div>';
        return;
    }
    const rows = s
        .map((g) => {
            const cls = g.live ? "row-live" : (g.played ? (g.result === "W" ? "row-win" : "row-loss") : "row-future");
            const seasonTag = g.season_type === "preseason"
                ? '<span class="badge tag-badge tag-pre">季前赛</span>' : "";
            const tags = seasonTag + (g.tags || [])
                .map((t) => `<span class="badge tag-badge">${t}</span>`)
                .join("");
            const note = localStorage.getItem(`note_${favActive}_${g.game_date}`) || "";
            const dateLabel = g.date_cn ? g.date_cn.slice(5) : g.game_date;
            const timeLabel = g.time_cn ? `<div class="sched-time">${g.time_cn} 北京</div>` : "";
            const statusCell = (g.played && g.score)
                ? `<span class="result-pill ${g.result === "W" ? "win" : "loss"}">${g.result} ${g.score}</span>`
                : (g.live
                    ? `<span class="result-pill live">进行中 ${g.score || ""}</span>`
                    : (g.played
                        ? '<span class="result-pill future">终场</span>'
                        : `<span class="result-pill future">${g.time_cn || "未开赛"}</span>`));
            return `<tr class="${cls}">
                <td>
                    <div class="sched-date">${dateLabel}</div>
                    ${timeLabel}
                </td>
                <td>
                    <div class="sched-opp">
                        ${teamMark(g.opponent)}
                        <span>${teamDisplay(g.opponent, true)}</span>
                        <span class="home-tag">${g.is_home ? "主" : "客"}</span>
                    </div>
                    <div class="sched-tools">
                        <button class="h2h-btn" data-opp="${g.opponent}" title="查看交锋">交锋</button>
                        <button class="note-btn" data-date="${g.game_date}" title="添加备注">备注</button>
                    </div>
                    ${note ? `<div class="note-text">📌 ${note}</div>` : ""}
                </td>
                <td>${statusCell}</td>
                <td>${tags}</td>
            </tr>`;
        })
        .join("");
    $("scheduleBox").innerHTML = `
        <div class="sched-scroll"><table class="table table-sm table-dark sched-table">
            <thead><tr><th>日期（北京）</th><th>对阵</th><th>结果</th><th>标签</th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div>`;
    $("scheduleBox").querySelectorAll(".h2h-btn").forEach((b) => {
        b.addEventListener("click", () => openH2h(b.dataset.opp));
    });
    $("scheduleBox").querySelectorAll(".note-btn").forEach((b) => {
        b.addEventListener("click", () => toggleNote(b.dataset.date));
    });
}

function renderAttendance(a) {
    attData = a;
    applyAttFilter();
}

function applyAttFilter() {
    let list = attData;
    if (attFilter === "core") {
        list = attData.filter((p) => p.label === "铁人" || p.label === "稳定首发" || p.start_rate >= 60);
    } else if (attFilter === "edge") {
        list = attData.filter((p) => p.label === "轮换边缘" || p.attendance < 55);
    }
    const rows = list
        .slice(0, 14)
        .map(
            (p) => `<tr>
                <td>${playerCN(p.player)}</td>
                <td>${posLabel(p.pos)}</td>
                <td>
                    <div class="progress thin-progress">
                        <div class="progress-bar ${p.attendance >= 70 ? "bg-success" : "bg-warning"}" style="width:${p.attendance}%">${p.attendance}%</div>
                    </div>
                </td>
                <td><span class="badge tag-badge">${p.label}</span></td>
            </tr>`
        )
        .join("");
    const season = $("seasonSelect").value;
    const teamTxt = teamCN(favActive);
    const teamGames = (attData[0] && attData[0].team_games) || 82;
    const noteHead = `<div class="att-note small text-muted">📊 ${season} 赛季 · <b>常规赛</b>出勤与首发，仅统计当前主队（${teamTxt}）当季有出场的球员，<b>非全联盟</b>；季后赛不出勤。</div>`;
    const noteFoot = `<div class="att-note-foot small text-muted mt-1">
        标签标准：<b>铁人</b>＝出场≥${Math.round(teamGames * 0.878)}场；<b>稳定首发</b>＝首发率≥60%；<b>主力轮换</b>＝出勤率≥55%；其余为<b>轮换边缘</b>。
        出勤率=出场数/${teamGames}（该赛季球队场次，封顶100%），首发率=首发数/出场数。</div>`;
    $("attendanceBox").innerHTML = rows
        ? `${noteHead}<div class="sched-scroll"><table class="table table-sm table-dark sched-table">
            <thead><tr><th>球员</th><th>位置</th><th>出勤率</th><th>标签</th></tr></thead>
            <tbody>${rows}</tbody></table></div>${noteFoot}`
        : `${noteHead}<div class="text-muted">无匹配球员</div>${noteFoot}`;
}

function renderInjury(inj) {
    if (!inj || !inj.length) {
        $("injuryBox").innerHTML = '<div class="text-muted">暂无伤病记录（ESPN 当前无该队记录）</div>';
        return;
    }
    const updated = inj.find((x) => x.updated_at)?.updated_at || "";
    let updatedTxt = "";
    if (updated) {
        const dt = new Date(updated);
        if (!Number.isNaN(dt.getTime())) {
            updatedTxt = ` · 更新 ${dt.toLocaleString("zh-CN", {
                timeZone: "Asia/Shanghai", month: "2-digit", day: "2-digit",
                hour: "2-digit", minute: "2-digit",
            })} 北京`;
        }
    }
    $("injuryBox").innerHTML = inj
        .map(
            (x) => `<div class="injury-item">
                <div><b>${playerCN(x.player)}</b> <span class="badge tag-badge">${x.status}</span>
                    ${x.is_sample ? '<span class="badge tag-badge tag-pre">示例数据</span>' : ""}</div>
                <div class="small text-muted">${x.injury_type || "伤病"} · 预计复出：${x.return_date || "待定"}</div>
                ${x.note && !x.is_sample ? `<div class="injury-note small text-muted">${x.note}</div>` : ""}
            </div>`
        )
        .join("") + `<div class="att-note-foot small text-muted mt-1">数据源：ESPN${updatedTxt}</div>`;
}

function renderRoster(rost) {
    if (!rost || !rost.stats || !rost.stats.count) {
        $("rosterBox").innerHTML = '<div class="text-muted">暂无数据</div>';
        return;
    }
    const st = rost.stats;
    const posOrder = ["G", "F", "C", "未知"];
    const groupHtml = posOrder
        .filter((p) => rost.groups[p])
        .map((p) => {
            const list = rost.groups[p];
            const shown = list.slice(0, 6).map((pl) => {
                const dn = playerCN(pl.player);
                const short = cnOn ? dn : pl.player.split(" ").pop();
                const pts = pl.pts == null ? "-" : pl.pts;
                return `<span class="roster-player ${pl.tag === "核心" ? "core" : ""}" title="${dn} · ${pl.tag}">${short} ${pts}分</span>`;
            }).join("");
            const more = list.length > 6 ? `<span class="roster-player">+${list.length - 6}</span>` : "";
            return `<div class="roster-pos">
                <span class="pos-tag">${posLabel(p)}</span>
                ${shown}${more}
            </div>`;
        })
        .join("");
    $("rosterBox").innerHTML = `
        <div class="roster-stats">
            <span class="mini-label">共 ${st.count} 人</span>
            <span class="mini-label">平均年龄 ${st.avg_age}</span>
            <span class="mini-label">新秀 ${st.rookie}</span>
            <span class="mini-label">老将 ${st.veteran}</span>
            <span class="mini-label">核心 ${st.core}</span>
            <span class="mini-label">轮换/角色 ${st.role}</span>
        </div>
        <div class="mt-2">${groupHtml}</div>`;
}

// ---------- 主队选择 / 多主队 ----------
async function openFavTeamModal() {
    const season = $("seasonSelect").value;
    const teams = await fetchJSON(`/api/teams?season=${encodeURIComponent(season)}`);
    const mine = favTeams.map((t) => t.team);
    $("teamGrid").innerHTML = teams
        .map((t) => `<button class="team-chip ${mine.includes(t.abbr) ? "active" : ""}"
                    style="--team-color:${teamColor(t.abbr)}" data-abbr="${t.abbr}">
                    ${teamMark(t.abbr)}<span>${teamDisplay(t.abbr, true)}</span>
                </button>`)
        .join("");
    const modal = bootstrap.Modal.getOrCreateInstance($("favTeamModal"));
    modal.show();
    $("teamGrid").onclick = async (e) => {
        const chip = e.target.closest(".team-chip");
        if (!chip) return;
        const abbr = chip.dataset.abbr;
        if (mine.includes(abbr)) {
            await fetchJSON(`/api/fav_team/remove`, "POST", { team: abbr }); // 取消关注
            showToast(`已取消关注 ${teamDisplay(abbr, true)}`);
        } else {
            const res = await fetchJSON(`/api/fav_team`, "POST", { team: abbr }); // 添加关注
            if (res && res.ok === false) {
                showToast(res.msg || "添加主队失败", "error");
                return;
            }
            showToast(`已关注 ${teamDisplay(abbr, true)}`);
        }
        await loadFavTeam();
        modal.hide();
    };
}

// 顶部 chips：点击切换默认主队 / 点 ✕ 取消关注
document.addEventListener("click", async (e) => {
    const chip = e.target.closest(".fav-chip");
    const del = e.target.closest(".chip-x");
    if (del) {
        await fetchJSON(`/api/fav_team/remove`, "POST", { team: del.dataset.del });
        showToast(`已取消关注 ${teamDisplay(del.dataset.del, true)}`);
        await loadFavTeam();
        return;
    }
    if (chip && chip.dataset.abbr && chip.dataset.abbr !== favActive) {
        await fetchJSON(`/api/fav_team/active`, "POST", { team: chip.dataset.abbr });
        await loadFavTeam();
    }
});

// ---------- 历史交锋 ----------
async function openH2h(opp) {
    if (!favActive) return;
    const d = await fetchJSON(`/api/h2h?team=${encodeURIComponent(favActive)}&opp=${encodeURIComponent(opp)}`);
    $("h2hTitle").textContent = `${teamCN(favActive)} vs ${teamCN(opp)} 历史交锋`;
    if (!d.total) {
        $("h2hBody").innerHTML = '<div class="text-muted p-2">本赛季暂无完赛记录</div>';
        showModal("h2hModal");
        return;
    }
    const last5 = d.last5
        .map(
            (g) => `<span class="block ${g.result === "W" ? "block-win" : "block-loss"}">${g.result}</span><span class="small ms-1">${g.date} 分差 ${g.margin > 0 ? "+" : ""}${g.margin}</span><br>`
        )
        .join("");
    $("h2hBody").innerHTML = `
        <div class="h2h-summary">
            <span class="mini-label">${d.wins} 胜 ${d.losses} 负</span>
            <span class="mini-label">平均净胜 ${d.avg_margin > 0 ? "+" : ""}${d.avg_margin}</span>
        </div>
        <div class="mt-2 small">近 5 次交锋</div>
        <div class="mt-1">${last5 || '<span class="text-muted">不足 5 场</span>'}</div>
        <div class="small text-muted mt-2">* 基于已导入的赛季赛程数据</div>`;
    showModal("h2hModal");
}

// ---------- 赛程备注（本地存储） ----------
function toggleNote(date) {
    const key = `note_${favActive}_${date}`;
    const old = localStorage.getItem(key) || "";
    const txt = prompt(`为 ${date} 这场比赛添加备注（留空则删除）：`, old);
    if (txt === null) return;
    if (txt.trim()) localStorage.setItem(key, txt.trim());
    else localStorage.removeItem(key);
    loadMainTeam(favActive);
}

// ---------- 观赛提醒（本地存储） ----------
function bindRemindToggle() {
    $("remindToggle").checked = localStorage.getItem("remindOn") === "1";
    $("remindToggle").addEventListener("change", (e) => {
        localStorage.setItem("remindOn", e.target.checked ? "1" : "0");
        if (e.target.checked) checkRemind();
    });
}

function checkRemind() {
    if (localStorage.getItem("remindOn") !== "1" || !favActive) return;
    const now = Date.now();
    fetchJSON(`/api/schedule?team=${encodeURIComponent(favActive)}`).then((sched) => {
        const soon = sched.filter((g) => {
            if (g.played || g.is_preseason || !g.tipoff_utc) return false;
            const diff = new Date(g.tipoff_utc).getTime() - now;
            return diff >= 0 && diff <= 3 * 86400000;
        }).filter((g) => {
            const key = `remind_seen_${favActive}_${g.game_date}_${g.opponent}`;
            if (localStorage.getItem(key) === "1") return false;
            localStorage.setItem(key, "1");
            return true;
        });
        if (soon.length) {
            const lines = soon
                .map((g) => `${g.date_cn} ${g.time_cn || ""} 北京 ${g.is_home ? "主场" : "客场"} vs ${teamCN(g.opponent)}`.trim())
                .join("\n");
            alert(`⏰ 主队 ${teamCN(favActive)} 3 天内开赛（北京时间）：\n${lines}`);
        }
    }).catch((err) => console.error(err));
}

// =====================================================================
// 观察名单
// =====================================================================
async function addWatch() {
    if (!currentPlayerId) {
        showToast("请先在「球员」下拉框中选择一名球员", "error");
        return;
    }
    const opt = $("playerSelect").selectedOptions[0];
    const name = opt ? (opt.dataset.en || opt.textContent.split(" (")[0]) : "";
    await fetchJSON(
        `/api/watchlist/add?player_id=${encodeURIComponent(currentPlayerId)}&player_name=${encodeURIComponent(name)}`
    );
    showToast("已加入观察名单");
}

async function loadWatchSeasons() {
    const seasons = await fetchJSON(`/api/seasons?stage=${watchStage}`);
    const cur = $("watchSeason").value || $("seasonSelect").value;
    $("watchSeason").innerHTML = seasons
        .map((s) => `<option value="${s}">${s} 赛季</option>`)
        .join("");
    $("watchSeason").value = seasons.includes(cur) ? cur : seasons[0];
}

async function openWatchlist() {
    setStageToggle("watchStageToggle", watchStage);
    await loadWatchSeasons();
    const wl = await fetchJSON("/api/watchlist");
    $("watchlistBox").innerHTML = wl.length
        ? wl.map((p) => {
              const g = p.g || 0;
              const avg = (v) => (g && v != null ? (v / g).toFixed(1) : "--");
              const avgPts = avg(p.pts);
              const avgReb = avg(p.trb);
              const avgAst = avg(p.ast);
              return `
            <div class="watch-card">
                <div class="d-flex justify-content-between align-items-start">
                    <div>
                        <b>${playerCN(p.player_name)}</b>
                        <small class="text-muted"> · ${posLabel(p.pos)} · ${teamCN(p.team || "-")} · 最新常规赛 ${p.season || ""}</small>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-primary me-1" data-watch-load="${p.player_id}" data-watch-name="${p.player_name}">查看</button>
                        <button class="btn btn-sm btn-danger" data-watch-del="${p.player_id}">移除</button>
                    </div>
                </div>
                <div class="small text-muted mt-1">最新常规赛场均 ${avgPts} 分 · ${avgReb} 板 · ${avgAst} 助（${g} 场）　<span class="text-warning">点「查看」可按上方选择的年份/常规赛·季后赛查看</span></div>
            </div>`;
          }).join("")
        : '<div class="text-muted p-3">还没有收藏球员，去左侧选择球员后点「⭐ 收藏到观察名单」</div>';
    const modal = bootstrap.Modal.getOrCreateInstance($("watchlistModal"));
    modal.show();
    $("watchlistBox").onclick = async (e) => {
        const loadBtn = e.target.closest("[data-watch-load]");
        const delBtn = e.target.closest("[data-watch-del]");
        if (loadBtn) {
            const pid = loadBtn.dataset.watchLoad;
            const name = loadBtn.dataset.watchName;
            const season = $("watchSeason").value;
            const stage = watchStage;
            modal.hide();
            // 以观察名单选择的独立 stage/season 打开详情
            setTimeout(() => showDetail(pid, name, stage, season), 200);
        }
        if (delBtn) {
            await fetchJSON(`/api/watchlist/remove?player_id=${encodeURIComponent(delBtn.dataset.watchDel)}`);
            await openWatchlist();
        }
    };
}

// =====================================================================
// 球员/球队搜索（含中文别名）
// =====================================================================
function bindShortcuts() {
    document.addEventListener("keydown", (e) => {
        if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
        const tag = (document.activeElement || {}).tagName || "";
        if (["INPUT", "TEXTAREA", "SELECT"].includes(tag)) return;
        if (document.querySelector(".modal.show")) return;
        const key = e.key.toLowerCase();
        if (e.key === "?") {
            e.preventDefault();
            showModal("helpModal");
        } else if (key === "f") {
            e.preventDefault();
            openFavTeamModal();
        } else if (key === "w") {
            e.preventDefault();
            openWatchlist();
        } else if (key === "c") {
            e.preventDefault();
            openCompare();
        } else if (key === "m") {
            e.preventDefault();
            openRadarMulti();
        }
    });
}

function bindSearch() {
    const input = $("searchInput");
    document.addEventListener("keydown", (e) => {
        const tag = (document.activeElement || {}).tagName || "";
        if (document.querySelector(".modal.show") && e.key !== "Escape") return;
        if (e.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(tag)) {
            e.preventDefault();
            input.focus();
        }
        if (e.key === "Escape") {
            input.blur();
            $("searchResult").innerHTML = "";
        }
    });
    input.addEventListener("input", () => {
        clearTimeout(searchTimer);
        const q = input.value.trim();
        if (!q) {
            $("searchResult").innerHTML = "";
            return;
        }
        searchTimer = setTimeout(async () => {
            const season = $("seasonSelect").value;
            const rs = await fetchJSON(`/api/search?q=${encodeURIComponent(q)}&season=${encodeURIComponent(season)}&${stageParam()}`);
            $("searchResult").innerHTML = rs.length
                ? rs
                      .map((r) => {
                          const isTeam = r.type === "team";
                          const showName = isTeam ? teamCN(r.team) : playerCN(r.player);
                          const subTeam = isTeam ? "" : ` · ${teamCN(r.team)}`;
                          const subPos = isTeam ? "球队" : posLabel(r.pos);
                          return `<div class="search-item" data-type="${r.type}" data-pid="${r.player_id}" data-name="${r.player}">
                              ${isTeam ? "🏟️" : "🏀"} ${showName}${!cnOn && r.cn ? `<span class="cn-tag">${r.cn}</span>` : ""} <small>${subTeam.trimStart()} · ${subPos}</small>
                          </div>`;
                      })
                      .join("")
                : '<div class="search-item muted">无匹配结果</div>';
        }, 300);
    });
    input.addEventListener("blur", () => {
        setTimeout(() => ($("searchResult").innerHTML = ""), 200);
    });
    $("searchResult").addEventListener("mousedown", async (e) => {
        const item = e.target.closest(".search-item");
        if (!item) return;
        const type = item.dataset.type;
        if (type === "team") {
            // 球队结果 → 加入主队（POST）
            const res = await fetchJSON(`/api/fav_team`, "POST", { team: item.dataset.pid });
            if (res && res.ok === false) {
                showToast(res.msg || "添加主队失败", "error");
                return;
            }
            showToast(`已关注 ${teamDisplay(item.dataset.pid, true)}`);
            await loadFavTeam();
            input.value = "";
            $("searchResult").innerHTML = "";
            return;
        }
        const pid = item.dataset.pid;
        const opt = [...$("playerSelect").options].find((o) => o.value === pid);
        if (opt) $("playerSelect").value = pid;
        else {
            const o = new Option(playerCN(item.dataset.name), pid);
            o.dataset.en = item.dataset.name;
            $("playerSelect").add(o);
            $("playerSelect").value = pid;
        }
        input.value = "";
        $("searchResult").innerHTML = "";
        loadPlayerCharts();
    });
}

// =====================================================================
// 对位对比（独立数据类型/赛季，切换不重置）
// =====================================================================
function matchInSelect(sel, oldPid, oldEn) {
    const opts = [...sel.options];
    let hit = opts.find((o) => o.value === oldPid);
    if (hit) return hit.value;
    const nm = normName(oldEn || "");
    if (nm) {
        hit = opts.find((o) => normName(o.dataset.en || optName(o.textContent)) === nm);
        if (hit) return hit.value;
    }
    return null;
}

// 切换赛季/常规赛季后赛后，旧球员在新列表里没有（如未进季后赛）时，
// 仍保留该球员（补临时 option），不主动重置；后端返回“无数据”原因。
function appendMissingOption(sel, pid, en) {
    if (!pid) return;
    if ([...sel.options].some((o) => o.value === pid)) {
        sel.value = pid;
        return;
    }
    const label = playerCN(en || pid);
    const o = document.createElement("option");
    o.value = pid;
    o.dataset.en = en || "";
    o.textContent = `${label}（该赛季无数据）`;
    sel.appendChild(o);
    sel.value = pid;
}

async function openCompare() {
    setStageToggle("compareStageToggle", compareStage);
    const firstOpen = !$("compareA").options.length;
    await loadCompareSeasons();
    await loadComparePlayers();
    if (firstOpen && !$("compareA").value && favActive) {
        // 仅首次打开时，若有主队则预选主队一名球员
        const mine = [...$("compareA").options].find((o) => o.dataset.team === favActive);
        if (mine) $("compareA").value = mine.value;
    }
    await renderCompare();
    showModal("compareModal");
}

async function loadCompareSeasons() {
    const seasons = await fetchJSON(`/api/seasons?stage=${compareStage}`);
    const cur = $("compareSeason").value || $("seasonSelect").value;
    $("compareSeason").innerHTML = seasons
        .map((s) => `<option value="${s}">${s} 赛季</option>`)
        .join("");
    $("compareSeason").value = seasons.includes(cur) ? cur : seasons[0];
}

async function loadComparePlayers() {
    const season = $("compareSeason").value;
    const players = await fetchJSON(`/api/players?season=${encodeURIComponent(season)}&stage=${compareStage}`);
    const oldA = $("compareA").value;
    const oldAEn = $("compareA").selectedOptions[0] ? ($("compareA").selectedOptions[0].dataset.en || "") : "";
    const oldB = $("compareB").value;
    const oldBEn = $("compareB").selectedOptions[0] ? ($("compareB").selectedOptions[0].dataset.en || "") : "";
    const opts = players
        .map((p) => `<option value="${p.player_id}" data-en="${p.player}" data-team="${p.team}">${playerCN(p.player)} (${teamCN(p.team)})</option>`)
        .join("");
    $("compareA").innerHTML = '<option value="">选择球员</option>' + opts;
    $("compareB").innerHTML = '<option value="">选择球员</option>' + opts;
    // 保留已选球员（跨 stage 按英文姓名匹配）；新列表里没有时补临时 option，不重置
    const keepA = matchInSelect($("compareA"), oldA, oldAEn);
    const keepB = matchInSelect($("compareB"), oldB, oldBEn);
    if (keepA) $("compareA").value = keepA;
    else if (oldA) appendMissingOption($("compareA"), oldA, oldAEn);
    if (keepB) $("compareB").value = keepB;
    else if (oldB) appendMissingOption($("compareB"), oldB, oldBEn);
}

async function renderCompare() {
    const a = $("compareA").value;
    const b = $("compareB").value;
    const swapBtn = $("compareSwapBtn");
    if (swapBtn) swapBtn.disabled = !(a && b);
    if (!a || !b) {
        $("compareResult").innerHTML = '<div class="text-muted">选择两名球员开始对比（我方球员选 A）</div>';
        return;
    }
    const season = $("compareSeason").value;
    const d = await fetchJSON(`/api/compare?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}&season=${encodeURIComponent(season)}&stage=${compareStage}`);
    if (!d.a || !d.b) {
        const msgs = (d.missing || []).map((m) => `⚠️ ${m.reason.message}`).join("<br/>");
        $("compareResult").innerHTML = `<div class="alert alert-warning py-2 small">${msgs || "所选球员在该赛季暂无数据"}</div>`;
        return;
    }
    const fields = [
        ["pts", "得分"], ["reb", "篮板"], ["ast", "助攻"],
        ["stl", "抢断"], ["blk", "盖帽"], ["tov", "失误"],
        ["fg", "命中率%"], ["x3p", "三分%"],
    ];
    const isPct = (k) => k === "fg" || k === "x3p";
    const lowerBetter = new Set(["tov"]);
    const fmt = (k, v) => {
        if (v === null || v === undefined || Number.isNaN(v)) return "--";
        return isPct(k) ? `${v} %` : `${v}`;
    };
    const rows = fields
        .map(([k, label]) => {
            const va = d.a[k], vb = d.b[k];
            const both = va !== null && vb !== null && va !== undefined && vb !== undefined;
            const aBetter = both && (lowerBetter.has(k) ? va < vb : va > vb);
            const bBetter = both && (lowerBetter.has(k) ? vb < va : vb > va);
            return `<tr><td class="${aBetter ? "adv-a" : ""}">${fmt(k, va)}</td><td class="mid-cell">${label}</td><td class="${bBetter ? "adv-b" : ""}">${fmt(k, vb)}</td></tr>`;
        })
        .join("");
    const tags = (x) => `${x.fmvp_count ? `<span class="fmvp-tag">FMVP ×${x.fmvp_count}</span>` : ""}${x.team_titles ? `<span class="title-tag">队史 ${x.team_titles} 冠</span>` : ""}`;
    $("compareResult").innerHTML = `
        <div class="small text-muted mb-1">赛季：${season} · ${compareStage === "po" ? "🔥季后赛" : "🏀常规赛"}场均</div>
        <div class="table-responsive"><table class="table table-sm table-dark compare-table">
            <thead><tr>
                <th>${d.a.name} <small class="text-muted">${posLabel(d.a.pos)} · ${d.a.team}</small><div class="compare-tags">${tags(d.a)}</div></th>
                <th></th>
                <th>${d.b.name} <small class="text-muted">${posLabel(d.b.pos)} · ${d.b.team}</small><div class="compare-tags">${tags(d.b)}</div></th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table></div>
        <div class="small text-muted mt-2">🟥 红色 = A 优势 · 🟦 蓝色 = B 优势 · 失误越低越好 · 数据为该赛季场均</div>`;
}

// =====================================================================
// 多球员雷达 + 柱状图对比（独立数据类型/赛季，切换保留，放大加粗）
// =====================================================================
async function openRadarMulti() {
    setStageToggle("multiStageToggle", multiStage);
    await loadMultiSeasons();
    await loadMultiPlayers();
    renderMultiChips();
    if (!multiSel.length) {
        multiRadarChart.clear();
        multiBarChart.clear();
    } else {
        renderMultiRadar();
    }
    showModal("radarMultiModal");
}

async function loadMultiSeasons() {
    const seasons = await fetchJSON(`/api/seasons?stage=${multiStage}`);
    const cur = $("multiSeason").value || $("seasonSelect").value;
    $("multiSeason").innerHTML = seasons
        .map((s) => `<option value="${s}">${s} 赛季</option>`)
        .join("");
    $("multiSeason").value = seasons.includes(cur) ? cur : seasons[0];
}

async function loadMultiPlayers() {
    const season = $("multiSeason").value;
    const players = await fetchJSON(`/api/players?season=${encodeURIComponent(season)}&stage=${multiStage}`);
    $("multiAdd").innerHTML =
        '<option value="">—— 选择球员加入对比 ——</option>' +
        players.map((p) => `<option value="${p.player_id}" data-en="${p.player}" data-team="${p.team}">${playerCN(p.player)} (${teamCN(p.team)})</option>`).join("");
    $("multiAddBtn").disabled = true;
    // 跨 stage / 赛季重新映射已选球员（按姓名），保留选择
    const next = [];
    for (const item of multiSel) {
        let hit = players.find((p) => p.player_id === item.pid);
        if (!hit) {
            const nm = normName(item.name);
            hit = players.find((p) => normName(p.player) === nm);
        }
        if (hit) next.push({ pid: hit.player_id, name: hit.player });
        else next.push(item);
    }
    multiSel = next;
}

function multiAddPlayer() {
    const pid = $("multiAdd").value;
    if (!pid) return;
    if (multiSel.some((x) => x.pid === pid)) {
        showToast("这名球员已经在对比列表里了", "error");
        return;
    }
    if (multiSel.length >= 6) {
        showToast("最多同时对比 6 名球员", "error");
        return;
    }
    const sel = $("multiAdd").selectedOptions[0];
    const name = sel ? (sel.dataset.en || optName(sel.textContent)) : pid;
    multiSel.push({ pid, name });
    $("multiAdd").value = "";
    $("multiAddBtn").disabled = true;
    renderMultiChips();
    renderMultiRadar();
}

function renderMultiChips() {
    $("multiChips").innerHTML = multiSel.length
        ? multiSel
              .map((item) => {
                  const opt = [...$("multiAdd").options].find((o) => o.value === item.pid);
                  const inSeason = !!opt;
                  return `<span class="fav-chip ${inSeason ? "active" : "chip-missing"}" title="${inSeason ? "" : "该赛季无数据"}">${playerCN(item.name)}${inSeason ? "" : "（该赛季无数据）"} <b class="chip-x" data-rm="${item.pid}">✕</b></span>`;
              })
              .join("")
        : '<span class="text-muted small">请选择 2-6 名球员进行叠加对比</span>';
    const clearBtn = $("multiClearBtn");
    if (clearBtn) clearBtn.disabled = !multiSel.length;
    $("multiChips").querySelectorAll("[data-rm]").forEach((x) => {
        x.addEventListener("click", () => {
            multiSel = multiSel.filter((p) => p.pid !== x.dataset.rm);
            renderMultiChips();
            renderMultiRadar();
        });
    });
}

async function renderMultiRadar() {
    if (!multiSel.length) {
        multiRadarChart.clear();
        multiBarChart.clear();
        return;
    }
    const season = $("multiSeason").value;
    const ids = multiSel.map((x) => x.pid).join(",");
    const opt = await fetchJSON(`/api/radar_multi?ids=${encodeURIComponent(ids)}&season=${encodeURIComponent(season)}&stage=${multiStage}`);
    if (opt && opt.series) {
        opt.radar = opt.radar || {};
        opt.radar.radius = "72%";
        opt.radar.axisName = { fontSize: 14, color: "#c7d6f0", fontWeight: 600 };
        opt.radar.splitLine = { lineStyle: { color: "rgba(96,165,250,0.2)" } };
        opt.radar.splitArea = { areaStyle: { color: ["rgba(96,165,250,0.03)", "rgba(96,165,250,0.08)"] } };
        opt.series[0].lineStyle = { width: 2.5 };
        opt.series[0].symbolSize = 7;
        opt.legend = Object.assign(opt.legend || {}, { bottom: 0, textStyle: { fontSize: 13 }, itemWidth: 18, itemHeight: 12 });
        opt.tooltip = { trigger: "item" };
        multiRadarChart.setOption(opt, true);
    } else {
        multiRadarChart.clear();
    }
    await renderMultiBar(season);
}

// 多球员六维分组柱状图（放大加粗 + 数值标签）
async function renderMultiBar(season) {
    if (!multiSel.length) {
        multiBarChart.clear();
        return;
    }
    const ids = multiSel.map((x) => x.pid).join(",");
    const d = await fetchJSON(`/api/multi_bar?ids=${encodeURIComponent(ids)}&season=${encodeURIComponent(season)}&stage=${multiStage}`);
    if (!d.players || !d.players.length) {
        multiBarChart.clear();
        return;
    }
    const colors = ["#f0a500", "#38bdf8", "#e879f9", "#4ade80", "#f87171", "#a78bfa"];
    const option = {
        title: {
            text: "六维数据分组柱状对比（场均）",
            left: "center",
            textStyle: { fontSize: 15 },
        },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        legend: { bottom: 0, type: "scroll", textStyle: { fontSize: 13 }, itemWidth: 18, itemHeight: 12 },
        grid: { left: 50, right: 25, bottom: 70, top: 55 },
        xAxis: {
            type: "category",
            data: d.dims,
            axisLabel: { fontSize: 15, color: "#c7d6f0", fontWeight: 600 },
            axisLine: { lineStyle: { color: "rgba(96,165,250,0.4)" } },
        },
        yAxis: {
            type: "value",
            axisLabel: { fontSize: 12, color: "#7a8ab0" },
            splitLine: { lineStyle: { color: "rgba(96,165,250,0.12)" } },
        },
        series: d.players.map((name, i) => ({
            name,
            type: "bar",
            data: d.data[i],
            barMaxWidth: 34,
            barGap: "15%",
            itemStyle: { color: colors[i % colors.length], borderRadius: [3, 3, 0, 0] },
            label: { show: true, position: "top", fontSize: 11, color: "#e6edf7", formatter: (p) => p.value },
        })),
    };
    multiBarChart.setOption(option, true);
}

window.addEventListener("DOMContentLoaded", init);
