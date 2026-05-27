"""探险组件服务。"""

from __future__ import annotations

from datetime import timedelta

from .. import combat_log_text
from ..combat_core import service as combat_service
from ..common import CoreService, dump_json, load_json, now, random, ts
from ..constants import ENCOUNTER_SECONDS, EXPLORE_MINUTES
from ..format_text import T
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
        panel = T.panel()
        panel.section("探险地点")
        for row in rows:
            panel.line(
                f"{row['name']}｜推荐 **{row['recommended_level']}** 级｜"
                f"怪物 {row['min_level']}-{row['max_level']} 级｜{row['desc']}"
            )
        return panel.render()

    def current_location(self, client_id: str) -> str:
        """查看当前位置。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        panel = T.panel()
        panel.section("当前位置")
        panel.line(f"{player['location_name']} ({player['x']},{player['y']})")
        return (
            panel.render()
            + "<去 天枢城><去 青岚坊><去 赤霞港><去 玄铁岭><去 万药谷><去 云梦泽><去 流沙海市>"
            "<去 寒霜关><去 雷泽城><去 碧潮岛><去 星陨墟>"
        )

    def start(self, client_id: str, location_name: str = "") -> str:
        """开始探险。

        不带地点时使用玩家当前位置；带地点时先切到该探险地点再开始。
        移动没有时间成本，所以这里直接更新位置，避免用户还要先发一次导航。
        """

        player, error = self.require_player(client_id)
        if error:
            return error
        self.cleanup_battle_records()
        assert player is not None
        active = self._active_record(client_id)
        if active:
            return T.hint("你已经在探险中或有待领取结果。", "发送：探险状态 查看进度；30 分钟后发送：结束探险<探险状态><结束探险>")
        if player["status"] != "空闲":
            return T.hint(f"当前状态为 {player['status']}，不能开始探险。", "先处理当前状态")
        if player["hp"] <= 0:
            return T.hint("血气不足，不能开始探险。", "发送：休息，时间到后发送：结束休息")
        target_name = location_name.strip() or player["location_name"]
        location = self._exploration_location(target_name)
        if not location:
            if location_name.strip():
                return T.hint(f"没有找到探险地点：{target_name}。", "发送：探险列表 查看可探险地点。<探险列表>")
            return T.hint("当前位置不是探险地点。", "发送：探险列表 查看可探险地点，或发送：探险 地点名<探险列表>")

        weapon_service.ensure_starter_weapon(client_id)
        explore_player = dict(player)
        explore_player["location_name"] = location["name"]
        explore_player["x"] = location["x"]
        explore_player["y"] = location["y"]
        result = self._precompute(client_id, explore_player)
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
                return T.hint("你已经在探险中或有待领取结果。", "发送：探险状态 查看进度；30 分钟后发送：结束探险<探险状态><结束探险>")
            for item_id, quantity in result.get("medicine_used", {}).items():
                row = conn.execute(
                    "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
                    (client_id, item_id),
                ).fetchone()
                if not row or int(row["quantity"]) < int(quantity):
                    return T.hint("自动用药库存已变化，无法开始探险。", "发送：纳戒 确认恢复药数量后，再发送：探险<纳戒>")
            cursor = conn.execute(
                """
                UPDATE players
                SET status = '探险中', location_name = ?, x = ?, y = ?
                WHERE client_id = ? AND status = '空闲'
                """,
                (location["name"], location["x"], location["y"], client_id),
            )
            if cursor.rowcount <= 0:
                return T.hint("当前状态已变化，不能开始探险。", "发送：修仙信息 查看当前状态后再操作。<修仙信息>")
            for item_id, quantity in result.get("medicine_used", {}).items():
                self.remove_ring_conn(conn, client_id, item_id, int(quantity))
            conn.execute(
                """
                INSERT INTO exploration_records
                (client_id, location_name, status, started_at, ready_at, result)
                VALUES (?, ?, '探险中', ?, ?, ?)
                """,
                (client_id, location["name"], ts(started), ts(ready), dump_json(result)),
            )
        auto_state = "开启" if player["auto_use_medicine"] else "关闭"
        return f"开始探险：{location['name']}。自动用药：{auto_state}。30 分钟后可结算。<探险状态>"

    def status(self, client_id: str) -> str:
        """查看探险状态。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        record = self._active_record(client_id)
        if not record:
            return T.hint("当前没有探险。", "发送：探险列表 选地点，再发送：探险<探险列表>")
        result = load_json(record["result"], {})
        events = list(result.get("events", []))
        current = now()
        elapsed = max(0, int((current - self._time(record["started_at"])).total_seconds()))
        total = EXPLORE_MINUTES * 60
        done = min(total, elapsed)
        if result.get("dead"):
            state = "已重伤，预计算已停止"
            reason = "本体战斗失败，后续不再继续遇怪。"
        elif result.get("bag_full"):
            state = "背包已满，预计算已停止"
            reason = "下一件背包掉落已经装不下，后续不再继续遇怪。"
        elif elapsed >= total:
            state = "已到点，待领取"
            reason = "30 分钟已到，可以领取本次探险结果。"
        else:
            state = "探险中"
            reason = "预计算已经完成，但本体仍需等 30 分钟冷却到点。"
        ready_at = self._time(record["ready_at"])
        can_claim = not (ready_at and current < ready_at)
        if can_claim:
            action = "现在可以发送：结束探险"
            time_text = "可领取"
        else:
            left = max(1, int((ready_at - current).total_seconds() // 60) + 1)
            action = f"{left} 分钟后发送：结束探险"
            time_text = f"还需约 {left} 分钟"

        display_player = self._result_display_player(result, player)
        summary = self._status_summary(display_player, result, events)
        panel = T.panel()
        panel.section(f"探险状态·{record['location_name']}")
        panel.line(f"状态：{state}")
        panel.line(f"时间：已过 **{done // 60}/{EXPLORE_MINUTES}** 分钟｜{time_text}")
        panel.line(f"原因：{reason}")
        panel.line(f"战斗：{summary['fight_text']}")
        panel.line(f"预计经验：**+{summary['exp_total']}**")
        panel.line(f"最后状态：血气 **{summary['hp_left']}/{display_player['max_hp']}**｜精神 **{summary['mp_left']}/{display_player['max_mp']}**")
        if summary["drop_text"]:
            panel.line(f"预计收获：{summary['drop_text']}")
        else:
            panel.line("预计收获：暂无掉落")
        if summary["medicine_text"]:
            panel.line(f"自动用药：{summary['medicine_text']}")
        return T.attach(panel.render(), f"{action}<结束探险>")

    def claim(self, client_id: str) -> str | dict:
        """领取探险结果。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        record = self._active_record(client_id)
        if not record:
            return T.hint("当前没有可领取探险。", "发送：探险 开始一轮，或发送：探险记录 查看历史。<探险>")
        ready_at = self._time(record["ready_at"])
        if ready_at and now() < ready_at:
            left = max(1, int((ready_at - now()).total_seconds() // 60) + 1)
            return T.hint(f"探险还没有到 30 分钟冷却，{left} 分钟后才能结束探险。", "先发送：探险状态 查看预计算结果。<探险状态>")
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
                mp_left = 0
                event["mp_left"] = 0
                break

        with self.db.transaction() as conn:
            active = conn.execute(
                "SELECT * FROM exploration_records WHERE record_id = ? AND claimed = 0",
                (record["record_id"],),
            ).fetchone()
            if not active:
                return T.hint("当前没有可领取探险。", "发送：探险 开始一轮，或发送：探险记录 查看历史。<探险>")
            for item_id, quantity in drops.items():
                ok, reason = self.can_add_backpack_conn(conn, client_id, item_id, quantity)
                if not ok:
                    return T.hint("背包空间不足，无法领取探险结果。", f"{reason}<特殊自动出售>")
            old_level, new_level = self.add_exp_conn(conn, client_id, exp_total)
            for item_id, quantity in drops.items():
                self.add_backpack_conn(conn, client_id, item_id, quantity)
            for item_id, quantity in ring_drops.items():
                self.add_ring_conn(conn, client_id, item_id, quantity)
            for event in events:
                self.record_weapon_combat_conn(
                    conn,
                    client_id,
                    int(event.get("weapon_id", 0)),
                    monster_kill=bool(event.get("win")),
                    damage=int(event.get("highest_damage", 0)),
                )
            for drop in self._weapon_drops_from_result(result):
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
                (max(1, hp_left), 0 if hp_left <= 0 else max(0, mp_left), client_id),
            )
            conn.execute(
                """
                UPDATE exploration_records
                SET status = '已领取', finished_at = ?, claimed = 1
                WHERE record_id = ?
                """,
                (ts(), record["record_id"]),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '领取探险', ?, ?)",
                (
                    client_id,
                    (
                        f"record_id={record['record_id']}, location={record['location_name']}, "
                        f"exp={exp_total}, level={old_level}->{new_level}, "
                        f"items={sum(drops.values()) + sum(ring_drops.values())}, "
                        f"weapons={len(weapon_drops)}, dead={int(dead)}"
                    ),
                    ts(),
                ),
            )

        final_player = self.player(client_id) or player
        log_player = self._result_display_player(result, final_player)
        return self._claim_log_block(
            record=record,
            player=log_player,
            events=events,
            exp_total=exp_total,
            old_level=old_level,
            new_level=new_level,
            drops=drops,
            ring_drops=ring_drops,
            weapon_drops=weapon_drops,
            medicine_used=result.get("medicine_used", {}),
            dead=dead,
            bag_full=bool(result.get("bag_full")),
        )

    def records(self, client_id: str) -> str:
        """查看最近探险记录。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        self.cleanup_battle_records()
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
            return T.hint("暂无探险记录。", "发送：探险 开始第一次探险。<探险>")
        panel = T.panel()
        panel.section("探险记录")
        for row in rows:
            panel.line(f"#{row['record_id']}｜{row['location_name']}｜{row['status']}｜{row['started_at']}")
        return panel.render()

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
        medicine_stock = self._medicine_stock(client_id) if player["auto_use_medicine"] else {}
        medicine_used: dict[str, int] = {}
        for _event_index in range(fight_count):
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
                return self._precompute_result(
                    player,
                    events,
                    medicine_used,
                    explore_bonus,
                    dead=True,
                    bag_full=False,
                    client_id=client_id,
                )
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
                    return self._precompute_result(
                        player,
                        events,
                        medicine_used,
                        explore_bonus,
                        dead=False,
                        bag_full=True,
                        client_id=client_id,
                    )
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
                        return self._precompute_result(
                            player,
                            events,
                            medicine_used,
                            explore_bonus,
                            dead=False,
                            bag_full=True,
                            client_id=client_id,
                        )
                    event["location_drop_item_id"] = location_drop
            if random.random() < 0.16 + explore_bonus * 0.3:
                event["ring_drop_id"] = self._roll_ring_drop()
            events.append(event)
        return self._precompute_result(
            player,
            events,
            medicine_used,
            explore_bonus,
            dead=False,
            bag_full=False,
            client_id=client_id,
        )

    def _precompute_result(
        self,
        player: dict,
        events: list[dict],
        medicine_used: dict[str, int],
        explore_bonus: float,
        *,
        dead: bool,
        bag_full: bool,
        client_id: str = "",
    ) -> dict:
        """整理预计算结果，并按整轮探险判定武器掉落。

        武器不再提前绑定到某一场战斗，避免玩家在随机武器场次之前死亡时
        把整轮武器机会吞掉。只要本轮至少胜利过，就按整轮概率抽一次。
        """

        result = {
            "dead": dead,
            "bag_full": bag_full,
            "medicine_used": medicine_used,
            "events": events,
            "player_snapshot": self._player_snapshot(player),
        }
        if client_id:
            result["combat_snapshot"] = self._combat_snapshot(client_id, player)
        if any(event.get("win") for event in events) and random.random() < self._weapon_drop_chance(explore_bonus):
            result["weapon_drop"] = weapon_service.roll_weapon_drop(player["level"], player["location_name"])
        return result

    @staticmethod
    def _player_snapshot(player: dict) -> dict:
        """保存本轮探险开始时会影响展示的玩家状态。"""

        fields = (
            "client_id",
            "display_name",
            "level",
            "exp",
            "hp",
            "mp",
            "max_hp",
            "max_mp",
            "base_attack",
            "defense",
            "source_stones",
            "status",
            "location_name",
            "x",
            "y",
            "auto_use_medicine",
            "battle_log_detail",
        )
        return {key: player[key] for key in fields if key in player}

    def _combat_snapshot(self, client_id: str, player: dict) -> dict:
        """保存探险开始时用于玩家对战的完整战斗快照。"""

        weapon = weapon_service.equipped_weapon(client_id)
        skill = weapon_service.skill(weapon["skill_id"]) if weapon else None
        equipment_effects = self.equipment_bonuses(client_id)
        weapon_effects = self._weapon_effects(weapon)
        return {
            "player": self._player_snapshot(player),
            "weapon": dict(weapon) if weapon else {},
            "skill": dict(skill) if skill else {},
            "skill_label": weapon_service.weapon_skill_label(int(weapon["weapon_id"]), skill) if weapon and skill else "",
            "equipment_effects": equipment_effects,
            "weapon_effects": weapon_effects,
            "effects": self._merge_effects(equipment_effects, weapon_effects),
        }

    @staticmethod
    def _result_display_player(result: dict, player: dict) -> dict:
        """用开始快照修正探险展示用状态，避免领取时面板变化影响日志。"""

        snapshot = result.get("player_snapshot")
        if not isinstance(snapshot, dict):
            return player

        display_player = dict(player)
        for key in ("level", "max_hp", "max_mp", "location_name", "x", "y", "auto_use_medicine"):
            if key in snapshot:
                display_player[key] = snapshot[key]
        return display_player

    @staticmethod
    def _weapon_drop_chance(explore_bonus: float) -> float:
        """整轮探险武器掉落概率。"""

        return max(0.0, min(0.55, 0.35 + explore_bonus))

    def _monster_level_range(self, player: dict) -> tuple[int, int]:
        """按当前探险地点决定怪物等级段。"""

        location = self.db.fetch_one(
            "SELECT min_level, max_level FROM exploration_locations WHERE name = ?",
            (player["location_name"],),
        )
        if location:
            return max(1, int(location["min_level"])), max(1, int(location["max_level"]))
        return max(1, player["level"] - 5), max(5, player["level"] + 8)

    def _exploration_location(self, name: str) -> dict | None:
        """读取探险地点，并补上导航坐标。"""

        location = self.db.fetch_one(
            "SELECT * FROM exploration_locations WHERE name = ?",
            (name.strip(),),
        )
        if not location:
            return None
        coord = self.db.fetch_one(
            "SELECT x, y FROM trade_locations WHERE name = ?",
            (location["name"],),
        )
        location["x"] = int(coord["x"]) if coord else 0
        location["y"] = int(coord["y"]) if coord else 0
        return location

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

        恢复类、宝石和技能书都进纳戒，所以探险获得时直接写入纳戒。
        """

        rows = self.db.fetch_all("""
            SELECT equipment_item_id, category
            FROM equipment_item_defs
            WHERE category IN ('恢复类', '宝石', '技能书')
            """)
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

    def _claim_log_block(
        self,
        *,
        record: dict,
        player: dict,
        events: list[dict],
        exp_total: int,
        old_level: int,
        new_level: int,
        drops: dict[str, int],
        ring_drops: dict[str, int],
        weapon_drops: list[str],
        medicine_used: dict[str, int],
        dead: bool,
        bag_full: bool,
    ) -> str | dict:
        """把结束探险的战斗过程和最终结算整理成代码块文本。"""

        if not combat_log_text.wants_detail(player):
            return combat_log_text.exploration_brief(
                record=record,
                player=player,
                events=events,
                exp_total=exp_total,
                old_level=old_level,
                new_level=new_level,
                drops_text=self._format_backpack_awards(drops),
                ring_drops_text=self._format_ring_awards(ring_drops),
                weapon_drops_text=self._format_weapon_awards(weapon_drops),
                medicine_text=self._format_medicine_used(medicine_used) if medicine_used else "无",
                stop_reason=self._stop_reason(dead, bag_full),
                event_drop_text=self._event_drop_text,
            )

        wins = sum(1 for event in events if event.get("win"))
        losses = max(0, len(events) - wins)
        hp_left = int(player.get("hp", 1))
        mp_left = int(player.get("mp", 0))
        lines = [
            "探险结束",
            f"记录：#{record['record_id']}",
            f"地点：{record['location_name']}",
            f"开始时间：{record['started_at']}",
            f"可领取时间：{record['ready_at']}",
            f"领取时间：{ts()}",
            "",
            f"战斗总览：{len(events)} 场，胜 {wins} 场，败 {losses} 场。",
            "",
            "一、战斗明细",
        ]

        if events:
            for index, event in enumerate(events, start=1):
                lines.extend(self._event_log_lines(index, event, player))
        else:
            lines.append("本次没有战斗事件。")

        lines.extend(
            [
                "",
                "二、最终结算",
                f"经验：+{exp_total}",
                f"等级：{old_level} -> {new_level}" if new_level > old_level else f"等级：{new_level}，未升级",
                f"最终血气：{hp_left}/{player['max_hp']}",
                f"最终精神：{mp_left}/{player['max_mp']}",
                f"背包获得：{self._format_backpack_awards(drops)}",
                f"纳戒获得：{self._format_ring_awards(ring_drops)}",
                f"武器获得：{self._format_weapon_awards(weapon_drops)}",
                f"自动用药：{self._format_medicine_used(medicine_used) if medicine_used else '无'}",
                f"停止原因：{self._stop_reason(dead, bag_full)}",
                "当前状态：空闲",
            ]
        )
        return "```javascript\r\n" + "\r\n".join(lines) + "\r\n```"

    def _event_log_lines(self, index: int, event: dict, player: dict) -> list[str]:
        """整理单场战斗日志，细到每一次出手。"""

        hp_left = max(0, int(event.get("hp_left", 0)))
        mp_left = max(0, int(event.get("mp_left", 0)))
        lines = [
            f"第 {index} 战",
            f"  概况：{event.get('summary', '无战斗摘要')}",
        ]
        actions = event.get("actions")
        if isinstance(actions, list) and actions:
            for action in actions:
                lines.extend(self._action_log_lines(action, event, player))
        else:
            lines.append("  逐次出手：无记录")
        lines.append(f"  战后：血气 {hp_left}/{player['max_hp']}，精神 {mp_left}/{player['max_mp']}")
        lines.append(f"  掉落：{self._event_drop_text(event)}")
        if event.get("bag_full"):
            lines.append("  动作：背包已满，本场后停止后续预计算。")
        if hp_left <= 0:
            lines.append("  动作：本体重伤，本场后停止后续预计算。")
        return lines

    def _action_log_lines(self, action: dict, event: dict, player: dict) -> list[str]:
        """整理一次行动条出手日志。"""

        round_no = int(action.get("round", 0))
        monster_name = str(event.get("monster") or "怪物")
        monster_hp_left = max(0, int(action.get("monster_hp_left", 0)))
        monster_hp_max = max(1, int(action.get("monster_hp_max", 1)))
        lines = [f"  第 {round_no} 次行动"]
        if action.get("actor") == "player":
            total_damage = int(action.get("player_total_damage", action.get("damage", 0)))
            combo_damage = int(action.get("combo_damage", 0))
            skill_name = str(action.get("skill_name") or "")
            if action.get("skill_used"):
                attack_text = f"技能「{skill_name}」"
                cost_text = f"，消耗精神 {int(action.get('mp_cost', 0))}"
            else:
                attack_text = "普通攻击"
                cost_text = ""
            combo_text = f"，连击追加 {combo_damage}" if combo_damage > 0 else ""
            life_steal = int(action.get("life_steal", 0))
            steal_text = f"，吸血 +{life_steal}" if life_steal > 0 else ""
            effect = combat_service.action_effect_text(action)
            effect_text = f"，{effect}" if effect else ""
            lines.append(
                f"    我方出手：{attack_text}，造成 {total_damage} 伤害"
                f"{combo_text}{steal_text}{effect_text}{cost_text}；"
                f"{monster_name} 血气 {monster_hp_left}/{monster_hp_max}"
            )
            if monster_hp_left <= 0:
                lines.append(f"    敌方出手：{monster_name} 已倒下，未能出手。")
            return lines

        player_hp_left = max(0, int(action.get("player_hp_left", 0)))
        player_mp_left = max(0, int(action.get("player_mp_left", 0)))
        if action.get("dodged"):
            lines.append(f"    敌方出手：{monster_name} 攻击落空；" f"我方血气 {player_hp_left}/{player['max_hp']}，精神 {player_mp_left}/{player['max_mp']}")
            return lines

        hurt = int(action.get("monster_damage", 0))
        skill_name = str(action.get("monster_skill_name") or "")
        attack_text = f"技能「{skill_name}」" if action.get("monster_skill_used") else "普通攻击"
        effect = combat_service.action_effect_text(action)
        effect_text = f"，{effect}" if effect else ""
        lines.append(
            f"    敌方出手：{attack_text}，造成 {hurt} 伤害{effect_text}；" f"我方血气 {player_hp_left}/{player['max_hp']}，精神 {player_mp_left}/{player['max_mp']}"
        )
        return lines

    def _event_drop_text(self, event: dict) -> str:
        """整理单场战斗掉落。"""

        texts = []
        if event.get("drop_item_id"):
            texts.append("怪物掉落 " + self._item_name(event["drop_item_id"]))
        if event.get("location_drop_item_id"):
            texts.append("地点特产 " + self._item_name(event["location_drop_item_id"]))
        if event.get("ring_drop_id"):
            texts.append("纳戒物品 " + self._ring_item_name(event["ring_drop_id"]))
        if event.get("weapon_drop"):
            drop = event["weapon_drop"]
            texts.append(f"武器预掉落 {drop['name']}[{drop['quality']}] 上限{drop['max_level']}")
        return "、".join(texts) if texts else "无"

    @staticmethod
    def _weapon_drops_from_result(result: dict) -> list[dict]:
        """读取本轮武器掉落。

        武器按整轮探险奖励结算，只读取 result["weapon_drop"]。
        """

        drops = []
        result_drop = result.get("weapon_drop")
        if result_drop:
            drops.append(result_drop)
        return drops

    def _format_backpack_awards(self, drops: dict[str, int]) -> str:
        """整理背包最终获得。"""

        if not drops:
            return "无"
        return "、".join(f"{self._item_name(item_id)} x{quantity}" for item_id, quantity in drops.items())

    def _format_ring_awards(self, drops: dict[str, int]) -> str:
        """整理纳戒最终获得。"""

        if not drops:
            return "无"
        return "、".join(f"{self._ring_item_name(item_id)} x{quantity}" for item_id, quantity in drops.items())

    @staticmethod
    def _format_weapon_awards(weapon_drops: list[str]) -> str:
        """整理武器最终获得。"""

        return "、".join(weapon_drops) if weapon_drops else "无"

    @staticmethod
    def _stop_reason(dead: bool, bag_full: bool) -> str:
        """整理本次预计算停止原因。"""

        if dead:
            return "本体重伤，已自动撤离"
        if bag_full:
            return "背包已满，提前停止"
        return "30 分钟到点"

    def _item_name(self, item_id: str) -> str:
        """读取背包物品名称。"""

        item = self.item_def(item_id)
        return item["name"] if item else item_id

    def _ring_item_name(self, item_id: str) -> str:
        """读取纳戒物品名称。"""

        item = self.equipment_item_def(item_id)
        return item["name"] if item else item_id

    def _status_summary(self, player: dict, result: dict, events: list[dict]) -> dict:
        """整理探险状态摘要。

        探险在开始时已经预计算完整结果；状态页只展示摘要，
        真正发放经验、物品和武器仍然必须等 `结束探险`。
        """

        wins = sum(1 for event in events if event.get("win"))
        losses = max(0, len(events) - wins)
        exp_total = sum(int(event.get("exp", 0)) for event in events)
        hp_left = int(events[-1].get("hp_left", player["hp"])) if events else int(player["hp"])
        mp_left = int(events[-1].get("mp_left", player["mp"])) if events else int(player["mp"])
        fight_text = f"{len(events)} 场，胜 {wins}，败 {losses}"

        backpack_drops: dict[str, int] = {}
        ring_drops: dict[str, int] = {}
        weapon_drops: list[str] = []
        for event in events:
            for key in ("drop_item_id", "location_drop_item_id"):
                item_id = event.get(key)
                if item_id:
                    backpack_drops[item_id] = backpack_drops.get(item_id, 0) + 1
            ring_id = event.get("ring_drop_id")
            if ring_id:
                ring_drops[ring_id] = ring_drops.get(ring_id, 0) + 1
        for weapon_drop in self._weapon_drops_from_result(result):
            weapon_drops.append(f"{weapon_drop['name']}[{weapon_drop['quality']}]上限{weapon_drop['max_level']}")

        drop_parts = []
        if backpack_drops:
            drop_parts.append("背包 " + self._format_drop_preview(backpack_drops, ring=False))
        if ring_drops:
            drop_parts.append("纳戒 " + self._format_drop_preview(ring_drops, ring=True))
        if weapon_drops:
            drop_parts.append("武器 " + self._limit_texts(weapon_drops))

        medicine_used = result.get("medicine_used", {})
        return {
            "fight_text": fight_text,
            "exp_total": exp_total,
            "hp_left": max(0, hp_left),
            "mp_left": max(0, mp_left),
            "drop_text": "；".join(drop_parts),
            "medicine_text": self._format_medicine_used(medicine_used) if medicine_used else "",
        }

    def _format_drop_preview(self, drops: dict[str, int], ring: bool) -> str:
        """把掉落预览转成短文本。"""

        texts = []
        for item_id, quantity in drops.items():
            item = self.equipment_item_def(item_id) if ring else self.item_def(item_id)
            texts.append(f"{item['name'] if item else item_id} x{quantity}")
        return self._limit_texts(texts)

    @staticmethod
    def _limit_texts(texts: list[str], limit: int = 5) -> str:
        """限制状态页单行长度，避免掉落太多时刷屏。"""

        if len(texts) <= limit:
            return "、".join(texts)
        return "、".join(texts[:limit]) + f" 等{len(texts)}种"

    @staticmethod
    def _time(value: str):
        """转换时间。"""

        from ..common import dt

        return dt(value) or now()


service = ExplorationService(db)

__all__ = ["ExplorationService", "service"]
