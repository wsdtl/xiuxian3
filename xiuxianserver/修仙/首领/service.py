"""岁时情劫首领服务。

岁时情劫按每日 04:00 的业务日刷新。
节气和传统节日命中时，玩家发送首领相关命令才会懒加载生成当日首领。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from math import sqrt
from statistics import median
from typing import Any

from lunardate import LunarDate

from .. import combat_log_text
from ..combat_core import CombatCore
from ..common import (
    CoreService,
    RING_CATEGORY_BOOK,
    RING_CATEGORY_GEM,
    RING_CATEGORY_RECOVERY,
    currency_amount,
    dt,
    dump_json,
    money,
    now,
    player_level_label,
    quality_label,
    random,
    ring_category_key,
    ts,
    weapon_id_label,
)
from ..constants import (
    DAY_RESET_HOUR,
    MAX_LEVEL,
    SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES,
    SEASONAL_BOSS_MAX_CHALLENGES,
)
from ..format_text import T
from ..rules import damage_after_defense, monster_exp
from ..sect_war import record_sect_merit_conn, sect_direction_bonus_conn
from ..sql import db
from ..weapon_core import WeaponCore

from .seasonal_package import (
    ALL_BOSS_DEFS,
    BOSS_DEFS,
    DAILY_BOSS_DEFS,
    HIGH_WEIGHT_FESTIVALS,
    LUNAR_FESTIVAL_DATES,
    SEASONAL_BOSS_KIND,
    BossDef,
    _solar_term_key,
    seasonal_skill_for_event,
)

SEASONAL_LOW_CONTRIBUTION_FLOORS = {
    "feather": 0.025,
    "material": 0.015,
    "gem": 0.080,
    "book": 0.030,
    "weapon": 0.015,
}
SEASONAL_FEATHER_SCORE_BONUS = 0.018
SEASONAL_FEATHER_CHANCE_CAP = 0.22


class SeasonalBossService(CoreService):
    """按节令出现的岁时情劫首领。"""

    def __init__(self, database) -> None:
        super().__init__(database)
        self.combat_core = CombatCore(database)
        self.weapon_core = WeaponCore(database)

    def status(self, client_id: str) -> str:
        """查看今日岁时情劫。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        event = self._today_event(create=True, update=True)
        if not event:
            pending = self._latest_rewardable(client_id)
            next_info = self._next_boss_text()
            if pending:
                return T.hint("今日无岁时情劫，但你有首领奖励待领取。", "发送：首领奖励<首领奖励>")
            return T.hint("今日无岁时情劫。", next_info)
        return self._format_status(event)

    def ranking(self, client_id: str) -> str:
        """查看今日或最近首领排行。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        event = self._today_event(create=False, update=True) or self._latest_event()
        if not event:
            return T.hint("暂无岁时情劫记录。", self._next_boss_text())
        rows = self._participants(event["event_id"])
        if not rows:
            return T.hint(f"{event['boss_name']} 暂无挑战记录。", "发送：挑战首领 参与今日岁时情劫。<挑战首领>")
        panel = T.panel()
        panel.section(f"岁时情劫排行·{event['boss_name']}")
        for index, row in enumerate(rows[:10], start=1):
            panel.line(
                f"{index}. {self.format_player_name(row['client_id'])} "
                f"伤害 **{row['damage']}**｜贡献 {self._contribution(row['damage'], event):.1%}｜"
                f"挑战{row['challenge_count']}/{SEASONAL_BOSS_MAX_CHALLENGES}次"
            )
        return panel.render()

    def challenge(self, client_id: str) -> str | dict:
        """挑战今日岁时情劫。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        self.cleanup_battle_records()
        assert player is not None

        event = self._today_event(create=True, update=True)
        if not event:
            return T.hint("今日无岁时情劫。", self._next_boss_text())
        if event["status"] != "开启":
            return T.hint(f"{event['boss_name']} 已经{event['status']}，不能继续挑战。", "发送：首领奖励 查看是否可以领取奖励。<首领奖励>")
        if player["status"] != "空闲":
            return self._busy_challenge_hint(player["status"])
        if int(player["hp"]) <= 0:
            return T.hint("血气不足，无法挑战首领。", "发送：休息，时间到后发送：结束休息")

        check = self._challenge_check(event, client_id)
        if check:
            return check

        result = self._fight_boss(player, event)
        damage = min(int(result["damage"]), int(event["hp"]))
        killed = False
        challenge_record_id = 0
        with self.db.transaction() as conn:
            fresh = conn.execute(
                "SELECT * FROM seasonal_boss_events WHERE event_id = ? AND status = '开启'",
                (event["event_id"],),
            ).fetchone()
            if not fresh:
                return T.hint("今日岁时情劫已经结束。", "发送：首领奖励 查看是否可以领取奖励。<首领奖励>")
            fresh_player = conn.execute(
                "SELECT status, hp FROM players WHERE client_id = ?",
                (client_id,),
            ).fetchone()
            if not fresh_player:
                return T.hint("你还没有创建用户。", "发送：创建用户 名称，例如：创建用户 青衫客")
            if str(fresh_player["status"]) != "空闲":
                return self._busy_challenge_hint(str(fresh_player["status"]))
            if int(fresh_player["hp"]) <= 0:
                return T.hint("血气不足，无法挑战首领。", "发送：休息，时间到后发送：结束休息")
            current = conn.execute(
                """
                SELECT challenge_count, last_challenge_at
                FROM seasonal_boss_participants
                WHERE event_id = ? AND client_id = ?
                """,
                (event["event_id"], client_id),
            ).fetchone()
            if current and int(current["challenge_count"]) >= SEASONAL_BOSS_MAX_CHALLENGES:
                return T.hint("今日挑战次数已用完。", "等下一次岁时情劫出现后再来。<状态><纳戒>")
            if current:
                last = dt(current["last_challenge_at"])
                left = timedelta(minutes=SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES) - (now() - last) if last else timedelta()
                if left > timedelta():
                    return self._boss_cooldown_hint(left, dt(fresh["closes_at"]))

            damage = min(damage, int(fresh["hp"]))
            left_hp = max(0, int(fresh["hp"]) - damage)
            killed = left_hp <= 0
            result["event_id"] = int(event["event_id"])
            result["boss_name"] = str(event["boss_name"])
            result["boss_label"] = "首领"
            result["damage"] = damage
            result["hp_before"] = int(fresh["hp"])
            result["hp_after"] = left_hp
            result["killed"] = killed
            result["player_max_hp"] = int(player["max_hp"])
            result["player_max_mp"] = int(player["max_mp"])
            conn.execute(
                "UPDATE players SET hp = ?, mp = ? WHERE client_id = ?",
                (result["hp_left"], result["mp_left"], client_id),
            )
            self.reset_rest_window_conn(conn, client_id, int(result["hp_left"]), int(result["mp_left"]))
            conn.execute(
                """
                INSERT INTO seasonal_boss_participants
                (event_id, client_id, damage, challenge_count, last_challenge_at, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(event_id, client_id)
                DO UPDATE SET
                    damage = damage + excluded.damage,
                    challenge_count = challenge_count + 1,
                    last_challenge_at = excluded.last_challenge_at,
                    updated_at = excluded.updated_at
                """,
                (event["event_id"], client_id, damage, ts(), ts(), ts()),
            )
            cursor = conn.execute(
                """
                INSERT INTO boss_challenge_records
                (event_id, client_id, damage, hp_before, hp_after, killed, result, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event["event_id"],
                    client_id,
                    damage,
                    int(fresh["hp"]),
                    left_hp,
                    1 if killed else 0,
                    dump_json(result),
                    ts(),
                ),
            )
            challenge_record_id = int(cursor.lastrowid)
            if killed:
                conn.execute(
                    """
                    UPDATE seasonal_boss_events
                    SET hp = 0, status = '已击破', killed_at = ?, result = ?
                    WHERE event_id = ?
                    """,
                    (ts(), dump_json({"killer": client_id}), event["event_id"]),
                )
            else:
                conn.execute(
                    "UPDATE seasonal_boss_events SET hp = ? WHERE event_id = ?",
                    (left_hp, event["event_id"]),
                )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '挑战首领', ?, ?)",
                (
                    client_id,
                    (
                        f"event={event['event_id']}, boss={event['boss_name']}, damage={damage}, "
                        f"weapon_exp={int(result.get('weapon_exp', 0)) if int(result.get('weapon_id', 0)) > 0 else 0}"
                    ),
                    ts(),
                ),
            )
            self.record_weapon_combat_conn(
                conn,
                client_id,
                int(result.get("weapon_id", 0)),
                boss_challenge=True,
                damage=int(result.get("highest_damage", damage)),
                weapon_exp=int(result.get("weapon_exp", 0)),
            )

        return self._challenge_log_block(
            title=f"挑战岁时情劫：{event['boss_name']}",
            boss_name=event["boss_name"],
            player=player,
            result=result,
            damage=damage,
            left_hp=left_hp,
            max_hp=int(event["max_hp"]),
            killed=killed,
            killed_text=f"{event['boss_name']} 已被送回岁时深处，可以领取首领奖励。",
            alive_text=f"再次挑战需等待 {SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES} 分钟。",
            hurt_text="你被旧念重伤，建议先休息。",
            log_kind="boss",
            record_id=challenge_record_id,
        )

    def reward(self, client_id: str) -> str:
        """领取最近一次可领取的首领奖励。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        self._today_event(create=False, update=True)
        event = self._latest_rewardable(client_id)
        if not event:
            active = self._today_event(create=False, update=False)
            if active:
                return T.hint("今日岁时情劫还没有结束。", "继续挑战，或等其被击破/次日 04:00 退去后再发送：首领奖励<首领奖励>")
            return T.hint("没有可领取的首领奖励。", "发送：首领 查看今日是否有岁时情劫。<首领>")

        participant = self.db.fetch_one(
            "SELECT * FROM seasonal_boss_participants WHERE event_id = ? AND client_id = ?",
            (event["event_id"], client_id),
        )
        if not participant:
            return T.hint("你没有参与这次岁时情劫。", "下一次出现时发送：挑战首领<挑战首领>")
        if int(participant["reward_claimed"]):
            return participant["reward_text"] or T.hint("奖励已经领取。", "发送：首领 查看今日状态。<首领>")

        reward = self._roll_reward(event, participant, player)
        with self.db.transaction() as conn:
            fresh = conn.execute(
                "SELECT reward_claimed FROM seasonal_boss_participants WHERE event_id = ? AND client_id = ?",
                (event["event_id"], client_id),
            ).fetchone()
            if not fresh or int(fresh["reward_claimed"]):
                return T.hint("奖励已经领取。", "发送：首领 查看今日状态。<首领>")
            old_level, new_level = self.add_exp_conn(conn, client_id, reward["exp"])
            conn.execute(
                "UPDATE players SET raw_stones = raw_stones + ? WHERE client_id = ?",
                (reward["stones"], client_id),
            )
            for item_id, quantity in reward["ring_items"]:
                self.add_ring_conn(conn, client_id, item_id, quantity)
            for gem_id, level, quantity in reward["gems"]:
                self.add_gem_conn(conn, client_id, gem_id, level, quantity)
            feather_lines = []
            for _ in range(reward["feathers"]):
                cursor = conn.execute(
                    """
                    INSERT INTO inscription_feathers
                    (client_id, source_key, source_name, title, flavor_text, obtained_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        event["boss_key"],
                        event["boss_name"],
                        f"{event['boss_name']}遗羽",
                        event["feather_text"],
                        ts(),
                    ),
                )
                feather_lines.append(f"获得铭刻之羽 〔{int(cursor.lastrowid)}〕：{event['boss_name']}遗羽")
            weapon_texts = []
            for drop in reward.get("weapons", []):
                weapon_id = self.weapon_core.create_weapon_conn(
                    conn,
                    client_id,
                    drop["weapon_def_id"],
                    drop["quality"],
                    drop["max_level"],
                    equipped=False,
                )
                weapon_texts.append(f"获得武器 {weapon_id_label(weapon_id)} {drop['name']}[{quality_label(drop['quality'])}] 上限{drop['max_level']}")

            lines = [
                f"岁时情劫奖励：{event['boss_name']}",
                f"结果：{event['status']}｜你为本次旧愿留下 {reward['contribution']:.1%} 伤痕，位列第{reward['rank']}",
                f"首领权重：{event['weight_type']}｜珍贵抽取：{reward.get('loot_rolls', 1)} 次",
                f"宗门增益：珍贵掉落 +{float(reward.get('influence_bonus') or 0.0):.1%}",
                f"{currency_amount(reward['stones'])}，经验+{reward['exp']}",
            ]
            if new_level > old_level:
                lines.append(f"等级提升：{player_level_label(old_level)} → {player_level_label(new_level)}")
            lines.extend(reward["item_texts"])
            lines.extend(feather_lines)
            if feather_lines:
                lines.append(event["feather_text"])
            lines.extend(weapon_texts)
            text = "\n".join(lines)
            conn.execute(
                """
                UPDATE seasonal_boss_participants
                SET reward_claimed = 1, reward_text = ?, updated_at = ?
                WHERE event_id = ? AND client_id = ?
                """,
                (text, ts(), event["event_id"], client_id),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '领取首领奖励', ?, ?)",
                (
                    client_id,
                    (
                        f"event_id={event['event_id']}, boss={event['boss_name']}, "
                        f"rank={reward['rank']}, exp={reward['exp']}, stones={reward['stones']}, "
                        f"feathers={reward['feathers']}"
                    ),
                    ts(),
                ),
            )
            record_sect_merit_conn(
                conn,
                client_id,
                "influence",
                max(25, int(reward["contribution"] * 1200) + (100 if int(reward["rank"]) <= 3 else 0)),
                source="领取首领奖励",
                detail=f"event_id={event['event_id']}, boss={event['boss_name']}, rank={reward['rank']}",
            )
        return text

    def _today_event(self, create: bool, update: bool) -> dict[str, Any] | None:
        """读取或生成当前业务日首领。"""

        day = self._business_date()
        if update:
            self._close_expired_events()
        event = self.db.fetch_one(
            "SELECT * FROM seasonal_boss_events WHERE business_day = ?",
            (day.isoformat(),),
        )
        if event:
            return dict(event)
        if not create:
            return None
        boss_def, event_type, weight_type = self._boss_for_date(day)
        if not boss_def:
            return None
        return self._open_event(day, boss_def, event_type, weight_type)

    def _open_event(self, day: date, boss_def: BossDef, event_type: str, weight_type: str) -> dict[str, Any]:
        """按当前服务器生态生成今日首领。"""

        snapshot = self._world_snapshot()
        level = max(3, min(MAX_LEVEL, snapshot["median_level"] + random.randint(-3, 5)))
        median_attack = max(8, snapshot["median_attack"])
        median_hp = max(120, snapshot["median_hp"])
        defense = max(1, int(median_attack * random.uniform(0.32, 0.52)))
        attack = max(1, int(median_hp / 22 + level * 1.5))
        one_challenge_damage = self._estimate_challenge_damage(median_attack, level, defense)
        expected_players = max(3, min(30, round(snapshot["active_count"] * 0.65)))
        expected_attempts = 4 if weight_type == "普通节气" else SEASONAL_BOSS_MAX_CHALLENGES
        difficulty = random.uniform(1.25, 1.55)
        max_hp = max(360, int(one_challenge_damage * expected_players * expected_attempts * difficulty))
        opened = datetime.combine(day, time(hour=DAY_RESET_HOUR))
        closes = opened + timedelta(days=1)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO seasonal_boss_events (
                    business_day, boss_key, event_type, weight_type, boss_name, title,
                    scene, story, farewell, feather_text, location_name, atmosphere,
                    level, max_hp, hp, attack, defense, difficulty,
                    status, opened_at, closes_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '开启', ?, ?)
                """,
                (
                    day.isoformat(),
                    boss_def.key,
                    event_type,
                    weight_type,
                    boss_def.name,
                    boss_def.title,
                    boss_def.scene,
                    boss_def.story,
                    boss_def.farewell,
                    boss_def.feather_text,
                    boss_def.location,
                    dump_json(list(boss_def.atmosphere)),
                    level,
                    max_hp,
                    max_hp,
                    attack,
                    defense,
                    difficulty,
                    ts(opened),
                    ts(closes),
                ),
            )
            event_id = int(cursor.lastrowid)
        event = self.db.fetch_one("SELECT * FROM seasonal_boss_events WHERE event_id = ?", (event_id,))
        assert event is not None
        return dict(event)

    def _close_expired_events(self) -> None:
        """过了次日 04:00，未击破的首领会退去。"""

        self.db.execute(
            """
            UPDATE seasonal_boss_events
            SET status = '已退去', result = ?
            WHERE status = '开启' AND closes_at <= ?
            """,
            (dump_json({"reason": "timeout"}), ts()),
        )

    def _latest_event(self) -> dict[str, Any] | None:
        """读取最近一条首领记录。"""

        row = self.db.fetch_one("SELECT * FROM seasonal_boss_events ORDER BY opened_at DESC LIMIT 1")
        return dict(row) if row else None

    def _latest_rewardable(self, client_id: str) -> dict[str, Any] | None:
        """读取玩家最近可领取的首领。"""

        row = self.db.fetch_one(
            """
            SELECT e.*
            FROM seasonal_boss_events e
            JOIN seasonal_boss_participants p ON p.event_id = e.event_id
            WHERE p.client_id = ?
              AND p.reward_claimed = 0
              AND e.status IN ('已击破', '已退去')
            ORDER BY e.opened_at DESC
            LIMIT 1
            """,
            (client_id,),
        )
        return dict(row) if row else None

    def _challenge_check(self, event: dict[str, Any], client_id: str) -> str:
        """检查挑战次数和 30 分钟冷却。"""

        row = self.db.fetch_one(
            """
            SELECT challenge_count, last_challenge_at
            FROM seasonal_boss_participants
            WHERE event_id = ? AND client_id = ?
            """,
            (int(event["event_id"]), client_id),
        )
        if not row:
            return ""
        if int(row["challenge_count"]) >= SEASONAL_BOSS_MAX_CHALLENGES:
            return T.hint("今日挑战次数已用完。", "等下一次岁时情劫出现后再来。<状态><纳戒>")
        last = dt(row["last_challenge_at"])
        if not last:
            return ""
        left = timedelta(minutes=SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES) - (now() - last)
        if left <= timedelta():
            return ""
        return self._boss_cooldown_hint(left, dt(event["closes_at"]))

    @staticmethod
    def _boss_cooldown_hint(left: timedelta, closes_at: datetime | None) -> str:
        """首领冷却提示要同时考虑本轮首领是否会先退去。"""

        seconds = max(1, int(left.total_seconds()))
        left_text = f"{seconds // 60}分{seconds % 60}秒"
        current = now()
        ready_at = current + timedelta(seconds=seconds)
        if closes_at and ready_at >= closes_at:
            return T.hint(
                (
                    f"岁时旧念尚未重新凝形，还需 {left_text}。"
                    f"首领仍在，退去点 {closes_at.strftime('%H:%M:%S')}；"
                    f"你约 {ready_at.strftime('%H:%M:%S')} 才能再出手，赶不上本轮。"
                ),
                "退去后发送：首领奖励<首领奖励>",
            )
        return T.hint(f"岁时旧念尚未重新凝形，还需 {left_text}。", "冷却结束后再来。<状态><纳戒>")

    @staticmethod
    def _busy_challenge_hint(status: str) -> str:
        """玩家本体忙碌时，解释为什么不能挑战首领。"""

        if status == "探险中":
            return T.hint(
                "本体正在探险，不能挑战首领。",
                "行商化身仍可跑商；先发送：探险状态，30 分钟后发送：结束探险，再发送：挑战首领",
            )
        return T.hint(f"当前状态为 {status}，不能挑战首领。", "先结束当前状态，再发送：挑战首领")

    def _fight_boss(self, player: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        """只计算一次战斗并返回逐次出手结果；数据库记录由外层 challenge() 写入。"""

        action_limit = 14 + min(4, int(player["level"]) // 25)
        return self.combat_core.fight_boss(
            player,
            event,
            boss_kind=SEASONAL_BOSS_KIND,
            action_limit=action_limit,
            enemy_skill=seasonal_skill_for_event(event),
        )

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
        log_kind: str = "",
        record_id: int = 0,
    ) -> str | dict:
        """按玩家设置返回首领挑战短摘要，并附带战斗日志链接。"""

        return combat_log_text.boss_brief(
            title=title,
            boss_name=boss_name,
            boss_label="首领",
            player=player,
            result=result,
            damage=damage,
            left_hp=left_hp,
            max_hp=max_hp,
            killed=killed,
            killed_text=killed_text,
            alive_text=alive_text,
            hurt_text=hurt_text,
            log_kind=log_kind,
            record_id=record_id,
            client_id=str(player["client_id"]),
            detail=combat_log_text.wants_detail(player),
        )

    def _roll_reward(self, event: dict[str, Any], participant: dict[str, Any], player: dict[str, Any]) -> dict[str, Any]:
        """按贡献、排名和节日权重生成奖励。"""

        rows = self._participants(event["event_id"])
        rank = next((index for index, row in enumerate(rows, start=1) if row["client_id"] == player["client_id"]), len(rows))
        contribution = self._contribution(int(participant["damage"]), event)
        contribution_score = self._contribution_score(contribution)
        killed_factor = 1.0 if event["status"] == "已击破" else 0.55
        weight = str(event["weight_type"])
        rates = self._reward_rates(weight)
        influence_bonus = self._public_battle_reward_bonus(str(player["client_id"]))
        rank_factor = {1: 1.18, 2: 1.08, 3: 1.0}.get(rank, 0.92)
        stones = max(1, int((int(event["level"]) * 850 + int(event["max_hp"]) * 0.015) * killed_factor * (0.45 + contribution_score * 2.5) * rank_factor))
        exp = max(1, int(monster_exp(event["level"], 1.8, player["level"]) * killed_factor * (0.6 + contribution_score * 1.8)))
        loot_rolls = self._good_loot_rolls(contribution_score, rank, influence_bonus)
        ring_items: list[tuple[str, int]] = []
        gems: list[tuple[str, int, int]] = []
        item_texts: list[str] = []
        feathers = 0
        weapons: list[dict[str, Any]] = []
        location_name = str(event["location_name"])

        recover = self._random_equipment_item(RING_CATEGORY_RECOVERY)
        if recover:
            ring_items.append((recover["ring_item_id"], 1))
            item_texts.append(f"纳戒获得 {recover['name']} x1")
        for _ in range(loot_rolls):
            reward = self._roll_good_loot(
                weight,
                contribution_score,
                rank,
                rates,
                location_name,
                influence_bonus,
                allow_feather=feathers <= 0,
            )
            if not reward:
                continue
            kind = reward["kind"]
            if kind == "feather":
                feathers += 1
            elif kind == "gem":
                gems.append((reward["item_id"], int(reward["level"]), 1))
                item_texts.append(f"宝石获得 {reward['name']} {int(reward['level'])}级 x1")
            elif kind == "weapon":
                weapons.append(reward["drop"])
            else:
                ring_items.append((reward["item_id"], 1))
                item_texts.append(f"纳戒获得 {reward['name']} x1")
        return {
            "rank": rank,
            "contribution": contribution,
            "loot_rolls": loot_rolls,
            "stones": stones,
            "exp": exp,
            "feathers": feathers,
            "ring_items": ring_items,
            "gems": gems,
            "weapons": weapons,
            "weapon": weapons[0] if weapons else None,
            "item_texts": item_texts,
            "influence_bonus": influence_bonus,
        }

    def _reward_rates(self, weight_type: str) -> dict[str, float]:
        """从数据库读取首领掉落概率；缺失时用每日旧愿兜底。"""

        row = self.db.fetch_one(
            "SELECT * FROM seasonal_boss_reward_rates WHERE weight_type = ?",
            (weight_type,),
        ) or self.db.fetch_one(
            "SELECT * FROM seasonal_boss_reward_rates WHERE weight_type = '每日旧愿'",
        )
        if not row:
            return {
                "feather_chance": 0.025,
                "feather_rank_chance": 0.012,
                "material_chance": 0.015,
                "material_rank_chance": 0.010,
                "gem_chance": 0.080,
                "book_chance": 0.030,
                "weapon_chance": 0.015,
            }
        return {
            "feather_chance": float(row["feather_chance"]),
            "feather_rank_chance": float(row["feather_rank_chance"]),
            "material_chance": float(row["material_chance"]),
            "material_rank_chance": float(row["material_rank_chance"]),
            "gem_chance": float(row["gem_chance"]),
            "book_chance": float(row["book_chance"]),
            "weapon_chance": float(row["weapon_chance"]),
        }

    @staticmethod
    def _contribution_score(contribution: float) -> float:
        """奖励加成使用 sqrt(贡献度)，低贡献保留机会，高贡献收益更稳但不过度线性碾压。"""

        return sqrt(max(0.0, min(1.0, float(contribution))))

    @staticmethod
    def _good_loot_rolls(contribution_score: float, rank: int, influence_bonus: float = 0.0) -> int:
        """按 sqrt 贡献度决定珍贵战利品抽取次数。"""

        score = max(0.0, min(1.0, float(contribution_score)))
        bonus = max(0.0, min(0.08, float(influence_bonus)))
        rolls = 1
        if random.random() < min(0.95, score * 1.15 + bonus):
            rolls += 1
        if random.random() < min(0.75, max(0.0, score - 0.18) * 0.95 + bonus * 0.8):
            rolls += 1
        rank_bonus = 0.16 if rank == 1 else 0.10 if rank == 2 else 0.06 if rank == 3 else 0.0
        if random.random() < min(0.45, max(0.0, score - 0.45) * 0.65 + rank_bonus + bonus * 0.5):
            rolls += 1
        return min(4, rolls)

    def _public_battle_reward_bonus(self, client_id: str) -> float:
        """宗门影响力给公共战斗珍贵掉落小幅修正，不影响货币和经验。"""

        with self.db.transaction() as conn:
            return min(0.08, max(0.0, sect_direction_bonus_conn(conn, client_id, "influence") * 0.12))

    def _roll_good_loot(
        self,
        weight_type: str,
        contribution_score: float,
        rank: int,
        rates: dict[str, float],
        location_name: str = "",
        influence_bonus: float = 0.0,
        allow_feather: bool = True,
    ) -> dict[str, Any] | None:
        """从首领珍贵战利品池里随机一次。"""

        score = max(0.0, min(1.0, float(contribution_score)))
        rare_bonus_factor = 1.0 + max(0.0, min(0.08, float(influence_bonus)))
        feather_chance = self._feather_chance(weight_type, score, rank, rates, influence_bonus)
        if allow_feather and random.random() < feather_chance:
            return {"kind": "feather"}

        weights = [
            ("material", (max(rates["material_chance"], SEASONAL_LOW_CONTRIBUTION_FLOORS["material"]) + score * 0.10) * rare_bonus_factor),
            ("gem", max(rates["gem_chance"], SEASONAL_LOW_CONTRIBUTION_FLOORS["gem"]) + score * 0.10),
            ("book", (max(rates["book_chance"], SEASONAL_LOW_CONTRIBUTION_FLOORS["book"]) + score * 0.08) * rare_bonus_factor),
            ("weapon", (max(rates["weapon_chance"], SEASONAL_LOW_CONTRIBUTION_FLOORS["weapon"]) + score * 0.06) * rare_bonus_factor),
        ]
        if rank <= 3:
            weights[0] = ("material", weights[0][1] + rates["material_rank_chance"])

        total = sum(max(0.0, weight) for _kind, weight in weights)
        if total <= 0:
            return None
        roll = random.random() * total
        current = 0.0
        kind = "gem"
        for candidate, weight in weights:
            current += max(0.0, weight)
            if roll <= current:
                kind = candidate
                break

        if kind == "feather":
            return {"kind": "feather"}
        if kind == "material":
            item_id = random.choice(("kaikongqi", "xisuiye"))
            item = self.ring_item_def(item_id)
            return {"kind": "material", "item_id": item["ring_item_id"], "name": item["name"]} if item else None
        if kind == "gem":
            item = self._random_equipment_item(RING_CATEGORY_GEM)
            if not item:
                return None
            level = 1 + (1 if random.random() < min(0.25, score) else 0)
            return {"kind": "gem", "item_id": item["ring_item_id"], "name": item["name"], "level": level}
        if kind == "book":
            item = self._random_equipment_item(RING_CATEGORY_BOOK)
            item = self.maybe_upgrade_extreme_book_item(item, location_name, 0.006)
            return {"kind": "book", "item_id": item["ring_item_id"], "name": item["name"]} if item else None
        return {"kind": "weapon", "drop": self.weapon_core.roll_weapon_drop()}

    @staticmethod
    def _feather_chance(
        weight_type: str,
        contribution_score: float,
        rank: int,
        rates: dict[str, float],
        influence_bonus: float = 0.0,
    ) -> float:
        """铭刻之羽独立判定概率；贡献和排名只做小幅修正。"""

        score = max(0.0, min(1.0, float(contribution_score)))
        bonus_factor = 1.0 + max(0.0, min(0.08, float(influence_bonus)))
        chance = max(rates["feather_chance"], SEASONAL_LOW_CONTRIBUTION_FLOORS["feather"])
        chance += score * SEASONAL_FEATHER_SCORE_BONUS
        if rank <= 3:
            chance += rates["feather_rank_chance"]
        if rank == 1 and weight_type == "高权重传统节日":
            chance += rates["feather_rank_chance"]
        return min(SEASONAL_FEATHER_CHANCE_CAP, chance * bonus_factor)

    def _random_equipment_item(self, category: str) -> dict[str, Any] | None:
        """随机纳戒物品，不包含开孔器。"""

        category_key = ring_category_key(category)
        rows = self.db.fetch_all(
            """
            SELECT * FROM ring_item_defs
            WHERE category_key = ?
              AND ring_item_id != 'kaikongqi'
              AND ring_item_id != 'cuifengdan'
              AND ring_item_id NOT LIKE 'extreme_%'
            """,
            (category_key,),
        )
        return random.choice(rows) if rows else None

    def _participants(self, event_id: int) -> list[dict[str, Any]]:
        """读取首领贡献排行。"""

        return self.db.fetch_all(
            """
            SELECT * FROM seasonal_boss_participants
            WHERE event_id = ?
            ORDER BY damage DESC, updated_at ASC
            """,
            (event_id,),
        )

    def _contribution(self, damage: int, event: dict[str, Any]) -> float:
        """计算个人伤害占首领总血量的比例。"""

        max_hp = int(event.get("max_hp") or 0)
        if max_hp <= 0:
            return 0.0
        return max(0.0, min(1.0, int(damage) / max_hp))

    def _world_snapshot(self) -> dict[str, int]:
        """读取近期活跃生态，用于动态难度。"""

        players = self.db.fetch_all("SELECT * FROM players")
        if not players:
            return {"active_count": 1, "median_level": 1, "median_attack": 12, "median_hp": 120}
        levels = sorted(max(1, int(row["level"])) for row in players)
        attacks = []
        hps = []
        for row in players:
            weapon = self.equipped_weapon_row(str(row["client_id"]))
            attacks.append(max(1, int(row["base_attack"]) + self.weapon_attack(weapon)))
            hps.append(max(1, int(row["max_hp"])))
        return {
            "active_count": max(1, len(players)),
            "median_level": int(median(levels)),
            "median_attack": int(median(attacks)),
            "median_hp": int(median(hps)),
        }

    @staticmethod
    def _estimate_challenge_damage(median_attack: int, level: int, boss_defense: int) -> int:
        """估算中位玩家单次挑战伤害。"""

        per_round = damage_after_defense(int(median_attack * 1.25 + level * 2.2), boss_defense)
        return max(25, per_round * 10)

    @staticmethod
    def _business_date() -> date:
        """取当前业务日日期。"""

        return (now() - timedelta(hours=DAY_RESET_HOUR)).date()

    def _boss_for_date(self, value: date) -> tuple[BossDef | None, str, str]:
        """选择指定日期的首领。

        节气、传统节日优先；普通日从代码里的“每日旧愿”首领池稳定轮换。
        """

        special = self._special_boss_for_date(value)
        if special[0]:
            return special
        boss_def = self._daily_boss_for_date(value)
        if boss_def:
            return boss_def, "每日旧愿", "每日旧愿"
        return None, "", ""

    def _special_boss_for_date(self, value: date) -> tuple[BossDef | None, str, str]:
        """只选择节气或传统节日首领；普通日不会兜底。"""

        choices: list[tuple[int, str, str, str]] = []
        term_key = _solar_term_key(value)
        if term_key:
            choices.append((1, "二十四节气", "普通节气", term_key))

        try:
            lunar = LunarDate.fromSolarDate(value.year, value.month, value.day)
            festival_key = LUNAR_FESTIVAL_DATES.get((lunar.month, lunar.day))
            if festival_key:
                weight = "高权重传统节日" if festival_key in HIGH_WEIGHT_FESTIVALS else "普通传统节日"
                priority = 3 if festival_key in HIGH_WEIGHT_FESTIVALS else 2
                choices.append((priority, "传统节日", weight, festival_key))
            tomorrow_lunar = LunarDate.fromSolarDate((value + timedelta(days=1)).year, (value + timedelta(days=1)).month, (value + timedelta(days=1)).day)
            if tomorrow_lunar.month == 1 and tomorrow_lunar.day == 1:
                choices.append((2, "传统节日", "普通传统节日", "chuxi"))
        except ValueError:
            pass

        for _priority, event_type, weight_type, boss_key in sorted(choices, key=lambda item: item[0], reverse=True):
            boss_def = ALL_BOSS_DEFS.get(boss_key)
            if boss_def:
                return boss_def, event_type, weight_type
        return None, "", ""

    def _daily_boss_for_date(self, value: date) -> BossDef | None:
        """普通日按日期稳定轮换一只每日旧愿首领。"""

        daily_bosses = [DAILY_BOSS_DEFS[key] for key in sorted(DAILY_BOSS_DEFS)]
        if not daily_bosses:
            return None
        return daily_bosses[value.toordinal() % len(daily_bosses)]

    def _next_boss_text(self) -> str:
        """展示下一次岁时情劫。"""

        start = self._business_date()
        for offset in range(1, 370):
            day = start + timedelta(days=offset)
            boss_def, event_type, _weight = self._boss_for_date(day)
            if boss_def:
                return f"下一次岁时情劫：{day.isoformat()} · {event_type} · {boss_def.name}，约 {offset} 天后。"
        return "暂未找到下一次岁时情劫。"

    def _format_status(self, event: dict[str, Any]) -> str:
        """格式化当前首领状态。"""

        closes = dt(event["closes_at"])
        left = max(0, int((closes - now()).total_seconds() // 60) + 1) if closes else 0
        extra = "\n今日为人间重节，旧愿尤深，铭刻之羽更易遗落。" if event["weight_type"] == "高权重传统节日" else ""
        location = str(event["location_name"])
        panel = T.panel()
        panel.section(f"今日岁时情劫·{event['boss_name']}")
        panel.line(f"{event['title']}，现于{location}。")
        panel.line(event["scene"])
        panel.line(f"强度：**世界平均水平**｜血量：**{event['hp']}/{event['max_hp']}**｜状态：{event['status']}")
        panel.line(f"剩余约 **{left}** 分钟｜挑战冷却 {SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES} 分钟｜每日最多 {SEASONAL_BOSS_MAX_CHALLENGES} 次")
        panel.line(f"{event['story']}{extra}")
        status = str(event["status"])
        if status == "开启":
            return T.attach(panel.render(), "发送：挑战首领<挑战首领>")
        if status in {"已击破", "已退去"}:
            return T.attach(panel.render(), "发送：首领奖励<首领奖励>")
        return panel.render()


service = SeasonalBossService(db)

__all__ = ["BOSS_DEFS", "SeasonalBossService", "service"]
