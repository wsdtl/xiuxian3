"""世界物资、城池状态、藏宝图和战备的公共业务。"""

from __future__ import annotations

import math
import random
import sqlite3
from datetime import timedelta
from typing import Any

from .common import (
    CoreService,
    QUALITY_EPIC,
    business_day,
    currency_amount,
    currency_name,
    dt,
    dump_json,
    load_json,
    money,
    now,
    quality_factor,
    quality_label,
    quality_rank,
    row_value,
    split_words,
    to_int,
    ts,
)
from .constants import (
    CITY_MAX_LEVEL,
    TRADE_ACTIVE_WINDOW_DAYS,
    WORLD_COORD_MAX,
    WORLD_COORD_MIN,
)
from .format_text import T
from .sect_war import record_sect_merit_conn, sect_direction_bonus_conn
from .sql import TRADE_LOCATION_NAMES_BY_ID, TRADE_LOCATIONS, WAR_PREP_SEED, db, world_category_key
from .weapon_core import WeaponCore


CITY_LOCATION_IDS = tuple(TRADE_LOCATION_NAMES_BY_ID)
CITY_LOCATION_NAMES = tuple(TRADE_LOCATION_NAMES_BY_ID.values())
CITY_LOCATION_SET = set(CITY_LOCATION_NAMES)

WORLD_RECYCLE_CATEGORY_KEYS = {"medicine", "life", "build", "relic"}
MEDICINE_ROLE_STATE_COLUMNS = {
    "material": "medicine_material",
    "catalyst": "medicine_catalyst",
    "fuel": "medicine_fuel",
}
LIFE_STATE_COLUMNS_BY_KEY = {
    "chengshi": "life_food",
    "yanxian": "life_salt",
    "shuijing": "life_water",
    "yibei": "life_cloth",
    "ranan": "life_fuel",
}
LIFE_THRESHOLDS = (100, 240, 430, 680, 1000, 1400, 1900, 2500, 3200, 4000)
TREASURE_AUCTION_HOURS = 24
TREASURE_PICKUP_HOURS = 72
TREASURE_BID_LIMIT = 10

MEDICINE_CARRY_TEXTS = (
    "你替药铺看了眼炉火，掌柜立刻想起还有 {items} 能孝敬路费。",
    "丹坊说今日无药，你掀开炉盖闻了闻，柜台后面就多出 {items}。",
    "药童刚想喊价，你把商路护送四个字说重了点，顺回 {items}。",
    "地方药号账本写得很清白，可你翻到夹页，夹页里正好压着 {items}。",
    "你说替城里看看药性，掌柜连连点头，把 {items} 当验药费递了出来。",
    "商队镖头说药铺嘴硬，你过去敲了敲门，门缝里塞出 {items}。",
    "你夸丹炉火候不错，炉旁小厮吓得连夜把 {items} 归入护路消耗。",
    "掌柜表示药柜空了，你指了指后院药香，片刻后多了 {items}。",
    "你替药号算了一笔灾后安民账，算到最后账上少了 {items}。",
    "丹坊试图装作无事发生，你把伏火炭一拨，顺手带走 {items}。",
    "药铺小二口风很紧，直到你提起妖兽巡街，他才想起还有 {items}。",
    "你把这趟商路说成救苦济急，地方药号只好把 {items} 写作香火支出。",
)


class WorldMaterialService(CoreService):
    """世界物资回收、药路顺药、藏宝图和战备公共服务。"""

    def __init__(self, database) -> None:
        super().__init__(database)
        self.weapon_core = WeaponCore(database)

    def _city_location(
        self,
        location_name: object = "",
        location_id: object = "",
    ) -> dict[str, Any] | None:
        """读取 11 个城池承接点；稳定 ID 优先，展示名只用于玩家输入。"""

        with self.db.transaction() as conn:
            return self._city_location_conn(conn, location_name, location_id)

    @staticmethod
    def _city_location_conn(
        conn: sqlite3.Connection,
        location_name: object = "",
        location_id: object = "",
    ) -> dict[str, Any] | None:
        stable_id = str(location_id or "").strip()
        row = None
        if stable_id:
            row = conn.execute(
                "SELECT location_id, name, x, y FROM trade_locations WHERE location_id = ?",
                (stable_id,),
            ).fetchone()
        if row is None:
            name = str(location_name or "").strip()
            if name:
                row = conn.execute(
                    "SELECT location_id, name, x, y FROM trade_locations WHERE name = ?",
                    (name,),
                ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _city_location_id_conn(
        conn: sqlite3.Connection,
        location_name: object = "",
        location_id: object = "",
    ) -> str:
        city = WorldMaterialService._city_location_conn(conn, location_name, location_id)
        return str(city["location_id"]) if city else ""

    def _player_city_location(self, player: dict[str, Any]) -> dict[str, Any] | None:
        return self._city_location(row_value(player, "location_name", ""), row_value(player, "location_id", ""))

    @staticmethod
    def _buyer_location_id_conn(conn: sqlite3.Connection, buyer_name: object, buyer_id: object = "") -> str:
        stable_id = str(buyer_id or "").strip()
        if stable_id:
            return stable_id
        row = conn.execute(
            "SELECT location_id FROM special_buyers WHERE buyer_name = ?",
            (str(buyer_name or "").strip(),),
        ).fetchone()
        return str(row["location_id"]) if row else ""

    def war_prep_state(self, buyer_name: object = "", location_id: object = "") -> dict[str, Any]:
        """读取特殊收购点的战备蓄能状态，供位置和地图展示。"""

        with self.db.transaction() as conn:
            return self.war_prep_state_conn(conn, buyer_name, location_id)

    def war_prep_state_conn(
        self,
        conn: sqlite3.Connection,
        buyer_name: object = "",
        location_id: object = "",
    ) -> dict[str, Any]:
        buyer_id = self._buyer_location_id_conn(conn, buyer_name, location_id)
        if not buyer_id:
            return {}
        threshold = self.war_prep_threshold_conn(conn)
        conn.execute("UPDATE war_prep_states SET threshold = ? WHERE location_id = ?", (threshold, buyer_id))
        row = conn.execute("SELECT * FROM war_prep_states WHERE location_id = ?", (buyer_id,)).fetchone()
        if not row:
            return {}
        value = max(0, int(row["prep_value"] or 0))
        threshold = max(1, int(row["threshold"] or threshold))
        return {
            "location_id": buyer_id,
            "buyer_name": str(row["buyer_name"] or buyer_name or ""),
            "prep_name": str(row["prep_name"] or ""),
            "loot_subtype": str(row["loot_subtype"] or ""),
            "value": value,
            "threshold": threshold,
            "progress": min(1.0, value / threshold),
            "pending": bool(int(row["pending"] or 0)),
            "pending_at": str(row["pending_at"] or ""),
            "last_opened_at": str(row["last_opened_at"] or ""),
        }

    @staticmethod
    def war_prep_state_lines(state: dict[str, Any]) -> list[str]:
        """格式化特殊收购点战备蓄能展示。"""

        if not state:
            return []
        value = max(0, int(state.get("value", 0) or 0))
        threshold = max(1, int(state.get("threshold", 1) or 1))
        percent = min(999, int(value / threshold * 100))
        name = str(state.get("prep_name") or "战备蓄能")
        status = "已入待牵引队列" if state.get("pending") else f"{percent}%"
        lines = [f"{name}：{value}/{threshold}（{status}）"]
        if state.get("pending"):
            lines.append("已可牵引异界虫洞；下一次战备调度会优先消耗该蓄能。")
        else:
            lines.append("出售对应战利品会继续累积；满值后可牵引异界虫洞。")
        if state.get("last_opened_at"):
            lines.append(f"上次牵引：{state['last_opened_at']}")
        return lines

    def recycle(self, client_id: str, message: str) -> str:
        """回收药路、民生、建设和古物。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        city = self._player_city_location(player)
        if not city:
            return T.hint(
                "当前位置不能回收普通世界物资。",
                "只有 11 个普通探险/跑商城池承接药路、民生、建设和古物；可发送：出售 物品名 数量 或 自动出售。",
                buttons=("探险列表", "自动出售"),
            )
        location_name = str(city["name"])
        location_id = str(city["location_id"])

        targets, parse_error = self._recycle_targets(client_id, message)
        if parse_error:
            return parse_error
        if not targets:
            return T.hint(
                "没有可回收的世界物资。",
                "发送：出售 物品名 数量，或 自动出售清理背包。",
                buttons=("背包", "探险"),
            )

        lines: list[str] = []
        total_stones = 0
        total_quantity = 0
        generated_maps: list[str] = []
        with self.db.transaction() as conn:
            self.settle_city_id_conn(conn, location_id)
            for item, quantity in targets:
                category, subtype = self.item_world_type(item)
                category_key, subtype_key = self.item_world_keys(item)
                if category_key not in WORLD_RECYCLE_CATEGORY_KEYS:
                    continue
                quantity = max(1, int(quantity))
                if not self.remove_backpack_conn(conn, client_id, item["item_id"], quantity):
                    return T.hint(f"背包中 {item['name']} 数量不足。", "发送：背包 确认库存。<背包>")
                state_delta = self._apply_material_conn(conn, location_name, item, quantity, category, subtype)
                stones = self._material_stones(conn, location_name, item, quantity, category, subtype)
                conn.execute(
                    "UPDATE players SET raw_stones = raw_stones + ? WHERE client_id = ?",
                    (stones, client_id),
                )
                conn.execute(
                    """
                    INSERT INTO world_material_records
                    (client_id, location_name, location_id, item_id, item_name, category, category_key, subtype, subtype_key, quantity, stones, state_delta, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        location_name,
                        location_id,
                        item["item_id"],
                        item["name"],
                        category,
                        category_key,
                        subtype,
                        subtype_key,
                        quantity,
                        stones,
                        dump_json(state_delta),
                        ts(),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO game_logs (client_id, action, detail, created_at)
                    VALUES (?, '物资回收', ?, ?)
                    """,
                    (
                        client_id,
                        f"location={location_name}, item={item['item_id']}, category={category}, subtype={subtype}, quantity={quantity}, stones={stones}",
                        ts(),
                    ),
                )
                self._record_sect_material_merit_conn(conn, client_id, item, quantity, category, subtype, state_delta)
                total_stones += stones
                total_quantity += quantity
                lines.append(self._material_line(item, quantity, category_key, category, subtype, stones, state_delta))
                map_text = self._try_generate_treasure_map_conn(conn, location_name)
                if map_text:
                    generated_maps.append(map_text)

        state = self.city_state(location_name)
        panel = T.panel()
        panel.section(f"城池吸收·{location_name}")
        for line in lines[:12]:
            panel.line(line)
        if len(lines) > 12:
            panel.line(f"另有 {len(lines) - 12} 类物资已入账。")
        panel.hr()
        panel.line(f"合计：{total_quantity} 件，收入 **{money(total_stones)}**")
        panel.lines(self.city_state_lines_from_state(state, compact=True))
        for text in generated_maps:
            panel.line(text)
        self.refresh_titles(client_id)
        return T.attach(panel.render(), T.buttons("背包", "自动出售", "探险"))

    def treasure_status(self, client_id: str, message: str = "") -> str:
        """查看当前位置或指定城池的藏宝图。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        target_text = message.strip()
        city = self._city_location(target_text) if target_text else self._player_city_location(player)
        if city:
            target = str(city["name"])
            target_id = str(city["location_id"])
            self.city_state_by_id(target_id)
            row = self.db.fetch_one(
                """
                SELECT *
                FROM treasure_maps
                WHERE city_id = ? AND status IN ('拍卖中', '可拾取', '宗主待领', '已成交')
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (target_id,),
            )
            if not row:
                state = self.city_state_by_id(target_id)
                lines = self.city_state_lines_from_state(state, compact=False)
                return T.hint(f"{target} 暂无藏宝图。", "\n".join(lines) if lines else "出售古物可推动神秘蓄能。<自动出售>")
            return self._format_treasure_map(row, player)

        own = self._claimable_treasure(client_id, player)
        if own:
            return self._format_treasure_map(own, player)
        rows = self.db.fetch_all(
            """
            SELECT *
            FROM treasure_maps
            WHERE status = '拍卖中'
            ORDER BY expires_at ASC
            LIMIT 5
            """
        )
        if not rows:
            return T.hint("当前没有正在挂牌的藏宝图。", "出售古物蓄能满后，城池会生成藏宝图。<自动出售>")
        panel = T.panel()
        panel.section("藏宝图")
        for row in rows:
            panel.line(
                f"{row['city_name']}｜当前价 {money(row['current_price'])}｜"
                f"出价 {row['bid_count']}/{TREASURE_BID_LIMIT}｜武器上限 {row['weapon_max_level']}"
            )
        return T.attach(panel.render(), T.buttons("探险列表", "自动出售"))

    def treasure_bid(self, client_id: str, message: str) -> str:
        """给当前位置城池的藏宝图出价。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        city = self._player_city_location(player)
        if not city:
            return T.hint("只有在挂牌城池才能出价。", "先导航到对应城池，再发送：藏宝图出价 数量。<探险列表><藏宝图>")
        location_name = str(city["name"])
        location_id = str(city["location_id"])
        amount = to_int(message, 0)
        if amount <= 0:
            return T.hint("出价格式不正确。", "发送：藏宝图出价 数量，例如：藏宝图出价 20000。<藏宝图>")
        with self.db.transaction() as conn:
            self.settle_city_id_conn(conn, location_id)
            row = conn.execute(
                """
                SELECT *
                FROM treasure_maps
                WHERE city_id = ? AND status = '拍卖中'
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (location_id,),
            ).fetchone()
            if not row:
                return T.hint(f"{location_name} 当前没有藏宝图拍卖。", "出售古物蓄能满后才会挂牌。<自动出售>")
            if str(row["highest_bidder"]) == client_id:
                return T.hint("你已经是当前最高出价者。", "等别人覆盖后才能再次出价。<藏宝图>")
            current_price = int(row["current_price"])
            min_add = max(1000, int(current_price * 0.05))
            min_price = current_price + min_add
            if amount < min_price:
                return T.hint(f"出价太低，当前至少需要 {money(min_price)}。", f"发送：藏宝图出价 {min_price}<藏宝图出价 {min_price}>")
            if not self.spend_stones_conn(conn, client_id, amount):
                return T.hint(f"随身{currency_name()}不足，需要锁定 {money(amount)}。", f"先取出{currency_name()}或继续跑商。<银行><商场推荐>")
            old_bidder = str(row["highest_bidder"] or "")
            old_price = int(row["current_price"] or 0)
            if old_bidder:
                conn.execute("UPDATE players SET raw_stones = raw_stones + ? WHERE client_id = ?", (old_price, old_bidder))
                conn.execute("UPDATE treasure_map_bids SET active = 0 WHERE map_id = ?", (row["map_id"],))
            bid_count = int(row["bid_count"]) + 1
            conn.execute(
                """
                INSERT INTO treasure_map_bids (map_id, client_id, amount, active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (row["map_id"], client_id, amount, ts()),
            )
            conn.execute(
                """
                UPDATE treasure_maps
                SET current_price = ?, highest_bidder = ?, bid_count = ?
                WHERE map_id = ?
                """,
                (amount, client_id, bid_count, row["map_id"]),
            )
            if bid_count >= TREASURE_BID_LIMIT:
                fresh = conn.execute("SELECT * FROM treasure_maps WHERE map_id = ?", (row["map_id"],)).fetchone()
                self._settle_auction_conn(conn, dict(fresh))
        if bid_count >= TREASURE_BID_LIMIT:
            return T.attach(
                T.success(f"藏宝图第 {TREASURE_BID_LIMIT} 次出价落锤：{money(amount)}。你已拍下 {location_name} 藏宝图，发送：领取藏宝图。"),
                T.buttons("领取藏宝图", "藏宝图"),
            )
        return T.attach(
            T.success(f"出价成功：{location_name} 藏宝图当前价 {money(amount)}，出价 {bid_count}/{TREASURE_BID_LIMIT}。"),
            T.buttons("藏宝图", "领取藏宝图"),
        )

    def treasure_claim(self, client_id: str) -> str:
        """领取已成交、宗主待领或脚下可拾取藏宝图。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        with self.db.transaction() as conn:
            for city_id in CITY_LOCATION_IDS:
                self._settle_treasure_maps_conn(conn, city_id)
            row = self._claimable_treasure_conn(conn, client_id, player)
            if not row:
                return T.hint("当前没有可领取的藏宝图。", "拍下藏宝图、宗主待领，或走到荒地藏宝图坐标后才能领取。<藏宝图>")
            weapon_id = self.weapon_core.create_weapon_conn(
                conn,
                client_id,
                str(row["weapon_def_id"]),
                QUALITY_EPIC,
                int(row["weapon_max_level"]),
                equipped=False,
            )
            conn.execute(
                """
                UPDATE treasure_maps
                SET status = '已领取',
                    owner_client_id = ?,
                    settled_at = COALESCE(settled_at, ?),
                    result = ?
                WHERE map_id = ?
                """,
                (
                    client_id,
                    ts(),
                    dump_json({"claimed_by": client_id, "weapon_id": weapon_id}),
                    row["map_id"],
                ),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '领取藏宝图', ?, ?)",
                (client_id, f"map_id={row['map_id']}, weapon_id={weapon_id}, city={row['city_name']}", ts()),
            )
            merit = max(100, int(row["current_price"] or 0) // 100 + int(row["weapon_max_level"] or 0) * 10)
            record_sect_merit_conn(
                conn,
                client_id,
                "influence",
                merit,
                source="领取藏宝图",
                detail=f"map_id={row['map_id']}, city={row['city_name']}, weapon={row['weapon_name']}",
            )
        return (
            f"藏宝图兑现：{row['city_name']} 旧藏被你翻了出来，"
            f"获得武器〔{weapon_id}〕{row['weapon_name']}[{quality_label(QUALITY_EPIC)}] 上限{row['weapon_max_level']}。"
            + T.buttons("武器", "藏宝图")
        )

    def city_state(self, location_name: str) -> dict[str, Any] | None:
        """读取并懒结算城池状态。"""

        city = self._city_location(location_name)
        if not city:
            return None
        return self.city_state_by_id(str(city["location_id"]))

    def city_state_by_id(self, location_id: str) -> dict[str, Any] | None:
        """按稳定城池 ID 读取并懒结算城池状态。"""

        if str(location_id or "") not in CITY_LOCATION_IDS:
            return None
        with self.db.transaction() as conn:
            return self.settle_city_id_conn(conn, str(location_id))

    def city_state_lines(self, location_name: str, compact: bool = True) -> list[str]:
        """生成地点文本里的城池状态短句。"""

        state = self.city_state(location_name)
        return self.city_state_lines_from_state(state, compact=compact) if state else []

    def city_state_lines_from_state(self, state: dict[str, Any] | None, compact: bool = True) -> list[str]:
        """把城池状态格式化为短文本。"""

        if not state:
            return []
        level = int(row_value(state, "city_level", 1))
        build_exp = int(row_value(state, "build_exp", 0))
        next_need = self.build_exp_need(level)
        life_tier = self.life_tier(state)
        relic_energy = int(row_value(state, "relic_energy", 0))
        relic_limit = self.relic_limit(level)
        medicine_stock = self.medicine_stock_score(state)
        lines = [
            f"城池 Lv.{level}，影响半径 {level}，建设 {build_exp}/{next_need}。",
        ]
        if compact:
            life_text = "薄" if life_tier <= 1 else "渐起" if life_tier <= 3 else "偏盛" if life_tier <= 6 else "浓厚"
            med_text = "药路偏紧" if medicine_stock < 800 else "药路有源" if medicine_stock < 3000 else "药路丰沛"
            lines.append(f"民生恩赐{life_text}，{med_text}，神秘蓄能 {relic_energy}/{relic_limit}。")
        else:
            lines.extend(
                [
                    f"民生阶数：{life_tier}/10，影响极·技能书概率。",
                    f"药路底盘：{medicine_stock}，影响跑商顺药。",
                    f"神秘蓄能：{relic_energy}/{relic_limit}，满后生成藏宝图。",
                ]
            )
        map_line = self._treasure_map_line(str(state["location_name"]))
        if map_line:
            lines.append(map_line)
        return lines

    def settle_city_conn(self, conn: sqlite3.Connection, location_name: str) -> dict[str, Any]:
        """懒结算城池状态并返回最新行。"""

        location_id = self._city_location_id_conn(conn, location_name)
        if not location_id:
            return {}
        return self.settle_city_id_conn(conn, location_id)

    def settle_city_id_conn(self, conn: sqlite3.Connection, location_id: str) -> dict[str, Any]:
        """按稳定城池 ID 懒结算城池状态并返回最新行。"""

        city = self._city_location_conn(conn, location_id=location_id)
        if not city:
            return {}
        city_name = str(city["name"])
        row = conn.execute("SELECT * FROM city_world_states WHERE location_id = ?", (location_id,)).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO city_world_states (location_name, location_id, last_settled_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (city_name, location_id, ts(), ts()),
            )
            row = conn.execute("SELECT * FROM city_world_states WHERE location_id = ?", (location_id,)).fetchone()
        assert row is not None
        state = dict(row)
        last = dt(str(state.get("last_settled_at") or ""))
        if not last:
            last = now()
        hours = max(0, int((now() - last).total_seconds() // 3600))
        if hours <= 0:
            self._settle_treasure_maps_conn(conn, location_id)
            return state

        guard = max(0, int(state["medicine_guard"]) - hours * self._medicine_guard_decay(state))
        life_values = {
            "life_food": int(state["life_food"]),
            "life_salt": int(state["life_salt"]),
            "life_water": int(state["life_water"]),
            "life_cloth": int(state["life_cloth"]),
            "life_fuel": int(state["life_fuel"]),
        }
        days = hours // 24
        if days > 0:
            for key, value in list(life_values.items()):
                tier = self._tier_for_value(value)
                decay = self._life_daily_decay(tier) * days
                life_values[key] = max(0, value - decay)

        conn.execute(
            """
            UPDATE city_world_states
            SET medicine_guard = ?,
                life_food = ?, life_salt = ?, life_water = ?, life_cloth = ?, life_fuel = ?,
                last_settled_at = ?, updated_at = ?
            WHERE location_id = ?
            """,
            (
                guard,
                life_values["life_food"],
                life_values["life_salt"],
                life_values["life_water"],
                life_values["life_cloth"],
                life_values["life_fuel"],
                ts(),
                ts(),
                location_id,
            ),
        )
        self._settle_treasure_maps_conn(conn, location_id)
        row = conn.execute("SELECT * FROM city_world_states WHERE location_id = ?", (location_id,)).fetchone()
        assert row is not None
        return dict(row)

    def maybe_carry_medicine(self, conn: sqlite3.Connection, client_id: str, location_name: str) -> str:
        """普通跑商出售后按当地药路状态随机顺药。"""

        city = self._city_location_conn(conn, location_name)
        if not city:
            return ""
        location_name = str(city["name"])
        location_id = str(city["location_id"])
        state = self.settle_city_id_conn(conn, location_id)
        med_score = self.medicine_stock_score(state)
        if med_score <= 0:
            return ""
        guard = int(state["medicine_guard"])
        pressure = self._medicine_consumption_pressure(conn)
        chance = 0.04 + min(0.14, med_score / 30000) + min(0.06, pressure)
        support_bonus = sect_direction_bonus_conn(conn, client_id, "support")
        chance += min(0.06, support_bonus * 0.075)
        guard_factor = max(0.5, 1.0 - guard / 160)
        chance *= guard_factor
        if random.random() >= chance:
            return ""

        quantity = 1
        if med_score >= 1800 and random.random() < 0.45:
            quantity += 1
        if med_score >= 4200 and random.random() < 0.25:
            quantity += 1
        if med_score >= 8000 and pressure > 0.025 and random.random() < 0.18:
            quantity += random.randint(1, 2)
        if support_bonus > 0 and random.random() < min(0.30, support_bonus):
            quantity += 1
        quantity = max(1, min(5, quantity))

        ring_id = self._weighted_medicine_ring_id(state)
        if not ring_id:
            return ""
        item = conn.execute("SELECT name FROM ring_item_defs WHERE ring_item_id = ?", (ring_id,)).fetchone()
        if not item:
            return ""
        self.add_ring_conn(conn, client_id, ring_id, quantity)
        consume = quantity * 80
        conn.execute(
            """
            UPDATE city_world_states
            SET medicine_material = max(0, medicine_material - ?),
                medicine_catalyst = max(0, medicine_catalyst - ?),
                medicine_fuel = max(0, medicine_fuel - ?),
                medicine_guard = min(100, medicine_guard + ?),
                updated_at = ?
            WHERE location_id = ?
            """,
            (
                consume,
                max(1, consume // 2),
                max(1, consume // 3),
                8 + quantity * 4,
                ts(),
                location_id,
            ),
        )
        conn.execute(
            """
            INSERT INTO trade_records
            (client_id, action, item_id, quantity, total_price, fee, location_name, location_id, business_day, created_at)
            VALUES (?, 'medicine_carry', ?, ?, 0, 0, ?, ?, ?, ?)
            """,
            (client_id, ring_id, quantity, location_name, location_id, business_day(), ts()),
        )
        record_sect_merit_conn(
            conn,
            client_id,
            "support",
            quantity * 80,
            source="商路顺药",
            detail=f"location={location_name}, item={ring_id}, quantity={quantity}",
        )
        item_text = f"{item['name']} x{quantity}"
        return random.choice(MEDICINE_CARRY_TEXTS).format(items=item_text)

    def add_war_prep_conn(
        self,
        conn: sqlite3.Connection,
        buyer_name: str,
        item: dict[str, Any],
        quantity: int,
        client_id: str = "",
    ) -> dict[str, Any]:
        """特殊出售战利品时增加对应势力战备。"""

        category, subtype = self.item_world_type(item)
        category_key, _subtype_key = self.item_world_keys(item)
        if category_key != "loot":
            return {"added": 0, "text": ""}
        buyer_id = self._buyer_location_id_conn(conn, buyer_name)
        if not buyer_id:
            return {"added": 0, "text": ""}
        prep = WAR_PREP_SEED.get(buyer_id)
        if not prep:
            return {"added": 0, "text": ""}
        added = self._war_prep_value(item, quantity)
        threshold = self.war_prep_threshold_conn(conn)
        now_text = ts()
        row = conn.execute("SELECT * FROM war_prep_states WHERE location_id = ?", (buyer_id,)).fetchone()
        if not row:
            conn.execute(
                """
                INSERT INTO war_prep_states
                (location_id, buyer_name, prep_name, loot_subtype, threshold, last_settled_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (buyer_id, buyer_name, prep[0], prep[1], threshold, now_text, now_text),
            )
        conn.execute(
            """
            UPDATE war_prep_states
            SET prep_value = prep_value + ?,
                threshold = ?,
                pending = CASE WHEN prep_value + ? >= ? THEN 1 ELSE pending END,
                pending_at = CASE WHEN prep_value + ? >= ? AND pending_at IS NULL THEN ? ELSE pending_at END,
                updated_at = ?
            WHERE location_id = ?
            """,
            (added, threshold, added, threshold, added, threshold, now_text, now_text, buyer_id),
        )
        if client_id:
            record_sect_merit_conn(
                conn,
                client_id,
                "influence",
                added,
                source="战利品战备",
                detail=f"buyer={buyer_name}, item={item['item_id']}, quantity={quantity}, prep={prep[0]}",
            )
        row = conn.execute("SELECT * FROM war_prep_states WHERE location_id = ?", (buyer_id,)).fetchone()
        current_value = int(row["prep_value"]) if row else added
        pending = bool(int(row["pending"])) if row else current_value >= threshold
        text = f"{prep[0]} +{added}，当前 {current_value}/{threshold}" + ("，已入待牵引队列" if pending else "")
        return {
            "added": added,
            "text": text,
            "buyer_name": buyer_name,
            "prep_name": prep[0],
            "threshold": threshold,
            "current": current_value,
            "pending": pending,
        }

    def pending_war_prep(self) -> dict[str, Any] | None:
        """读取下一条可牵引战备。"""

        with self.db.transaction() as conn:
            return self.pending_war_prep_conn(conn)

    def pending_war_prep_conn(self, conn: sqlite3.Connection) -> dict[str, Any] | None:
        """事务内读取下一条可牵引战备。"""

        threshold = self.war_prep_threshold_conn(conn)
        conn.execute("UPDATE war_prep_states SET threshold = ? WHERE threshold != ?", (threshold, threshold))
        rows = conn.execute(
            """
            SELECT *
            FROM war_prep_states
            WHERE pending = 1 AND prep_value >= ?
            ORDER BY
                datetime(COALESCE(last_opened_at, '1970-01-01T00:00:00')) ASC,
                datetime(COALESCE(pending_at, updated_at)) ASC,
                (prep_value - threshold) DESC
            """,
            (threshold,),
        ).fetchall()
        if not rows:
            return None
        return dict(rows[0])

    def consume_war_prep_conn(self, conn: sqlite3.Connection, buyer_name: str, threshold: int) -> None:
        """牵引战备虫洞后扣除本次阈值，溢出保留。"""

        buyer_id = self._buyer_location_id_conn(conn, buyer_name)
        if not buyer_id:
            return
        conn.execute(
            """
            UPDATE war_prep_states
            SET prep_value = max(0, prep_value - ?),
                pending = CASE WHEN max(0, prep_value - ?) >= threshold THEN 1 ELSE 0 END,
                pending_at = CASE WHEN max(0, prep_value - ?) >= threshold THEN ? ELSE NULL END,
                last_opened_at = ?,
                updated_at = ?
            WHERE location_id = ?
            """,
            (threshold, threshold, threshold, ts(), ts(), ts(), buyer_id),
        )

    def war_prep_threshold_conn(self, conn: sqlite3.Connection) -> int:
        """按活跃人数计算战备阈值。"""

        cutoff = ts(now() - timedelta(days=TRADE_ACTIVE_WINDOW_DAYS))
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM players p
            WHERE p.created_at >= ?
               OR EXISTS (SELECT 1 FROM game_logs g WHERE g.client_id = p.client_id AND g.created_at >= ?)
               OR EXISTS (SELECT 1 FROM trade_records t WHERE t.client_id = p.client_id AND t.created_at >= ?)
               OR EXISTS (SELECT 1 FROM exploration_records e WHERE e.client_id = p.client_id AND e.started_at >= ?)
               OR EXISTS (SELECT 1 FROM wormhole_participants wp WHERE wp.client_id = p.client_id AND wp.updated_at >= ?)
               OR EXISTS (SELECT 1 FROM seasonal_boss_participants sp WHERE sp.client_id = p.client_id AND sp.updated_at >= ?)
               OR EXISTS (SELECT 1 FROM duel_records d WHERE (d.from_client_id = p.client_id OR d.to_client_id = p.client_id) AND d.created_at >= ?)
               OR EXISTS (SELECT 1 FROM combat_logs c WHERE c.client_id = p.client_id AND c.created_at >= ?)
            """,
            (cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff),
        ).fetchone()
        active = max(1, int(row["count"] if row else 1))
        return max(1800, min(6000, 1800 + active * 240))

    def item_world_type(self, item: dict[str, Any]) -> tuple[str, str]:
        """从物品 effect 读取世界物资大类和小类。"""

        effect = load_json(item.get("effect"), {})
        return str(effect.get("world_category") or item.get("category") or ""), str(effect.get("world_subtype") or "")

    def item_world_keys(self, item: dict[str, Any]) -> tuple[str, str]:
        """读取世界物资稳定规则键；展示名换皮后业务只认这组键。"""

        effect = load_json(item.get("effect"), {})
        category_key = str(effect.get("world_category_key") or "").strip()
        subtype_key = str(effect.get("world_subtype_key") or "").strip()
        return category_key, subtype_key

    @staticmethod
    def build_exp_need(level: int) -> int:
        """城池升下一级需要的建设经验。"""

        current = max(1, min(CITY_MAX_LEVEL, int(level)))
        if current >= CITY_MAX_LEVEL:
            return 0
        return int(1200 * (current ** 1.8) + 3000 * current)

    @staticmethod
    def relic_limit(level: int) -> int:
        """城池藏宝图神秘蓄能上限。"""

        return 5000 + max(1, int(level)) * 180

    @staticmethod
    def life_tier(state: dict[str, Any]) -> int:
        """按五类民生值计算当地恩赐阶数。"""

        values = [
            int(row_value(state, "life_food", 0)),
            int(row_value(state, "life_salt", 0)),
            int(row_value(state, "life_water", 0)),
            int(row_value(state, "life_cloth", 0)),
            int(row_value(state, "life_fuel", 0)),
        ]
        tiers = [WorldMaterialService._tier_for_value(value) for value in values]
        average = int(sum(tiers) / len(tiers)) if tiers else 0
        if tiers and min(tiers) <= average - 2:
            average -= 1
        return max(0, min(10, average))

    def extreme_book_upgrade_chance(self, location_name: str, play_bonus: float = 0.0) -> float:
        """读取某地民生提供的极·技能书升级概率。"""

        state = self.city_state(location_name)
        tier = self.life_tier(state) if state else 0
        return min(0.06, 0.002 + tier * 0.0045 + max(0.0, float(play_bonus)))

    @staticmethod
    def medicine_stock_score(state: dict[str, Any]) -> int:
        """药路三类来源的综合值。"""

        return (
            int(row_value(state, "medicine_material", 0))
            + int(row_value(state, "medicine_catalyst", 0))
            + int(row_value(state, "medicine_fuel", 0))
        )

    @staticmethod
    def _tier_for_value(value: int) -> int:
        tier = 0
        for threshold in LIFE_THRESHOLDS:
            if int(value) >= threshold:
                tier += 1
        return tier

    @staticmethod
    def _life_daily_decay(tier: int) -> int:
        if tier <= 0:
            return 0
        threshold = LIFE_THRESHOLDS[min(9, tier - 1)]
        if tier <= 3:
            rate = 0.06
        elif tier <= 6:
            rate = 0.08
        elif tier <= 8:
            rate = 0.10
        elif tier == 9:
            rate = 0.12
        else:
            rate = 0.15
        return max(1, int(threshold * rate))

    def _recycle_targets(self, client_id: str, message: str) -> tuple[list[tuple[dict[str, Any], int]], str]:
        parts = split_words(message)
        if not parts:
            return [], T.hint("出售格式不正确。", "发送：出售 物品名 数量，或 自动出售。<背包>")
        keyword = "".join(parts)
        rows = self.backpack_rows(client_id)
        if keyword in {"全部", "全回收", "一键回收"}:
            return self._recyclable_rows(rows), ""
        keyword_key = self._recycle_category_key(keyword)
        if keyword_key:
            return [row for row in self._recyclable_rows(rows) if self.item_world_keys(row[0])[0] == keyword_key], ""
        if len(parts) > 1 and parts[-1].lstrip("+-").isdigit():
            quantity = to_int(parts[-1], 0)
            item_name = " ".join(parts[:-1])
        else:
            quantity = 1
            item_name = message.strip()
        if quantity <= 0:
            return [], T.hint("出售数量必须大于 0。", "发送：出售 物品名 数量。")
        item = self.item_def_by_name(item_name)
        if not item:
            return [], T.hint(f"没有找到物资：{item_name}。", "发送：背包 查看准确名称。<背包>")
        category, _subtype = self.item_world_type(item)
        category_key, _subtype_key = self.item_world_keys(item)
        if category_key == "trade":
            return [], T.hint(f"{item['name']} 是纯经济商场货。", "发送：出售 物品名 数量，系统会自动选择商场。<出售>")
        if category_key == "loot":
            return [], T.hint(f"{item['name']} 是战利品。", "发送：出售 物品名 数量，系统会自动前往收购点。<出售>")
        if category_key not in WORLD_RECYCLE_CATEGORY_KEYS:
            return [], T.hint(f"{item['name']} 不能走城池吸收。", "武器、宝石、技能书可发送：出售全部 武器/宝石/技能书。")
        return [(item, quantity)], ""

    def _recyclable_rows(self, rows: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
        result = []
        for row in rows:
            category_key, _subtype_key = self.item_world_keys(row)
            if category_key in WORLD_RECYCLE_CATEGORY_KEYS:
                result.append((row, int(row["quantity"])))
        return result

    def _recycle_category_key(self, keyword: str) -> str:
        """把当前皮肤分类名、默认分类名或稳定键解析成可回收世界大类。"""

        value = str(keyword or "").strip()
        if not value:
            return ""
        if value in WORLD_RECYCLE_CATEGORY_KEYS:
            return value
        default_key = world_category_key(value)
        if default_key in WORLD_RECYCLE_CATEGORY_KEYS:
            return default_key
        rows = self.db.fetch_all(
            """
            SELECT category, json_extract(effect, '$.world_category_key') AS category_key
            FROM item_defs
            WHERE json_extract(effect, '$.world_category_key') IN ('medicine', 'life', 'build', 'relic')
            GROUP BY category, category_key
            """
        )
        for row in rows:
            if str(row.get("category") or "").strip() == value:
                key = str(row.get("category_key") or "").strip()
                return key if key in WORLD_RECYCLE_CATEGORY_KEYS else ""
        return ""

    def _apply_material_conn(
        self,
        conn: sqlite3.Connection,
        location_name: str,
        item: dict[str, Any],
        quantity: int,
        category: str,
        subtype: str,
    ) -> dict[str, Any]:
        location_id = self._city_location_id_conn(conn, location_name)
        if not location_id:
            return {}
        category_key, subtype_key = self.item_world_keys(item)
        if category_key == "medicine":
            amount = self._medicine_state_value(item, quantity)
            column = self._medicine_state_column(item)
            conn.execute(
                f"UPDATE city_world_states SET {column} = {column} + ?, updated_at = ? WHERE location_id = ?",
                (amount, ts(), location_id),
            )
            return {column: amount}
        if category_key == "life":
            amount = self._life_state_value(item, quantity)
            column = LIFE_STATE_COLUMNS_BY_KEY.get(subtype_key, "life_food")
            conn.execute(
                f"UPDATE city_world_states SET {column} = {column} + ?, updated_at = ? WHERE location_id = ?",
                (amount, ts(), location_id),
            )
            return {column: amount}
        if category_key == "build":
            exp = self._build_exp_value(item, quantity)
            old_row = conn.execute("SELECT city_level, build_exp FROM city_world_states WHERE location_id = ?", (location_id,)).fetchone()
            old_level = int(old_row["city_level"]) if old_row else 1
            old_exp = 0 if old_level >= CITY_MAX_LEVEL else int(old_row["build_exp"] if old_row else 0)
            level, build_exp = self._apply_build_exp(old_level, old_exp + exp)
            conn.execute(
                "UPDATE city_world_states SET city_level = ?, build_exp = ?, updated_at = ? WHERE location_id = ?",
                (level, build_exp, ts(), location_id),
            )
            return {"build_exp": exp, "level_up": max(0, level - old_level)}
        if category_key == "relic":
            energy = self._relic_energy_value(item, quantity)
            conn.execute(
                "UPDATE city_world_states SET relic_energy = relic_energy + ?, updated_at = ? WHERE location_id = ?",
                (energy, ts(), location_id),
            )
            return {"relic_energy": energy}
        return {}

    def _material_stones(
        self,
        conn: sqlite3.Connection,
        location_name: str,
        item: dict[str, Any],
        quantity: int,
        category: str,
        subtype: str,
    ) -> int:
        _ = conn, location_name
        category_key, _subtype_key = self.item_world_keys(item)
        amount = max(1, int(quantity))
        base_price = max(1, int(item.get("base_price", 1) or 1))
        rank = quality_rank(item.get("quality"))
        factor = quality_factor(item.get("quality"))
        if category_key == "medicine":
            unit = max(55, int(base_price * 0.33 * factor))
            return int(unit * amount * random.uniform(0.9, 1.35))
        if category_key == "life":
            unit = max(80, int(base_price * (0.42 + rank * 0.08)))
            return int(unit * amount * random.uniform(1.1, 1.8))
        if category_key == "build":
            unit = max(90, int(base_price * (0.18 + rank * 0.055)))
            return int(unit * amount * random.uniform(0.9, 1.2))
        if category_key == "relic":
            unit = max(180, int(base_price * (0.36 + rank * 0.06)))
            return int(unit * amount * random.uniform(0.9, 1.25))
        return max(1, base_price * amount)

    def _apply_build_exp(self, level: int, build_exp: int) -> tuple[int, int]:
        current_level = max(1, min(CITY_MAX_LEVEL, int(level)))
        current_exp = max(0, int(build_exp))
        while current_level < CITY_MAX_LEVEL:
            need = self.build_exp_need(current_level)
            if need <= 0 or current_exp < need:
                break
            current_exp -= need
            current_level += 1
        if current_level >= CITY_MAX_LEVEL:
            current_exp = 0
        return current_level, current_exp

    def _material_line(self, item: dict[str, Any], quantity: int, category_key: str, category: str, subtype: str, stones: int, delta: dict[str, Any]) -> str:
        if category_key == "build":
            level_text = f"，城池升级 +{delta.get('level_up')}" if int(delta.get("level_up", 0)) > 0 else ""
            return f"{item['name']} x{quantity}｜建设经验 +{delta.get('build_exp', 0)}{level_text}｜{currency_amount(stones)}"
        if category_key == "relic":
            return f"{item['name']} x{quantity}｜神秘蓄能 +{delta.get('relic_energy', 0)}｜{currency_amount(stones)}"
        if category_key == "life":
            return f"{item['name']} x{quantity}｜民生底盘 +{sum(int(v) for v in delta.values())}｜{currency_amount(stones)}"
        if category_key == "medicine":
            return f"{item['name']} x{quantity}｜药路来源 +{sum(int(v) for v in delta.values())}｜{currency_amount(stones)}"
        return f"{item['name']} x{quantity}｜{category}/{subtype}｜{currency_amount(stones)}"

    @staticmethod
    def _medicine_state_column(item: dict[str, Any]) -> str:
        """药路物资计入哪一类储备，只看稳定 effect 字段。"""

        effect = load_json(item.get("effect"), {})
        role = str(effect.get("medicine_material_role") or "").strip()
        return MEDICINE_ROLE_STATE_COLUMNS.get(role) or "medicine_material"

    @staticmethod
    def _medicine_state_value(item: dict[str, Any], quantity: int) -> int:
        """药路状态值：按基础价和品质计算，不按药名或小类名判断。"""

        unit = max(70, int(int(item.get("base_price", 260) or 260) * 0.36 * quality_factor(item.get("quality"))))
        return unit * max(1, int(quantity))

    @staticmethod
    def _life_state_value(item: dict[str, Any], quantity: int) -> int:
        """民生状态值：量大刚需，按基础价和品质折算。"""

        base_price = int(item.get("base_price", 180) or 180)
        unit = max(90, int(base_price * (0.45 + quality_rank(item.get("quality")) * 0.08)))
        return unit * max(1, int(quantity))

    @staticmethod
    def _build_exp_value(item: dict[str, Any], quantity: int) -> int:
        """建设经验：城池成长主价值，按基础价和品质拉开差距。"""

        base_price = int(item.get("base_price", 420) or 420)
        rank = quality_rank(item.get("quality"))
        unit = max(320, int(base_price * (0.85 + rank * 0.22)))
        return unit * max(1, int(quantity))

    @staticmethod
    def _relic_energy_value(item: dict[str, Any], quantity: int) -> int:
        """古物蓄能：神秘物质只看含量强弱，含量由品质和基础价体现。"""

        base_price = int(item.get("base_price", 1300) or 1300)
        factor = quality_factor(item.get("quality"))
        unit = max(8, int((base_price / 115) * factor))
        return unit * max(1, int(quantity))

    @staticmethod
    def _war_prep_value(item: dict[str, Any], quantity: int) -> int:
        """战备蓄能：按战利品价值和品质折算，不按战利品展示小类名判断。"""

        base_price = int(item.get("base_price", 620) or 620)
        rank = quality_rank(item.get("quality"))
        unit = max(18, int(base_price / 34 * (0.85 + rank * 0.18)))
        return unit * max(1, int(quantity))

    def _record_sect_material_merit_conn(
        self,
        conn: sqlite3.Connection,
        client_id: str,
        item: dict[str, Any],
        quantity: int,
        category: str,
        subtype: str,
        state_delta: dict[str, Any],
    ) -> None:
        """世界物资回收同步沉淀宗门三底蕴。"""

        category_key, _subtype_key = self.item_world_keys(item)
        if category_key == "build":
            amount = int(state_delta.get("build_exp", 0) or 0)
            merit = "build"
        elif category_key == "medicine":
            amount = sum(int(v) for v in state_delta.values())
            merit = "support"
        elif category_key == "life":
            amount = int(sum(int(v) for v in state_delta.values()) * 0.8)
            merit = "support"
        elif category_key == "relic":
            amount = max(1, int(self._material_stones(conn, "", item, quantity, category, subtype) / 4))
            merit = "influence"
        else:
            return
        record_sect_merit_conn(
            conn,
            client_id,
            merit,
            amount,
            source=f"{category}回收",
            detail=f"item={item['item_id']}, subtype={subtype}, quantity={quantity}",
        )

    def _try_generate_treasure_map_conn(self, conn: sqlite3.Connection, location_name: str) -> str:
        city = self._city_location_conn(conn, location_name)
        if not city:
            return ""
        location_name = str(city["name"])
        location_id = str(city["location_id"])
        state = conn.execute("SELECT * FROM city_world_states WHERE location_id = ?", (location_id,)).fetchone()
        if not state:
            return ""
        active = conn.execute(
            """
            SELECT 1 FROM treasure_maps
            WHERE city_id = ? AND status IN ('拍卖中', '可拾取', '宗主待领', '已成交')
            LIMIT 1
            """,
            (location_id,),
        ).fetchone()
        if active:
            return ""
        level = int(state["city_level"])
        limit = self.relic_limit(level)
        if int(state["relic_energy"]) < limit:
            return ""
        weapon = self._city_treasure_weapon(location_name, level)
        current = now()
        conn.execute(
            "UPDATE city_world_states SET relic_energy = relic_energy - ?, updated_at = ? WHERE location_id = ?",
            (limit, ts(current), location_id),
        )
        conn.execute(
            """
            INSERT INTO treasure_maps
            (city_name, city_id, status, current_price, weapon_def_id, weapon_name, weapon_max_level, generated_at, expires_at, result)
            VALUES (?, ?, '拍卖中', ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                location_name,
                location_id,
                self._treasure_start_price(level),
                weapon["weapon_def_id"],
                weapon["name"],
                weapon["max_level"],
                ts(current),
                ts(current + timedelta(hours=TREASURE_AUCTION_HOURS)),
                dump_json({"source": "relic_energy", "city_level": level}),
            ),
        )
        return f"{location_name}秘库震动，藏宝图挂牌，底价 {money(self._treasure_start_price(level))}。"

    def _settle_treasure_maps_conn(self, conn: sqlite3.Connection, location_id: str) -> None:
        rows = conn.execute(
            """
            SELECT *
            FROM treasure_maps
            WHERE city_id = ? AND status IN ('拍卖中', '可拾取')
            """,
            (str(location_id),),
        ).fetchall()
        for row in rows:
            expires = dt(row["expires_at"])
            if not expires or now() < expires:
                continue
            if row["status"] == "拍卖中":
                self._settle_auction_conn(conn, dict(row))
            elif row["status"] == "可拾取":
                self._reroll_treasure_spot_conn(conn, dict(row))

    def _settle_auction_conn(self, conn: sqlite3.Connection, row: dict[str, Any]) -> None:
        if str(row["highest_bidder"]):
            conn.execute(
                """
                UPDATE treasure_maps
                SET status = '已成交', owner_client_id = ?, settled_at = ?, result = ?
                WHERE map_id = ?
                """,
                (
                    row["highest_bidder"],
                    ts(),
                    dump_json({"settle": "auction", "price": int(row["current_price"])}),
                    row["map_id"],
                ),
            )
            return
        self._reroll_treasure_spot_conn(conn, row)

    def _reroll_treasure_spot_conn(self, conn: sqlite3.Connection, row: dict[str, Any]) -> None:
        spot = self._random_treasure_spot(conn, str(row.get("city_name") or ""))
        expires = now() + timedelta(hours=TREASURE_PICKUP_HOURS)
        if spot.get("sect_id"):
            master = str(spot["master_client_id"])
            conn.execute(
                """
                UPDATE treasure_maps
                SET status = '宗主待领', x = ?, y = ?, owner_client_id = ?, owner_sect_id = ?, expires_at = ?, result = ?
                WHERE map_id = ?
                """,
                (
                    spot["x"],
                    spot["y"],
                    master,
                    int(spot["sect_id"]),
                    ts(expires),
                    dump_json({"settle": "sect_spot", "sect_name": spot["name"], "city_name": row.get("city_name", "")}),
                    row["map_id"],
                ),
            )
            return
        conn.execute(
            """
            UPDATE treasure_maps
            SET status = '可拾取', x = ?, y = ?, highest_bidder = '', owner_client_id = '', expires_at = ?, result = ?
            WHERE map_id = ?
            """,
            (
                spot["x"],
                spot["y"],
                ts(expires),
                dump_json({"settle": "wilderness_spot", "city_name": row.get("city_name", ""), "near_city": bool(spot.get("near_city"))}),
                row["map_id"],
            ),
        )

    def _random_treasure_spot(self, conn: sqlite3.Connection, city_name: str = "") -> dict[str, Any]:
        occupied = {
            (int(row["x"]), int(row["y"]))
            for row in conn.execute("SELECT x, y FROM world_locations").fetchall()
        }
        occupied.update(
            (int(row["location_x"]), int(row["location_y"]))
            for row in conn.execute("SELECT location_x, location_y FROM sects").fetchall()
        )
        occupied.update(
            (int(row["x"]), int(row["y"]))
            for row in conn.execute("SELECT x, y FROM treasure_maps WHERE status = '可拾取' AND x IS NOT NULL AND y IS NOT NULL").fetchall()
        )
        city_id = self._city_location_id_conn(conn, city_name)
        city_point = self._city_point(conn, city_id)
        if city_point:
            radius = self._city_treasure_radius(conn, city_id)
            for _ in range(500):
                x = random.randint(max(WORLD_COORD_MIN, city_point["x"] - radius), min(WORLD_COORD_MAX, city_point["x"] + radius))
                y = random.randint(max(WORLD_COORD_MIN, city_point["y"] - radius), min(WORLD_COORD_MAX, city_point["y"] + radius))
                if (x, y) in occupied:
                    continue
                if self._distance(city_point["x"], city_point["y"], x, y) <= radius:
                    return {"x": x, "y": y, "near_city": True}
        sect_spot = self._random_sect_treasure_spot(conn)
        if sect_spot and random.random() < 0.2:
            return sect_spot
        for _ in range(700):
            x = random.randint(WORLD_COORD_MIN, WORLD_COORD_MAX)
            y = random.randint(WORLD_COORD_MIN, WORLD_COORD_MAX)
            if (x, y) not in occupied:
                return {"x": x, "y": y}
        if sect_spot:
            return sect_spot
        return {"x": WORLD_COORD_MIN, "y": WORLD_COORD_MIN}

    @staticmethod
    def _random_sect_treasure_spot(conn: sqlite3.Connection) -> dict[str, Any] | None:
        """藏宝图落到宗门山门时，转为宗主待领。"""

        sects = [dict(row) for row in conn.execute("SELECT * FROM sects").fetchall()]
        if not sects:
            return None
        sect = random.choice(sects)
        return {
            "x": int(sect["location_x"]),
            "y": int(sect["location_y"]),
            "sect_id": int(sect["sect_id"]),
            "master_client_id": str(sect["master_client_id"]),
            "name": str(sect["name"]),
        }

    @staticmethod
    def _city_point(conn: sqlite3.Connection, city_id: str) -> dict[str, int] | None:
        """读取 11 个普通城池坐标。"""

        row = conn.execute(
            "SELECT x, y FROM trade_locations WHERE location_id = ?",
            (str(city_id),),
        ).fetchone()
        return {"x": int(row["x"]), "y": int(row["y"])} if row else None

    @staticmethod
    def _distance(x1: int, y1: int, x2: int, y2: int) -> float:
        return math.hypot(int(x1) - int(x2), int(y1) - int(y2))

    def _city_treasure_radius(self, conn: sqlite3.Connection, city_id: str) -> int:
        row = conn.execute("SELECT city_level FROM city_world_states WHERE location_id = ?", (city_id,)).fetchone()
        level = int(row["city_level"]) if row else 1
        return max(1, min(CITY_MAX_LEVEL, level))

    def _city_treasure_weapon(self, location_name: str, city_level: int) -> dict[str, Any]:
        with self.db.transaction() as conn:
            location_id = self._city_location_id_conn(conn, location_name)
        rows = self.db.fetch_all("SELECT * FROM weapon_defs WHERE drop_location_id = ?", (location_id,))
        if not rows:
            rows = self.db.fetch_all("SELECT * FROM weapon_defs")
        weapon = random.choice(rows)
        max_level = min(88, 68 + int(math.floor(max(1, city_level) * 0.16)) + random.randint(0, 3))
        return {"weapon_def_id": weapon["weapon_def_id"], "name": weapon["name"], "max_level": max(66, max_level)}

    @staticmethod
    def _treasure_start_price(city_level: int) -> int:
        return int(30000 + max(1, int(city_level)) * 800)

    def _treasure_map_line(self, location_name: str) -> str:
        with self.db.transaction() as conn:
            location_id = self._city_location_id_conn(conn, location_name)
        if not location_id:
            return ""
        row = self.db.fetch_one(
            """
            SELECT status, current_price, bid_count, expires_at, x, y
            FROM treasure_maps
            WHERE city_id = ? AND status IN ('拍卖中', '可拾取', '宗主待领', '已成交')
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (location_id,),
        )
        if not row:
            return ""
        if row["status"] == "拍卖中":
            return f"藏宝图拍卖中，当前价 {money(row['current_price'])}，出价 {row['bid_count']}/{TREASURE_BID_LIMIT}。"
        if row["status"] == "可拾取":
            return f"藏宝图已落荒地 ({row['x']},{row['y']})，有缘者自取。"
        if row["status"] == "已成交":
            return "藏宝图已成交，正在等买主领取。"
        return "藏宝图被宗门山门卷入，宗主待领取。"

    def _claimable_treasure(self, client_id: str, player: dict[str, Any]) -> dict[str, Any] | None:
        with self.db.transaction() as conn:
            row = self._claimable_treasure_conn(conn, client_id, player)
            return dict(row) if row else None

    @staticmethod
    def _claimable_treasure_conn(conn: sqlite3.Connection, client_id: str, player: dict[str, Any]) -> sqlite3.Row | None:
        row = conn.execute(
            """
            SELECT *
            FROM treasure_maps
            WHERE status IN ('已成交', '宗主待领')
              AND owner_client_id = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (client_id,),
        ).fetchone()
        if row:
            return row
        return conn.execute(
            """
            SELECT *
            FROM treasure_maps
            WHERE status = '可拾取'
              AND x = ? AND y = ?
            ORDER BY generated_at DESC
            LIMIT 1
            """,
            (int(player["x"]), int(player["y"])),
        ).fetchone()

    def _format_treasure_map(self, row: dict[str, Any], player: dict[str, Any]) -> str:
        panel = T.panel()
        panel.section(f"藏宝图·{row['city_name']}")
        panel.line(f"状态：{row['status']}｜武器：{row['weapon_name']}[{quality_label(QUALITY_EPIC)}] 上限{row['weapon_max_level']}")
        if row["status"] == "拍卖中":
            expires = dt(row["expires_at"])
            left = max(0, int((expires - now()).total_seconds() // 60) + 1) if expires else 0
            min_price = int(row["current_price"]) + max(1000, int(int(row["current_price"]) * 0.05))
            panel.line(f"当前价：{money(row['current_price'])}｜出价 {row['bid_count']}/{TREASURE_BID_LIMIT}｜剩余约 {left} 分钟")
            panel.line(f"最低下一口：{money(min_price)}")
            return T.attach(panel.render(), T.buttons(f"藏宝图出价 {min_price}", "藏宝图"))
        if row["status"] == "可拾取":
            panel.line(f"落点：({row['x']},{row['y']})｜当前位置：({player['x']},{player['y']})")
            if int(player["x"]) == int(row["x"]) and int(player["y"]) == int(row["y"]):
                return T.attach(panel.render(), T.buttons("领取藏宝图"))
            return T.attach(panel.render(), T.buttons(f"导航 {row['x']} {row['y']}", "藏宝图"))
        if row["status"] in {"已成交", "宗主待领"} and str(row["owner_client_id"]) == str(player["client_id"]):
            panel.line(f"这张图已经归你名下，领取后会兑现为城池特色{quality_label(QUALITY_EPIC)}武器。")
            return T.attach(panel.render(), T.buttons("领取藏宝图"))
        return panel.render()

    def _medicine_consumption_pressure(self, conn: sqlite3.Connection) -> float:
        cutoff = ts(now() - timedelta(days=1))
        row = conn.execute(
            """
            SELECT COALESCE(SUM(quantity), 0) AS total
            FROM trade_records
            WHERE action = 'medicine_carry' AND created_at >= ?
            """,
            (cutoff,),
        ).fetchone()
        used = int(row["total"] if row else 0)
        return min(0.06, used / 500)

    def _medicine_guard_decay(self, state: dict[str, Any]) -> int:
        base = 6
        if (
            int(row_value(state, "medicine_material", 0)) >= 1000
            and int(row_value(state, "medicine_catalyst", 0)) >= 1000
            and int(row_value(state, "medicine_fuel", 0)) >= 1000
        ):
            base += 2
        return base

    def _weighted_medicine_ring_id(self, state: dict[str, Any]) -> str:
        material = max(1, int(row_value(state, "medicine_material", 0)))
        catalyst = max(1, int(row_value(state, "medicine_catalyst", 0)))
        fuel = max(1, int(row_value(state, "medicine_fuel", 0)))
        weights = {
            "xueqidan": material + fuel // 2,
            "yinmingcao": material + fuel // 2,
            "huichunlu": material + catalyst // 3,
            "ningshenlu": material + catalyst // 3,
            "shenggudan": catalyst + fuel // 2,
            "yanghundan": catalyst + material // 3,
        }
        keys = list(weights)
        return random.choices(keys, weights=[weights[key] for key in keys], k=1)[0]


service = WorldMaterialService(db)

__all__ = [
    "CITY_LOCATION_NAMES",
    "CITY_LOCATION_SET",
    "TREASURE_BID_LIMIT",
    "WORLD_RECYCLE_CATEGORY_KEYS",
    "WorldMaterialService",
    "service",
]
