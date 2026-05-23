"""战斗公共结算。

探险和对战都需要战斗计算，所以放在根目录。
二级组件只调用这里，避免“探险引用战斗、对战引用战斗”的组件互绑。
"""

from __future__ import annotations

from .common import CoreService, random, ts
from .constants import MAX_COMBAT_ROUNDS
from .rules import damage_after_defense, monster_exp
from .sql import db
from .weapon_core import service as weapon_core


class CombatCore(CoreService):
    """玩家打怪和玩家对战的基础结算。"""

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
        skill = weapon_core.skill(weapon["skill_id"]) if weapon else None
        effects = self._merge_effects(self.equipment_bonuses(client_id), self._weapon_effects(weapon))
        skill_interval = self._skill_interval(skill, weapon, effects) if skill else 0
        skill_cost = self._skill_cost(skill, effects) if skill else 0

        hp = int(player["hp"] if start_hp is None else start_hp)
        mp = int(player["mp"] if start_mp is None else start_mp)
        monster_hp = int(monster["hp"])
        rounds = 0
        skill_times = 0
        player_attack = int(player["base_attack"]) + (int(weapon["attack"]) if weapon else 0)
        actions = []

        while hp > 0 and monster_hp > 0 and rounds < MAX_COMBAT_ROUNDS:
            rounds += 1
            raw = self._attack_raw(player_attack, int(player["level"]), effects)
            skill_used = False
            skill_name = ""
            if skill and skill_interval and rounds % skill_interval == 0:
                if mp >= skill_cost:
                    raw = int(raw * self._skill_power(skill, effects))
                    mp -= skill_cost
                    skill_used = True
                    skill_times += 1
                    skill_name = str(skill["name"])
            damage = damage_after_defense(raw, monster["defense"], self._pierce_rate(effects))
            combo_damage = self._combo_damage(raw, monster["defense"], effects)
            total_damage = damage + combo_damage
            monster_hp = max(0, monster_hp - total_damage)
            hp_before_steal = hp
            if effects.get("life_steal"):
                hp = min(int(player["max_hp"]), hp + int(total_damage * effects["life_steal"]))
            action = {
                "round": rounds,
                "player_raw": raw,
                "player_damage": damage,
                "combo_damage": combo_damage,
                "player_total_damage": total_damage,
                "skill_used": skill_used,
                "skill_name": skill_name,
                "mp_cost": skill_cost if skill_used else 0,
                "player_hp_after_steal": hp,
                "life_steal": max(0, hp - hp_before_steal),
                "monster_hp_left": monster_hp,
                "monster_hp_max": int(monster["hp"]),
                "monster_attack": False,
                "monster_damage": 0,
                "monster_hurt_raw": 0,
                "player_hp_left": hp,
                "player_mp_left": mp,
                "dodged": False,
            }
            if monster_hp <= 0:
                actions.append(action)
                break
            if random.random() >= effects.get("dodge_bonus", 0):
                hurt = damage_after_defense(monster["attack"], player["defense"])
                reduced_hurt = self._reduce_damage(hurt, effects, skill_used)
                hp -= reduced_hurt
                action["monster_attack"] = True
                action["monster_hurt_raw"] = hurt
                action["monster_damage"] = reduced_hurt
            else:
                action["dodged"] = True
            action["player_hp_left"] = max(0, hp)
            action["player_mp_left"] = 0 if hp <= 0 else max(0, mp)
            actions.append(action)

        win = hp > 0 and monster_hp <= 0
        mp_left = 0 if hp <= 0 else max(0, mp)
        exp = monster_exp(monster["level"], 1.0 if win else 0.25, player["level"])
        summary = (
            f"遭遇 {monster['name']}，战斗 {rounds} 回合，"
            f"{'胜利' if win else '失败'}，技能触发 {skill_times} 次，经验+{exp}"
        )
        return {
            "win": win,
            "summary": summary,
            "exp": exp,
            "hp_left": max(0, hp),
            "mp_left": mp_left,
            "monster": monster["name"],
            "monster_hp_left": max(0, monster_hp),
            "actions": actions,
            "drop_item_id": monster["drop_item_id"] if win and random.random() <= monster["drop_chance"] else "",
        }

    def duel(self, left_id: str, right_id: str, write_log: bool = True) -> dict:
        """两个玩家切磋；只算胜负，并返回逐回合日志。"""

        left = self.player(left_id)
        right = self.player(right_id)
        if not left or not right:
            return {"winner_id": "", "loser_id": "", "summary": "玩家不存在", "actions": []}

        left_weapon = weapon_core.equipped_weapon(left_id)
        right_weapon = weapon_core.equipped_weapon(right_id)
        left_skill = weapon_core.skill(left_weapon["skill_id"]) if left_weapon else None
        right_skill = weapon_core.skill(right_weapon["skill_id"]) if right_weapon else None
        left_effects = self._merge_effects(self.equipment_bonuses(left_id), self._weapon_effects(left_weapon))
        right_effects = self._merge_effects(self.equipment_bonuses(right_id), self._weapon_effects(right_weapon))
        left_hp = int(left["max_hp"])
        right_hp = int(right["max_hp"])
        left_mp = int(left["max_mp"])
        right_mp = int(right["max_mp"])
        left_interval = self._skill_interval(left_skill, left_weapon, left_effects) if left_skill else 0
        right_interval = self._skill_interval(right_skill, right_weapon, right_effects) if right_skill else 0
        left_cost = self._skill_cost(left_skill, left_effects) if left_skill else 0
        right_cost = self._skill_cost(right_skill, right_effects) if right_skill else 0
        left_attack = int(left["base_attack"]) + (int(left_weapon["attack"]) if left_weapon else 0)
        right_attack = int(right["base_attack"]) + (int(right_weapon["attack"]) if right_weapon else 0)
        rounds = 0
        actions = []

        while left_hp > 0 and right_hp > 0 and rounds < 60:
            rounds += 1
            left_skill_used = bool(left_skill and left_interval and rounds % left_interval == 0 and left_mp >= left_cost)
            right_skill_used = bool(right_skill and right_interval and rounds % right_interval == 0 and right_mp >= right_cost)
            if left_skill_used:
                left_mp -= left_cost
            if right_skill_used:
                right_mp -= right_cost
            action = {
                "round": rounds,
                "left": None,
                "right": None,
            }

            if random.random() >= right_effects.get("dodge_bonus", 0):
                left_raw = self._attack_raw(left_attack, int(left["level"]), left_effects)
                if left_skill_used:
                    left_raw = int(left_raw * self._skill_power(left_skill, left_effects))
                left_base_damage = damage_after_defense(left_raw, right["defense"], self._pierce_rate(left_effects))
                left_combo_damage = self._combo_damage(left_raw, right["defense"], left_effects)
                left_before_reduce = left_base_damage + left_combo_damage
                left_final_damage = self._reduce_damage(left_before_reduce, right_effects, right_skill_used)
                right_hp -= left_final_damage
                right_mp = self._suppress_mp(right_mp, int(right["max_mp"]), left_effects)
                left_steal = 0
                if left_effects.get("life_steal"):
                    before_steal = left_hp
                    left_hp = min(int(left["max_hp"]), left_hp + int(left_before_reduce * left_effects["life_steal"]))
                    left_steal = max(0, left_hp - before_steal)
                if right_hp <= 0:
                    right_mp = 0
                action["left"] = {
                    "actor_id": left_id,
                    "target_id": right_id,
                    "skill_used": left_skill_used,
                    "skill_name": str(left_skill["name"]) if left_skill_used and left_skill else "",
                    "mp_cost": left_cost if left_skill_used else 0,
                    "damage": left_final_damage,
                    "combo_damage": left_combo_damage,
                    "life_steal": left_steal,
                    "target_hp_left": max(0, right_hp),
                    "target_mp_left": max(0, right_mp),
                    "actor_hp_left": max(0, left_hp),
                    "actor_mp_left": max(0, left_mp),
                    "dodged": False,
                }
            else:
                action["left"] = {
                    "actor_id": left_id,
                    "target_id": right_id,
                    "skill_used": left_skill_used,
                    "skill_name": str(left_skill["name"]) if left_skill_used and left_skill else "",
                    "mp_cost": left_cost if left_skill_used else 0,
                    "damage": 0,
                    "combo_damage": 0,
                    "life_steal": 0,
                    "target_hp_left": max(0, right_hp),
                    "target_mp_left": max(0, right_mp),
                    "actor_hp_left": max(0, left_hp),
                    "actor_mp_left": max(0, left_mp),
                    "dodged": True,
                }

            if right_hp <= 0:
                actions.append(action)
                break

            if random.random() >= left_effects.get("dodge_bonus", 0):
                right_raw = self._attack_raw(right_attack, int(right["level"]), right_effects)
                if right_skill_used:
                    right_raw = int(right_raw * self._skill_power(right_skill, right_effects))
                right_base_damage = damage_after_defense(right_raw, left["defense"], self._pierce_rate(right_effects))
                right_combo_damage = self._combo_damage(right_raw, left["defense"], right_effects)
                right_before_reduce = right_base_damage + right_combo_damage
                right_final_damage = self._reduce_damage(right_before_reduce, left_effects, left_skill_used)
                left_hp -= right_final_damage
                left_mp = self._suppress_mp(left_mp, int(left["max_mp"]), right_effects)
                right_steal = 0
                if right_effects.get("life_steal"):
                    before_steal = right_hp
                    right_hp = min(int(right["max_hp"]), right_hp + int(right_before_reduce * right_effects["life_steal"]))
                    right_steal = max(0, right_hp - before_steal)
                if left_hp <= 0:
                    left_mp = 0
                action["right"] = {
                    "actor_id": right_id,
                    "target_id": left_id,
                    "skill_used": right_skill_used,
                    "skill_name": str(right_skill["name"]) if right_skill_used and right_skill else "",
                    "mp_cost": right_cost if right_skill_used else 0,
                    "damage": right_final_damage,
                    "combo_damage": right_combo_damage,
                    "life_steal": right_steal,
                    "target_hp_left": max(0, left_hp),
                    "target_mp_left": max(0, left_mp),
                    "actor_hp_left": max(0, right_hp),
                    "actor_mp_left": max(0, right_mp),
                    "dodged": False,
                }
            else:
                action["right"] = {
                    "actor_id": right_id,
                    "target_id": left_id,
                    "skill_used": right_skill_used,
                    "skill_name": str(right_skill["name"]) if right_skill_used and right_skill else "",
                    "mp_cost": right_cost if right_skill_used else 0,
                    "damage": 0,
                    "combo_damage": 0,
                    "life_steal": 0,
                    "target_hp_left": max(0, left_hp),
                    "target_mp_left": max(0, left_mp),
                    "actor_hp_left": max(0, right_hp),
                    "actor_mp_left": max(0, right_mp),
                    "dodged": True,
                }
            actions.append(action)

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
            f"{rounds} 回合后 {self.format_player_name(winner_id)} 获胜。"
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
            "left_hp_left": max(0, left_hp),
            "right_hp_left": max(0, right_hp),
            "left_mp_left": max(0, left_mp),
            "right_mp_left": max(0, right_mp),
            "left_max_hp": int(left["max_hp"]),
            "right_max_hp": int(right["max_hp"]),
            "left_max_mp": int(left["max_mp"]),
            "right_max_mp": int(right["max_mp"]),
        }

service = CombatCore(db)

__all__ = ["CombatCore", "service"]
