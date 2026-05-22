"""可使用物品效果。

背包和纳戒都会用到“使用物品”，所以效果结算放在根目录公共模块。
"""

from __future__ import annotations

import sqlite3

from .common import CoreService, hint, load_json, money, random
from .sql import db


class ItemEffectService(CoreService):
    """结算经验、源石、血气、精神和洗髓这几类使用效果。"""

    def apply(self, client_id: str, item_def: dict, source: str) -> str:
        """使用一个物品，并把效果写回玩家。"""

        with self.db.transaction() as conn:
            return self.apply_conn(conn, client_id, item_def, source)

    def apply_conn(self, conn: sqlite3.Connection, client_id: str, item_def: dict, source: str) -> str:
        """在当前事务里结算物品效果。"""

        player = conn.execute("SELECT * FROM players WHERE client_id = ?", (client_id,)).fetchone()
        if not player:
            return hint("你还没有创建用户。", "发送：创建用户 名称，例如：创建用户 青衫客")

        effect = load_json(item_def["effect"], {})
        texts: list[str] = []

        exp_delta = int(effect.get("exp_delta") or 0)
        if effect.get("random_exp_min") is not None:
            exp_delta += random.randint(int(effect["random_exp_min"]), int(effect["random_exp_max"]))
        if exp_delta:
            old, new = self.add_exp_conn(conn, client_id, exp_delta)
            texts.append(f"经验+{exp_delta}")
            if new > old:
                texts.append(f"等级提升到 {new}")

        stones_delta = int(effect.get("source_stones_delta") or 0)
        if effect.get("random_stones_segments"):
            stones_delta += self._random_stones_by_level(effect["random_stones_segments"], player["level"])
        if effect.get("random_stones_min") is not None:
            stones_delta += random.randint(int(effect["random_stones_min"]), int(effect["random_stones_max"]))
        if stones_delta:
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (stones_delta, client_id),
            )
            texts.append(f"源石+{money(stones_delta)}")

        hp_delta = int(effect.get("hp_delta") or 0)
        mp_delta = int(effect.get("mp_delta") or 0)
        hp_ratio = float(effect.get("hp_ratio") or 0)
        mp_ratio = float(effect.get("mp_ratio") or 0)
        if hp_delta or mp_delta or hp_ratio or mp_ratio:
            player = conn.execute("SELECT * FROM players WHERE client_id = ?", (client_id,)).fetchone() or player
            hp_add = hp_delta + int(player["max_hp"] * hp_ratio)
            mp_add = mp_delta + int(player["max_mp"] * mp_ratio)
            new_hp = min(player["max_hp"], player["hp"] + hp_add)
            new_mp = min(player["max_mp"], player["mp"] + mp_add)
            conn.execute(
                "UPDATE players SET hp = ?, mp = ? WHERE client_id = ?",
                (new_hp, new_mp, client_id),
            )
            if hp_add:
                texts.append(f"血气+{hp_add}")
            if mp_add:
                texts.append(f"精神+{mp_add}")

        if effect.get("wash_physique"):
            texts.append(self._wash_physique_conn(conn, client_id))

        conn.execute(
            "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '使用物品', ?, datetime('now', 'localtime'))",
            (client_id, f"{source}:{item_def['name']}"),
        )
        return f"使用 {item_def['name']} 成功：" + ("，".join(texts) if texts else "暂无效果。")

    def _wash_physique_conn(self, conn: sqlite3.Connection, client_id: str) -> str:
        """使用洗髓液重置体质。

        规则很直接：大概率从更高体质里抽，小概率从更低体质里抽。
        抽完后同步写入 physique_id 和 physique，再重算玩家面板数值。
        """

        rows = [
            dict(row)
            for row in conn.execute(
                """
                SELECT physique_id, name, grade, kind, level, physique_value, desc
                FROM physique_defs
                ORDER BY level, physique_value, name
                """
            ).fetchall()
        ]
        if not rows:
            return "体质库为空，暂时无法洗髓"

        player = conn.execute(
            "SELECT physique_id, physique FROM players WHERE client_id = ?",
            (client_id,),
        ).fetchone()
        if not player:
            return "玩家不存在"

        current = self._find_physique(rows, player["physique_id"]) or rows[0]
        target = self._choose_wash_target(rows, current)
        old_value = int(current["physique_value"])
        new_value = int(target["physique_value"])

        conn.execute(
            "UPDATE players SET physique_id = ?, physique = ? WHERE client_id = ?",
            (target["physique_id"], new_value, client_id),
        )
        self.recalc_player_conn(conn, client_id)

        if new_value > old_value:
            trend = "提升"
        elif new_value < old_value:
            trend = "回落"
        else:
            trend = "稳定"

        delta = new_value - old_value
        return (
            f"洗髓{trend}："
            f"{current['name']}[{current['grade']}/{current['kind']}] -> "
            f"{target['name']}[{target['grade']}/{target['kind']}]，体质{delta:+d}"
        )

    @staticmethod
    def _find_physique(rows: list[dict], physique_id: str) -> dict | None:
        """按 id 找体质定义。"""

        for row in rows:
            if row["physique_id"] == physique_id:
                return row
        return None

    @staticmethod
    def _choose_wash_target(rows: list[dict], current: dict) -> dict:
        """按洗髓概率选择新体质。"""

        current_level = int(current["level"])
        max_level = max(int(row["level"]) for row in rows)
        roll = random.random()
        up_rate, same_rate = ItemEffectService._wash_rates(current_level)

        if roll < up_rate:
            pool = [
                row
                for row in rows
                if current_level < int(row["level"]) <= min(max_level, current_level + 2)
            ]
            if pool:
                return random.choice(pool)
            return random.choice([row for row in rows if int(row["level"]) == max_level])

        if roll < up_rate + same_rate:
            pool = [row for row in rows if int(row["level"]) == current_level]
            return random.choice(pool or rows)

        pool = [
            row
            for row in rows
            if max(0, current_level - 2) <= int(row["level"]) < current_level
        ]
        return random.choice(pool or [current])

    @staticmethod
    def _wash_rates(current_level: int) -> tuple[float, float]:
        """返回洗髓的提升率和稳定率。

        三年服不能让体质太快毕业，所以越高阶越难提升。
        剩下的概率就是回落率：低阶 10%，中阶 15%-20%，高阶 25%-30%。
        """

        if current_level <= 3:
            return 0.35, 0.55
        if current_level <= 6:
            return 0.22, 0.63
        if current_level <= 9:
            return 0.14, 0.66
        if current_level <= 12:
            return 0.07, 0.68
        return 0.0, 0.70

    @staticmethod
    def _random_stones_by_level(segments: object, level: int) -> int:
        """按玩家等级段随机福袋源石。"""

        if not isinstance(segments, list):
            return 0

        player_level = int(level)
        fallback: dict | None = None
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            fallback = segment
            min_level = int(segment.get("min_level", 1))
            max_level = int(segment.get("max_level", 100))
            if min_level <= player_level <= max_level:
                return random.randint(int(segment.get("min", 0)), int(segment.get("max", 0)))

        if fallback:
            return random.randint(int(fallback.get("min", 0)), int(fallback.get("max", 0)))
        return 0


service = ItemEffectService(db)

__all__ = ["ItemEffectService", "service"]
