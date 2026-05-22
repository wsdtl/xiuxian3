"""武器公共能力。

二级组件如果需要“发初始武器、读取当前武器、生成掉落武器”，统一调用这里。
这样探险、战斗、武器组件之间不会互相引用。
"""

from __future__ import annotations

from .common import CoreService, dump_json, quality_factor, random, random_quality, ts
from .sql import db


class WeaponCore(CoreService):
    """武器实例的基础读写能力。"""

    def ensure_starter_weapon(self, client_id: str) -> None:
        """玩家没有武器时，补一把默认短剑。"""

        exists = self.db.fetch_one("SELECT weapon_id FROM player_weapons WHERE owner_id = ? LIMIT 1", (client_id,))
        if exists:
            return
        self.create_weapon(client_id, "qinglan_duanjian", "凡品", 40, equipped=True)

    def create_drop_weapon(self, client_id: str, player_level: int, location_name: str = "") -> str:
        """直接创建一把掉落武器，并返回展示文本。"""

        drop = self.roll_weapon_drop(player_level, location_name)
        weapon_id = self.create_weapon(
            client_id,
            drop["weapon_def_id"],
            drop["quality"],
            drop["max_level"],
            equipped=False,
        )
        return f"#{weapon_id} {drop['name']}[{drop['quality']}] 上限{drop['max_level']}"

    def roll_weapon_drop(self, player_level: int, location_name: str = "") -> dict:
        """只随机出掉落结果，不写入数据库。

        探险预计算阶段会先记录掉落结果，等玩家发送“结束探险”时再真正发放。
        """

        rows = self.db.fetch_all("SELECT * FROM weapon_defs")
        if location_name:
            same_location = [row for row in rows if row["drop_location"] == location_name]
            rows = same_location or rows
        weapon_def = random.choice(rows)
        return {
            "weapon_def_id": weapon_def["weapon_def_id"],
            "name": weapon_def["name"],
            "quality": random_quality(),
            "max_level": self.random_max_level(player_level),
        }

    def create_weapon(
        self,
        client_id: str,
        weapon_def_id: str,
        quality: str,
        max_level: int,
        equipped: bool = False,
    ) -> int:
        """创建一把玩家真实拥有的武器。"""

        with self.db.transaction() as conn:
            return self.create_weapon_conn(
                conn,
                client_id,
                weapon_def_id,
                quality,
                max_level,
                equipped=equipped,
            )

    def create_weapon_conn(
        self,
        conn,
        client_id: str,
        weapon_def_id: str,
        quality: str,
        max_level: int,
        equipped: bool = False,
    ) -> int:
        """在事务里创建一把玩家真实拥有的武器。"""

        weapon_def = self.db.fetch_one("SELECT * FROM weapon_defs WHERE weapon_def_id = ?", (weapon_def_id,))
        if not weapon_def:
            raise ValueError("武器定义不存在")
        attack = max(1, int(weapon_def["base_attack"] * quality_factor(quality)))
        if equipped:
            conn.execute("UPDATE player_weapons SET equipped = 0 WHERE owner_id = ?", (client_id,))
        cursor = conn.execute(
            """
            INSERT INTO player_weapons
            (owner_id, weapon_def_id, level, max_level, quality, attack, skill_id, enchant_slots, equipped, enchant_effects, created_at)
            VALUES (?, ?, 0, ?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                client_id,
                weapon_def_id,
                max_level,
                quality,
                attack,
                weapon_def["skill_id"],
                1 if equipped else 0,
                dump_json([]),
                ts(),
            ),
        )
        return int(cursor.lastrowid)

    def equipped_weapon(self, client_id: str) -> dict | None:
        """读取玩家当前装备的武器。"""

        self.ensure_starter_weapon(client_id)
        return self.db.fetch_one(
            """
            SELECT w.*, d.name, d.weapon_type
            FROM player_weapons w
            JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
            WHERE w.owner_id = ? AND w.equipped = 1
            LIMIT 1
            """,
            (client_id,),
        )

    def weapons(self, client_id: str) -> list[dict]:
        """读取玩家全部武器。"""

        return self.db.fetch_all(
            """
            SELECT w.*, d.name, d.weapon_type
            FROM player_weapons w
            JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
            WHERE w.owner_id = ?
            ORDER BY w.equipped DESC, w.weapon_id
            """,
            (client_id,),
        )

    def weapon(self, client_id: str, weapon_id: int) -> dict | None:
        """读取玩家某一把武器。"""

        return self.db.fetch_one(
            """
            SELECT w.*, d.name, d.weapon_type
            FROM player_weapons w
            JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
            WHERE w.owner_id = ? AND w.weapon_id = ?
            """,
            (client_id, weapon_id),
        )

    def skill(self, skill_id: str) -> dict:
        """读取武器自带技能；缺失时给一个普通攻击兜底。"""

        return self.db.fetch_one("SELECT * FROM weapon_skill_defs WHERE skill_id = ?", (skill_id,)) or {
            "name": "普通攻击",
            "cost_mp": 0,
            "interval": 99,
            "power": 1.0,
        }

    @staticmethod
    def random_max_level(player_level: int) -> int:
        """按玩家等级随机武器等级上限。"""

        level = int(player_level)
        if level <= 20:
            return random.randint(20, 45)
        if level <= 40:
            return random.randint(35, 65)
        if level <= 60:
            return random.randint(50, 80)
        if level <= 80:
            return random.randint(65, 95)
        return random.randint(80, 100)


service = WeaponCore(db)

__all__ = ["WeaponCore", "service"]
