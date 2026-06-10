"""修仙模块冒烟测试。

运行方式：

    python test/修仙_冒烟测试.py

测试使用临时 SQLite，不写入真实 xiuxian.db。
"""

from __future__ import annotations

import sys
from datetime import date
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 修仙.combat_core import CombatCore
from 修仙.common import CoreService, business_day, dump_json, load_json, weapon_id_label
from 修仙.constants import (
    BANK_LEVELS,
    ENCOUNTER_SECONDS,
    EXPLORE_MINUTES,
    WORMHOLE_DAILY_MAX_LIMIT,
    WORMHOLE_DAILY_MIN_LIMIT,
)
from 修仙.item_effects import ItemEffectService
from 修仙.rules import exp_need, monster_exp, monster_exp_rate, weapon_enchant_slots
from 修仙.sql import XiuxianDB
from 修仙.weapon_core import WeaponCore
from 修仙.商场.service import TradeService
from 修仙.修仙物品.service import TreasureService
from 修仙.对战.service import DuelService
from 修仙.wormhole_service import WormholeService
from 修仙.探险.service import ExplorationService
from 修仙.二手市场.service import SecondHandService
from 修仙.武器.service import WeaponService
from 修仙.源库.service import SourceVaultService
from 修仙.修仙帮助.service import HelpService
from 修仙.玩家.service import PlayerService
from 修仙.纳戒.service import RingService
from 修仙.装备.service import EquipmentService
from 修仙.铭刻.service import InscriptionService
from 修仙.首领.service import BOSS_DEFS, DAILY_BOSS_DEFS, SeasonalBossService
from 修仙.修仙界历史.service import XiuxianHistoryService

combat_core_module = import_module("修仙.combat_core")
exploration_service_module = import_module("修仙.探险.service")
ring_service_module = import_module("修仙.纳戒.service")
backpack_service_module = import_module("修仙.背包.service")
duel_service_module = import_module("修仙.对战.service")
wormhole_service_module = import_module("修仙.wormhole_service")
seasonal_boss_service_module = import_module("修仙.首领.service")


def main() -> None:
    """按当前服务层跑一轮基础玩法。"""

    _check_exp_rules()
    _check_weapon_enchant_slots()
    _check_weapon_interval_rules()
    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "xiuxian_test.db")
        services = _build_services(db)
        try:
            _check_player(services)
            _check_battle_loss_mp(services)
            _check_inventory(services)
            _check_equipment(services)
            _check_inscription(services)
            _check_duel(services)
            _check_second_hand_ring(services)
            _check_second_hand_weapon(services)
            _check_weapon_and_explore(services)
            _check_trade_and_treasure(services)
            _check_history(services)
            _check_wormhole(services)
            _check_seasonal_boss(services)
        finally:
            db.close()

    print("修仙冒烟测试通过")


def _build_services(db: XiuxianDB) -> dict[str, object]:
    """创建测试服务，并把跨模块公共能力换成同一个临时库。"""

    item_effects = ItemEffectService(db)
    weapon_core = WeaponCore(db)
    combat_core_module.weapon_core = weapon_core
    combat_core = CombatCore(db)

    ring_service_module.item_effects = item_effects
    backpack_service_module.item_effects = item_effects
    exploration_service_module.weapon_service = weapon_core
    exploration_service_module.combat_service = combat_core
    duel_service_module.combat_service = combat_core
    wormhole_service_module.weapon_service = weapon_core
    wormhole_service_module.combat_service = combat_core
    seasonal_boss_service_module.weapon_service = weapon_core
    seasonal_boss_service_module.combat_service = combat_core

    return {
        "player": PlayerService(db),
        "help": HelpService(db),
        "vault": SourceVaultService(db),
        "ring": RingService(db),
        "equipment": EquipmentService(db),
        "inscription": InscriptionService(db),
        "weapon": WeaponService(db),
        "explore": ExplorationService(db),
        "second_hand": SecondHandService(db),
        "trade": TradeService(db),
        "treasure": TreasureService(db),
        "duel": DuelService(db),
        "combat": combat_core,
        "wormhole": WormholeService(db),
        "seasonal_boss": SeasonalBossService(db),
        "history": XiuxianHistoryService(db),
    }


def _payload_text(value: Any) -> str:
    """把 text/markdown 回复统一还原成可断言的正文。"""

    if not isinstance(value, dict):
        return str(value)
    message = value.get("message", "")
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(message)


def _must_contain(value: Any, text: str) -> None:
    """断言返回文本包含指定内容。"""

    body = _payload_text(value)
    assert text in body, f"返回内容没有包含 {text!r}：{value}"


def _check_weapon_enchant_slots() -> None:
    """检查武器按长期等级节点增加附魔栏。"""

    assert weapon_enchant_slots(9, 100) == 0
    assert weapon_enchant_slots(10, 10) == 1
    assert weapon_enchant_slots(25, 25) == 2
    assert weapon_enchant_slots(40, 40) == 3
    assert weapon_enchant_slots(60, 60) == 4
    assert weapon_enchant_slots(80, 80) == 5
    assert weapon_enchant_slots(95, 95) == 6
    assert weapon_enchant_slots(100, 100) == 7
    assert weapon_enchant_slots(100, 59) == 3
    assert weapon_enchant_slots(100, 94) == 5


def _check_exp_rules() -> None:
    """检查 40 级后经验加难和等级差经验倍率。"""

    assert exp_need(40) == 134405
    assert exp_need(50) == 376508
    assert exp_need(90) == 13584737
    fight_count = EXPLORE_MINUTES * 60 // ENCOUNTER_SECONDS
    full_win_runs = sum(
        exp_need(level) / (fight_count * monster_exp(level, 1.0, level))
        for level in range(1, 100)
    )
    assert 8900 <= full_win_runs <= 9200
    assert monster_exp_rate(50, 50) == 1.0
    assert monster_exp_rate(45, 50) < 1.0
    assert monster_exp_rate(55, 50) > 1.0
    assert monster_exp(45, 1.0, 50) < monster_exp(50, 1.0, 50)
    assert monster_exp(55, 1.0, 50) > monster_exp(50, 1.0, 50)


def _check_weapon_interval_rules() -> None:
    """检查武器类型和技能书都能影响速度、技能蓄势节奏。"""

    skill = {"interval": 4, "cost_mp": 0, "power": 1.0}
    assert CombatCore._skill_interval(skill, {"weapon_type": "匕"}, {}) == 3
    assert CombatCore._skill_interval(skill, {"weapon_type": "斧"}, {}) == 5
    assert CombatCore._skill_interval(skill, {"weapon_type": "剑"}, {"interval_delta": -1}) == 3
    light = CoreService.combat_profile(30, {"weapon_type": "匕", "attack": 28, "level": 0}, skill, {})
    heavy = CoreService.combat_profile(30, {"weapon_type": "斧", "attack": 40, "level": 0}, skill, {})
    assert light["speed"] > heavy["speed"]
    assert light["skill_charge_gain"] > heavy["skill_charge_gain"]
    assert "高频" in light["skill_tempo"]
    assert "爆发" in heavy["weapon_style"]


def _check_player(services: dict[str, object]) -> None:
    """检查玩家、签到、新手礼包和源库。"""

    player: PlayerService = services["player"]  # type: ignore[assignment]
    help_service: HelpService = services["help"]  # type: ignore[assignment]
    vault: SourceVaultService = services["vault"]  # type: ignore[assignment]

    _check_bank_interest_caps()
    _must_contain(help_service.command_guide(), "<探险状态>")
    _must_contain(help_service.command_guide(), "<结束探险>")
    create_text = player.create("u1", "青衫客")
    _must_contain(create_text, "创建成功")
    assert "u1" not in create_text
    _must_contain(player.create("u9", "青衫客"), "名称已经被使用")
    _must_contain(player.create("u1", "青衫客"), "已经创建过用户")
    profile_text = player.profile("u1")
    _must_contain(profile_text, "攻击")
    _must_contain(profile_text, "防御")
    _must_contain(profile_text, "速度：")
    _must_contain(profile_text, "技能节奏：")
    _must_contain(profile_text, "蓄势基准：")
    _must_contain(profile_text, "定位：")
    _must_contain(profile_text, "凡体")
    _must_contain(profile_text, "头部 Lv0")
    _must_contain(profile_text, "气运：未签到")
    _must_contain(profile_text, "天气：")
    _must_contain(profile_text, "灵潮：")
    _must_contain(profile_text, "今日加成：")
    _must_contain(profile_text, "战斗日志：简要")
    assert "死敌：" not in profile_text
    assert not any("头部" in line and "左手" in line for line in profile_text.splitlines())
    assert "id:" not in profile_text
    assert "u1" not in profile_text
    high_physiques = player.db.fetch_all("SELECT name, effect FROM physique_defs WHERE level >= 10")
    assert high_physiques
    assert all(row["effect"] != "{}" for row in high_physiques)
    assert len({row["effect"] for row in high_physiques}) >= 8
    _must_contain(player.auto_medicine("u1", ""), "当前状态：**开启**")
    _must_contain(player.auto_medicine("u1", "关闭"), "自动用药已关闭")
    _must_contain(player.auto_medicine("u1", "开启"), "自动用药已开启")
    _must_contain(player.battle_log("u1", ""), "当前模式：**简要**")
    _must_contain(player.battle_log("u1", "开启"), "战斗日志已切换为详细")
    _must_contain(player.profile("u1"), "战斗日志：详细")
    _must_contain(player.battle_log("u1", "关闭"), "战斗日志已切换为简要")
    _must_contain(player.sign("u1"), "签到成功")
    _must_contain(player.sign("u1"), "*今日已经签到过了。*")
    _must_contain(player.profile("u1"), "气运：")
    _must_contain(player.newbie_gift("u1"), "新手礼包领取成功")
    _must_contain(player.newbie_gift("u1"), "新手礼包已经领取过了")
    _must_contain(vault.info("u1"), "源库")
    player.add_stones("u1", 10_000)
    _must_contain(vault.deposit("u1", 1000), "已存入源石")
    _must_contain(vault.withdraw("u1", 100), "已取出源石")


def _check_bank_interest_caps() -> None:
    """源库日上限覆盖满库存 24 小时利息，并保持高星级总量更高。"""

    last_cap = 0
    last_cap_rate = 1.0
    for conf in BANK_LEVELS.values():
        full_day_interest = int(conf["limit"] * conf["hour_rate"] * 24)
        cap_rate = conf["daily_interest_limit"] / conf["limit"]

        assert conf["daily_interest_limit"] >= full_day_interest
        assert conf["daily_interest_limit"] > last_cap
        assert cap_rate <= last_cap_rate
        last_cap = conf["daily_interest_limit"]
        last_cap_rate = cap_rate


def _check_inventory(services: dict[str, object]) -> None:
    """检查纳戒和恢复类物品实际生效。"""

    player: PlayerService = services["player"]  # type: ignore[assignment]
    ring: RingService = services["ring"]  # type: ignore[assignment]

    _must_contain(ring.list_items("u1"), "血契丹")
    before_exp = player.player("u1")["exp"]  # type: ignore[index]
    _must_contain(ring.use_item("u1", "血契丹"), "血气+")
    after_exp = player.player("u1")["exp"]  # type: ignore[index]
    assert after_exp == before_exp

    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "fudai", 1)
    before_stones = player.player("u1")["source_stones"]  # type: ignore[index]
    _must_contain(ring.use_item("u1", "福袋"), "源石+")
    after_stones = player.player("u1")["source_stones"]  # type: ignore[index]
    assert 10_000 <= after_stones - before_stones <= 30_000

    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "fudai", 3)
    before_stones = player.player("u1")["source_stones"]  # type: ignore[index]
    _must_contain(ring.use_item("u1", "福袋 3"), "使用 福袋 x3 成功")
    after_stones = player.player("u1")["source_stones"]  # type: ignore[index]
    assert 30_000 <= after_stones - before_stones <= 90_000
    assert not ring.db.fetch_one(
        "SELECT 1 FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u1", "fudai"),
    )

    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "fudai", 2)
    before_stones = player.player("u1")["source_stones"]  # type: ignore[index]
    _must_contain(ring.use_item("u1", "福袋 3"), "纳戒里没有足够的 福袋 x3")
    after_stones = player.player("u1")["source_stones"]  # type: ignore[index]
    assert after_stones == before_stones
    row = ring.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u1", "fudai"),
    )
    assert row and row["quantity"] == 2

    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "xisuiye", 1)
        ring.add_ring_conn(conn, "u1", "fengren_shu", 1)
    _must_contain(ring.use_item("u1", "洗髓液"), "不能直接使用")
    _must_contain(ring.use_item("u1", "风刃书"), "不能直接使用")
    _must_contain(ring.wash("u1"), "洗髓")
    row = player.player("u1")
    assert row and row["physique_id"]
    physique = player.db.fetch_one(
        "SELECT physique_value FROM physique_defs WHERE physique_id = ?",
        (row["physique_id"],),
    )
    assert physique and int(row["physique"]) == int(physique["physique_value"])


def _check_battle_loss_mp(services: dict[str, object]) -> None:
    """检查战败后精神归零。"""

    combat: CombatCore = services["combat"]  # type: ignore[assignment]
    combat.db.execute(
        "UPDATE players SET hp = 1, mp = 50 WHERE client_id = ?",
        ("u1",),
    )
    result = combat.fight_monster(
        "u1",
        {
            "name": "测试重击怪",
            "level": 1,
            "hp": 9999,
            "attack": 9999,
            "defense": 0,
            "drop_item_id": "",
            "drop_chance": 0,
        },
    )
    assert result["hp_left"] == 0
    assert result["mp_left"] == 0
    combat.db.execute(
        "UPDATE players SET hp = max_hp, mp = max_mp WHERE client_id = ?",
        ("u1",),
    )


def _check_equipment(services: dict[str, object]) -> None:
    """检查装备升级和宝石镶嵌。"""

    equipment: EquipmentService = services["equipment"]  # type: ignore[assignment]

    with equipment.db.transaction() as conn:
        conn.execute("UPDATE players SET source_stones = source_stones + 50_000 WHERE client_id = ?", ("u1",))
        equipment.add_ring_conn(conn, "u1", "huxinyu", 1)
        equipment.add_ring_conn(conn, "u1", "huxinyu", 1)
        equipment.add_ring_conn(conn, "u1", "jucai zijing", 1)
        equipment.add_ring_conn(conn, "u1", "xuangui shi", 1)
        equipment.add_ring_conn(conn, "u1", "kaikongqi", 6)
    _must_contain(equipment.list_equipment("u1"), "头部")
    _must_contain(equipment.upgrade("u1", "头部"), "升级成功")
    _must_contain(equipment.inlay("u1", "头部 1 护心玉"), "镶嵌成功")
    _must_contain(equipment.inlay("u1", "左手 2 聚财紫晶"), "镶嵌成功")
    _must_contain(equipment.inlay("u1", "头部 4 玄龟石"), "当前只开启到 3 号孔")
    _must_contain(equipment.open_hole("u1", "头部"), "开孔成功")
    _must_contain(equipment.inlay("u1", "头部 4 玄龟石"), "镶嵌成功")
    _must_contain(equipment.inlay("u1", "头部 2 护心玉"), "镶嵌成功")
    _must_contain(equipment.upgrade_inlay("u1", "护心玉"), "需要用装备位和孔位号定位")
    for _ in range(5):
        _must_contain(equipment.open_hole("u1", "头部"), "开孔成功")
    _must_contain(equipment.open_hole("u1", "头部"), "已经达到 9 孔上限")
    _must_contain(equipment.upgrade_inlay("u1", "头部 1"), "升级成功")
    row = equipment.db.fetch_one(
        """
        SELECT level FROM fixed_equipment_inlays
        WHERE client_id = ? AND slot = ? AND hole_no = ?
        """,
        ("u1", "头部", 1),
    )
    assert row and row["level"] == 2
    _must_contain(equipment.remove_inlay("u1", "头部 1"), "护心玉 2级已回到纳戒")
    _must_contain(equipment.my_inlays("u1"), "护心玉 2级")
    with equipment.db.transaction() as conn:
        equipment.add_gem_conn(conn, "u1", "huxinyu", 1, 1)
    _must_contain(equipment.inlay("u1", "头部 1 护心玉"), "多种等级")
    _must_contain(equipment.inlay("u1", "头部 1 护心玉 2级"), "护心玉 2级")
    with equipment.db.transaction() as conn:
        equipment.add_gem_conn(conn, "u1", "huxinyu", 2, 2)
        conn.execute(
            "UPDATE players SET location_name = '琢玉楼', x = 320, y = 760 WHERE client_id = ?",
            ("u1",),
        )
    before_recycle = equipment.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    preview = equipment.recycle_gem("u1", "")
    _must_contain(preview, "护心玉 2级")
    _must_contain(preview, "当前倍率")
    _must_contain(equipment.recycle_gem("u1", "护心玉 2级 1"), "回收成功")
    after_recycle = equipment.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_recycle and after_recycle
    gained = int(after_recycle["source_stones"]) - int(before_recycle["source_stones"])
    assert gained > 0
    gem_left = equipment.db.fetch_one(
        "SELECT quantity FROM gem_items WHERE client_id = ? AND gem_id = ? AND level = ?",
        ("u1", "huxinyu", 2),
    )
    assert gem_left and int(gem_left["quantity"]) == 1
    record = equipment.db.fetch_one(
        "SELECT total_price FROM gem_recycle_records WHERE client_id = ? AND business_day = ?",
        ("u1", business_day()),
    )
    assert record and int(record["total_price"]) == gained
    with equipment.db.transaction() as conn:
        equipment.add_gem_conn(conn, "u1", "huxinyu", 1, 2)
        equipment.add_gem_conn(conn, "u1", "xuangui shi", 1, 1)
        equipment.add_gem_conn(conn, "u1", "huxinyu", 2, 1)
    before_level_batch = equipment.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    level_batch_text = equipment.recycle_gem("u1", "1级全部")
    _must_contain(level_batch_text, "1级宝石批量回收")
    _must_contain(level_batch_text, "回收 **4** 颗")
    after_level_batch = equipment.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_level_batch and after_level_batch
    assert int(after_level_batch["source_stones"]) > int(before_level_batch["source_stones"])
    assert not equipment.db.fetch_one("SELECT 1 FROM gem_items WHERE client_id = ? AND level = 1", ("u1",))
    assert equipment.db.fetch_one("SELECT 1 FROM gem_items WHERE client_id = ? AND level = 2", ("u1",))
    before_gem_batch = equipment.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    gem_batch_text = equipment.recycle_gem("u1", "全部")
    _must_contain(gem_batch_text, "宝石批量回收")
    _must_contain(gem_batch_text, "护心玉 2级")
    after_gem_batch = equipment.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_gem_batch and after_gem_batch
    assert int(after_gem_batch["source_stones"]) > int(before_gem_batch["source_stones"])
    assert not equipment.db.fetch_one("SELECT 1 FROM gem_items WHERE client_id = ?", ("u1",))
    equipment.db.execute(
        "UPDATE players SET location_name = '天枢城', x = 0, y = 0 WHERE client_id = ?",
        ("u1",),
    )


def _check_inscription(services: dict[str, object]) -> None:
    """检查铭刻之羽能改装备、武器、自带技能和已附魔技能书的显示名。"""

    inscription: InscriptionService = services["inscription"]  # type: ignore[assignment]
    player: PlayerService = services["player"]  # type: ignore[assignment]
    weapon: WeaponService = services["weapon"]  # type: ignore[assignment]
    equipment: EquipmentService = services["equipment"]  # type: ignore[assignment]

    weapon.ensure_starter_weapon("u1")
    weapon_row = weapon.db.fetch_one(
        "SELECT weapon_id FROM player_weapons WHERE owner_id = ? ORDER BY weapon_id LIMIT 1",
        ("u1",),
    )
    assert weapon_row is not None
    weapon_id = int(weapon_row["weapon_id"])

    with inscription.db.transaction() as conn:
        _add_feathers_conn(conn, "u1", 4)
        inscription.add_ring_conn(conn, "u1", "fengren_shu", 1)
        conn.execute(
            "UPDATE player_weapons SET level = 20, max_level = 45 WHERE owner_id = ? AND weapon_id = ?",
            ("u1", weapon_id),
    )

    _must_contain(inscription.fixed_equipment("u1", "头部 青云冠"), "铭刻成功")
    _must_contain(equipment.list_equipment("u1"), "青云冠（头部）")
    _must_contain(player.profile("u1"), "青云冠（头部）")
    with inscription.db.transaction() as conn:
        _add_feathers_conn(conn, "u1", 1)
    _must_contain(inscription.fixed_equipment("u1", "饰品 月华沉梦"), "铭刻成功")
    profile_text = player.profile("u1")
    _must_contain(profile_text, "月华沉梦（饰品）")
    assert not any("右脚" in line and "月华沉梦" in line for line in profile_text.splitlines())
    _must_contain(inscription.weapon("u1", f"武器#{weapon_id} 青云剑"), "铭刻成功")
    _must_contain(weapon.list_weapons("u1"), "青云剑（青岚短剑）")
    _must_contain(inscription.skill("u1", f"武器#{weapon_id} 青云斩"), "铭刻成功")
    _must_contain(weapon.list_weapons("u1"), "青云斩（风刃斩）")
    _must_contain(player.profile("u1"), "青云斩（风刃斩）")
    _must_contain(weapon.enchant("u1", f"{weapon_id} 风刃书"), "附魔成功")
    _must_contain(inscription.enchant("u1", f"武器#{weapon_id} 1 青云破"), "铭刻成功")
    _must_contain(weapon.list_weapons("u1"), "青云破（风刃书）")
    detail_text = weapon.detail("u1", f"武器#{weapon_id}")
    _must_contain(detail_text, "武器详情")
    _must_contain(detail_text, "模板：青岚短剑")
    _must_contain(detail_text, "定位：")
    _must_contain(detail_text, "速度：")
    _must_contain(detail_text, "技能节奏：")
    _must_contain(detail_text, "蓄势基准：")
    _must_contain(detail_text, "自带技能：")
    _must_contain(detail_text, "附魔栏：")
    _must_contain(detail_text, "青云破（风刃书）")

    feather = inscription.db.fetch_one(
        "SELECT COUNT(*) AS count FROM inscription_feathers WHERE client_id = ?",
        ("u1",),
    )
    assert feather and int(feather["count"]) == 0


def _check_duel(services: dict[str, object]) -> None:
    """检查押注决斗只能被接受一次。"""

    player: PlayerService = services["player"]  # type: ignore[assignment]
    duel: DuelService = services["duel"]  # type: ignore[assignment]
    explore: ExplorationService = services["explore"]  # type: ignore[assignment]

    _must_contain(player.create("u2", "白衣客"), "创建成功")
    _must_contain(player.rename("u2", "青衫客"), "名称已经被使用")
    player.add_stones("u1", 10_000)
    player.add_stones("u2", 10_000)
    _must_contain(duel.duel("u1", "白衣客 1000"), "发起决斗")
    duel_result = duel.accept_duel("u2", "青衫客")
    _must_contain(duel_result, "决斗结算")
    _must_contain(duel_result, "决斗结束")
    _must_contain(duel_result, "技能：")
    duel_body = _payload_text(duel_result)
    assert "一、战斗明细" not in duel_body
    assert "u1" not in duel_body
    assert "u2" not in duel_body
    _must_contain(duel.accept_duel("u2", "青衫客"), "没有找到待接受")

    _must_contain(player.battle_log("u2", "开启"), "详细")
    _must_contain(duel.duel("u1", "白衣客 100"), "发起决斗")
    detail_duel_result = duel.accept_duel("u2", "青衫客")
    _must_contain(detail_duel_result, "```javascript")
    _must_contain(detail_duel_result, "一、战斗明细")
    _must_contain(detail_duel_result, "出手")
    _must_contain(detail_duel_result, "二、最终结算")
    _must_contain(player.battle_log("u2", "关闭"), "简要")

    before = player.player("u1")["source_stones"]  # type: ignore[index]
    _must_contain(duel.duel("u1", "白衣客 500"), "发起决斗")
    frozen = player.player("u1")["source_stones"]  # type: ignore[index]
    assert before - frozen == 500
    duel.db.execute(
        "UPDATE duel_requests SET expires_at = ? WHERE status = '等待'",
        ("2000-01-01 00:00:00",),
    )
    _must_contain(duel.accept_duel("u2", "青衫客"), "没有找到待接受")
    refunded = player.player("u1")["source_stones"]  # type: ignore[index]
    assert refunded == before

    with duel.db.transaction() as conn:
        for index in range(1, 13):
            conn.execute(
                """
                INSERT INTO duel_records
                (duel_id, mode, from_client_id, to_client_id, winner_id, loser_id, stake, fee, summary, created_at)
                VALUES (?, '切磋', 'u1', 'u2', 'u1', 'u2', 0, 0, ?, '2099-01-01T00:00:00')
                """,
                (100000 + index, f"窗口记录{index:02d}"),
            )
    records_text = duel.records("u1")
    assert records_text.count("窗口记录") == 10
    _must_contain(records_text, "窗口记录12")
    _must_contain(records_text, "窗口记录03")
    assert "窗口记录01" not in records_text
    assert "窗口记录02" not in records_text

    u1_before = dict(player.player("u1"))  # type: ignore[arg-type]
    u2_before = dict(player.player("u2"))  # type: ignore[arg-type]
    duel.db.execute(
        """
        UPDATE players
        SET level = 50, hp = 2000, max_hp = 2000, mp = 800, max_mp = 800,
            base_attack = 260, defense = 160, status = '空闲'
        WHERE client_id = 'u1'
        """
    )
    duel.db.execute(
        """
        UPDATE players
        SET level = 1, hp = 30, max_hp = 30, mp = 10, max_mp = 10,
            base_attack = 1, defense = 0, status = '探险中', location_name = '青岚坊'
        WHERE client_id = 'u2'
        """
    )
    target_snapshot_player = dict(player.player("u2"))  # type: ignore[arg-type]
    robbery_result = {
        "dead": False,
        "bag_full": False,
        "medicine_used": {},
        "events": [{"win": True, "drop_item_id": "yaodan", "hp_left": 30, "mp_left": 10, "actions": []}],
        "player_snapshot": explore._player_snapshot(target_snapshot_player),
        "combat_snapshot": explore._combat_snapshot("u2", target_snapshot_player),
    }
    with duel.db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO exploration_records
            (client_id, location_name, status, started_at, ready_at, result)
            VALUES ('u2', '青岚坊', '探险中', '2099-01-01T00:00:00', '2099-01-01T00:30:00', ?)
            """,
            (dump_json(robbery_result),),
        )
        conn.execute(
            """
            INSERT INTO player_hatreds
            (from_client_id, to_client_id, hate_value, robbery_count, last_reason, updated_at)
            VALUES ('u1', 'u2', 2, 2, '测试仇恨', '2099-01-01T00:00:00')
            """
        )
    robbery_text = duel.robbery("u1", "白衣客")
    _must_contain(robbery_text, "抢劫成功")
    _must_contain(robbery_text, "妖丹")
    _must_contain(robbery_text, "复仇触发")
    assert duel.db.fetch_one("SELECT 1 FROM player_hatreds WHERE from_client_id = 'u1' AND to_client_id = 'u2'") is None
    revenge_hate = duel.db.fetch_one(
        "SELECT hate_value FROM player_hatreds WHERE from_client_id = 'u2' AND to_client_id = 'u1'"
    )
    assert revenge_hate and int(revenge_hate["hate_value"]) == 1
    _must_contain(player.profile("u1"), "死敌：白衣客（仇恨 **1**，报复指数 **20**，抢劫 **1** 次）")
    robbed_record = duel.db.fetch_one("SELECT result FROM exploration_records WHERE client_id = 'u2' AND claimed = 0")
    assert robbed_record
    robbed_result = load_json(robbed_record["result"], {})
    assert not robbed_result["events"][0].get("drop_item_id")
    assert duel.db.fetch_one("SELECT quantity FROM backpack_items WHERE client_id = 'u1' AND item_id = 'yaodan'")
    with duel.db.transaction() as conn:
        conn.execute("DELETE FROM exploration_records WHERE client_id = 'u2' AND claimed = 0")
        conn.execute("DELETE FROM backpack_items WHERE client_id = 'u1' AND item_id = 'yaodan'")
        for row in (u1_before, u2_before):
            conn.execute(
                """
                UPDATE players
                SET level = ?, hp = ?, max_hp = ?, mp = ?, max_mp = ?,
                    base_attack = ?, defense = ?, status = ?, location_name = ?, x = ?, y = ?
                WHERE client_id = ?
                """,
                (
                    row["level"],
                    row["hp"],
                    row["max_hp"],
                    row["mp"],
                    row["max_mp"],
                    row["base_attack"],
                    row["defense"],
                    row["status"],
                    row["location_name"],
                    row["x"],
                    row["y"],
                    row["client_id"],
                ),
            )

    with duel.db.transaction() as conn:
        conn.execute(
            "INSERT INTO combat_logs (client_id, target, summary, created_at) VALUES ('u1', 'u2', '旧战斗', '2000-01-01T00:00:00')"
        )
        conn.execute(
            """
            INSERT INTO robbery_records
            (exploration_record_id, robber_id, target_id, winner_id, success, loot_text, loot_json, hate_before, hate_used, result, business_day, created_at)
            VALUES (999999, 'u1', 'u2', 'u1', 1, '旧抢劫', '[]', 0, 0, '{}', '2000-01-01', '2000-01-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO duel_records
            (duel_id, mode, from_client_id, to_client_id, winner_id, loser_id, stake, fee, summary, created_at)
            VALUES (99999, '切磋', 'u1', 'u2', 'u1', 'u2', 0, 0, '旧决斗', '2000-01-01T00:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO exploration_records
            (client_id, location_name, status, started_at, ready_at, finished_at, result, claimed)
            VALUES ('u1', '青岚坊', '已领取', '2000-01-01T00:00:00', '2000-01-01T00:30:00', '2000-01-01T00:40:00', '{}', 1)
            """
        )
    duel.cleanup_battle_records(force=True)
    assert not duel.db.fetch_one("SELECT 1 FROM combat_logs WHERE summary = '旧战斗'")
    assert not duel.db.fetch_one("SELECT 1 FROM duel_records WHERE summary = '旧决斗'")
    assert not duel.db.fetch_one("SELECT 1 FROM robbery_records WHERE loot_text = '旧抢劫'")
    assert not duel.db.fetch_one("SELECT 1 FROM exploration_records WHERE result = '{}'")


def _check_second_hand_ring(services: dict[str, object]) -> None:
    """检查纳戒物品可以按名称、数量和总价交易。"""

    player: PlayerService = services["player"]  # type: ignore[assignment]
    ring: RingService = services["ring"]  # type: ignore[assignment]
    second_hand: SecondHandService = services["second_hand"]  # type: ignore[assignment]

    player.add_stones("u2", 100_000)
    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "xueqidan", 1)

    before = ring.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u2", "xueqidan"),
    )
    before_quantity = int(before["quantity"]) if before else 0

    _must_contain(second_hand.sell("u1", "血契丹 1 500"), "上架成功")
    market_text = second_hand.list_items("u2")
    _must_contain(market_text, "血契丹 x1")
    assert "u1" not in market_text
    _must_contain(second_hand.buy("u2", "青衫客"), "购买成功")

    after = ring.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u2", "xueqidan"),
    )
    assert after and int(after["quantity"]) == before_quantity + 1

    with ring.db.transaction() as conn:
        ring.add_gem_conn(conn, "u1", "huxinyu", 1, 1)
        ring.add_gem_conn(conn, "u1", "huxinyu", 2, 1)
    _must_contain(second_hand.sell("u1", "护心玉 1 500"), "多种等级")
    _must_contain(second_hand.sell("u1", "护心玉 2级 1 500"), "护心玉 2级")
    market_text = second_hand.list_items("u2")
    _must_contain(market_text, "护心玉 2级 x1")
    assert "u1" not in market_text
    before_gem = ring.db.fetch_one(
        "SELECT quantity FROM gem_items WHERE client_id = ? AND gem_id = ? AND level = 2",
        ("u2", "huxinyu"),
    )
    before_gem_quantity = int(before_gem["quantity"]) if before_gem else 0
    _must_contain(second_hand.buy("u2", "青衫客"), "护心玉 2级")
    after_gem = ring.db.fetch_one(
        "SELECT quantity FROM gem_items WHERE client_id = ? AND gem_id = ? AND level = 2",
        ("u2", "huxinyu"),
    )
    assert after_gem and int(after_gem["quantity"]) == before_gem_quantity + 1


def _check_second_hand_weapon(services: dict[str, object]) -> None:
    """检查武器按实例 ID 上架、托管和成交。"""

    player: PlayerService = services["player"]  # type: ignore[assignment]
    second_hand: SecondHandService = services["second_hand"]  # type: ignore[assignment]
    weapon: WeaponService = services["weapon"]  # type: ignore[assignment]

    weapon.ensure_starter_weapon("u1")
    equipped = weapon.equipped_weapon("u1")
    assert equipped is not None
    _must_contain(second_hand.sell("u1", f"武器#{equipped['weapon_id']} 1000"), "已装备武器不能上架")

    only_id = weapon.create_weapon("u3", "qinglan_duanjian", "凡品", 40, equipped=False)
    player.create_player("u3", "灰衣客")
    _must_contain(second_hand.sell("u3", f"武器#{only_id} 1000"), "不能上架最后一把武器")

    weapon_id = weapon.create_weapon("u1", "qinglan_duanjian", "良品", 45, equipped=False)
    player.add_stones("u2", 100_000)
    _must_contain(second_hand.sell("u1", f"武器#{weapon_id} 1000"), "上架成功")
    _must_contain(second_hand.list_items("u2"), f"武器{weapon_id_label(weapon_id)}")
    assert weapon.weapon("u1", weapon_id) is None
    _must_contain(second_hand.buy("u2", "青衫客"), "购买成功")
    assert weapon.weapon("u2", weapon_id) is not None


def _check_weapon_and_explore(services: dict[str, object]) -> None:
    """检查武器列表、探险预计算和领取。"""

    weapon: WeaponService = services["weapon"]  # type: ignore[assignment]
    explore: ExplorationService = services["explore"]  # type: ignore[assignment]

    _must_contain(weapon.list_weapons("u1"), "青岚短剑")
    first_weapon = weapon.db.fetch_one(
        "SELECT weapon_id FROM player_weapons WHERE owner_id = ? ORDER BY weapon_id LIMIT 1",
        ("u1",),
    )
    assert first_weapon is not None
    detail_text = weapon.detail("u1", str(first_weapon["weapon_id"]))
    _must_contain(detail_text, "武器详情")
    _must_contain(detail_text, "模板：")
    _must_contain(detail_text, "定位：")
    _must_contain(detail_text, "速度：")
    _must_contain(detail_text, "蓄势基准：")
    recycle_weapon_id = weapon.create_weapon("u1", "qinglan_duanjian", "良品", 45, equipped=False)
    before_recycle = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    weapon.db.execute(
        "UPDATE players SET location_name = '铸剑阁', x = -120, y = 760 WHERE client_id = ?",
        ("u1",),
    )
    preview = weapon.recycle("u1", "")
    _must_contain(preview, weapon_id_label(recycle_weapon_id))
    _must_contain(preview, "当前倍率")
    recycle_weapon = weapon.weapon("u1", recycle_weapon_id)
    assert recycle_weapon is not None
    location = weapon.db.fetch_one(
        "SELECT * FROM recycle_locations WHERE name = ? AND recycle_type = 'weapon'",
        ("铸剑阁",),
    )
    assert location
    quote = weapon._recycle_quote(dict(recycle_weapon), float(location["price_factor"]), 1, 0)
    assert quote["value"] <= quote["single_cap"]
    _must_contain(weapon.recycle("u1", f"武器#{recycle_weapon_id}"), "回收成功")
    after_recycle = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_recycle and after_recycle
    assert int(after_recycle["source_stones"]) > int(before_recycle["source_stones"])
    assert weapon.weapon("u1", recycle_weapon_id) is None
    record = weapon.db.fetch_one(
        "SELECT total_price FROM weapon_recycle_records WHERE client_id = ? AND business_day = ?",
        ("u1", business_day()),
    )
    assert record and int(record["total_price"]) == int(after_recycle["source_stones"]) - int(before_recycle["source_stones"])
    pressure_weapon_id = weapon.create_weapon("u1", "qinglan_duanjian", "良品", 45, equipped=False)
    pressure_weapon = weapon.weapon("u1", pressure_weapon_id)
    assert pressure_weapon is not None
    pressured_quote = weapon._recycle_quote(
        dict(pressure_weapon),
        float(location["price_factor"]),
        1,
        weapon._today_recycle_income("u1"),
    )
    assert pressured_quote["rate"] < quote["rate"]

    batch_weapon_id_1 = weapon.create_weapon("u1", "qinglan_duanjian", "良品", 45, equipped=False)
    batch_weapon_id_2 = weapon.create_weapon("u1", "pojun_qiang", "凡品", 40, equipped=False)
    before_batch = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    batch_text = weapon.recycle("u1", f"{batch_weapon_id_1} {batch_weapon_id_2}")
    _must_contain(batch_text, "武器批量回收")
    _must_contain(batch_text, weapon_id_label(batch_weapon_id_1))
    _must_contain(batch_text, weapon_id_label(batch_weapon_id_2))
    after_batch = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_batch and after_batch
    assert int(after_batch["source_stones"]) > int(before_batch["source_stones"])
    assert weapon.weapon("u1", batch_weapon_id_1) is None
    assert weapon.weapon("u1", batch_weapon_id_2) is None

    with weapon.db.transaction() as conn:
        weapon.add_ring_conn(conn, "u1", "fengren_shu", 2)
        conn.execute(
            "UPDATE players SET location_name = '藏经阁', x = 120, y = 820 WHERE client_id = ?",
            ("u1",),
        )
    before_book_recycle = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    before_book = weapon.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u1", "fengren_shu"),
    )
    before_book_quantity = int(before_book["quantity"]) if before_book else 0
    book_preview = weapon.recycle_book("u1", "")
    _must_contain(book_preview, "风刃书")
    _must_contain(book_preview, "当前倍率")
    _must_contain(weapon.recycle_book("u1", "风刃书 1"), "回收成功")
    after_book_recycle = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_book_recycle and after_book_recycle
    book_gained = int(after_book_recycle["source_stones"]) - int(before_book_recycle["source_stones"])
    assert book_gained > 0
    book_left = weapon.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u1", "fengren_shu"),
    )
    after_book_quantity = int(book_left["quantity"]) if book_left else 0
    assert after_book_quantity == before_book_quantity - 1
    book_record = weapon.db.fetch_one(
        """
        SELECT total_price FROM book_recycle_records
        WHERE client_id = ? AND business_day = ?
        ORDER BY record_id DESC LIMIT 1
        """,
        ("u1", business_day()),
    )
    assert book_record and int(book_record["total_price"]) == book_gained
    with weapon.db.transaction() as conn:
        weapon.add_ring_conn(conn, "u1", "fengren_shu", 1)
        weapon.add_ring_conn(conn, "u1", "poxie_shu", 2)
    before_book_batch = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    book_batch_text = weapon.recycle_book("u1", "全部")
    _must_contain(book_batch_text, "技能书批量回收")
    _must_contain(book_batch_text, "回收 **5** 本")
    _must_contain(book_batch_text, "破甲书")
    after_book_batch = weapon.db.fetch_one("SELECT source_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_book_batch and after_book_batch
    assert int(after_book_batch["source_stones"]) > int(before_book_batch["source_stones"])
    assert not weapon.db.fetch_one(
        """
        SELECT 1
        FROM ring_items r
        JOIN equipment_item_defs e ON e.equipment_item_id = r.equipment_item_id
        WHERE r.client_id = ? AND e.category = '技能书'
        """,
        ("u1",),
    )

    weapon.db.execute(
        "UPDATE players SET location_name = '天枢城', x = 0, y = 0 WHERE client_id = ?",
        ("u1",),
    )
    weapon.db.execute(
        "UPDATE players SET location_name = '星陨墟', x = 5, y = -43, status = '空闲' WHERE client_id = ?",
        ("u1",),
    )
    _must_contain(explore.start("u1"), "开始探险")
    high_record = explore.db.fetch_one(
        "SELECT result FROM exploration_records WHERE client_id = ? AND claimed = 0",
        ("u1",),
    )
    assert high_record
    high_names = {
        row["name"]
        for row in explore.db.fetch_all("SELECT name FROM monster_defs WHERE level BETWEEN 70 AND 100")
    }
    high_result = load_json(high_record["result"], {})
    high_snapshot = high_result.get("player_snapshot", {})
    assert high_snapshot.get("location_name") == "星陨墟"
    assert "max_hp" in high_snapshot
    high_events = high_result.get("events", [])
    assert any(event.get("monster") in high_names for event in high_events)
    old_random = exploration_service_module.random.random
    try:
        exploration_service_module.random.random = lambda: 0.0
        forced_result = explore._precompute_result(
            {
                "level": 1,
                "location_name": "青岚坊",
            },
            [{"win": True}],
            {},
            0.0,
            dead=True,
            bag_full=False,
        )
    finally:
        exploration_service_module.random.random = old_random
    assert forced_result.get("weapon_drop")
    assert not forced_result["events"][0].get("weapon_drop")
    with explore.db.transaction() as conn:
        conn.execute("DELETE FROM exploration_records WHERE client_id = ? AND claimed = 0", ("u1",))
        conn.execute(
            "UPDATE players SET location_name = '天枢城', x = 0, y = 0, status = '空闲' WHERE client_id = ?",
            ("u1",),
        )
    with explore.db.transaction() as conn:
        conn.execute(
            "UPDATE players SET hp = 10, mp = 1, auto_use_medicine = 1, status = '空闲' WHERE client_id = ?",
            ("u1",),
        )
        explore.add_ring_conn(conn, "u1", "xueqidan", 2)
        explore.add_ring_conn(conn, "u1", "yinmingcao", 2)
    before_hp_medicine = explore.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u1", "xueqidan"),
    )
    before_hp_medicine_quantity = int(before_hp_medicine["quantity"]) if before_hp_medicine else 0
    _must_contain(explore.start("u1", "青岚坊"), "开始探险：青岚坊")
    record = explore.db.fetch_one(
        "SELECT location_name, result FROM exploration_records WHERE client_id = ? AND claimed = 0",
        ("u1",),
    )
    assert record
    assert record["location_name"] == "青岚坊"
    result = load_json(record["result"], {})
    snapshot = result.get("player_snapshot", {})
    assert snapshot.get("location_name") == "青岚坊"
    events = result.get("events", [])
    assert not any(event.get("weapon_drop") for event in events)
    assert len(explore._weapon_drops_from_result(result)) <= 1
    after_hp_medicine = explore.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND equipment_item_id = ?",
        ("u1", "xueqidan"),
    )
    after_hp_medicine_quantity = int(after_hp_medicine["quantity"]) if after_hp_medicine else 0
    assert after_hp_medicine_quantity < before_hp_medicine_quantity
    _must_contain(explore.status("u1"), "探险状态")
    _must_contain(explore.claim("u1"), "30 分钟冷却")
    explore.db.execute(
        "UPDATE exploration_records SET ready_at = ? WHERE client_id = ?",
        ("2000-01-01T00:00:00", "u1"),
    )
    explore.db.execute("UPDATE players SET battle_log_detail = 1 WHERE client_id = ?", ("u1",))
    claim_text = explore.claim("u1")
    _must_contain(claim_text, "```javascript")
    _must_contain(claim_text, "探险结束")
    assert "领取动作" not in claim_text
    _must_contain(claim_text, "一、战斗明细")
    _must_contain(claim_text, "我方出手")
    _must_contain(claim_text, "敌方出手")
    _must_contain(claim_text, "二、最终结算")
    explore.db.execute("UPDATE players SET battle_log_detail = 0 WHERE client_id = ?", ("u1",))
    explore.db.execute(
        "UPDATE players SET location_name = '天枢城', x = 0, y = 0 WHERE client_id = ?",
        ("u1",),
    )


def _check_trade_and_treasure(services: dict[str, object]) -> None:
    """检查商场和修仙物品详情查询。"""

    trade: TradeService = services["trade"]  # type: ignore[assignment]
    treasure: TreasureService = services["treasure"]  # type: ignore[assignment]

    _must_contain(trade.locations("u1"), "天枢城")
    _must_contain(trade.locations("u1"), "铸剑阁")
    _must_contain(trade.locations("u1"), "琢玉楼")
    _must_contain(trade.locations("u1"), "藏经阁")
    _must_contain(trade.detail("u1", "铸剑阁"), "铸剑阁详情")
    _must_contain(trade.detail("u1", "琢玉楼"), "宝石")
    _must_contain(trade.detail("u1", "藏经阁"), "技能书")
    _must_contain(trade.current("u1"), "商场")
    recommend_text = trade.recommend("u1")
    _must_contain(recommend_text, "商场购买")
    _must_contain(recommend_text, "导航")
    _must_contain(recommend_text, "商场出售")
    _must_contain(trade.buy("u1", "青岚玉 1"), "不出售")
    player = trade.player("u1")
    assert player is not None
    options = trade._trade_options("u1", player)
    assert options, "商场推荐应该至少给出一条可盈利路线"
    option = options[0]
    trade_item = str(option["item_name"])
    trade_quantity = int(option["quantity"])
    trade_target = str(option["target"])
    _must_contain(trade.buy("u1", f"{trade_item} {trade_quantity}"), "购买成功")
    _must_contain(trade.navigate("u1", trade_target), "已到达")
    _must_contain(trade.sell("u1", f"{trade_item} {trade_quantity}"), "出售成功")
    reward_text = trade.daily_reward("u1")
    _must_contain(reward_text, "跑商奖励领取成功")
    _must_contain(reward_text, "净利润")
    _must_contain(trade.daily_reward("u1"), "已经领取")
    _must_contain(treasure.info("u1", "星纹玉简"), "星纹玉简")
    _must_contain(treasure.info("u1", "福袋"), "存放：纳戒")
    _must_contain(treasure.info("u1", "青岚短剑"), "武器模板")
    _must_contain(treasure.info("u1", "风刃斩"), "武器自带技能")
    _must_contain(treasure.info("u1", "风刃书"), "附魔效果")
    _must_contain(treasure.info("u1", "凡体"), "体质资料")
    for table in (
        "item_defs",
        "equipment_item_defs",
        "weapon_defs",
        "weapon_skill_defs",
        "weapon_enchants",
        "physique_defs",
    ):
        for row in treasure.db.fetch_all(f"SELECT name FROM {table}"):
            text = treasure.info("u1", row["name"])
            _must_contain(text, row["name"])
            assert "没有找到修仙物品" not in text
    _must_contain(trade.navigate("u1", "镇妖司"), "已到达")
    _must_contain(trade.buy("u1", "星纹玉简 1"), "当前位置不是商场地点")
    _must_contain(trade.special_buyers("u1"), "今日收购价")
    with trade.db.transaction() as conn:
        trade.add_backpack_conn(conn, "u1", "yaodan", 101)
    _must_contain(trade.special_sell("u1", "妖丹 1"), "特殊出售成功")
    _must_contain(trade.special_sell("u1", "妖丹 100"), "特殊出售成功")
    with trade.db.transaction() as conn:
        trade.add_backpack_conn(conn, "u1", "yaogu", 2)
        trade.add_backpack_conn(conn, "u1", "mohe", 1)
    _must_contain(trade.special_auto_sell("u1"), "特殊自动出售")
    _must_contain(trade.records("u1"), "特殊自动出售")
    explore: ExplorationService = services["explore"]  # type: ignore[assignment]
    _must_contain(explore.start("u1"), "当前位置不是探险地点")


def _check_history(services: dict[str, object]) -> None:
    """检查修仙早报里的全服天气和灵潮。"""

    history: XiuxianHistoryService = services["history"]  # type: ignore[assignment]

    text = history.newspaper("u1")
    _must_contain(text, "修仙早报")
    _must_contain(text, "天地气象")
    _must_contain(text, "今日天气")
    _must_contain(text, "今日灵潮")
    _must_contain(text, "全服生效")


def _check_wormhole(services: dict[str, object]) -> None:
    """检查异界虫洞的开启、挑战和领奖。"""

    wormhole: WormholeService = services["wormhole"]  # type: ignore[assignment]

    assert wormhole._daily_event_limit(0) == WORMHOLE_DAILY_MIN_LIMIT
    assert wormhole._daily_event_limit(1) == WORMHOLE_DAILY_MIN_LIMIT
    assert wormhole._daily_event_limit(4) == 4
    assert wormhole._daily_event_limit(40) == WORMHOLE_DAILY_MAX_LIMIT

    with wormhole.db.transaction() as conn:
        conn.execute("DELETE FROM wormhole_notices")
        conn.execute("DELETE FROM wormhole_participants")
        conn.execute("DELETE FROM wormholes")
    _must_contain(wormhole.status("u1"), "当前没有开启")
    event = wormhole._open_event("u1", "test", "天枢城")
    wormhole.db.execute(
        "UPDATE players SET location_name = ?, x = ?, y = ?, hp = max_hp, mp = max_mp, status = '探险中' WHERE client_id = ?",
        (event["location_name"], event["x"], event["y"], "u1"),
    )
    _must_contain(wormhole.status("u1"), "异界虫洞")
    _must_contain(wormhole.status("u1"), "今日出现")
    _must_contain(wormhole.ranking("u1"), "暂无挑战记录")
    _must_contain(wormhole.challenge("u1"), "行商化身")
    wormhole.db.execute("UPDATE players SET status = '空闲' WHERE client_id = ?", ("u1",))
    wormhole.db.execute("UPDATE players SET battle_log_detail = 1 WHERE client_id = ?", ("u1",))
    challenge_text = wormhole.challenge("u1")
    _must_contain(challenge_text, "挑战虫洞")
    _must_contain(challenge_text, "```javascript")
    _must_contain(challenge_text, "一、战斗明细")
    _must_contain(challenge_text, "我方出手")
    _must_contain(challenge_text, "Boss 出手")
    wormhole.db.execute("UPDATE players SET battle_log_detail = 0 WHERE client_id = ?", ("u1",))
    _must_contain(wormhole.challenge("u1"), "冷却中")

    with wormhole.db.transaction() as conn:
        conn.execute(
            "UPDATE wormholes SET hp = 1 WHERE wormhole_id = ?",
            (event["wormhole_id"],),
        )
        conn.execute(
            "UPDATE wormhole_participants SET last_challenge_at = '2000-01-01T00:00:00' WHERE wormhole_id = ? AND client_id = ?",
            (event["wormhole_id"], "u1"),
        )
        conn.execute("UPDATE players SET hp = max_hp, mp = max_mp WHERE client_id = ?", ("u1",))
    kill_text = wormhole.challenge("u1")
    _must_contain(kill_text, "Boss 已被击杀")
    _must_contain(kill_text, "我方技能")
    assert "二、最终结算" not in _payload_text(kill_text)
    reward_text = wormhole.reward("u1")
    _must_contain(reward_text, "虫洞奖励")
    assert "开孔器" not in reward_text
    assert "铭刻之羽" not in reward_text
    assert "异界残片" not in reward_text
    assert "兑换" not in reward_text

    with wormhole.db.transaction() as conn:
        conn.execute("DELETE FROM wormhole_notices")
        conn.execute("DELETE FROM wormhole_participants")
        conn.execute("DELETE FROM wormholes")
    daily_limit = wormhole._daily_event_limit(wormhole._world_snapshot()["active_count"])
    for index in range(daily_limit):
        capped_event = wormhole._open_event("u1", "test", "天枢城")
        wormhole.db.execute(
            "UPDATE wormholes SET status = '已退去', closes_at = ? WHERE wormhole_id = ?",
            ("2000-01-01T00:00:00", capped_event["wormhole_id"]),
        )
    assert wormhole._today_opened_count() == daily_limit
    assert wormhole.try_discover("u1", "trade_sell", "天枢城") == ""
    _must_contain(wormhole.status("u1"), "今日异界虫洞次数已满")


def _check_seasonal_boss(services: dict[str, object]) -> None:
    """检查岁时情劫、铭刻之羽文案和领奖流程。"""

    seasonal_boss: SeasonalBossService = services["seasonal_boss"]  # type: ignore[assignment]
    inscription: InscriptionService = services["inscription"]  # type: ignore[assignment]

    with seasonal_boss.db.transaction() as conn:
        conn.execute("DELETE FROM inscription_feathers WHERE client_id = ?", ("u1",))
        conn.execute("DELETE FROM seasonal_boss_participants")
        conn.execute("DELETE FROM seasonal_boss_events")
    boss_def, event_type, _weight = seasonal_boss._boss_for_date(date(2026, 7, 23))
    assert boss_def is not None and boss_def.key == "dashu"
    assert event_type == "二十四节气"
    boss_def, event_type, weight_type = seasonal_boss._boss_for_date(date(2026, 7, 22))
    assert boss_def is not None
    assert event_type == "每日旧愿"
    assert weight_type == "每日旧愿"
    assert boss_def.key in DAILY_BOSS_DEFS
    assert len(DAILY_BOSS_DEFS) >= 24
    daily_rates = seasonal_boss.db.fetch_one(
        "SELECT * FROM seasonal_boss_reward_rates WHERE weight_type = '每日旧愿'",
    )
    assert daily_rates is not None
    assert float(daily_rates["feather_chance"]) < 0.05
    assert float(daily_rates["weapon_chance"]) < 0.02
    event = seasonal_boss._open_event(date(2099, 2, 4), BOSS_DEFS["lichun"], "二十四节气", "普通节气")
    seasonal_boss.db.execute(
        "UPDATE seasonal_boss_events SET business_day = ?, hp = 1 WHERE event_id = ?",
        (seasonal_boss._business_date().isoformat(), event["event_id"]),
    )
    seasonal_boss.db.execute(
        "UPDATE players SET status = '探险中', hp = max_hp, mp = max_mp WHERE client_id = ?",
        ("u1",),
    )

    _must_contain(seasonal_boss.status("u1"), "折柳青郎")
    _must_contain(seasonal_boss.ranking("u1"), "暂无挑战记录")
    _must_contain(seasonal_boss.challenge("u1"), "行商化身")
    seasonal_boss.db.execute("UPDATE players SET status = '空闲' WHERE client_id = ?", ("u1",))
    seasonal_boss.db.execute("UPDATE players SET battle_log_detail = 1 WHERE client_id = ?", ("u1",))
    challenge_text = seasonal_boss.challenge("u1")
    _must_contain(challenge_text, "已被送回岁时深处")
    _must_contain(challenge_text, "```javascript")
    _must_contain(challenge_text, "一、战斗明细")
    _must_contain(challenge_text, "我方出手")
    _must_contain(challenge_text, "首领出手")
    seasonal_boss.db.execute("UPDATE players SET battle_log_detail = 0 WHERE client_id = ?", ("u1",))
    _must_contain(seasonal_boss.challenge("u1"), "不能继续挑战")
    old_boss_random = seasonal_boss_service_module.random.random
    try:
        seasonal_boss_service_module.random.random = lambda: 0.0
        reward_text = seasonal_boss.reward("u1")
    finally:
        seasonal_boss_service_module.random.random = old_boss_random
    _must_contain(reward_text, "岁时情劫奖励")
    _must_contain(reward_text, "珍贵战利品")
    assert any(text in reward_text for text in ("开孔器", "洗髓液", "铭刻之羽", "宝石获得", "纳戒获得", "获得武器"))

    feather = seasonal_boss.db.fetch_one(
        "SELECT feather_id FROM inscription_feathers WHERE client_id = ? ORDER BY feather_id LIMIT 1",
        ("u1",),
    )
    assert feather is not None
    feather_text = inscription.feathers("u1")
    _must_contain(feather_text, "折柳青郎遗羽")
    _must_contain(feather_text, "我一直在这里")
    _must_contain(inscription.fixed_equipment("u1", f"护甲 宿雨甲 #{feather['feather_id']}"), "旧念已入其名")


def _add_feathers_conn(conn, client_id: str, quantity: int) -> None:
    """给测试玩家补充带文案的铭刻之羽实例。"""

    for index in range(quantity):
        conn.execute(
            """
            INSERT INTO inscription_feathers
            (client_id, source_key, source_name, title, flavor_text, obtained_at)
            VALUES (?, 'test', '测试岁时情劫', ?, ?, '2000-01-01T00:00:00')
            """,
            (client_id, f"测试遗羽{index + 1}", f"这是一枚用于测试的铭刻之羽文案 {index + 1}。"),
        )


if __name__ == "__main__":
    main()
