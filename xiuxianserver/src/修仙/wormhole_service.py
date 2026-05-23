"""异界虫洞组件服务。

虫洞是跑商过程中偶发的全服动态 Boss。
商场只负责“可能发现虫洞”，挑战、排行、奖励都由本组件自己处理。
"""

from __future__ import annotations

import random
from datetime import timedelta
from statistics import median
from typing import Any

from .common import CoreService, business_day, dt, dump_json, hint, load_json, money, now, ts
from .constants import (
    MAX_LEVEL,
    WORMHOLE_ACTIVE_WINDOW_DAYS,
    WORMHOLE_CHALLENGE_COOLDOWN_MINUTES,
    WORMHOLE_DAILY_ACTIVE_PLAYER_STEP,
    WORMHOLE_DAILY_BASE_LIMIT,
    WORMHOLE_DAILY_MIN_LIMIT,
    WORMHOLE_DAILY_MAX_LIMIT,
    WORMHOLE_DURATION_MINUTES,
    WORMHOLE_NOTICE_COOLDOWN_MINUTES,
)
from .rules import damage_after_defense, monster_exp
from .sql import db
from .weapon_core import service as weapon_service


BOSS_POOL = (
    ("裂天游魂", "游魂", 0.95),
    ("玄砂魔将", "魔将", 1.05),
    ("赤潮妖君", "妖君", 1.08),
    ("黑水龙影", "龙影", 1.15),
    ("星骸古卫", "古卫", 1.2),
)


DISCOVERY_CHANCES = {
    "navigate": 0.012,
    "trade_buy": 0.018,
    "trade_sell": 0.02,
    "trade_auto_sell": 0.03,
    "special_sell": 0.025,
    "special_auto_sell": 0.035,
}


class WormholeService(CoreService):
    """异界虫洞的开启、挑战、排行和奖励。"""

    def status(self, client_id: str) -> str:
        """查看当前异界虫洞。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        event = self._active_event()
        if not event:
            pending = self._latest_rewardable(client_id)
            if pending:
                return hint("当前没有开启的异界虫洞，但你有虫洞奖励待领取。", "发送：虫洞奖励")
            snapshot = self._world_snapshot()
            opened_today = self._today_opened_count()
            daily_limit = self._daily_event_limit(snapshot["active_count"])
            if opened_today >= daily_limit:
                return hint(
                    f"今日异界虫洞次数已满：{opened_today}/{daily_limit}。",
                    "明日 04:00 后会重新计算；活跃人数越多，每日虫洞上限越高。",
                )
            return hint(
                f"当前没有开启的异界虫洞，今日已出现 {opened_today}/{daily_limit}。",
                "跑商、导航或特殊出售时有概率发现虫洞。",
            )
        return self._format_status(event)

    def challenge(self, client_id: str) -> str:
        """挑战当前虫洞 Boss。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        self.cleanup_battle_records()
        assert player is not None

        event = self._active_event()
        if not event:
            return hint("当前没有开启的异界虫洞。", "跑商、导航或特殊出售时有概率发现虫洞。")
        if event["status"] != "开启":
            return hint(f"{event['boss_name']} 已经{event['status']}，不能继续挑战。", "发送：虫洞奖励 查看是否可以领取奖励。")
        if player["status"] != "空闲":
            return self._busy_challenge_hint(player["status"])
        if player["location_name"] != event["location_name"]:
            return hint(
                f"虫洞位于 {event['location_name']}，你当前在 {player['location_name']}。",
                f"发送：导航 {event['location_name']}，到达后发送：挑战虫洞",
            )
        if int(player["hp"]) <= 0:
            return hint("血气不足，无法挑战虫洞。", "发送：休息，时间到后发送：结束休息")

        check = self._challenge_check(event["wormhole_id"], client_id)
        if check:
            return check

        result = self._fight_boss(player, event)
        killed = False
        with self.db.transaction() as conn:
            fresh = conn.execute(
                "SELECT * FROM wormholes WHERE wormhole_id = ? AND status = '开启'",
                (event["wormhole_id"],),
            ).fetchone()
            if not fresh:
                return hint("异界虫洞已经关闭。", "发送：虫洞奖励 查看是否可以领取奖励。")

            current = conn.execute(
                """
                SELECT last_challenge_at
                FROM wormhole_participants
                WHERE wormhole_id = ? AND client_id = ?
                """,
                (event["wormhole_id"], client_id),
            ).fetchone()
            if current:
                last = dt(current["last_challenge_at"])
                left = timedelta(minutes=WORMHOLE_CHALLENGE_COOLDOWN_MINUTES) - (now() - last) if last else timedelta()
                if left > timedelta():
                    seconds = max(1, int(left.total_seconds()))
                    return hint(f"挑战虫洞冷却中，还需 {seconds // 60}分{seconds % 60}秒。", "稍后再发送：挑战虫洞")

            damage = min(max(1, int(result["damage"])), int(fresh["hp"]))
            left_hp = max(0, int(fresh["hp"]) - damage)
            killed = left_hp <= 0
            conn.execute(
                "UPDATE players SET hp = ?, mp = ? WHERE client_id = ?",
                (result["hp_left"], result["mp_left"], client_id),
            )
            conn.execute(
                """
                INSERT INTO wormhole_participants
                (wormhole_id, client_id, damage, challenge_count, last_challenge_at, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(wormhole_id, client_id)
                DO UPDATE SET
                    damage = damage + excluded.damage,
                    challenge_count = challenge_count + 1,
                    last_challenge_at = excluded.last_challenge_at,
                    updated_at = excluded.updated_at
                """,
                (event["wormhole_id"], client_id, damage, ts(), ts(), ts()),
            )
            if killed:
                conn.execute(
                    """
                    UPDATE wormholes
                    SET hp = 0, status = '已击杀', killed_at = ?, result = ?
                    WHERE wormhole_id = ?
                    """,
                    (ts(), dump_json({"killer": client_id}), event["wormhole_id"]),
                )
            else:
                conn.execute(
                    "UPDATE wormholes SET hp = ? WHERE wormhole_id = ?",
                    (left_hp, event["wormhole_id"]),
                )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '挑战虫洞', ?, ?)",
                (client_id, f"wormhole={event['wormhole_id']}, damage={damage}", ts()),
            )

        return self._challenge_log_block(
            title=f"挑战虫洞：{event['boss_name']}",
            boss_name=event["boss_name"],
            player=player,
            result=result,
            damage=damage,
            left_hp=left_hp,
            max_hp=int(event["max_hp"]),
            killed=killed,
            killed_text="Boss 已被击杀，发送：虫洞奖励",
            alive_text=f"再次挑战需等待 {WORMHOLE_CHALLENGE_COOLDOWN_MINUTES} 分钟。",
            hurt_text="你被虫洞反震重伤，建议先休息。",
        )

    def ranking(self, client_id: str) -> str:
        """查看当前或最近虫洞排行。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        event = self._active_event() or self._latest_event()
        if not event:
            return hint("暂无异界虫洞记录。", "跑商、导航或特殊出售时有概率发现虫洞。")
        rows = self._participants(event["wormhole_id"])
        if not rows:
            return hint(f"{event['boss_name']} 暂无挑战记录。", "发送：挑战虫洞 参与本次虫洞。")
        lines = [f"☆异界虫洞排行·{event['boss_name']}☆"]
        for index, row in enumerate(rows[:10], start=1):
            lines.append(
                f"{index}. {self.format_player_name(row['client_id'])} "
                f"伤害{row['damage']} 贡献{self._contribution(row['damage'], event):.1%} "
                f"挑战{row['challenge_count']}次"
            )
        return "\n".join(lines)

    def reward(self, client_id: str) -> str:
        """领取最近一次可领取的虫洞奖励。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        self._close_expired_events()
        event = self._latest_rewardable(client_id)
        if not event:
            active = self._active_event()
            if active:
                return hint("当前异界虫洞还没有结束。", "继续挑战，或等 Boss 被击杀/虫洞退去后再发送：虫洞奖励")
            return hint("没有可领取的虫洞奖励。", "发送：虫洞 查看当前是否有异界虫洞。")

        participant = self.db.fetch_one(
            "SELECT * FROM wormhole_participants WHERE wormhole_id = ? AND client_id = ?",
            (event["wormhole_id"], client_id),
        )
        if not participant:
            return hint("你没有参与这次虫洞。", "下一次发现虫洞后发送：挑战虫洞")
        if int(participant["reward_claimed"]):
            return participant["reward_text"] or "虫洞奖励已经领取。"

        reward = self._roll_reward(event, participant, player)
        with self.db.transaction() as conn:
            fresh = conn.execute(
                "SELECT reward_claimed FROM wormhole_participants WHERE wormhole_id = ? AND client_id = ?",
                (event["wormhole_id"], client_id),
            ).fetchone()
            if not fresh or int(fresh["reward_claimed"]):
                return "虫洞奖励已经领取。"

            old_level, new_level = self.add_exp_conn(conn, client_id, reward["exp"])
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (reward["stones"], client_id),
            )
            for item_id, quantity in reward["ring_items"]:
                self.add_ring_conn(conn, client_id, item_id, quantity)
            for gem_id, level, quantity in reward["gems"]:
                self.add_gem_conn(conn, client_id, gem_id, level, quantity)

            weapon_text = ""
            if reward["weapon"]:
                drop = reward["weapon"]
                weapon_id = weapon_service.create_weapon_conn(
                    conn,
                    client_id,
                    drop["weapon_def_id"],
                    drop["quality"],
                    drop["max_level"],
                    equipped=False,
                )
                weapon_text = f"获得武器 #{weapon_id} {drop['name']}[{drop['quality']}] 上限{drop['max_level']}"

            lines = [
                f"虫洞奖励：{event['boss_name']}",
                f"贡献：{reward['contribution']:.1%}，排名：{reward['rank']}",
                f"源石+{money(reward['stones'])}，经验+{reward['exp']}",
            ]
            if new_level > old_level:
                lines.append(f"等级提升：{old_level} -> {new_level}")
            lines.extend(reward["item_texts"])
            if weapon_text:
                lines.append(weapon_text)
            text = "\n".join(lines)
            conn.execute(
                """
                UPDATE wormhole_participants
                SET reward_claimed = 1, reward_text = ?, updated_at = ?
                WHERE wormhole_id = ? AND client_id = ?
                """,
                (text, ts(), event["wormhole_id"], client_id),
            )
        return text

    def try_discover(self, client_id: str, source: str, location_name: str) -> str:
        """跑商动作后尝试发现虫洞；没有触发时返回空文本。"""

        self._close_expired_events()
        active = self._active_event()
        if active:
            return self.notice(client_id, active)

        snapshot = self._world_snapshot()
        opened_today = self._today_opened_count()
        daily_limit = self._daily_event_limit(snapshot["active_count"])
        if opened_today >= daily_limit:
            return ""

        chance = self._discovery_chance(source, snapshot["active_count"], opened_today, daily_limit)
        if random.random() >= chance:
            return ""
        event = self._open_event(client_id, source, location_name)
        return self.notice(client_id, event, force=True)

    def notice(self, client_id: str, event: dict[str, Any] | None = None, force: bool = False) -> str:
        """给玩家追加虫洞提示；同一玩家有提示冷却，避免刷屏。"""

        event = event or self._active_event()
        if not event:
            return ""
        if not force:
            row = self.db.fetch_one(
                """
                SELECT last_notice_at
                FROM wormhole_notices
                WHERE wormhole_id = ? AND client_id = ?
                """,
                (event["wormhole_id"], client_id),
            )
            last = dt(row["last_notice_at"]) if row else None
            if last and now() - last < timedelta(minutes=WORMHOLE_NOTICE_COOLDOWN_MINUTES):
                return ""
        with self.db.transaction() as conn:
            conn.execute(
                """
                INSERT INTO wormhole_notices (wormhole_id, client_id, last_notice_at)
                VALUES (?, ?, ?)
                ON CONFLICT(wormhole_id, client_id)
                DO UPDATE SET last_notice_at = excluded.last_notice_at
                """,
                (event["wormhole_id"], client_id, ts()),
            )
        return (
            f"\n异界虫洞撕开：{event['boss_name']} 出现在 {event['location_name']}。"
            f"发送：导航 {event['location_name']}，再发送：挑战虫洞"
        )

    def _open_event(self, opened_by: str, source: str, location_name: str) -> dict[str, Any]:
        """按当前服务器生态生成一只动态 Boss。"""

        point = self._location_point(location_name)
        snapshot = self._world_snapshot()
        boss_name, boss_kind, boss_factor = random.choice(BOSS_POOL)
        level = max(3, min(MAX_LEVEL, snapshot["median_level"] + random.randint(-3, 8)))
        median_attack = max(10, snapshot["median_attack"])
        median_hp = max(120, snapshot["median_hp"])
        defense = max(1, int(median_attack * random.uniform(0.3, 0.5) * boss_factor))
        attack = max(1, int((median_hp / 22 + level * 1.4) * boss_factor))
        one_damage = self._estimate_challenge_damage(median_attack, level, defense)
        expected_players = max(1, min(20, round(snapshot["active_count"] * 0.28)))
        expected_attempts = 4
        difficulty = random.uniform(0.9, 1.15) * boss_factor
        max_hp = max(320, int(one_damage * expected_players * expected_attempts * difficulty))
        opened_at = now()
        closes_at = opened_at + timedelta(minutes=WORMHOLE_DURATION_MINUTES)

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO wormholes (
                    boss_name, boss_kind, location_name, x, y,
                    level, max_hp, hp, attack, defense, difficulty,
                    opened_by, source, status, opened_at, closes_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '开启', ?, ?)
                """,
                (
                    boss_name,
                    boss_kind,
                    point["name"],
                    point["x"],
                    point["y"],
                    level,
                    max_hp,
                    max_hp,
                    attack,
                    defense,
                    difficulty,
                    opened_by,
                    source,
                    ts(opened_at),
                    ts(closes_at),
                ),
            )
            wormhole_id = int(cursor.lastrowid)
        event = self.db.fetch_one("SELECT * FROM wormholes WHERE wormhole_id = ?", (wormhole_id,))
        assert event is not None
        return event

    def _active_event(self) -> dict[str, Any] | None:
        """读取当前仍开启的虫洞。"""

        self._close_expired_events()
        row = self.db.fetch_one(
            """
            SELECT *
            FROM wormholes
            WHERE status = '开启'
            ORDER BY opened_at DESC
            LIMIT 1
            """
        )
        return row

    def _latest_event(self) -> dict[str, Any] | None:
        """读取最近一条虫洞记录。"""

        return self.db.fetch_one("SELECT * FROM wormholes ORDER BY opened_at DESC LIMIT 1")

    def _latest_rewardable(self, client_id: str) -> dict[str, Any] | None:
        """读取玩家最近可领奖的虫洞。"""

        return self.db.fetch_one(
            """
            SELECT w.*
            FROM wormholes w
            JOIN wormhole_participants p ON p.wormhole_id = w.wormhole_id
            WHERE p.client_id = ?
              AND p.reward_claimed = 0
              AND w.status IN ('已击杀', '已退去')
            ORDER BY w.opened_at DESC
            LIMIT 1
            """,
            (client_id,),
        )

    def _close_expired_events(self) -> None:
        """超过持续时间后，未击杀的虫洞会退去。"""

        self.db.execute(
            """
            UPDATE wormholes
            SET status = '已退去', result = ?
            WHERE status = '开启' AND closes_at <= ?
            """,
            (dump_json({"reason": "timeout"}), ts()),
        )

    def _challenge_check(self, wormhole_id: int, client_id: str) -> str:
        """检查挑战冷却。"""

        row = self.db.fetch_one(
            """
            SELECT last_challenge_at
            FROM wormhole_participants
            WHERE wormhole_id = ? AND client_id = ?
            """,
            (wormhole_id, client_id),
        )
        if not row:
            return ""
        last = dt(row["last_challenge_at"])
        if not last:
            return ""
        left = timedelta(minutes=WORMHOLE_CHALLENGE_COOLDOWN_MINUTES) - (now() - last)
        if left <= timedelta():
            return ""
        seconds = max(1, int(left.total_seconds()))
        return hint(f"挑战虫洞冷却中，还需 {seconds // 60}分{seconds % 60}秒。", "稍后再发送：挑战虫洞")

    @staticmethod
    def _busy_challenge_hint(status: str) -> str:
        """玩家本体忙碌时，解释为什么不能挑战虫洞。"""

        if status == "探险中":
            return hint(
                "本体正在探险，不能挑战虫洞。",
                "行商化身仍可跑商；先发送：探险状态，30 分钟后发送：结束探险，再发送：挑战虫洞",
            )
        return hint(f"当前状态为 {status}，不能挑战虫洞。", "先结束当前状态，再发送：挑战虫洞")

    def _fight_boss(self, player: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        """结算一次虫洞挑战；这里只算数值和逐回合日志，不写数据库。"""

        client_id = player["client_id"]
        weapon_service.ensure_starter_weapon(client_id)
        weapon = weapon_service.equipped_weapon(client_id)
        skill = weapon_service.skill(weapon["skill_id"]) if weapon else None
        bonuses = self._merge_effects(self.equipment_bonuses(client_id), self._weapon_effects(weapon))
        player_attack = int(player["base_attack"]) + (int(weapon["attack"]) if weapon else 0)
        hp = int(player["hp"])
        mp = int(player["mp"])
        total_damage = 0
        skill_times = 0
        rounds = 10 + min(4, int(player["level"]) // 25)
        interval = self._skill_interval(skill, weapon, bonuses)
        skill_cost = self._skill_cost(skill, bonuses)
        boss_hp = int(event["hp"])
        actions: list[dict[str, Any]] = []

        for round_no in range(1, rounds + 1):
            raw = player_attack + random.randint(int(player["level"]), max(int(player["level"]) * 4, int(player["level"]) + 3))
            raw = int(raw * (1 + float(bonuses.get("hit_bonus", 0)) * 0.5))
            skill_used = False
            skill_name = ""
            if skill and interval and round_no % interval == 0 and mp >= skill_cost:
                raw = int(raw * self._skill_power(skill, bonuses))
                mp -= skill_cost
                skill_times += 1
                skill_used = True
                skill_name = str(skill["name"])
            damage = damage_after_defense(raw, int(event["defense"]), self._pierce_rate(bonuses))
            combo_damage = self._combo_damage(raw, int(event["defense"]), bonuses)
            round_damage = damage + combo_damage
            total_damage += round_damage
            boss_hp = max(0, boss_hp - round_damage)
            hp_before_steal = hp
            if bonuses.get("life_steal"):
                hp = min(int(player["max_hp"]), hp + int(round_damage * float(bonuses["life_steal"])))
            action = {
                "round": round_no,
                "raw": raw,
                "damage": round_damage,
                "base_damage": damage,
                "combo_damage": combo_damage,
                "life_steal": max(0, hp - hp_before_steal),
                "skill_used": skill_used,
                "skill_name": skill_name,
                "mp_cost": skill_cost if skill_used else 0,
                "boss_hp_left": boss_hp,
                "boss_hp_max": int(event["max_hp"]),
                "boss_attack": False,
                "boss_damage": 0,
                "player_hp_left": hp,
                "player_mp_left": mp,
                "dodged": False,
            }
            if boss_hp <= 0:
                actions.append(action)
                break
            if random.random() >= min(0.45, float(bonuses.get("dodge_bonus", 0))):
                hurt = damage_after_defense(
                    random.randint(max(1, int(event["attack"] * 0.75)), max(1, int(event["attack"] * 1.18))),
                    int(player["defense"]),
                )
                reduced_hurt = self._reduce_damage(hurt, bonuses, skill_used)
                hp -= reduced_hurt
                action["boss_attack"] = True
                action["boss_hurt_raw"] = hurt
                action["boss_damage"] = reduced_hurt
            else:
                action["dodged"] = True
            action["player_hp_left"] = max(0, hp)
            action["player_mp_left"] = 0 if hp <= 0 else max(0, mp)
            actions.append(action)
            if hp <= 0:
                break
        mp_left = 0 if hp <= 0 else max(0, mp)
        return {
            "damage": max(1, total_damage),
            "hp_left": max(0, hp),
            "mp_left": mp_left,
            "skill_times": skill_times,
            "actions": actions,
        }

    def _challenge_log_block(
        self,
        *,
        title: str,
        boss_name: str,
        player: dict[str, Any],
        result: dict[str, Any],
        damage: int,
        left_hp: int,
        max_hp: int,
        killed: bool,
        killed_text: str,
        alive_text: str,
        hurt_text: str,
    ) -> str:
        """把 Boss 挑战整理成包含逐次出手的代码块。"""

        lines = [
            title,
            "",
            "一、战斗明细",
        ]
        actions = result.get("actions")
        if isinstance(actions, list) and actions:
            for action in actions:
                lines.extend(self._boss_action_lines(action, boss_name, player))
        else:
            lines.append("无逐次出手记录。")

        lines.extend(
            [
                "",
                "二、最终结算",
                f"本次造成伤害：{damage}",
                f"战斗后血气：{result['hp_left']}/{player['max_hp']}",
                f"战斗后精神：{result['mp_left']}/{player['max_mp']}",
                f"武器技能触发：{result['skill_times']} 次",
            ]
        )
        if int(result["hp_left"]) <= 0:
            lines.append(hurt_text)
        if killed:
            lines.append(killed_text)
        else:
            lines.append(f"剩余血量：{left_hp}/{max_hp}")
            lines.append(alive_text)
        return "```javascript\r\n" + "\r\n".join(lines) + "\r\n```"

    @staticmethod
    def _boss_action_lines(action: dict[str, Any], boss_name: str, player: dict[str, Any]) -> list[str]:
        """整理一回合 Boss 战日志。"""

        round_no = int(action.get("round", 0))
        damage = int(action.get("damage", 0))
        combo_damage = int(action.get("combo_damage", 0))
        life_steal = int(action.get("life_steal", 0))
        boss_hp_left = max(0, int(action.get("boss_hp_left", 0)))
        boss_hp_max = max(1, int(action.get("boss_hp_max", 1)))
        skill_name = str(action.get("skill_name") or "")
        if action.get("skill_used"):
            attack_text = f"技能「{skill_name}」"
            cost_text = f"，消耗精神 {int(action.get('mp_cost', 0))}"
        else:
            attack_text = "普通攻击"
            cost_text = ""
        combo_text = f"，连击追加 {combo_damage}" if combo_damage > 0 else ""
        steal_text = f"，吸血 +{life_steal}" if life_steal > 0 else ""
        lines = [
            f"第 {round_no} 回合",
            f"  我方出手：{attack_text}，造成 {damage} 伤害{combo_text}{steal_text}{cost_text}；{boss_name} 血气 {boss_hp_left}/{boss_hp_max}",
        ]
        if boss_hp_left <= 0:
            lines.append(f"  Boss 出手：{boss_name} 已倒下。")
            return lines

        hp_left = max(0, int(action.get("player_hp_left", 0)))
        mp_left = max(0, int(action.get("player_mp_left", 0)))
        if action.get("dodged"):
            lines.append(
                f"  Boss 出手：{boss_name} 攻击落空；"
                f"我方血气 {hp_left}/{player['max_hp']}，精神 {mp_left}/{player['max_mp']}"
            )
            return lines

        hurt = int(action.get("boss_damage", 0))
        raw_hurt = int(action.get("boss_hurt_raw", hurt))
        reduce_text = f"，减免 {max(0, raw_hurt - hurt)}" if raw_hurt > hurt else ""
        lines.append(
            f"  Boss 出手：{boss_name} 造成 {hurt} 伤害{reduce_text}；"
            f"我方血气 {hp_left}/{player['max_hp']}，精神 {mp_left}/{player['max_mp']}"
        )
        return lines

    def _roll_reward(self, event: dict[str, Any], participant: dict[str, Any], player: dict[str, Any]) -> dict[str, Any]:
        """按贡献、排名和是否击杀生成奖励。"""

        rows = self._participants(event["wormhole_id"])
        rank = next((index for index, row in enumerate(rows, start=1) if row["client_id"] == player["client_id"]), len(rows))
        contribution = self._contribution(int(participant["damage"]), event)
        killed_factor = 1.0 if event["status"] == "已击杀" else 0.55
        rank_factor = {1: 1.15, 2: 1.06, 3: 1.0}.get(rank, 0.9)
        stones = max(1, int((int(event["level"]) * 650 + int(event["max_hp"]) * 0.012) * killed_factor * (0.45 + contribution * 2.2) * rank_factor))
        exp = max(1, int(monster_exp(event["level"], 1.45, player["level"]) * killed_factor * (0.55 + contribution * 1.6)))
        ring_items: list[tuple[str, int]] = []
        gems: list[tuple[str, int, int]] = []
        item_texts: list[str] = []

        recover = self._random_equipment_item("恢复类")
        if recover:
            ring_items.append((recover["equipment_item_id"], 1))
            item_texts.append(f"纳戒获得 {recover['name']} x1")

        if random.random() < 0.08 + contribution * 0.25:
            special = self.equipment_item_def("xisuiye")
            if special:
                ring_items.append((special["equipment_item_id"], 1))
                item_texts.append(f"纳戒获得 {special['name']} x1")

        gem = self._random_equipment_item("宝石")
        if gem and random.random() < 0.15 + contribution * 0.3:
            level = 1 + (1 if random.random() < min(0.22, contribution) else 0)
            gems.append((gem["equipment_item_id"], level, 1))
            item_texts.append(f"宝石获得 {gem['name']} {level}级 x1")

        book = self._random_equipment_item("技能书")
        if book and random.random() < 0.06 + contribution * 0.22:
            ring_items.append((book["equipment_item_id"], 1))
            item_texts.append(f"纳戒获得 {book['name']} x1")

        weapon = None
        if random.random() < 0.03 + contribution * 0.16:
            weapon = weapon_service.roll_weapon_drop(max(player["level"], event["level"]), event["location_name"])

        return {
            "rank": rank,
            "contribution": contribution,
            "stones": stones,
            "exp": exp,
            "ring_items": ring_items,
            "gems": gems,
            "weapon": weapon,
            "item_texts": item_texts,
        }

    def _random_equipment_item(self, category: str) -> dict[str, Any] | None:
        """随机一个纳戒物品；排除只属于岁时情劫的产物。"""

        rows = self.db.fetch_all(
            """
            SELECT *
            FROM equipment_item_defs
            WHERE category = ?
              AND equipment_item_id != 'kaikongqi'
            """,
            (category,),
        )
        return random.choice(rows) if rows else None

    def _participants(self, wormhole_id: int) -> list[dict[str, Any]]:
        """读取虫洞贡献排行。"""

        return self.db.fetch_all(
            """
            SELECT *
            FROM wormhole_participants
            WHERE wormhole_id = ?
            ORDER BY damage DESC, updated_at ASC
            """,
            (wormhole_id,),
        )

    def _contribution(self, damage: int, event: dict[str, Any]) -> float:
        """计算个人伤害在总伤害中的占比。"""

        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(damage), 0) AS total FROM wormhole_participants WHERE wormhole_id = ?",
            (event["wormhole_id"],),
        )
        total = int(row["total"] if row else 0)
        if total <= 0:
            return 0.0
        return max(0.0, min(1.0, int(damage) / total))

    def _location_point(self, name: str) -> dict[str, Any]:
        """把商场、特殊收购点或系统回收点转成坐标。"""

        clean = name.strip()
        row = self.db.fetch_one("SELECT name, x, y FROM trade_locations WHERE name = ?", (clean,))
        if row:
            return row
        buyer = self.db.fetch_one(
            "SELECT buyer_name AS name, x, y FROM special_buyers WHERE buyer_name = ?",
            (clean,),
        )
        if buyer:
            return buyer
        recycle = self.db.fetch_one("SELECT name, x, y FROM recycle_locations WHERE name = ?", (clean,))
        if recycle:
            return recycle
        return {"name": clean or "天枢城", "x": 0, "y": 0}

    def _world_snapshot(self) -> dict[str, int]:
        """读取玩家生态，用来动态缩放虫洞强度。"""

        active_players = self._active_players()
        players = active_players or self.db.fetch_all("SELECT * FROM players")
        if not players:
            return {"active_count": 1, "median_level": 1, "median_attack": 12, "median_hp": 120}
        levels = sorted(max(1, int(row["level"])) for row in players)
        attacks = []
        hps = []
        for row in players:
            weapon = self.db.fetch_one(
                "SELECT attack FROM player_weapons WHERE owner_id = ? AND equipped = 1 LIMIT 1",
                (row["client_id"],),
            )
            attacks.append(max(1, int(row["base_attack"]) + (int(weapon["attack"]) if weapon else 0)))
            hps.append(max(1, int(row["max_hp"])))
        return {
            "active_count": max(1, len(active_players)),
            "median_level": int(median(levels)),
            "median_attack": int(median(attacks)),
            "median_hp": int(median(hps)),
        }

    def _active_players(self) -> list[dict[str, Any]]:
        """读取近期活跃玩家。

        近 7 天内创建、发过 WS 请求、跑商、探险、挑战或对战，都算活跃。
        这个人数只用于虫洞刷新和动态难度，不改变玩家数据。
        """

        cutoff = ts(now() - timedelta(days=WORMHOLE_ACTIVE_WINDOW_DAYS))
        return self.db.fetch_all(
            """
            SELECT *
            FROM players p
            WHERE p.created_at >= ?
               OR EXISTS (SELECT 1 FROM request_idempotency r WHERE r.client_id = p.client_id AND r.created_at >= ?)
               OR EXISTS (SELECT 1 FROM game_logs g WHERE g.client_id = p.client_id AND g.created_at >= ?)
               OR EXISTS (SELECT 1 FROM trade_records t WHERE t.client_id = p.client_id AND t.created_at >= ?)
               OR EXISTS (SELECT 1 FROM exploration_records e WHERE e.client_id = p.client_id AND e.started_at >= ?)
               OR EXISTS (SELECT 1 FROM wormhole_participants wp WHERE wp.client_id = p.client_id AND wp.updated_at >= ?)
               OR EXISTS (SELECT 1 FROM seasonal_boss_participants sp WHERE sp.client_id = p.client_id AND sp.updated_at >= ?)
               OR EXISTS (SELECT 1 FROM duel_records d WHERE (d.from_client_id = p.client_id OR d.to_client_id = p.client_id) AND d.created_at >= ?)
               OR EXISTS (SELECT 1 FROM combat_logs c WHERE c.client_id = p.client_id AND c.created_at >= ?)
            """,
            (cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff, cutoff),
        )

    def _today_opened_count(self) -> int:
        """统计今日已经生成过多少次虫洞。

        这里按修仙统一的 04:00 业务日计算，已击杀和已退去也计入当天次数。
        """

        rows = self.db.fetch_all(
            "SELECT opened_at FROM wormholes WHERE opened_at >= ?",
            (ts(now() - timedelta(days=2)),),
        )
        today = business_day()
        count = 0
        for row in rows:
            opened = dt(row["opened_at"])
            if opened and business_day(opened) == today:
                count += 1
        return count

    @staticmethod
    def _daily_event_limit(active_count: int) -> int:
        """按活跃人数计算每日虫洞生成上限。

        活跃人数只负责把上限往上抬；最低下限始终保留，
        避免低活跃日完全没有虫洞可打。
        """

        active = max(1, int(active_count))
        extra = (active - 1) // WORMHOLE_DAILY_ACTIVE_PLAYER_STEP
        dynamic_limit = WORMHOLE_DAILY_BASE_LIMIT + extra
        capped_limit = min(WORMHOLE_DAILY_MAX_LIMIT, dynamic_limit)
        return max(WORMHOLE_DAILY_MIN_LIMIT, capped_limit)

    @staticmethod
    def _discovery_chance(source: str, active_count: int, opened_today: int, daily_limit: int) -> float:
        """按活跃人数和今日剩余名额微调发现概率。"""

        base = DISCOVERY_CHANCES.get(source, 0.0)
        if base <= 0:
            return 0.0
        active_factor = 1.0 + min(1.2, max(0, int(active_count) - 1) * 0.08)
        remaining = max(0, int(daily_limit) - int(opened_today))
        remaining_factor = 1.0 + min(1.0, remaining / max(1, int(daily_limit)))
        return min(0.18, base * active_factor * remaining_factor)

    @staticmethod
    def _estimate_challenge_damage(median_attack: int, level: int, boss_defense: int) -> int:
        """估算中位玩家单次挑战伤害。"""

        per_round = damage_after_defense(int(median_attack * 1.25 + level * 2.0), boss_defense)
        return max(25, per_round * 10)

    def _format_status(self, event: dict[str, Any]) -> str:
        """格式化虫洞状态。"""

        closes = dt(event["closes_at"])
        left = max(0, int((closes - now()).total_seconds() // 60) + 1) if closes else 0
        snapshot = self._world_snapshot()
        opened_today = self._today_opened_count()
        daily_limit = self._daily_event_limit(snapshot["active_count"])
        return (
            f"☆异界虫洞·{event['boss_name']}☆\n"
            f"位置：{event['location_name']} ({event['x']},{event['y']})\n"
            f"等级:{event['level']} 血量:{event['hp']}/{event['max_hp']} 状态:{event['status']}\n"
            f"今日出现：{opened_today}/{daily_limit}，近{WORMHOLE_ACTIVE_WINDOW_DAYS}天活跃：{snapshot['active_count']}人\n"
            f"剩余约 {left} 分钟，挑战冷却 {WORMHOLE_CHALLENGE_COOLDOWN_MINUTES} 分钟。\n"
            f"发送：导航 {event['location_name']}，到达后发送：挑战虫洞"
        )


service = WormholeService(db)

__all__ = ["BOSS_POOL", "DISCOVERY_CHANCES", "WormholeService", "service"]
