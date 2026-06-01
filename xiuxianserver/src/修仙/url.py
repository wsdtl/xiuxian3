"""修仙模块 HTTP 路由入口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .sql import db


router = APIRouter()


@router.get("/xiuxian/live", response_class=HTMLResponse)
async def xiuxian_live_page() -> HTMLResponse:
    """修仙实时数据预览页。"""

    return HTMLResponse(_LIVE_PAGE_HTML)


@router.get("/xiuxian/live/data")
async def xiuxian_live_data() -> dict[str, Any]:
    """返回修仙实时总览数据。"""

    return {
        "summary": _summary(),
        "status": _status_rows(),
        "players": _player_rows(),
        "explorations": _exploration_rows(),
        "wormholes": _wormhole_rows(),
        "seasonal_bosses": _seasonal_boss_rows(),
        "market": _market_rows(),
        "logs": _recent_logs(),
    }


def _summary() -> dict[str, int]:
    """聚合当前世界核心指标。"""

    player = _one(
        """
        SELECT
            COUNT(*) AS total_players,
            COALESCE(SUM(source_stones), 0) AS total_stones,
            SUM(CASE WHEN status != '空闲' THEN 1 ELSE 0 END) AS busy_players,
            SUM(CASE WHEN status = '探险中' THEN 1 ELSE 0 END) AS exploring_players
        FROM players
        """
    )
    vault = _one("SELECT COALESCE(SUM(balance), 0) AS total_vault_balance FROM source_vaults")
    weapon = _one("SELECT COUNT(*) AS total_weapons FROM player_weapons")
    listing = _one("SELECT COUNT(*) AS active_listings FROM second_hand_listings")
    wormhole = _one("SELECT COUNT(*) AS open_wormholes FROM wormholes WHERE status = '开启'")
    boss = _one("SELECT COUNT(*) AS open_bosses FROM seasonal_boss_events WHERE status = '开启'")

    return {
        "total_players": _int(player, "total_players"),
        "busy_players": _int(player, "busy_players"),
        "exploring_players": _int(player, "exploring_players"),
        "total_stones": _int(player, "total_stones"),
        "total_vault_balance": _int(vault, "total_vault_balance"),
        "total_weapons": _int(weapon, "total_weapons"),
        "active_listings": _int(listing, "active_listings"),
        "open_wormholes": _int(wormhole, "open_wormholes"),
        "open_bosses": _int(boss, "open_bosses"),
    }


def _status_rows() -> list[dict[str, Any]]:
    """按玩家状态汇总人数。"""

    return db.fetch_all(
        """
        SELECT status, COUNT(*) AS total
        FROM players
        GROUP BY status
        ORDER BY total DESC, status
        """
    )


def _player_rows() -> list[dict[str, Any]]:
    """玩家实时榜单。"""

    return db.fetch_all(
        """
        SELECT
            p.display_name,
            p.level,
            p.exp,
            p.hp,
            p.max_hp,
            p.mp,
            p.max_mp,
            p.base_attack,
            p.defense,
            p.source_stones,
            p.status,
            p.location_name,
            p.x,
            p.y,
            p.auto_use_medicine,
            p.battle_log_detail,
            COALESCE(t.title, '') AS title,
            COALESCE(v.level, 1) AS vault_level,
            COALESCE(v.balance, 0) AS vault_balance,
            w.weapon_id,
            w.level AS weapon_level,
            w.max_level AS weapon_max_level,
            w.quality AS weapon_quality,
            w.attack AS weapon_attack,
            w.custom_name AS weapon_custom_name,
            d.name AS weapon_name,
            d.weapon_type
        FROM players p
        LEFT JOIN player_titles t
            ON t.client_id = p.client_id AND t.active = 1
        LEFT JOIN source_vaults v
            ON v.client_id = p.client_id
        LEFT JOIN player_weapons w
            ON w.owner_id = p.client_id AND w.equipped = 1
        LEFT JOIN weapon_defs d
            ON d.weapon_def_id = w.weapon_def_id
        ORDER BY p.level DESC, p.exp DESC, p.source_stones DESC
        LIMIT 50
        """
    )


def _exploration_rows() -> list[dict[str, Any]]:
    """当前未领取的探险记录。"""

    return db.fetch_all(
        """
        SELECT
            r.record_id,
            COALESCE(p.display_name, '未知玩家') AS display_name,
            r.location_name,
            r.status,
            r.started_at,
            r.ready_at,
            r.finished_at,
            r.claimed
        FROM exploration_records r
        LEFT JOIN players p ON p.client_id = r.client_id
        WHERE r.claimed = 0
        ORDER BY r.record_id DESC
        LIMIT 12
        """
    )


def _wormhole_rows() -> list[dict[str, Any]]:
    """最近虫洞状态。"""

    return db.fetch_all(
        """
        SELECT
            wormhole_id,
            boss_name,
            boss_kind,
            location_name,
            level,
            hp,
            max_hp,
            status,
            opened_at,
            closes_at
        FROM wormholes
        ORDER BY wormhole_id DESC
        LIMIT 8
        """
    )


def _seasonal_boss_rows() -> list[dict[str, Any]]:
    """最近岁时情劫首领状态。"""

    return db.fetch_all(
        """
        SELECT
            event_id,
            boss_name,
            event_type,
            weight_type,
            level,
            hp,
            max_hp,
            status,
            opened_at,
            closes_at
        FROM seasonal_boss_events
        ORDER BY event_id DESC
        LIMIT 8
        """
    )


def _market_rows() -> list[dict[str, Any]]:
    """二手市场当前挂单概览。"""

    return db.fetch_all(
        """
        SELECT
            item_type,
            COUNT(*) AS total,
            COALESCE(SUM(quantity), 0) AS quantity,
            COALESCE(SUM(total_price), 0) AS total_price
        FROM second_hand_listings
        GROUP BY item_type
        ORDER BY total DESC, item_type
        """
    )


def _recent_logs() -> list[dict[str, Any]]:
    """最近世界日志。"""

    return db.fetch_all(
        """
        SELECT
            g.action,
            g.detail,
            g.created_at,
            COALESCE(p.display_name, '未知玩家') AS display_name
        FROM game_logs g
        LEFT JOIN players p ON p.client_id = g.client_id
        ORDER BY g.log_id DESC
        LIMIT 24
        """
    )


def _one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    """读取一条聚合数据；空结果返回空字典。"""

    return db.fetch_one(sql, params) or {}


def _int(row: dict[str, Any], key: str) -> int:
    """安全读取整数。"""

    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


_LIVE_PAGE_HTML = r"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>修仙实时总览</title>
  <style>
    :root {
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --line: #d8d0c3;
      --ink: #252018;
      --muted: #716a60;
      --red: #a94237;
      --green: #32775f;
      --blue: #315f8d;
      --gold: #9b742c;
      --shadow: 0 10px 30px rgba(48, 39, 25, .08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(180deg, rgba(255,255,255,.78), rgba(255,255,255,.25)),
        var(--bg);
      font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", Arial, sans-serif;
      letter-spacing: 0;
    }
    .page {
      width: min(1500px, calc(100vw - 40px));
      margin: 0 auto;
      padding: 22px 0 28px;
    }
    .topbar {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 24px;
      margin-bottom: 16px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: 26px;
      line-height: 1.2;
      font-weight: 800;
    }
    .sub {
      color: var(--muted);
      font-size: 13px;
    }
    .refresh {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--muted);
      font-size: 13px;
      white-space: nowrap;
    }
    button {
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 12px;
      background: #fffaf1;
      color: var(--ink);
      cursor: pointer;
      font-size: 13px;
    }
    button:hover { border-color: var(--gold); }
    .grid {
      display: grid;
      grid-template-columns: 1.4fr .9fr;
      gap: 14px;
      align-items: start;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .card, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }
    .card {
      min-height: 82px;
      padding: 12px 14px;
    }
    .label {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .value {
      font-size: 22px;
      line-height: 1;
      font-weight: 800;
      font-variant-numeric: tabular-nums;
    }
    .value.small { font-size: 18px; }
    .panel {
      overflow: hidden;
      margin-bottom: 14px;
    }
    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      height: 44px;
      padding: 0 14px;
      border-bottom: 1px solid var(--line);
      background: #faf4e8;
    }
    .panel-title {
      font-size: 15px;
      font-weight: 800;
    }
    .panel-note {
      color: var(--muted);
      font-size: 12px;
    }
    table {
      width: 100%;
      min-width: 1120px;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 13px;
    }
    th, td {
      height: 40px;
      padding: 8px 10px;
      border-bottom: 1px solid #ece5d9;
      text-align: left;
      vertical-align: middle;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    th {
      height: 36px;
      color: var(--muted);
      background: #fffaf1;
      font-size: 12px;
      font-weight: 700;
    }
    tr:last-child td { border-bottom: 0; }
    .name {
      font-weight: 800;
    }
    .title {
      color: var(--gold);
      font-size: 12px;
      margin-left: 4px;
    }
    .bar {
      width: 100%;
      height: 7px;
      margin-top: 5px;
      overflow: hidden;
      border-radius: 4px;
      background: #eadfce;
    }
    .bar > span {
      display: block;
      height: 100%;
      width: 0;
      background: var(--green);
    }
    .bar.hp > span { background: var(--red); }
    .pill {
      display: inline-flex;
      align-items: center;
      height: 22px;
      max-width: 100%;
      border: 1px solid #d8d0c3;
      border-radius: 999px;
      padding: 0 8px;
      color: var(--muted);
      background: #fffaf1;
      font-size: 12px;
      line-height: 1;
    }
    .pill.busy {
      color: var(--blue);
      border-color: #b6c8d8;
      background: #edf5fb;
    }
    .list {
      padding: 10px 14px 12px;
    }
    .row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      padding: 9px 0;
      border-bottom: 1px solid #ece5d9;
      font-size: 13px;
    }
    .row:last-child { border-bottom: 0; }
    .mainline {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-weight: 700;
    }
    .meta {
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .num {
      color: var(--gold);
      font-weight: 800;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .empty {
      padding: 18px 14px;
      color: var(--muted);
      font-size: 13px;
    }
    .two-col {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
    }
    #players {
      overflow-x: auto;
    }
    @media (max-width: 1100px) {
      .page {
        width: calc(100vw - 24px);
        padding: 14px 0 22px;
      }
      .topbar {
        align-items: flex-start;
        flex-direction: column;
      }
      .cards {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .grid, .two-col {
        grid-template-columns: 1fr;
      }
    }
    @media (max-width: 560px) {
      h1 { font-size: 22px; }
      .cards {
        grid-template-columns: 1fr;
      }
      .card {
        min-height: 72px;
      }
    }
  </style>
</head>
<body>
  <main class="page">
    <header class="topbar">
      <div>
        <h1>修仙实时总览</h1>
        <div class="sub">只读预览页，当前通过数据库轮询展示世界状态。后续登录绑定后可在这里接入操作。</div>
      </div>
      <div class="refresh">
        <span id="lastUpdate">等待数据</span>
        <button type="button" id="refreshBtn">刷新</button>
      </div>
    </header>

    <section class="cards" id="summaryCards"></section>

    <section class="grid">
      <div>
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">玩家实时状态</div>
            <div class="panel-note">按等级、经验、源石排序，最多 50 人</div>
          </div>
          <div id="players"></div>
        </section>

        <section class="two-col">
          <div class="panel">
            <div class="panel-head">
              <div class="panel-title">未领取探险</div>
              <div class="panel-note">待结算或待领取</div>
            </div>
            <div class="list" id="explorations"></div>
          </div>
          <div class="panel">
            <div class="panel-head">
              <div class="panel-title">二手市场</div>
              <div class="panel-note">当前挂单</div>
            </div>
            <div class="list" id="market"></div>
          </div>
        </section>
      </div>

      <aside>
        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">玩家状态分布</div>
            <div class="panel-note">实时人数</div>
          </div>
          <div class="list" id="statusRows"></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">异界虫洞</div>
            <div class="panel-note">最近 8 条</div>
          </div>
          <div class="list" id="wormholes"></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">岁时情劫</div>
            <div class="panel-note">最近 8 条</div>
          </div>
          <div class="list" id="seasonalBosses"></div>
        </section>

        <section class="panel">
          <div class="panel-head">
            <div class="panel-title">最近日志</div>
            <div class="panel-note">最多 24 条</div>
          </div>
          <div class="list" id="logs"></div>
        </section>
      </aside>
    </section>
  </main>

  <script>
    const money = new Intl.NumberFormat("zh-CN");
    const percent = (current, max) => {
      const c = Number(current || 0);
      const m = Math.max(1, Number(max || 1));
      return Math.max(0, Math.min(100, Math.round(c / m * 100)));
    };
    const text = (value, fallback = "-") => {
      if (value === null || value === undefined || value === "") return fallback;
      return String(value);
    };
    const short = (value, size = 56) => {
      const raw = text(value, "");
      return raw.length > size ? raw.slice(0, size) + "..." : raw;
    };
    const statusClass = (value) => value && value !== "空闲" ? "pill busy" : "pill";
    const setHTML = (id, html) => {
      document.getElementById(id).innerHTML = html;
    };
    const empty = (label) => `<div class="empty">${label}</div>`;
    const row = (main, meta, right = "") => `
      <div class="row">
        <div>
          <div class="mainline">${main}</div>
          <div class="meta">${meta}</div>
        </div>
        <div class="num">${right}</div>
      </div>`;

    function renderSummary(summary) {
      const cards = [
        ["玩家", summary.total_players],
        ["忙碌中", `${summary.busy_players} / 探险 ${summary.exploring_players}`],
        ["随身源石", money.format(summary.total_stones)],
        ["源库余额", money.format(summary.total_vault_balance)],
        ["武器", money.format(summary.total_weapons)],
        ["二手挂单", money.format(summary.active_listings)],
        ["开启虫洞", money.format(summary.open_wormholes)],
        ["开启首领", money.format(summary.open_bosses)],
      ];
      setHTML("summaryCards", cards.map(([label, value]) => `
        <article class="card">
          <div class="label">${label}</div>
          <div class="value ${String(value).length > 8 ? "small" : ""}">${value}</div>
        </article>
      `).join(""));
    }

    function renderPlayers(players) {
      if (!players.length) {
        setHTML("players", empty("暂无玩家数据"));
        return;
      }
      const rows = players.map((p) => {
        const weaponName = p.weapon_custom_name ? `${p.weapon_custom_name}（${p.weapon_name}）` : text(p.weapon_name, "未装备");
        return `
          <tr>
            <td style="width: 14%">
              <span class="name">${text(p.display_name)}</span>
              ${p.title ? `<span class="title">${p.title}</span>` : ""}
            </td>
            <td style="width: 6%">Lv.${p.level}</td>
            <td style="width: 12%">
              ${p.hp}/${p.max_hp}
              <div class="bar hp"><span style="width:${percent(p.hp, p.max_hp)}%"></span></div>
            </td>
            <td style="width: 12%">
              ${p.mp}/${p.max_mp}
              <div class="bar"><span style="width:${percent(p.mp, p.max_mp)}%"></span></div>
            </td>
            <td style="width: 9%">${money.format(p.source_stones)}</td>
            <td style="width: 9%">${money.format(p.vault_balance)} / ${p.vault_level}星</td>
            <td style="width: 8%"><span class="${statusClass(p.status)}">${text(p.status)}</span></td>
            <td style="width: 12%">${text(p.location_name)} (${p.x},${p.y})</td>
            <td style="width: 18%">#${text(p.weapon_id)} ${weaponName} ${text(p.weapon_quality, "")} ${text(p.weapon_level, 0)}/${text(p.weapon_max_level, 0)}</td>
          </tr>
        `;
      }).join("");
      setHTML("players", `
        <table>
          <thead>
            <tr>
              <th>玩家</th><th>等级</th><th>血气</th><th>精神</th><th>源石</th><th>源库</th><th>状态</th><th>地点</th><th>武器</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      `);
    }

    function renderStatus(rows) {
      setHTML("statusRows", rows.length ? rows.map((item) =>
        row(`<span class="${statusClass(item.status)}">${text(item.status)}</span>`, "玩家当前状态", money.format(item.total))
      ).join("") : empty("暂无状态数据"));
    }

    function renderExplorations(rows) {
      setHTML("explorations", rows.length ? rows.map((item) =>
        row(`#${item.record_id} ${text(item.display_name)} · ${text(item.location_name)}`, `状态 ${text(item.status)}｜可领取 ${text(item.ready_at)}`, item.claimed ? "已领" : "未领")
      ).join("") : empty("暂无未领取探险"));
    }

    function renderMarket(rows) {
      setHTML("market", rows.length ? rows.map((item) =>
        row(text(item.item_type), `数量 ${money.format(item.quantity)}｜总价 ${money.format(item.total_price)}`, money.format(item.total))
      ).join("") : empty("暂无挂单"));
    }

    function renderWormholes(rows) {
      setHTML("wormholes", rows.length ? rows.map((item) =>
        row(`#${item.wormhole_id} ${text(item.boss_name)} Lv.${item.level}`, `${text(item.location_name)}｜${text(item.status)}｜血量 ${item.hp}/${item.max_hp}`, `${percent(item.hp, item.max_hp)}%`)
      ).join("") : empty("暂无虫洞记录"));
    }

    function renderSeasonalBosses(rows) {
      setHTML("seasonalBosses", rows.length ? rows.map((item) =>
        row(`#${item.event_id} ${text(item.boss_name)} Lv.${item.level}`, `${text(item.event_type)}｜${text(item.weight_type)}｜${text(item.status)}｜血量 ${item.hp}/${item.max_hp}`, `${percent(item.hp, item.max_hp)}%`)
      ).join("") : empty("暂无首领记录"));
    }

    function renderLogs(rows) {
      setHTML("logs", rows.length ? rows.map((item) =>
        row(`${text(item.display_name)} · ${text(item.action)}`, short(item.detail), text(item.created_at))
      ).join("") : empty("暂无日志"));
    }

    async function loadData() {
      const response = await fetch("/xiuxian/live/data", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      renderSummary(data.summary || {});
      renderPlayers(data.players || []);
      renderStatus(data.status || []);
      renderExplorations(data.explorations || []);
      renderMarket(data.market || []);
      renderWormholes(data.wormholes || []);
      renderSeasonalBosses(data.seasonal_bosses || []);
      renderLogs(data.logs || []);
      document.getElementById("lastUpdate").textContent = `已刷新 ${new Date().toLocaleTimeString("zh-CN")}`;
    }

    async function safeLoad() {
      try {
        await loadData();
      } catch (error) {
        document.getElementById("lastUpdate").textContent = `加载失败：${error.message}`;
      }
    }

    document.getElementById("refreshBtn").addEventListener("click", safeLoad);
    safeLoad();
    window.setInterval(safeLoad, 5000);
  </script>
</body>
</html>
"""
