"""战斗公共结算。

探险和对战都需要战斗计算，所以放在根目录。
二级组件只调用这里，避免“探险引用战斗、对战引用战斗”的组件互绑。
"""

from __future__ import annotations

from .common import CoreService, random, ts
from .rules import damage_after_defense, monster_exp
from .sql import db
from .weapon_core import service as weapon_core


class CombatCore(CoreService):
    """玩家打怪和玩家对战的基础结算。"""

    PLAYER_ACTION_LIMIT = 80
    BOSS_ACTION_LIMIT = 18

    def fight_monster(
        self,
        client_id: str,
        monster: dict,
        start_hp: int | None = None,
        start_mp: int | None = None,
    ) -> dict:
        """玩家和怪物打一场，返回本场摘要和逐次出手日志。"""

        player = self.player(client_id)
        if not player:
            return {"win": False, "summary": "玩家不存在", "exp": 0, "hp_left": 0, "actions": []}

        weapon = weapon_core.equipped_weapon(client_id)
        player_state = self._player_combat_state(
            client_id,
            player,
            weapon,
            hp=int(player["hp"] if start_hp is None else start_hp),
            mp=int(player["mp"] if start_mp is None else start_mp),
        )
        enemy_state = self._enemy_combat_state(
            "monster",
            str(monster["name"]),
            str(monster.get("kind") or "兽"),
            int(monster["level"]),
            int(monster["hp"]),
            int(monster["attack"]),
            int(monster["defense"]),
            boss=False,
        )
        actions = self._run_action_bar_combat(player_state, enemy_state, self.PLAYER_ACTION_LIMIT)
        win = player_state["hp"] > 0 and enemy_state["hp"] <= 0
        mp_left = 0 if player_state["hp"] <= 0 else max(0, int(player_state["mp"]))
        exp = monster_exp(monster["level"], 1.0 if win else 0.25, player["level"])
        summary = (
            f"遭遇 {monster['name']}，行动 {len(actions)} 次，"
            f"{'胜利' if win else '失败'}，技能触发 {player_state['skill_times']} 次，经验+{exp}"
        )
        highest_damage = max((int(action.get("player_total_damage", 0)) for action in actions), default=0)
        return {
            "win": win,
            "summary": summary,
            "exp": exp,
            "hp_left": max(0, int(player_state["hp"])),
            "mp_left": mp_left,
            "weapon_id": int(weapon["weapon_id"]) if weapon else 0,
            "highest_damage": highest_damage,
            "monster": monster["name"],
            "monster_hp_left": max(0, int(enemy_state["hp"])),
            "actions": actions,
            "drop_item_id": monster.get("drop_item_id", "") if win and random.random() <= float(monster.get("drop_chance", 0)) else "",
        }

    def fight_boss(self, player: dict, event: dict, *, boss_kind: str, action_limit: int | None = None) -> dict:
        """玩家挑战虫洞或首领 Boss。

        Boss 与怪物共用行动条和技能条，只是行动次数上限更短，适合一次挑战。
        """

        client_id = player["client_id"]
        weapon_core.ensure_starter_weapon(client_id)
        weapon = weapon_core.equipped_weapon(client_id)
        player_state = self._player_combat_state(
            client_id,
            player,
            weapon,
            hp=int(player["hp"]),
            mp=int(player["mp"]),
        )
        enemy_state = self._enemy_combat_state(
            "boss",
            str(event["boss_name"]),
            boss_kind,
            int(event["level"]),
            int(event["hp"]),
            int(event["attack"]),
            int(event["defense"]),
            max_hp=int(event.get("max_hp", event["hp"])),
            boss=True,
        )
        actions = self._run_action_bar_combat(player_state, enemy_state, action_limit or self.BOSS_ACTION_LIMIT)
        total_damage = max(0, int(event["hp"]) - max(0, int(enemy_state["hp"])))
        mp_left = 0 if player_state["hp"] <= 0 else max(0, int(player_state["mp"]))
        return {
            "damage": max(1, total_damage),
            "hp_left": max(0, int(player_state["hp"])),
            "mp_left": mp_left,
            "skill_times": int(player_state["skill_times"]),
            "boss_skill_times": int(enemy_state["skill_times"]),
            "weapon_id": int(weapon["weapon_id"]) if weapon else 0,
            "highest_damage": max((int(action.get("damage", 0)) for action in actions), default=0),
            "actions": actions,
        }

    def duel(self, left_id: str, right_id: str, write_log: bool = True) -> dict:
        """两个玩家切磋；只算胜负，并返回逐次出手日志。"""

        left = self.player(left_id)
        right = self.player(right_id)
        if not left or not right:
            return {"winner_id": "", "loser_id": "", "summary": "玩家不存在", "actions": []}

        left_weapon = weapon_core.equipped_weapon(left_id)
        right_weapon = weapon_core.equipped_weapon(right_id)
        left_state = self._player_combat_state(left_id, left, left_weapon, hp=int(left["max_hp"]), mp=int(left["max_mp"]))
        right_state = self._player_combat_state(right_id, right, right_weapon, hp=int(right["max_hp"]), mp=int(right["max_mp"]))
        return self._duel_from_states(left_id, right_id, left_state, right_state, left_weapon, right_weapon, write_log)

    def duel_with_snapshot(self, attacker_id: str, defender_snapshot: dict, write_log: bool = False) -> dict:
        """真实玩家和快照玩家对战。

        抢劫探险玩家时，进攻方读取当前真实状态；防守方使用探险开始时写入的战斗快照。
        """

        attacker = self.player(attacker_id)
        defender = defender_snapshot.get("player") if isinstance(defender_snapshot, dict) else None
        if not attacker or not isinstance(defender, dict):
            return {"winner_id": "", "loser_id": "", "summary": "玩家不存在", "actions": []}

        defender_id = str(defender.get("client_id", ""))
        attacker_weapon = weapon_core.equipped_weapon(attacker_id)
        defender_weapon = defender_snapshot.get("weapon") if isinstance(defender_snapshot.get("weapon"), dict) else None
        attacker_state = self._player_combat_state(
            attacker_id,
            attacker,
            attacker_weapon,
            hp=int(attacker["hp"]),
            mp=int(attacker["mp"]),
        )
        defender_state = self._snapshot_player_combat_state(defender_snapshot)
        return self._duel_from_states(
            attacker_id,
            defender_id,
            attacker_state,
            defender_state,
            attacker_weapon,
            defender_weapon,
            write_log,
        )

    def _duel_from_states(
        self,
        left_id: str,
        right_id: str,
        left_state: dict,
        right_state: dict,
        left_weapon: dict | None,
        right_weapon: dict | None,
        write_log: bool,
    ) -> dict:
        """用已经准备好的双方战斗状态结算玩家对战。"""

        rounds = 0
        actions = []

        while left_state["hp"] > 0 and right_state["hp"] > 0 and rounds < 80:
            actor_state, target_state = self._next_actor(left_state, right_state)
            rounds += 1
            side = "left" if actor_state is left_state else "right"
            action = {
                "round": rounds,
                "left": None,
                "right": None,
            }
            action[side] = self._player_vs_player_action(actor_state, target_state)
            actions.append(action)

        left_hp = int(left_state["hp"])
        right_hp = int(right_state["hp"])
        left_mp = int(left_state["mp"])
        right_mp = int(right_state["mp"])
        if left_hp == right_hp:
            winner_id = left_id if random.random() >= 0.5 else right_id
        elif left_hp > right_hp:
            winner_id = left_id
        else:
            winner_id = right_id
        loser_id = right_id if winner_id == left_id else left_id
        if loser_id == left_id:
            left_mp = 0
        else:
            right_mp = 0
        summary = (
            f"{self.format_player_name(left_id)} 对战 {self.format_player_name(right_id)}，"
            f"{rounds} 次行动后 {self.format_player_name(winner_id)} 获胜。"
        )
        left_highest = max(
            (int((action.get("left") or {}).get("damage", 0)) for action in actions),
            default=0,
        )
        right_highest = max(
            (int((action.get("right") or {}).get("damage", 0)) for action in actions),
            default=0,
        )
        if write_log:
            self.db.execute(
                "INSERT INTO combat_logs (client_id, target, summary, created_at) VALUES (?, ?, ?, ?)",
                (left_id, right_id, summary, ts()),
            )
        return {
            "winner_id": winner_id,
            "loser_id": loser_id,
            "summary": summary,
            "rounds": rounds,
            "actions": actions,
            "left_id": left_id,
            "right_id": right_id,
            "left_weapon_id": int(left_weapon["weapon_id"]) if left_weapon else 0,
            "right_weapon_id": int(right_weapon["weapon_id"]) if right_weapon else 0,
            "left_highest_damage": left_highest,
            "right_highest_damage": right_highest,
            "left_hp_left": max(0, left_hp),
            "right_hp_left": max(0, right_hp),
            "left_mp_left": max(0, left_mp),
            "right_mp_left": max(0, right_mp),
            "left_max_hp": int(left_state["max_hp"]),
            "right_max_hp": int(right_state["max_hp"]),
            "left_max_mp": int(left_state["max_mp"]),
            "right_max_mp": int(right_state["max_mp"]),
        }

    def _snapshot_player_combat_state(self, snapshot: dict) -> dict:
        """把探险开始时保存的玩家快照还原成战斗状态。"""

        player = dict(snapshot.get("player") or {})
        weapon = snapshot.get("weapon") if isinstance(snapshot.get("weapon"), dict) else None
        skill = snapshot.get("skill") if isinstance(snapshot.get("skill"), dict) else None
        effects = snapshot.get("effects") if isinstance(snapshot.get("effects"), dict) else {}
        client_id = str(player.get("client_id", ""))
        speed = self._actor_speed(int(player["level"]), weapon, effects)
        return {
            "kind": "player",
            "id": client_id,
            "name": self.format_player_name(client_id),
            "player": player,
            "weapon": weapon,
            "skill": skill,
            "skill_label": str(snapshot.get("skill_label") or (skill or {}).get("name") or ""),
            "effects": effects,
            "hp": int(player["hp"]),
            "max_hp": int(player["max_hp"]),
            "mp": int(player["mp"]),
            "max_mp": int(player["max_mp"]),
            "attack": int(player["base_attack"]) + (int(weapon["attack"]) if weapon else 0),
            "defense": int(player["defense"]),
            "cost": self._skill_cost(skill, effects) if skill else 0,
            "speed": speed,
            "meter": random.uniform(35, 95),
            "charge": self._skill_initial_charge(skill, weapon, effects, speed),
            "charge_gain": self._skill_charge_gain(skill, weapon, effects, speed),
            "guard": False,
            "guard_effects": {},
            "skill_times": 0,
        }

    def _player_combat_state(self, client_id: str, player: dict, weapon: dict | None, *, hp: int, mp: int) -> dict:
        """生成玩家战斗状态。"""

        skill = weapon_core.skill(weapon["skill_id"]) if weapon else None
        effects = self._merge_effects(self.equipment_bonuses(client_id), self._weapon_effects(weapon))
        speed = self._actor_speed(int(player["level"]), weapon, effects)
        return {
            "kind": "player",
            "id": client_id,
            "name": self.format_player_name(client_id),
            "player": player,
            "weapon": weapon,
            "skill": skill,
            "skill_label": weapon_core.weapon_skill_label(int(weapon["weapon_id"]), skill) if weapon and skill else "",
            "effects": effects,
            "hp": int(hp),
            "max_hp": int(player["max_hp"]),
            "mp": int(mp),
            "max_mp": int(player["max_mp"]),
            "attack": int(player["base_attack"]) + (int(weapon["attack"]) if weapon else 0),
            "defense": int(player["defense"]),
            "cost": self._skill_cost(skill, effects) if skill else 0,
            "speed": speed,
            "meter": random.uniform(35, 95),
            "charge": self._skill_initial_charge(skill, weapon, effects, speed),
            "charge_gain": self._skill_charge_gain(skill, weapon, effects, speed),
            "guard": False,
            "guard_effects": {},
            "skill_times": 0,
        }

    def _enemy_combat_state(
        self,
        enemy_id: str,
        name: str,
        kind: str,
        level: int,
        hp: int,
        attack: int,
        defense: int,
        *,
        max_hp: int | None = None,
        boss: bool,
    ) -> dict:
        """生成怪物或 Boss 战斗状态。"""

        skill = self._enemy_skill(kind, level, boss=boss)
        speed = self._enemy_speed(level, kind, boss=boss)
        hp_max = int(hp if max_hp is None else max_hp)
        return {
            "kind": "enemy",
            "id": enemy_id,
            "name": name,
            "enemy_kind": kind,
            "level": int(level),
            "skill": skill,
            "skill_label": str(skill["name"]),
            "effects": dict(skill.get("effects") or {}),
            "hp": int(hp),
            "max_hp": hp_max,
            "mp": 0,
            "max_mp": 0,
            "attack": int(attack),
            "defense": int(defense),
            "cost": 0,
            "speed": speed,
            "meter": random.uniform(30, 85),
            "charge": self._enemy_skill_initial_charge(skill, speed),
            "charge_gain": self._enemy_skill_charge_gain(skill, speed),
            "guard": False,
            "guard_effects": {},
            "skill_times": 0,
            "boss": bool(boss),
        }

    @staticmethod
    def _next_actor(left: dict, right: dict) -> tuple[dict, dict]:
        """推进行动条，返回这次出手者和目标。"""

        while True:
            left["meter"] += left["speed"]
            right["meter"] += right["speed"]
            ready = [state for state in (left, right) if state["meter"] >= 100]
            if not ready:
                continue
            actor = max(ready, key=lambda state: (state["meter"], state["speed"], random.random()))
            target = right if actor is left else left
            actor["meter"] -= 100
            return actor, target

    def _run_action_bar_combat(self, player_state: dict, enemy_state: dict, action_limit: int) -> list[dict]:
        """按行动条跑玩家和敌方战斗。"""

        actions: list[dict] = []
        while player_state["hp"] > 0 and enemy_state["hp"] > 0 and len(actions) < action_limit:
            actor, target = self._next_actor(player_state, enemy_state)
            action_no = len(actions) + 1
            if actor is player_state:
                actions.append(self._player_vs_enemy_action(action_no, actor, target))
            else:
                actions.append(self._enemy_vs_player_action(action_no, actor, target))
        return actions

    def _skill_ready(self, actor: dict, *, enemy: bool = False) -> bool:
        """推进技能条，并判断本次是否释放技能。"""

        actor["charge"] += actor["charge_gain"]
        skill = actor.get("skill")
        if not skill or actor["charge"] < 1:
            actor["guard"] = False
            actor["guard_effects"] = {}
            return False
        if int(actor.get("mp", 0)) < int(actor.get("cost", 0)):
            actor["guard"] = False
            actor["guard_effects"] = {}
            return False
        actor["mp"] -= int(actor.get("cost", 0))
        actor["charge"] = max(0.0, float(actor["charge"]) - 1.0)
        actor["skill_times"] = int(actor.get("skill_times", 0)) + 1
        actor["guard"] = True
        return True

    def _player_damage_parts(
        self,
        actor: dict,
        target: dict,
        effects: dict[str, float],
        skill_used: bool,
    ) -> tuple[int, int, int, int]:
        """计算玩家本次出手的基础伤害。

        返回值依次是：
        - raw：原始攻击值。
        - damage：扣防御后的主伤害。
        - combo_damage：连击追加伤害。
        - total_damage：主伤害 + 连击伤害，尚未计算护身和流血灼烧。
        """

        raw = self._attack_raw(int(actor["attack"]), int(actor["player"]["level"]), effects)
        if skill_used:
            raw = int(raw * self._skill_power(actor["skill"], effects))

        damage = damage_after_defense(raw, int(target["defense"]), self._pierce_rate(effects))
        combo_damage = self._combo_damage(raw, int(target["defense"]), effects)
        return raw, damage, combo_damage, damage + combo_damage

    @staticmethod
    def _enemy_damage_raw(actor: dict, target: dict, effects: dict[str, float], skill_used: bool) -> int:
        """计算怪物或 Boss 本次出手的扣防御伤害。"""

        attack = int(actor["attack"])
        raw = random.randint(max(1, int(attack * 0.78)), max(1, int(attack * 1.18)))
        if skill_used:
            raw = int(raw * float(actor["skill"].get("power", 1.0)))
        return damage_after_defense(raw, int(target["defense"]), float(effects.get("pierce_bonus", 0)))

    def _apply_hit_effects(
        self,
        actor: dict,
        target: dict,
        damage: int,
        heal_effects: dict[str, float],
        extra_effects: dict[str, float],
    ) -> dict[str, int]:
        """结算一次命中后的真实效果。

        damage 是已经经过防御和护身后的伤害。
        heal_effects 用来算攻击方回血；extra_effects 用来算目标受到的额外影响。
        """

        target["hp"] -= damage
        life_steal = self._heal_from_damage(actor, damage, heal_effects)
        mp_suppressed = self._suppress_target_mp(target, extra_effects)
        meter_reduced = self._reduce_target_meter(target, extra_effects)
        burn_damage = self._extra_hp_damage(target, extra_effects, "burn_rate", 0.035)
        bleed_damage = self._extra_hp_damage(target, extra_effects, "bleed_rate", 0.03)
        total_damage = damage + burn_damage + bleed_damage

        if target["hp"] <= 0:
            target["mp"] = 0

        return {
            "total_damage": total_damage,
            "life_steal": life_steal,
            "mp_suppressed": mp_suppressed,
            "meter_reduced": meter_reduced,
            "burn_damage": burn_damage,
            "bleed_damage": bleed_damage,
        }

    def _activate_guard_effects(self, actor: dict, skill_used: bool, skill_effects: dict[str, float]) -> dict[str, float]:
        """记录本次技能给自己留下的临时防守效果。"""

        actor["guard_effects"] = skill_effects if skill_used else {}
        return {
            "self_guard_rate": self._guard_rate(actor) if skill_used else 0,
            "self_dodge_rate": float(skill_effects.get("dodge_bonus", 0)) if skill_used else 0,
        }

    @staticmethod
    def _empty_hit_effects() -> dict[str, int]:
        """生成未命中或未造成附加效果时使用的空结果。"""

        return {
            "total_damage": 0,
            "life_steal": 0,
            "mp_suppressed": 0,
            "meter_reduced": 0,
            "burn_damage": 0,
            "bleed_damage": 0,
        }

    def _player_vs_enemy_action(self, action_no: int, actor: dict, target: dict) -> dict:
        """结算玩家打怪或打 Boss 的一次行动。"""

        skill_used = self._skill_ready(actor)
        skill_effects = self._weapon_skill_effects(actor["skill"]) if skill_used else {}
        merged_effects = self._merge_effects(actor["effects"], skill_effects)
        raw, damage, combo_damage, total_damage = self._player_damage_parts(actor, target, merged_effects, skill_used)
        guard_reduce_rate = self._guard_rate(target) if bool(target["guard"]) else 0
        total_damage = self._damage_after_guard(total_damage, target)
        hit_effects = self._apply_hit_effects(actor, target, total_damage, merged_effects, skill_effects)
        guard_effects = self._activate_guard_effects(actor, skill_used, skill_effects)
        total_damage = hit_effects["total_damage"]
        return {
            "round": action_no,
            "actor": "player",
            "raw": raw,
            "damage": total_damage,
            "player_raw": raw,
            "player_damage": damage,
            "player_total_damage": total_damage,
            "combo_damage": combo_damage,
            "life_steal": hit_effects["life_steal"],
            "mp_suppressed": hit_effects["mp_suppressed"],
            "meter_reduced": hit_effects["meter_reduced"],
            "burn_damage": hit_effects["burn_damage"],
            "bleed_damage": hit_effects["bleed_damage"],
            "skill_effects": skill_effects,
            "guard_reduce_rate": guard_reduce_rate,
            "self_guard_rate": guard_effects["self_guard_rate"],
            "self_dodge_rate": guard_effects["self_dodge_rate"],
            "skill_used": skill_used,
            "skill_name": actor["skill_label"] if skill_used else "",
            "mp_cost": int(actor["cost"]) if skill_used else 0,
            "monster_hp_left": max(0, int(target["hp"])),
            "monster_hp_max": int(target["max_hp"]),
            "boss_hp_left": max(0, int(target["hp"])),
            "boss_hp_max": int(target["max_hp"]),
            "monster_attack": False,
            "boss_attack": False,
            "monster_damage": 0,
            "boss_damage": 0,
            "player_hp_left": max(0, int(actor["hp"])),
            "player_mp_left": max(0, int(actor["mp"])),
            "dodged": False,
            "player_speed": round(float(actor["speed"]), 1),
            "enemy_speed": round(float(target["speed"]), 1),
        }

    def _enemy_vs_player_action(self, action_no: int, actor: dict, target: dict) -> dict:
        """结算怪物或 Boss 的一次行动。"""

        skill_used = self._skill_ready(actor, enemy=True)
        skill_effects = dict(actor["effects"]) if skill_used else {}
        dodged = random.random() < min(0.55, float(self._defense_effects(target).get("dodge_bonus", 0)))
        hurt_raw = 0
        hit_effects = self._empty_hit_effects()
        guard_reduce_rate = self._guard_rate(target) if bool(target["guard"]) else 0
        if not dodged:
            hurt_raw = self._enemy_damage_raw(actor, target, skill_effects, skill_used)
            hurt = self._damage_after_guard(hurt_raw, target)
            hit_effects = self._apply_hit_effects(actor, target, hurt, {}, skill_effects)
        guard_effects = self._activate_guard_effects(actor, skill_used, skill_effects)
        hurt = hit_effects["total_damage"]
        return {
            "round": action_no,
            "actor": "enemy",
            "enemy_skill_used": skill_used,
            "enemy_skill_name": actor["skill_label"] if skill_used else "",
            "boss_skill_used": skill_used,
            "boss_skill_name": actor["skill_label"] if skill_used else "",
            "monster_skill_used": skill_used,
            "monster_skill_name": actor["skill_label"] if skill_used else "",
            "monster_attack": True,
            "boss_attack": True,
            "monster_damage": max(0, hurt),
            "boss_damage": max(0, hurt),
            "monster_hurt_raw": max(0, hurt_raw),
            "boss_hurt_raw": max(0, hurt_raw),
            "mp_suppressed": hit_effects["mp_suppressed"],
            "meter_reduced": hit_effects["meter_reduced"],
            "burn_damage": hit_effects["burn_damage"],
            "bleed_damage": hit_effects["bleed_damage"],
            "skill_effects": skill_effects,
            "guard_reduce_rate": guard_reduce_rate,
            "self_guard_rate": guard_effects["self_guard_rate"],
            "monster_hp_left": max(0, int(actor["hp"])),
            "monster_hp_max": int(actor["max_hp"]),
            "boss_hp_left": max(0, int(actor["hp"])),
            "boss_hp_max": int(actor["max_hp"]),
            "player_hp_left": max(0, int(target["hp"])),
            "player_mp_left": max(0, int(target["mp"])),
            "dodged": dodged,
            "player_speed": round(float(target["speed"]), 1),
            "enemy_speed": round(float(actor["speed"]), 1),
        }

    def _player_vs_player_action(self, actor: dict, target: dict) -> dict:
        """结算玩家对玩家的一次行动。"""

        skill_used = self._skill_ready(actor)
        skill_effects = self._weapon_skill_effects(actor["skill"]) if skill_used else {}
        dodged = random.random() < float(self._defense_effects(target).get("dodge_bonus", 0))
        if dodged:
            guard_effects = self._activate_guard_effects(actor, skill_used, skill_effects)
            return self._duel_action_result(
                actor,
                target,
                skill_used,
                0,
                0,
                0,
                0,
                True,
                {
                    "skill_effects": skill_effects,
                    "self_guard_rate": guard_effects["self_guard_rate"],
                    "self_dodge_rate": guard_effects["self_dodge_rate"],
                },
                0,
            )

        merged_effects = self._merge_effects(actor["effects"], skill_effects)
        raw, base_damage, combo_damage, before_reduce = self._player_damage_parts(actor, target, merged_effects, skill_used)
        guard_reduce_rate = self._guard_rate(target) if bool(target["guard"]) else 0
        final_damage = self._damage_after_guard(before_reduce, target)
        hit_effects = self._apply_hit_effects(actor, target, final_damage, merged_effects, merged_effects)
        guard_effects = self._activate_guard_effects(actor, skill_used, skill_effects)
        extras = {
            "mp_suppressed": hit_effects["mp_suppressed"],
            "meter_reduced": hit_effects["meter_reduced"],
            "burn_damage": hit_effects["burn_damage"],
            "bleed_damage": hit_effects["bleed_damage"],
            "skill_effects": skill_effects,
            "guard_reduce_rate": guard_reduce_rate,
            "self_guard_rate": guard_effects["self_guard_rate"],
            "self_dodge_rate": guard_effects["self_dodge_rate"],
        }
        return self._duel_action_result(
            actor,
            target,
            skill_used,
            hit_effects["total_damage"],
            combo_damage,
            hit_effects["life_steal"],
            raw,
            False,
            extras,
            before_reduce,
        )

    @staticmethod
    def _duel_action_result(
        actor: dict,
        target: dict,
        skill_used: bool,
        damage: int,
        combo_damage: int,
        life_steal: int,
        raw: int,
        dodged: bool,
        extras: dict | None = None,
        before_reduce: int = 0,
    ) -> dict:
        """整理玩家对战的一次出手结果。"""

        result = {
            "actor_id": actor["id"],
            "target_id": target["id"],
            "skill_used": skill_used,
            "skill_name": actor["skill_label"] if skill_used else "",
            "mp_cost": int(actor["cost"]) if skill_used else 0,
            "raw": raw,
            "damage": damage,
            "combo_damage": combo_damage,
            "life_steal": life_steal,
            "target_hp_left": max(0, int(target["hp"])),
            "target_mp_left": max(0, int(target["mp"])),
            "actor_hp_left": max(0, int(actor["hp"])),
            "actor_mp_left": max(0, int(actor["mp"])),
            "dodged": dodged,
            "actor_speed": round(float(actor["speed"]), 1),
            "target_speed": round(float(target["speed"]), 1),
            "before_reduce": before_reduce,
        }
        if extras:
            result.update(extras)
        return result

    @staticmethod
    def _weapon_skill_effects(skill: dict | None) -> dict[str, float]:
        """武器自带技能的真实战斗效果。

        weapon_skill_defs 里只有文案、消耗、速度和倍率。
        这里按 skill_id 补上真正结算效果，避免“回春刺”等技能只有名字好看。
        """

        if not skill:
            return {}
        return {
            "bengshan": {"pierce_bonus": 0.06},
            "huichun": {"life_steal": 0.08},
            "shaying": {"combo_bonus": 0.18, "combo_damage_bonus": 0.10},
            "zhuixing": {"combo_bonus": 0.25, "combo_damage_bonus": 0.18},
            "xueying": {"life_steal": 0.12},
            "pojun": {"pierce_bonus": 0.12},
            "liehun": {"mp_suppress": 0.10},
            "yueshi": {"defense_suppress": 0.10},
            "xuandun": {"shield_bonus": 0.16},
            "zhenyue": {"damage_reduce": 0.10},
            "duannian": {"mp_suppress": 0.14},
            "chuanyun": {"pierce_bonus": 0.14},
            "liuguang": {"hit_bonus": 0.10, "pierce_bonus": 0.04},
            "xingluo": {"combo_bonus": 0.20, "combo_damage_bonus": 0.22},
            "jueying": {"dodge_bonus": 0.06},
        }.get(str(skill.get("skill_id") or ""), {})

    @staticmethod
    def _heal_from_damage(actor: dict, damage: int, effects: dict[str, float]) -> int:
        """按吸血效果回血，并返回实际回血量。"""

        rate = min(0.35, float(effects.get("life_steal", 0)))
        if rate <= 0:
            return 0

        before = int(actor["hp"])
        actor["hp"] = min(int(actor["max_hp"]), before + int(max(0, damage) * rate))
        return max(0, int(actor["hp"]) - before)

    def _suppress_target_mp(self, target: dict, effects: dict[str, float]) -> int:
        """按精神压制扣除目标精神，并返回实际扣除值。"""

        before = int(target.get("mp", 0))
        target["mp"] = self._suppress_mp(before, int(target.get("max_mp", 0)), effects)
        return max(0, before - int(target["mp"]))

    @staticmethod
    def _reduce_target_meter(target: dict, effects: dict[str, float]) -> int:
        """按眩晕/冲撞类效果压低目标行动条。"""

        rate = min(0.35, float(effects.get("stun_rate", 0)))
        if rate <= 0:
            return 0

        value = int(100 * rate)
        target["meter"] -= value
        return value

    @staticmethod
    def _extra_hp_damage(target: dict, effects: dict[str, float], key: str, factor: float) -> int:
        """结算灼烧/流血这类额外血气伤害。"""

        rate = float(effects.get(key, 0))
        if rate <= 0:
            return 0

        damage = max(1, int(int(target["max_hp"]) * rate * factor))
        target["hp"] -= damage
        return damage

    @staticmethod
    def _guard_rate(actor: dict) -> float:
        """读取本次技能后能提供的承伤比例。"""

        effects = CombatCore._defense_effects(actor)
        return min(
            0.7,
            float(effects.get("damage_reduce", 0))
            + float(effects.get("crit_resist_bonus", 0))
            + float(effects.get("shield_bonus", 0)),
        )

    def _damage_after_guard(self, damage: int, target: dict) -> int:
        """按目标当前护身状态减伤，并在本次受击后消耗护身状态。"""

        effects = self._defense_effects(target)
        final_damage = self._reduce_damage(damage, effects, bool(target["guard"]))
        target["guard"] = False
        target["guard_effects"] = {}
        return final_damage

    @staticmethod
    def _defense_effects(actor: dict) -> dict[str, float]:
        """读取防守侧当前生效的常驻效果和临时护身效果。"""

        effects = actor["effects"]
        if actor.get("guard") and isinstance(actor.get("guard_effects"), dict):
            return CoreService._merge_effects(effects, actor["guard_effects"])
        return effects

    @staticmethod
    def action_effect_text(action: dict) -> str:
        """把本次出手真正生效的额外效果整理成日志文本。"""

        texts = []
        effects = action.get("skill_effects")
        if not isinstance(effects, dict):
            effects = {}
        if float(effects.get("hit_bonus", 0)) > 0:
            texts.append(f"命中稳定 +{int(float(effects['hit_bonus']) * 100)}%")
        if float(effects.get("pierce_bonus", 0)) > 0:
            texts.append(f"防御穿透 +{int(float(effects['pierce_bonus']) * 100)}%")
        if float(effects.get("defense_suppress", 0)) > 0:
            texts.append(f"压低防御 +{int(float(effects['defense_suppress']) * 100)}%")
        if float(action.get("self_dodge_rate", 0)) > 0:
            texts.append(f"获得闪避 +{int(float(action['self_dodge_rate']) * 100)}%")
        if int(action.get("mp_suppressed", 0)) > 0:
            texts.append(f"精神压制 -{int(action['mp_suppressed'])}")
        if int(action.get("meter_reduced", 0)) > 0:
            texts.append(f"行动条 -{int(action['meter_reduced'])}")
        if int(action.get("burn_damage", 0)) > 0:
            texts.append(f"灼烧 {int(action['burn_damage'])}")
        if int(action.get("bleed_damage", 0)) > 0:
            texts.append(f"流血 {int(action['bleed_damage'])}")
        if float(action.get("guard_reduce_rate", 0)) > 0:
            texts.append(f"护身减伤 {int(float(action['guard_reduce_rate']) * 100)}%")
        if float(action.get("self_guard_rate", 0)) > 0:
            texts.append(f"获得护身 {int(float(action['self_guard_rate']) * 100)}%")
        return "，".join(texts)

service = CombatCore(db)

__all__ = ["CombatCore", "service"]
