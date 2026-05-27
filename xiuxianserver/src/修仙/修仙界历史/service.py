"""修仙界历史服务。"""

from __future__ import annotations

from ..format_text import T

from datetime import date, datetime, time, timedelta
from typing import Any

from ..common import (
    CoreService,
    business_day,
    dump_json,
    format_effect,
    load_json,
    money,
    ts,
    weapon_label_name,
    world_state_for_day,
)
from ..constants import DAY_RESET_HOUR
from ..sql import db


NEWSPAPER_TITLE = "修仙早报:v4"
NEWSPAPER_NAV_BUTTONS = "<风云榜><修仙早报><修仙界历史>"
OLD_TEXT_MARKERS = ("☆", "┌", "└", "├", "│", "模板:", "自带技能:", "附魔栏:", "存放:")
CHRONICLE_KEY_PREFIX = "xiuxian_history:"


class XiuxianHistoryService(CoreService):
    """风云榜、修仙早报、修仙界历史和公开人物志。"""

    def leaderboard(self, client_id: str) -> str:
        """查看当前业务日的全服榜单。"""

        _, error = self.require_player(client_id)
        if error:
            return error

        start, end = self._business_window()
        panel = T.panel()
        panel.section(f"风云榜·{business_day()}")
        panel.line(self._top_damage_text(start, end))
        panel.line(self._top_rich_text())
        panel.line(self._top_trade_text(start, end))
        panel.line(self._top_explore_text(start, end))
        panel.line(self._top_luck_text(start, end))
        panel.line(self._top_active_text(start, end))
        return panel.render() + "<风云榜><修仙早报><修仙界历史>"

    def newspaper(self, client_id: str) -> str:
        """查看今日修仙早报。"""

        _, error = self.require_player(client_id)
        if error:
            return error

        day = business_day()
        row = self.db.fetch_one("SELECT title, content FROM daily_newspapers WHERE business_day = ?", (day,))
        cached_content = self._current_newspaper_content(row)
        if cached_content:
            return self._newspaper_response(cached_content)

        content = self._build_newspaper(day)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_newspapers
                (business_day, title, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (day, NEWSPAPER_TITLE, content, ts()),
            )
        return self._newspaper_response(content)

    def _current_newspaper_content(self, row: Any) -> str:
        """只复用当前富文本版本的早报缓存。"""

        if not row or row["title"] != NEWSPAPER_TITLE:
            return ""
        content = str(row["content"])
        if any(marker in content for marker in OLD_TEXT_MARKERS):
            return ""
        return content

    def _newspaper_response(self, content: str) -> str:
        """早报缓存和新生成内容统一追加跳转按钮。"""

        return T.attach(content, NEWSPAPER_NAV_BUTTONS)

    def chronicle(self, client_id: str) -> str:
        """查看最近的修仙界历史。"""

        _, error = self.require_player(client_id)
        if error:
            return error

        day = business_day()
        self._save_or_get_chronicle(day, refresh=True)
        rows = self.db.fetch_all(
            """
            SELECT key, value
            FROM schema_meta
            WHERE key LIKE ?
            ORDER BY key DESC
            LIMIT 5
            """,
            (f"{CHRONICLE_KEY_PREFIX}%",),
        )

        panel = T.panel()
        panel.section("修仙界历史")
        for row in rows:
            current_day = str(row["key"]).removeprefix(CHRONICLE_KEY_PREFIX)
            entries = self._decode_entries(row["value"])
            panel.line(current_day)
            for entry in entries:
                panel.line(f"- {entry}")
        return panel.render() + "<风云榜><修仙早报><修仙界历史>"

    def profile(self, client_id: str, message: str) -> str:
        """公开查看一位玩家的修仙界档案。"""

        _, error = self.require_player(client_id)
        if error:
            return error

        if not message.strip():
            return T.hint("缺少要查看的玩家名称。", "发送：人物志 玩家名称，例如：人物志 青衫客")

        target_id = self.player_id_from_last_arg(message)
        target = self.player(target_id) if target_id else None
        if not target:
            return T.hint("没有找到这位玩家。", "请确认名称是否正确，或直接@对方。")

        title = self.refresh_titles(target_id, target) or "无"
        weapon = self.equipped_weapon_row(target_id)
        weapon_text = weapon_label_name(weapon) if weapon else "未佩戴"
        wormhole_count = self.stat_count(
            target_id,
            "wormhole_count",
            "SELECT COUNT(*) AS count FROM wormhole_participants WHERE client_id = ?",
            (target_id,),
        )
        boss_count = self.stat_count(
            target_id,
            "boss_count",
            "SELECT COUNT(*) AS count FROM seasonal_boss_participants WHERE client_id = ?",
            (target_id,),
        )
        explore_count = self.stat_count(
            target_id,
            "explore_count",
            "SELECT COUNT(*) AS count FROM exploration_records WHERE client_id = ?",
            (target_id,),
        )
        trade_count = self.stat_count(
            target_id,
            "trade_count",
            "SELECT COUNT(*) AS count FROM trade_records WHERE client_id = ?",
            (target_id,),
        )
        duel_wins = self.stat_count(
            target_id,
            "duel_win_count",
            "SELECT COUNT(*) AS count FROM duel_records WHERE winner_id = ?",
            (target_id,),
        )

        panel = T.panel()
        panel.section(f"{target['display_name']}人物志")
        panel.line(f"称号：{title}")
        panel.line(f"等级：**{target['level']}**")
        panel.line(f"常驻地点：{target['location_name']}")
        panel.line(f"代表武器：{weapon_text}")
        panel.line(
            f"修仙界事迹：参与虫洞 **{wormhole_count}** 次｜挑战首领 **{boss_count}** 次｜"
            f"探险 **{explore_count}** 次｜跑商 **{trade_count}** 次｜对战胜利 **{duel_wins}** 次"
        )
        return panel.render()

    def _build_newspaper(self, day: str) -> str:
        """生成今日修仙早报。"""

        start, end = self._business_window(day)
        panel = T.panel()
        panel.section(f"修仙早报·{day}")
        panel.line(f"小编按：今日修仙界从 {DAY_RESET_HOUR:02d}:00 起算，茶摊照例收风。")
        panel.hr()
        panel.section("天地气象")
        panel.lines(self._world_state_lines(day))
        panel.hr()
        panel.section("头版人物")
        panel.line(self._top_damage_text(start, end))
        panel.line(self._top_rich_text())
        panel.line(self._top_explore_text(start, end))
        panel.line(self._top_luck_text(start, end))
        panel.hr()
        panel.section("坊间传闻")
        panel.line(self._rumor_text(start, end))
        panel.hr()
        panel.section("商会风向")
        panel.line(self._business_wind_text(start, end))
        panel.hr()
        panel.section("首领动向")
        panel.lines(self._boss_trend_lines(day, start, end))
        return panel.render() + "<商场推荐><首领>"

    def _world_state_lines(self, day: str) -> list[str]:
        """生成早报里的全服天气和灵潮栏目。"""

        state = world_state_for_day(day)
        weather = state["weather"]
        tide = state["tide"]
        total = format_effect(state["effect"])
        return [
            f"今日天气：{weather['name']}。{weather['flavor']}（{format_effect(weather['effect'])}）",
            f"今日灵潮：{tide['name']}。{tide['flavor']}（{format_effect(tide['effect'])}）",
            f"全服生效：{total}",
        ]

    def _save_or_get_chronicle(self, day: str, refresh: bool = False) -> list[str]:
        """读取或保存某一天的大事记；当天会刷新，旧日保持沉淀结果。"""

        key = f"{CHRONICLE_KEY_PREFIX}{day}"
        if not refresh:
            row = self.db.fetch_one("SELECT value FROM schema_meta WHERE key = ?", (key,))
            if row:
                return self._decode_entries(row["value"])

        entries = self._build_chronicle_day(day)
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO schema_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, dump_json(entries)),
            )
        return entries

    def _build_chronicle_day(self, day: str) -> list[str]:
        """按当天实际数据生成世界年表条目。"""

        start, end = self._business_window(day)
        entries: list[str] = []

        boss = self.db.fetch_one(
            """
            SELECT boss_name, status
            FROM seasonal_boss_events
            WHERE business_day = ?
            ORDER BY event_id DESC
            LIMIT 1
            """,
            (day,),
        )
        if boss:
            entries.append(f"今日首领「{boss['boss_name']}」{self._status_word(boss['status'])}。")

        wormholes = self._wormhole_summary(start, end)
        if wormholes["total"]:
            entries.append(
                f"异界虫洞出现 {wormholes['total']} 次，"
                f"其中 {wormholes['killed']} 次被众人合力击破。"
            )

        trade = self._top_trade_row(start, end)
        if trade:
            entries.append(
                f"今日跑商最高收益由 {self.format_player_name(trade['client_id'])} 创下，"
                f"净利润 {money(trade['net'])}。"
            )

        damage = self._top_damage_row(start, end)
        if damage:
            entries.append(
                f"{self.format_player_name(damage['client_id'])} 今日 Boss 总伤害最高，留下 {damage['damage']} 点战绩。"
            )

        luck = self._top_luck_row(start, end)
        if luck:
            entries.append(
                f"{self.format_player_name(luck['owner_id'])} 获得 {luck['quality']}武器「{luck['name']}」，"
                "坊间称其手气正盛。"
            )

        new_players = self._count(
            """
            SELECT COUNT(*) AS count
            FROM players
            WHERE datetime(replace(created_at, 'T', ' ')) >= ?
              AND datetime(replace(created_at, 'T', ' ')) < ?
            """,
            (start, end),
        )
        if new_players:
            entries.append(f"今日新增 {new_players} 位道友入世，天枢城又添新灯。")

        return entries or ["今日山河无大事，茶摊照旧开张。"]

    def _top_damage_text(self, start: str, end: str) -> str:
        """今日 Boss 伤害最高者。"""

        row = self._top_damage_row(start, end)
        if not row:
            return "今日最猛：暂无 Boss 挑战记录。"
        return f"今日最猛：{self.format_player_name(row['client_id'])}，Boss 总伤害 {row['damage']}。"

    def _top_rich_text(self) -> str:
        """当前明面资产最高者。"""

        row = self._richest_row()
        if not row:
            return "今日最富：暂无玩家资产记录。"
        return f"今日最富：{self.format_player_name(row['client_id'])}，明面资产约 {money(row['total'])}。"

    def _top_trade_text(self, start: str, end: str) -> str:
        """今日普通跑商净利润最高者。"""

        row = self._top_trade_row(start, end)
        if not row:
            return "今日商魂：暂无普通跑商出售。"
        return f"今日商魂：{self.format_player_name(row['client_id'])}，跑商净利润 {money(row['net'])}。"

    def _top_explore_text(self, start: str, end: str) -> str:
        """今日探险次数最高者。"""

        row = self._top_explore_row(start, end)
        if not row:
            return "今日最勤：暂无探险记录。"
        return f"今日最勤：{self.format_player_name(row['client_id'])}，探险 {row['count']} 次。"

    def _top_luck_text(self, start: str, end: str) -> str:
        """今日珍稀武器获得者。"""

        row = self._top_luck_row(start, end)
        if not row:
            return "今日欧气：暂无珍稀武器入世。"
        return (
            f"今日欧气：{self.format_player_name(row['owner_id'])}，"
            f"新得 {row['quality']}武器「{row['name']}」{row['count']} 把。"
        )

    def _top_active_text(self, start: str, end: str) -> str:
        """今日关键行为最多者。"""

        row = self._top_active_row(start, end)
        if not row:
            return "今日活跃：暂无关键日志。"
        return f"今日活跃：{self.format_player_name(row['client_id'])}，关键行为 {row['count']} 次。"

    def _rumor_text(self, start: str, end: str) -> str:
        """生成一条坊间传闻。"""

        luck = self._top_luck_row(start, end)
        if luck:
            return f"坊间传闻：有人看见 {self.format_player_name(luck['owner_id'])} 抱着「{luck['name']}」路过茶摊。"

        active = self._top_active_row(start, end)
        if active:
            return f"坊间传闻：茶摊老板说，{self.format_player_name(active['client_id'])} 今日脚步最急。"

        rich = self._richest_row()
        if rich and int(rich["total"]) > 0:
            return f"坊间传闻：商会账房偷偷记下，{self.format_player_name(rich['client_id'])} 的源石声最响。"

        return "坊间传闻：今日风声尚轻，适合先签到，再慢慢探路。"

    def _business_wind_text(self, start: str, end: str) -> str:
        """生成商会风向。"""

        row = self._top_trade_row(start, end)
        if row:
            return (
                f"商会风向：今日普通跑商最高收益来自 {self.format_player_name(row['client_id'])}，"
                f"净利润 {money(row['net'])}。"
            )
        return "商会风向：今日普通跑商账簿还空着，想开张可先看 商场推荐。"

    def _boss_trend_lines(self, day: str, start: str, end: str) -> list[str]:
        """生成首领和虫洞动向。"""

        lines: list[str] = []
        boss = self.db.fetch_one(
            """
            SELECT boss_name, status
            FROM seasonal_boss_events
            WHERE business_day = ?
            ORDER BY event_id DESC
            LIMIT 1
            """,
            (day,),
        )
        if boss:
            lines.append(f"首领动向：岁时情劫「{boss['boss_name']}」{self._status_word(boss['status'])}。")
        else:
            lines.append("首领动向：今日暂无岁时情劫现世。")

        wormholes = self._wormhole_summary(start, end)
        if wormholes["total"]:
            lines.append(
                f"虫洞动向：今日出现 {wormholes['total']} 处异界虫洞，"
                f"开启 {wormholes['active']}，击破 {wormholes['killed']}。"
            )
        else:
            lines.append("虫洞动向：今日暂未发现异界虫洞。")
        return lines

    def _top_damage_row(self, start: str, end: str) -> dict[str, Any] | None:
        """查询今日 Boss 总伤害第一名。"""

        return self.db.fetch_one(
            """
            SELECT client_id, SUM(damage) AS damage
            FROM (
                SELECT client_id, damage, updated_at FROM wormhole_participants
                UNION ALL
                SELECT client_id, damage, updated_at FROM seasonal_boss_participants
            )
            WHERE datetime(replace(updated_at, 'T', ' ')) >= ?
              AND datetime(replace(updated_at, 'T', ' ')) < ?
            GROUP BY client_id
            ORDER BY damage DESC
            LIMIT 1
            """,
            (start, end),
        )

    def _richest_row(self) -> dict[str, Any] | None:
        """查询当前明面资产最高者。"""

        return self.db.fetch_one(
            """
            SELECT p.client_id,
                   p.source_stones + COALESCE(v.balance, 0) AS total
            FROM players p
            LEFT JOIN source_vaults v ON v.client_id = p.client_id
            ORDER BY total DESC
            LIMIT 1
            """
        )

    def _top_trade_row(self, start: str, end: str) -> dict[str, Any] | None:
        """查询今日普通跑商净利润第一名。"""

        return self.db.fetch_one(
            """
            SELECT client_id,
                   SUM(
                       CASE
                           WHEN action = 'sell' THEN total_price - fee
                           WHEN action = 'buy' THEN -(total_price + fee)
                           ELSE 0
                       END
                   ) AS net
            FROM trade_records
            WHERE action IN ('buy', 'sell')
              AND datetime(replace(created_at, 'T', ' ')) >= ?
              AND datetime(replace(created_at, 'T', ' ')) < ?
            GROUP BY client_id
            HAVING net > 0
            ORDER BY net DESC
            LIMIT 1
            """,
            (start, end),
        )

    def _top_explore_row(self, start: str, end: str) -> dict[str, Any] | None:
        """查询今日探险次数第一名。"""

        return self.db.fetch_one(
            """
            SELECT client_id, COUNT(*) AS count
            FROM exploration_records
            WHERE datetime(replace(started_at, 'T', ' ')) >= ?
              AND datetime(replace(started_at, 'T', ' ')) < ?
            GROUP BY client_id
            ORDER BY count DESC
            LIMIT 1
            """,
            (start, end),
        )

    def _top_luck_row(self, start: str, end: str) -> dict[str, Any] | None:
        """查询今日最高品质武器获得者。"""

        return self.db.fetch_one(
            """
            SELECT w.owner_id, w.quality, d.name, COUNT(*) AS count
            FROM player_weapons w
            JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
            WHERE w.quality IN ('稀品', '珍品')
              AND datetime(replace(w.created_at, 'T', ' ')) >= ?
              AND datetime(replace(w.created_at, 'T', ' ')) < ?
            GROUP BY w.owner_id, w.quality, d.name
            ORDER BY CASE w.quality WHEN '稀品' THEN 2 ELSE 1 END DESC, count DESC
            LIMIT 1
            """,
            (start, end),
        )

    def _top_active_row(self, start: str, end: str) -> dict[str, Any] | None:
        """查询今日关键行为最多者。"""

        return self.db.fetch_one(
            """
            SELECT client_id, COUNT(*) AS count
            FROM game_logs
            WHERE datetime(replace(created_at, 'T', ' ')) >= ?
              AND datetime(replace(created_at, 'T', ' ')) < ?
            GROUP BY client_id
            ORDER BY count DESC
            LIMIT 1
            """,
            (start, end),
        )

    def _wormhole_summary(self, start: str, end: str) -> dict[str, int]:
        """统计今日虫洞出现、开启和击破数量。"""

        row = self.db.fetch_one(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = '开启' THEN 1 ELSE 0 END) AS active,
                   SUM(CASE WHEN status = '已击杀' THEN 1 ELSE 0 END) AS killed
            FROM wormholes
            WHERE datetime(replace(opened_at, 'T', ' ')) >= ?
              AND datetime(replace(opened_at, 'T', ' ')) < ?
            """,
            (start, end),
        )
        return {
            "total": int(row["total"] or 0) if row else 0,
            "active": int(row["active"] or 0) if row else 0,
            "killed": int(row["killed"] or 0) if row else 0,
        }

    def _count(self, sql: str, params: tuple[Any, ...]) -> int:
        """执行 COUNT 查询并返回整数。"""

        row = self.db.fetch_one(sql, params)
        return int(row["count"] or 0) if row else 0

    @staticmethod
    def _decode_entries(value: Any) -> list[str]:
        """把 schema_meta 里的大事记 JSON 还原成文本列表。"""

        entries = load_json(value, [])
        if isinstance(entries, list):
            return [str(entry) for entry in entries if str(entry).strip()]
        return [str(value)]

    @staticmethod
    def _status_word(status: str) -> str:
        """把数据库状态转成早报里的短句。"""

        return {
            "开启": "正在现世",
            "已击破": "已被合力击破",
            "已击杀": "已被合力击破",
            "已退去": "已退去",
        }.get(status, str(status))

    @staticmethod
    def _business_window(day: str | None = None) -> tuple[str, str]:
        """返回业务日开始和结束时间。"""

        value = date.fromisoformat(day or business_day())
        start = datetime.combine(value, time(hour=DAY_RESET_HOUR))
        end = start + timedelta(days=1)
        return start.isoformat(sep=" ", timespec="seconds"), end.isoformat(sep=" ", timespec="seconds")


service = XiuxianHistoryService(db)

__all__ = ["XiuxianHistoryService", "service"]
