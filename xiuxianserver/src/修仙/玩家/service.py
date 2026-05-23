"""玩家组件服务。"""

from __future__ import annotations

from ..common import CoreService, business_day, dt, format_effect, hint, money, now, timedelta, ts, weapon_label_name
from ..constants import NEWBIE_GIFT_STONES, REST_MINUTES
from ..rules import sign_reward
from ..sql import db


class PlayerService(CoreService):
    """玩家创建、资料、签到和休息。"""

    def guide(self) -> str:
        """返回新手指引。"""

        return (
            "☆修仙新手指引☆\n"
            "1. 创建用户 名称\n"
            "2. 新手礼包\n"
            "3. 修仙信息 / 武器 / 纳戒\n"
            "4. 探险 地点名 -> 探险状态 -> 30分钟后结束探险\n"
            "5. 自动用药 开启 / 背包 / 使用 血契丹 / 洗髓 / 休息\n"
            "6. 商场列表 / 商场 / 商场推荐 / 商场奖励\n"
            "常用：签到、源库、地点、固定装备、铭刻、二手市场、特殊自动出售、切磋 对方名称"
        )

    def create(self, client_id: str, message: str) -> str:
        """创建用户。"""

        name = message.strip()
        if not name:
            return hint("缺少用户名称。", "发送：创建用户 青衫客")
        return self.create_player(client_id, name)

    def rename(self, client_id: str, message: str) -> str:
        """修改展示名称。"""

        name = message.strip()
        if not name:
            return hint("缺少新名称。", "发送：改名 云游客")
        return self.rename_player(client_id, name)

    def profile(self, client_id: str) -> str:
        """查看玩家信息。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        weapon = self._equipped_weapon(client_id)
        weapon_attack = int(weapon["attack"]) if weapon else 0
        total_attack = int(player["base_attack"]) + weapon_attack
        weapon_text = (
            f"#{weapon['weapon_id']} {weapon_label_name(weapon)}[{weapon['quality']}] 攻击:{weapon_attack}"
            if weapon
            else "未装备"
        )
        physique_text = self._physique_text(player)
        return (
            f"☆{player['display_name']}的修仙信息☆\n"
            f"等级:{player['level']} 经验:{self.next_level_text(player)}\n"
            f"血气:{player['hp']}/{player['max_hp']} 精神:{player['mp']}/{player['max_mp']}\n"
            f"体质:{physique_text}\n"
            f"攻击:{total_attack}(基础{player['base_attack']}+武器{weapon_attack}) 防御:{player['defense']}\n"
            f"当前武器:{weapon_text}\n"
            f"源石:{money(player['source_stones'])} 状态:{player['status']}\n"
            f"自动用药:{'开启' if player['auto_use_medicine'] else '关闭'}\n"
            f"地点:{player['location_name']} ({player['x']},{player['y']})"
        )

    def auto_medicine(self, client_id: str, message: str) -> str:
        """查看或修改探险自动用药开关。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        text = message.strip()
        if not text:
            state = "开启" if player["auto_use_medicine"] else "关闭"
            return f"自动用药当前为：{state}。"

        on_words = {"开启", "打开", "启用", "开", "on", "ON", "1"}
        off_words = {"关闭", "关掉", "停用", "关", "off", "OFF", "0"}
        if text in on_words:
            value = 1
            state = "开启"
        elif text in off_words:
            value = 0
            state = "关闭"
        else:
            return hint("自动用药参数不正确。", "发送：自动用药 开启 或 自动用药 关闭")

        self.db.execute("UPDATE players SET auto_use_medicine = ? WHERE client_id = ?", (value, client_id))
        return f"自动用药已{state}。探险预计算时会按这个开关决定是否消耗纳戒恢复类药物。"

    def sign(self, client_id: str) -> str:
        """每日签到。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        today = business_day()
        reward = sign_reward(player["level"])
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE players
                SET source_stones = source_stones + ?, last_sign_date = ?
                WHERE client_id = ?
                  AND (last_sign_date IS NULL OR last_sign_date != ?)
                """,
                (reward, today, client_id, today),
            )
            if cursor.rowcount <= 0:
                return hint("今日已经签到过了。", "每日 04:00 后可再次发送：签到")
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '签到', ?, ?)",
                (client_id, f"stones={reward}, day={today}", ts()),
            )
        return f"签到成功，获得源石 {money(reward)}。"

    def newbie_gift(self, client_id: str) -> str:
        """领取新手礼包。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None

        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE players
                SET newbie_claimed = 1, source_stones = source_stones + ?
                WHERE client_id = ? AND newbie_claimed = 0
                """,
                (NEWBIE_GIFT_STONES, client_id),
            )
            if cursor.rowcount <= 0:
                return hint("新手礼包已经领取过了。", "发送：纳戒 查看礼包物品，或发送：探险 开始升级。")
            self.add_ring_conn(conn, client_id, "xueqidan", 2)
            self.add_ring_conn(conn, client_id, "yinmingcao", 2)
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '新手礼包', ?, datetime('now', 'localtime'))",
                (client_id, "领取"),
            )
        return "新手礼包领取成功：源石 10000、血契丹 2、阴冥草 2。"

    def rest(self, client_id: str) -> str:
        """进入休息状态。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        if player["status"] != "空闲":
            return hint(f"当前状态为 {player['status']}，不能休息。", "先处理当前状态，例如：探险状态 / 结束探险 / 结束休息")

        until = now() + timedelta(minutes=REST_MINUTES)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                UPDATE players
                SET status = '休息中', status_until_at = ?
                WHERE client_id = ? AND status = '空闲'
                """,
                (ts(until), client_id),
            )
            if cursor.rowcount <= 0:
                return hint("当前状态已变化，不能休息。", "发送：修仙信息 查看当前状态后再操作。")
        return f"开始休息，需要 {REST_MINUTES} 分钟。"

    def end_rest(self, client_id: str) -> str:
        """休息满 1 分钟后恢复并退出。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        if player["status"] != "休息中":
            return hint("你当前不在休息中。", "血气不足可发送：休息；想查看状态可发送：修仙信息")

        until = dt(player["status_until_at"])
        if until and now() < until:
            left = max(1, int((until - now()).total_seconds()))
            return hint(f"还需要休息 {left} 秒。", "时间到后再发送：结束休息")

        recover_bonus = min(0.5, self.equipment_bonuses(client_id).get("recover_bonus", 0))
        hp = player["max_hp"]
        mp_add = int(max(5, player["max_mp"] // 5) * (1 + recover_bonus))
        mp = min(player["max_mp"], player["mp"] + mp_add)
        self.db.execute(
            "UPDATE players SET hp = ?, mp = ?, status = '空闲', status_until_at = NULL WHERE client_id = ?",
            (hp, mp, client_id),
        )
        return f"休息结束，血气恢复到 {hp}/{player['max_hp']}，精神恢复到 {mp}/{player['max_mp']}。"

    def _equipped_weapon(self, client_id: str) -> dict | None:
        """读取当前装备武器；只用于面板展示。"""

        return self.db.fetch_one(
            """
            SELECT w.weapon_id, w.quality, w.attack, w.custom_name, d.name
            FROM player_weapons w
            JOIN weapon_defs d ON d.weapon_def_id = w.weapon_def_id
            WHERE w.owner_id = ? AND w.equipped = 1
            LIMIT 1
            """,
            (client_id,),
        )

    def _physique_text(self, player: dict) -> str:
        """把体质 id 转成玩家能看懂的展示文本。"""

        row = self.db.fetch_one(
            "SELECT name, grade, kind, physique_value, effect FROM physique_defs WHERE physique_id = ?",
            (player["physique_id"],),
        )
        if not row:
            return str(player["physique"])
        effect = format_effect(row["effect"])
        return f"{row['name']}|{row['grade']}-{row['kind']}-{row['physique_value']}| 特性:{effect}"


service = PlayerService(db)

__all__ = ["PlayerService", "service"]
