"""探险组件服务。"""

from __future__ import annotations

from datetime import timedelta

from ..combat_core import service as combat_service
from ..common import CoreService, dump_json, hint, load_json, now, random, ts
from ..constants import ENCOUNTER_SECONDS, EXPLORE_MINUTES
from ..sql import db
from ..weapon_core import service as weapon_service


class ExplorationService(CoreService):
    """30 分钟探险预计算和领取。"""

    def locations(self, client_id: str) -> str:
        """查看探险地点。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.db.fetch_all("SELECT * FROM exploration_locations ORDER BY recommended_level")
        return "\n".join(
            f"{row['name']}：推荐{row['recommended_level']}级，怪物{row['min_level']}-{row['max_level']}级，{row['desc']}"
            for row in rows
        )

    def current_location(self, client_id: str) -> str:
        """查看当前位置。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        return f"当前位置：{player['location_name']} ({player['x']},{player['y']})"

    def start(self, client_id: str) -> str:
        """开始探险。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        active = self._active_record(client_id)
        if active:
            return hint("你已经在探险中或有待领取结果。", "发送：探险状态 查看进度；30 分钟后发送：结束探险")
        if player["status"] != "空闲":
            return hint(f"当前状态为 {player['status']}，不能开始探险。", "先处理当前状态，例如：结束休息 / 探险状态 / 结束探险")
        if player["hp"] <= 0:
            return hint("血气不足，不能开始探险。", "发送：休息，时间到后发送：结束休息")
        location = self.db.fetch_one(
            "SELECT * FROM exploration_locations WHERE name = ?",
            (player["location_name"],),
        )
        if not location:
            return hint("当前位置不是探险地点。", "发送：地点列表 查看可探险地点，再发送：导航 地点名")

        weapon_service.ensure_starter_weapon(client_id)
        result = self._precompute(client_id, player)
        started = now()
        ready = started + timedelta(minutes=EXPLORE_MINUTES)
        with self.db.transaction() as conn:
            active = conn.execute(
                """
                SELECT 1 FROM exploration_records
                WHERE client_id = ? AND claimed = 0
                LIMIT 1
                """,
                (client_id,),
            ).fetchone()
            if active:
                return hint("你已经在探险中或有待领取结果。", "发送：探险状态 查看进度；30 分钟后发送：结束探险")
            for item_id, quantity in result.get("medicine_used", {}).items():
                row = conn.execute(
                    "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
                    (client_id, item_id),
                ).fetchone()
                if not row or int(row["quantity"]) < int(quantity):
                    return hint("自动用药库存已变化，无法开始探险。", "发送：查看纳戒 确认恢复药数量后，再发送：探险")
            cursor = conn.execute(
                "UPDATE players SET status = '探险中' WHERE client_id = ? AND status = '空闲'",
                (client_id,),
            )
            if cursor.rowcount <= 0:
                return hint("当前状态已变化，不能开始探险。", "发送：修仙信息 查看当前状态后再操作。")
            for item_id, quantity in result.get("medicine_used", {}).items():
                self.remove_ring_conn(conn, client_id, item_id, int(quantity))
            conn.execute(
                """
                INSERT INTO exploration_records
                (client_id, location_name, status, started_at, ready_at, result)
                VALUES (?, ?, '探险中', ?, ?, ?)
                """,
                (client_id, player["location_name"], ts(started), ts(ready), dump_json(result)),
            )
        auto_state = "开启" if player["auto_use_medicine"] else "关闭"
        return f"开始探险：{player['location_name']}。自动用药：{auto_state}。30 分钟后可结算。"

    def status(self, client_id: str) -> str:
        """查看探险状态。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        record = self._active_record(client_id)
        if not record:
            return hint("当前没有探险。", "发送：地点列表 选地点，再发送：探险")
        result = load_json(record["result"], {})
        current = now()
        elapsed = max(0, int((current - self._time(record["started_at"])).total_seconds()))
        total = EXPLORE_MINUTES * 60
        done = min(total, elapsed)
        if result.get("dead"):
            state = "已死亡，等待结算"
        elif result.get("bag_full"):
            state = "背包已满，等待结算"
        elif elapsed >= total:
            state = "已到点，待领取"
        else:
            state = "探险中"
        ready_at = self._time(record["ready_at"])
        if ready_at and current < ready_at:
            left = max(1, int((ready_at - current).total_seconds() // 60) + 1)
            return f"探险状态：{state}。进度 {done // 60}/{EXPLORE_MINUTES} 分钟，{left} 分钟后可结束探险。"
        return f"探险状态：{state}。进度 {done // 60}/{EXPLORE_MINUTES} 分钟，可领取。"

    def claim(self, client_id: str) -> str:
        """领取探险结果。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        record = self._active_record(client_id)
        if not record:
            return hint("当前没有可领取探险。", "发送：探险 开始一轮，或发送：掉落记录 查看历史。")
        ready_at = self._time(record["ready_at"])
        if ready_at and now() < ready_at:
            left = max(1, int((ready_at - now()).total_seconds() // 60) + 1)
            return hint(f"探险还没有到 30 分钟冷却，{left} 分钟后才能结束探险。", "先发送：探险状态 查看预计算结果。")
        result = load_json(record["result"], {})
        events = list(result.get("events", []))

        exp_total = sum(int(event.get("exp", 0)) for event in events)
        drops: dict[str, int] = {}
        ring_drops: dict[str, int] = {}
        weapon_drops: list[str] = []
        hp_left = player["hp"]
        mp_left = player["mp"]
        dead = False
        for event in events:
            hp_left = int(event.get("hp_left", hp_left))
            mp_left = int(event.get("mp_left", mp_left))
            if event.get("drop_item_id"):
                drops[event["drop_item_id"]] = drops.get(event["drop_item_id"], 0) + 1
            if event.get("location_drop_item_id"):
                item_id = event["location_drop_item_id"]
                drops[item_id] = drops.get(item_id, 0) + 1
            if event.get("ring_drop_id"):
                ring_drops[event["ring_drop_id"]] = ring_drops.get(event["ring_drop_id"], 0) + 1
            if hp_left <= 0:
                dead = True
                break

        with self.db.transaction() as conn:
            active = conn.execute(
                "SELECT * FROM exploration_records WHERE record_id = ? AND claimed = 0",
                (record["record_id"],),
            ).fetchone()
            if not active:
                return hint("当前没有可领取探险。", "发送：探险 开始一轮，或发送：掉落记录 查看历史。")
            for item_id, quantity in drops.items():
                ok, reason = self.can_add_backpack_conn(conn, client_id, item_id, quantity)
                if not ok:
                    return f"背包空间不足，无法领取探险结果。\n{reason}"
            old_level, new_level = self.add_exp_conn(conn, client_id, exp_total)
            for item_id, quantity in drops.items():
                self.add_backpack_conn(conn, client_id, item_id, quantity)
            for item_id, quantity in ring_drops.items():
                self.add_ring_conn(conn, client_id, item_id, quantity)
            for drop in (event.get("weapon_drop") for event in events):
                if not drop:
                    continue
                weapon_id = weapon_service.create_weapon_conn(
                    conn,
                    client_id,
                    drop["weapon_def_id"],
                    drop["quality"],
                    drop["max_level"],
                    equipped=False,
                )
                weapon_drops.append(f"#{weapon_id} {drop['name']}[{drop['quality']}] 上限{drop['max_level']}")
            conn.execute(
                "UPDATE players SET hp = ?, mp = ?, status = '空闲' WHERE client_id = ?",
                (max(1, hp_left), max(0, mp_left), client_id),
            )
            conn.execute(
                """
                UPDATE exploration_records
                SET status = '已领取', finished_at = ?, claimed = 1
                WHERE record_id = ?
                """,
                (ts(), record["record_id"]),
            )

        lines = [f"探险结束：{record['location_name']}"]
        lines.append(f"战斗 {len(events)} 场，经验+{exp_total}")
        if new_level > old_level:
            lines.append(f"等级提升：{old_level} -> {new_level}")
        if drops:
            for item_id, quantity in drops.items():
                item = self.item_def(item_id)
                lines.append(f"获得 {item['name'] if item else item_id} x{quantity}")
        if ring_drops:
            for item_id, quantity in ring_drops.items():
                item = self.equipment_item_def(item_id)
                lines.append(f"纳戒获得 {item['name'] if item else item_id} x{quantity}")
        if weapon_drops:
            lines.extend(f"获得武器 {name}" for name in weapon_drops)
        medicine_used = result.get("medicine_used", {})
        if medicine_used:
            lines.append("自动用药：" + self._format_medicine_used(medicine_used))
        if dead:
            lines.append("本次探险中途重伤，已自动撤离。")
        if result.get("bag_full"):
            lines.append("背包已满，本次探险提前停止。")
        return "\n".join(lines)

    def records(self, client_id: str) -> str:
        """查看最近探险记录。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        rows = self.db.fetch_all(
            """
            SELECT * FROM exploration_records
            WHERE client_id = ?
            ORDER BY started_at DESC
            LIMIT 5
            """,
            (client_id,),
        )
        if not rows:
            return hint("暂无探险记录。", "发送：探险 开始第一次探险。")
        return "\n".join(f"#{row['record_id']} {row['location_name']} {row['status']} {row['started_at']}" for row in rows)

    def _precompute(self, client_id: str, player: dict) -> dict:
        """预计算 30 分钟探险事件。"""

        min_level, max_level = self._monster_level_range(player)
        monsters = self.db.fetch_all(
            """
            SELECT * FROM monster_defs
            WHERE level BETWEEN ? AND ?
            ORDER BY level
            """,
            (min_level, max_level),
        )
        if not monsters:
            monsters = self.db.fetch_all(
                "SELECT * FROM monster_defs WHERE level BETWEEN ? AND ? ORDER BY level",
                (max(1, player["level"] - 5), max(5, player["level"] + 8)),
            )
        if not monsters:
            monsters = self.db.fetch_all("SELECT * FROM monster_defs ORDER BY level LIMIT 1")
        fight_count = max(1, EXPLORE_MINUTES * 60 // ENCOUNTER_SECONDS)
        events = []
        hp_left = player["hp"]
        mp_left = player["mp"]
        weight_now = self.backpack_weight(client_id)
        item_kinds = {row["item_id"] for row in self.backpack_rows(client_id)}
        pending_drops: dict[str, int] = {}
        explore_bonus = min(0.2, self.equipment_bonuses(client_id).get("explore_bonus", 0))
        # 武器按整轮探险判定一次，避免 20 场战斗把掉率放大。
        weapon_drop_chance = max(0.0, min(0.55, 0.35 + explore_bonus))
        weapon_drop_index = random.randrange(fight_count) if random.random() < weapon_drop_chance else -1
        medicine_stock = self._medicine_stock(client_id) if player["auto_use_medicine"] else {}
        medicine_used: dict[str, int] = {}
        for event_index in range(fight_count):
            hp_left, mp_left = self._auto_use_medicine(
                hp_left,
                mp_left,
                player,
                medicine_stock,
                medicine_used,
            )
            monster = random.choice(monsters)
            event = combat_service.fight_monster(
                client_id,
                monster,
                start_hp=hp_left,
                start_mp=mp_left,
            )
            hp_left = int(event.get("hp_left", hp_left))
            mp_left = int(event.get("mp_left", mp_left))
            event["hp_left"] = hp_left
            event["mp_left"] = mp_left
            if hp_left <= 0:
                events.append(event)
                return {"dead": True, "bag_full": False, "medicine_used": medicine_used, "events": events}
            hp_left, mp_left = self._auto_use_medicine(
                hp_left,
                mp_left,
                player,
                medicine_stock,
                medicine_used,
            )
            event["hp_left"] = hp_left
            event["mp_left"] = mp_left
            if event.get("drop_item_id"):
                can_take, weight_now = self._take_drop_preview(
                    player,
                    event["drop_item_id"],
                    weight_now,
                    item_kinds,
                    pending_drops,
                )
                if not can_take:
                    event["drop_item_id"] = ""
                    event["bag_full"] = True
                    events.append(event)
                    return {"dead": False, "bag_full": True, "medicine_used": medicine_used, "events": events}
            if random.random() < 0.22 + explore_bonus * 0.5:
                location_drop = self._roll_location_drop(player["location_name"])
                if location_drop:
                    can_take, weight_now = self._take_drop_preview(
                        player,
                        location_drop,
                        weight_now,
                        item_kinds,
                        pending_drops,
                    )
                    if not can_take:
                        event["bag_full"] = True
                        events.append(event)
                        return {"dead": False, "bag_full": True, "medicine_used": medicine_used, "events": events}
                    event["location_drop_item_id"] = location_drop
            if random.random() < 0.16 + explore_bonus * 0.3:
                event["ring_drop_id"] = self._roll_ring_drop()
            if event_index == weapon_drop_index:
                event["weapon_drop"] = weapon_service.roll_weapon_drop(player["level"], player["location_name"])
            events.append(event)
        return {"dead": False, "bag_full": False, "medicine_used": medicine_used, "events": events}

    def _monster_level_range(self, player: dict) -> tuple[int, int]:
        """按当前探险地点决定怪物等级段。"""

        location = self.db.fetch_one(
            "SELECT min_level, max_level FROM exploration_locations WHERE name = ?",
            (player["location_name"],),
        )
        if location:
            return max(1, int(location["min_level"])), max(1, int(location["max_level"]))
        return max(1, player["level"] - 5), max(5, player["level"] + 8)

    def _active_record(self, client_id: str) -> dict | None:
        """读取未领取探险。"""

        return self.db.fetch_one(
            """
            SELECT * FROM exploration_records
            WHERE client_id = ? AND claimed = 0
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (client_id,),
        )

    def _take_drop_preview(
        self,
        player: dict,
        item_id: str,
        weight_now: int,
        item_kinds: set[str],
        pending_drops: dict[str, int],
    ) -> tuple[bool, int]:
        """预估背包是否还能装下本次掉落。"""

        item = self.item_def(item_id)
        if not item:
            return True, weight_now

        next_weight = weight_now + int(item["weight"])
        if next_weight > int(player["weight_limit"]):
            return False, weight_now

        known = item_id in item_kinds or item_id in pending_drops
        if not known and len(item_kinds) + len(pending_drops) + 1 > int(player["backpack_limit"]):
            return False, weight_now

        current = self.db.fetch_one(
            "SELECT quantity FROM backpack_items WHERE client_id = ? AND item_id = ?",
            (player["client_id"], item_id),
        )
        current_quantity = int(current["quantity"]) if current else 0
        pending_quantity = int(pending_drops.get(item_id, 0))
        if current_quantity + pending_quantity + 1 > int(item["stack_limit"]):
            return False, weight_now

        pending_drops[item_id] = pending_drops.get(item_id, 0) + 1
        return True, next_weight

    def _roll_location_drop(self, location_name: str) -> str:
        """按当前地点随机一个特产掉落。"""

        rows = self.db.fetch_all(
            """
            SELECT item_id
            FROM trade_goods
            WHERE home_location = ?
            """,
            (location_name,),
        )
        if not rows:
            return ""
        return random.choice(rows)["item_id"]

    def _roll_ring_drop(self) -> str:
        """随机掉落纳戒物品。

        恢复类、宝石和技能书都属于装备库，所以探险获得时直接进纳戒。
        """

        rows = self.db.fetch_all(
            """
            SELECT equipment_item_id, category
            FROM equipment_item_defs
            WHERE category IN ('恢复类', '宝石', '技能书')
            """
        )
        if not rows:
            return ""

        groups = {
            "恢复类": [row for row in rows if row["category"] == "恢复类"],
            "宝石": [row for row in rows if row["category"] == "宝石"],
            "技能书": [row for row in rows if row["category"] == "技能书"],
        }
        roll = random.random()
        if roll < 0.62 and groups["恢复类"]:
            return random.choice(groups["恢复类"])["equipment_item_id"]
        if roll < 0.86 and groups["宝石"]:
            return random.choice(groups["宝石"])["equipment_item_id"]
        if groups["技能书"]:
            return random.choice(groups["技能书"])["equipment_item_id"]
        return random.choice(rows)["equipment_item_id"]

    def _medicine_stock(self, client_id: str) -> dict[str, dict]:
        """读取可自动消耗的恢复药。

        只读取能恢复血气或精神的恢复类物品。
        福袋虽然也在恢复类里，但它只给源石，不会被自动使用。
        """

        rows = self.db.fetch_all(
            """
            SELECT r.equipment_item_id, r.quantity, e.name, e.effect
            FROM ring_items r
            JOIN equipment_item_defs e ON e.equipment_item_id = r.equipment_item_id
            WHERE r.client_id = ?
              AND r.quantity > 0
              AND e.category = '恢复类'
              AND e.usable = 1
            """,
            (client_id,),
        )
        stock: dict[str, dict] = {}
        for row in rows:
            effect = load_json(row["effect"], {})
            has_recovery = any(effect.get(key) for key in ("hp_delta", "hp_ratio", "mp_delta", "mp_ratio"))
            if not has_recovery:
                continue
            stock[row["equipment_item_id"]] = {
                "name": row["name"],
                "quantity": int(row["quantity"]),
                "effect": effect,
            }
        return stock

    def _auto_use_medicine(
        self,
        hp: int,
        mp: int,
        player: dict,
        stock: dict[str, dict],
        used: dict[str, int],
    ) -> tuple[int, int]:
        """按阈值自动使用恢复药。

        血气低于 45% 时补到约 75%。
        精神低于 30% 时补到约 65%。
        只修改本次探险预计算里的临时血气和精神，真正扣药在开始探险时统一扣。
        """

        if not stock:
            return hp, mp

        max_hp = int(player["max_hp"])
        max_mp = int(player["max_mp"])
        if hp > 0 and hp <= int(max_hp * 0.45):
            hp = self._recover_value(hp, max_hp, "hp", stock, used, int(max_hp * 0.75))
        if mp <= int(max_mp * 0.30):
            mp = self._recover_value(mp, max_mp, "mp", stock, used, int(max_mp * 0.65))
        return hp, mp

    def _recover_value(
        self,
        value: int,
        max_value: int,
        kind: str,
        stock: dict[str, dict],
        used: dict[str, int],
        target: int,
    ) -> int:
        """用最合适的恢复药把某个数值补到目标线。"""

        if value >= target:
            return min(max_value, value)

        while value < target:
            options = []
            for item_id, item in stock.items():
                if item["quantity"] <= 0:
                    continue
                effect = item["effect"]
                amount = int(effect.get(f"{kind}_delta") or 0)
                amount += int(max_value * float(effect.get(f"{kind}_ratio") or 0))
                if amount > 0:
                    options.append((amount, item_id))
            if not options:
                break

            need = target - value
            enough = [option for option in options if option[0] >= need]
            amount, item_id = min(enough or options)
            if not enough:
                amount, item_id = max(options)
            stock[item_id]["quantity"] -= 1
            used[item_id] = used.get(item_id, 0) + 1
            value = min(max_value, value + amount)
        return value

    def _format_medicine_used(self, medicine_used: dict[str, int]) -> str:
        """把自动消耗的恢复药整理成玩家可读文本。"""

        texts = []
        for item_id, quantity in medicine_used.items():
            item = self.equipment_item_def(item_id)
            texts.append(f"{item['name'] if item else item_id} x{quantity}")
        return "、".join(texts)

    @staticmethod
    def _time(value: str):
        """转换时间。"""

        from ..common import dt

        return dt(value) or now()


service = ExplorationService(db)

__all__ = ["ExplorationService", "service"]
