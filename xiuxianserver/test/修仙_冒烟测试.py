"""修仙模块冒烟测试。

运行方式：

    python test/修仙_冒烟测试.py

测试使用临时 SQLite，不写入真实 xiuxian.db。
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from fastapi import Response
from starlette.requests import Request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from 修仙.combat_core import CombatCore
from 修仙.common import CoreService, business_day, dump_json, load_json, now, ts, weapon_id_label
from 修仙.constants import (
    BANK_LEVELS,
    CITY_MAX_LEVEL,
    ENCOUNTER_SECONDS,
    DONGTIAN_ROUND_MIN_SECONDS,
    EXPLORE_MINUTES,
    MAX_LEVEL,
    REST_FAST_SECONDS,
    REST_FULL_MINUTES,
    SECT_LEVEL_MAX,
    WEAPON_EXP_PER_ACTION,
    WORLD_COORD_MAX,
    WORLD_COORD_MIN,
    WORMHOLE_DAILY_MAX_LIMIT,
    WORMHOLE_DAILY_MIN_LIMIT,
)
from 修仙.notifications import collect_notifications
from 修仙.public_url import build_public_base_url
from 修仙.rules import (
    exp_need,
    monster_exp,
    monster_exp_rate,
    player_exp_for_level,
    rest_recovery_rate,
    trade_daily_reward_thresholds,
    weapon_enchant_slots,
    weapon_exp_for_level,
    weapon_exp_from_combat,
)
from 修仙.sect_war import record_sect_merit_conn, sect_level_exp_need, sect_war_cycle_finished
from 修仙.sql import XiuxianDB
from 修仙.world_skin import (
    apply_world_skin_package,
    current_help_map_path,
    load_skin_package,
    resolve_skin_package,
    validate_skin_package,
)
from 修仙.world_materials import WorldMaterialService
from 修仙.贸易服务.service import TradeService
from 修仙.修仙物品.service import ItemInfoService
from 修仙.战斗日志.site import _action_text
from 修仙.battle_log_links import battle_log_url
from 修仙.对战.service import DuelService
from 修仙.wormhole_service import WormholeService
from 修仙.探险.service import ExplorationService
from 修仙.二手市场.service import SecondHandService
from 修仙.武器.service import WeaponService
from 修仙.银行.service import BankService
from 修仙.修仙帮助.service import HelpService
from 修仙.修仙百科.service import EncyclopediaService
from 修仙.用户组.service import UserGroupService
from 修仙.玩家.service import PlayerService
from 修仙.洞天福地.bianling_color import bianling_color_config, finish_bianling_color, start_bianling_color
from 修仙.洞天福地.hedan_furnace import finish_hedan_furnace, hedan_furnace_config, start_hedan_furnace
from 修仙.洞天福地.jianfeng_chazhen import (
    finish_jianfeng_chazhen,
    jianfeng_chazhen_config,
    start_jianfeng_chazhen,
)
from 修仙.洞天福地.lingguo_sum_ten import finish_lingguo_sum_ten, lingguo_sum_ten_config, start_lingguo_sum_ten
from 修仙.洞天福地.lingpai_memory import finish_lingpai_memory, lingpai_memory_config, start_lingpai_memory
from 修仙.洞天福地.lingxi_fishing import (
    LINGXI_GAME_DURATION_SECONDS,
    finish_lingxi_fishing,
    lingxi_fishing_config,
    start_lingxi_fishing,
)
from 修仙.洞天福地.lingquan_ten_drop import finish_lingquan_ten_drop, lingquan_ten_drop_config, start_lingquan_ten_drop
from 修仙.洞天福地.service import DongtianService, dongtian_medicine_embryo_rate
from 修仙.洞天福地.suixing_qieyu import finish_suixing_qieyu, start_suixing_qieyu, suixing_qieyu_config
from 修仙.洞天福地.zhuiyuan_hundred_floor import finish_zhuiyuan_hundred_floor, start_zhuiyuan_hundred_floor, zhuiyuan_hundred_floor_config
from 修仙.宗门.service import SectService
from 修仙.纳戒.service import RingService
from 修仙.保险箱.service import InsuranceBoxService
from 修仙.装备.service import EquipmentService
from 修仙.铭刻.service import InscriptionService
from 修仙.首领.service import BOSS_DEFS, DAILY_BOSS_DEFS, SeasonalBossService
from 修仙.首领.seasonal_package import SEASONAL_BOSS_KIND, SEASONAL_SKILL_TEMPLATES, seasonal_skill_for_event
from 修仙.修仙界历史.service import XiuxianHistoryService

seasonal_boss_service_module = import_module("修仙.首领.service")
exploration_service_module = import_module("修仙.探险.service")
dongtian_routes_module = import_module("修仙.洞天福地")
dongtian_service_module = import_module("修仙.洞天福地.service")


def main() -> None:
    """按当前服务层跑一轮基础玩法。"""

    _check_exp_rules()
    _check_weapon_enchant_slots()
    _check_weapon_interval_rules()
    _check_battle_log_renderer()
    _check_public_urls()
    _check_newbie_gift_skin_names()
    with TemporaryDirectory() as temp_dir:
        db = XiuxianDB(Path(temp_dir) / "xiuxian_test.db")
        services = _build_services(db)
        try:
            _check_player(services)
            _check_sect(services)
            _check_battle_loss_mp(services)
            _check_inventory(services)
            _check_insurance_box(services)
            _check_equipment(services)
            _check_inscription(services)
            _check_duel(services)
            _check_second_hand_ring(services)
            _check_second_hand_weapon(services)
            _check_weapon_and_explore(services)
            _check_trade_and_treasure(services)
            _check_encyclopedia(services)
            _check_dongtian(services)
            _check_history(services)
            _check_wormhole(services)
            _check_seasonal_boss(services)
            _check_level_cap_discards(services)
        finally:
            db.close()

    print("修仙冒烟测试通过")


def _build_services(db: XiuxianDB) -> dict[str, object]:
    """创建绑定同一个临时库的测试服务。"""

    return {
        "player": PlayerService(db),
        "sect": SectService(db),
        "help": HelpService(db),
        "encyclopedia": EncyclopediaService(db),
        "bank": BankService(db),
        "ring": RingService(db),
        "insurance": InsuranceBoxService(db),
        "equipment": EquipmentService(db),
        "inscription": InscriptionService(db),
        "weapon": WeaponService(db),
        "explore": ExplorationService(db),
        "second_hand": SecondHandService(db),
        "trade": TradeService(db),
        "treasure": ItemInfoService(db),
        "duel": DuelService(db),
        "combat": CombatCore(db),
        "wormhole": WormholeService(db),
        "seasonal_boss": SeasonalBossService(db),
        "history": XiuxianHistoryService(db),
        "user_group": UserGroupService(db),
        "dongtian": DongtianService(db),
    }


def _check_newbie_gift_skin_names() -> None:
    """新手礼包发稳定物品 ID，展示名必须跟随当前世界皮肤。"""

    with TemporaryDirectory() as temp_dir:
        test_db = XiuxianDB(Path(temp_dir) / "skin_gift.db")
        try:
            package = load_skin_package("perfect_world")
            assert resolve_skin_package("完美世界").skin_id == "perfect_world"
            errors = validate_skin_package(package, test_db)
            assert not errors, errors
            with test_db.transaction() as conn:
                apply_world_skin_package(conn, package, switched_by="test")

            physique = test_db.fetch_one(
                """
                SELECT name, grade, kind, desc, effect
                FROM physique_defs
                WHERE physique_id = ?
                """,
                ("qingfeng_lingti",),
            )
            assert physique
            assert physique["name"] == "清风灵骨"
            assert physique["grade"] == "洞天灵骨"
            assert physique["kind"] == "鲲鹏"
            assert "肉身宝术对应原体质" in physique["desc"]
            assert load_json(physique["effect"]).get("dodge_bonus") == 0.01

            player = PlayerService(test_db)
            player.create("skin_newbie", "SkinTester")
            text = player.newbie_gift("skin_newbie")
            _must_contain(text, "真血契丹 2")
            _must_contain(text, "阴冥宝草 2")
            assert "血契丹 2、阴冥草 2" not in text
        finally:
            test_db.close()


def _check_encyclopedia(services: dict[str, object]) -> None:
    """百科要能综合 Markdown 设定，也要保留具体物品结构化回答。"""

    encyclopedia: EncyclopediaService = services["encyclopedia"]  # type: ignore[assignment]
    encyclopedia.load()
    sect_answer = encyclopedia.ask("u1", "宗门大会奖励机制")
    _must_contain(sect_answer, "综合")
    _must_contain(sect_answer, "参考：")
    _must_contain(sect_answer, "宗门")

    button_answer = encyclopedia.ask("u1", "按钮规则")
    _must_contain(button_answer, "手写按钮")
    _must_contain(button_answer, "预测按钮")

    gem_answer = encyclopedia.ask("u1", "轻身水晶有什么用")
    _must_contain(gem_answer, "探险效率")
    _must_contain(gem_answer, "实际收益")

    with encyclopedia.db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO ring_items (client_id, ring_item_id, quantity)
            VALUES (?, 'kaikongqi', 1)
            ON CONFLICT(client_id, ring_item_id)
            DO UPDATE SET quantity = quantity + 1
            """,
            ("u1",),
        )
    hole_answer = encyclopedia.ask("u1", "开孔器怎么用")
    _must_contain(hole_answer, "不走“使用”")
    _must_contain(hole_answer, "开孔 装备位")
    _must_contain(hole_answer, "纳戒库存：开孔器 x1")
    _must_contain(hole_answer, "当前建议")
    assert "普通背包物品乱用" not in hole_answer
    with encyclopedia.db.transaction() as conn:
        conn.execute(
            "DELETE FROM ring_items WHERE client_id = ? AND ring_item_id = 'kaikongqi'",
            ("u1",),
        )


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


def _must_not_contain(value: Any, text: str) -> None:
    """断言返回文本不包含指定内容。"""

    body = _payload_text(value)
    assert text not in body, f"返回内容不应包含 {text!r}：{value}"


def _check_battle_log_renderer() -> None:
    """检查网页战斗日志能识别敌方出手数据。"""

    monster_text = _action_text(
        {
            "round": 2,
            "actor": "enemy",
            "monster_attack": True,
            "monster_damage": 37,
            "player_hp_left": 123,
            "player_mp_left": 45,
        },
        "青岚狼",
        "怪物",
    )
    _must_contain(monster_text, "青岚狼 使用普通攻击，造成 37 伤害")
    _must_contain(monster_text, "我方血气 123，精神 45")
    _must_not_contain(monster_text, "怪物战斗记录")

    monster_priority_text = _action_text(
        {
            "round": 23,
            "actor": "enemy",
            "monster_attack": True,
            "skill_used": True,
            "skill_name": "回春刺",
            "damage": 999,
            "player_total_damage": 999,
            "monster_damage": 51,
            "life_steal": 4,
            "mp_cost": 7,
            "player_hp_left": 675,
            "player_mp_left": 680,
        },
        "寒魄鬼",
        "怪物",
    )
    _must_contain(monster_priority_text, "寒魄鬼 使用技能「回春刺」，造成 51 伤害")
    _must_not_contain(monster_priority_text, "造成 999 伤害")

    mirror_text = _action_text(
        {
            "round": 24,
            "actor": "enemy",
            "monster_attack": False,
            "boss_attack": False,
            "skill_used": True,
            "skill_name": "回春刺",
            "damage": 999,
            "player_total_damage": 999,
            "monster_damage": 0,
            "boss_damage": 0,
            "life_steal": 4,
            "mp_cost": 7,
            "player_hp_left": 675,
            "player_mp_left": 680,
        },
        "太虚映身·寒魄鬼",
        "怪物",
    )
    _must_contain(mirror_text, "太虚映身·寒魄鬼 使用技能「回春刺」，造成 999 伤害")
    _must_contain(mirror_text, "吸血 +4")
    _must_contain(mirror_text, "消耗精神 7")
    _must_contain(mirror_text, "我方血气 675，精神 680")
    _must_not_contain(mirror_text, "怪物战斗记录")


def _check_public_urls() -> None:
    """公开链接协议跟随后端 SSL 状态。"""

    assert build_public_base_url("example.com", 8080, https_enabled=False) == "http://example.com:8080"
    assert build_public_base_url("example.com", 8443, https_enabled=True) == "https://example.com:8443"
    assert build_public_base_url("https://example.com", 443, https_enabled=False) == "https://example.com"
    assert build_public_base_url("http://example.com", 80, https_enabled=True) == "http://example.com"
    assert build_public_base_url("example.com/base", 8443, https_enabled=True) == "https://example.com:8443/base"
    assert battle_log_url("explore", 1).startswith("https://")
    with TemporaryDirectory() as temp_dir:
        test_db = XiuxianDB(Path(temp_dir) / "help_map.db")
        try:
            assert current_help_map_path(test_db).endswith("/static/map/default.jpg")
        finally:
            test_db.close()


def _advance_rest_seconds(player: PlayerService, client_id: str, seconds: int) -> None:
    """把当前休息状态模拟为已经持续指定秒数。"""

    row = player.player(client_id)
    assert row is not None
    full_seconds = REST_FULL_MINUTES * 60
    elapsed = max(0, min(full_seconds, int(row["rest_window_elapsed_seconds"] or 0)))
    remaining = max(0, full_seconds - elapsed)
    full_at = now() + timedelta(seconds=remaining - max(0, int(seconds)))
    player.db.execute(
        "UPDATE players SET status = '休息中', rest_full_at = ? WHERE client_id = ?",
        (ts(full_at), client_id),
    )


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
    player_total_exp = sum(exp_need(level) for level in range(1, MAX_LEVEL))
    weapon_total_exp = weapon_exp_for_level(MAX_LEVEL)
    ratio = weapon_total_exp / player_total_exp
    assert player_total_exp == 351398872
    assert weapon_total_exp == 117132935
    assert 0.32 <= ratio <= 0.35
    assert player_exp_for_level(1) == 0
    assert player_exp_for_level(MAX_LEVEL) == player_total_exp
    assert weapon_exp_for_level(0) == 0
    assert weapon_exp_for_level(1) < weapon_exp_for_level(40) < weapon_exp_for_level(100)
    assert sect_level_exp_need(1) == 5100
    assert sect_level_exp_need(SECT_LEVEL_MAX - 1) == 3300071
    assert sect_level_exp_need(SECT_LEVEL_MAX) == 0
    assert sum(sect_level_exp_need(level) for level in range(1, SECT_LEVEL_MAX)) == 129266969
    assert WorldMaterialService.build_exp_need(1) == 4200
    assert WorldMaterialService.build_exp_need(CITY_MAX_LEVEL - 1) == 5623567
    assert WorldMaterialService.build_exp_need(CITY_MAX_LEVEL) == 0
    assert sum(WorldMaterialService.build_exp_need(level) for level in range(1, CITY_MAX_LEVEL)) == 220526841
    assert WorldMaterialService.relic_limit(1) == 5180
    assert WorldMaterialService.relic_limit(50) == 14000
    assert WorldMaterialService.relic_limit(CITY_MAX_LEVEL) == 24260
    assert WorldMaterialService._treasure_start_price(1) == 30800
    assert WorldMaterialService._treasure_start_price(50) == 70000
    assert WorldMaterialService._treasure_start_price(CITY_MAX_LEVEL) == 115600
    assert monster_exp_rate(50, 50) == 1.0
    assert monster_exp_rate(45, 50) < 1.0
    assert monster_exp_rate(55, 50) > 1.0
    assert monster_exp(45, 1.0, 50) < monster_exp(50, 1.0, 50)
    assert monster_exp(55, 1.0, 50) > monster_exp(50, 1.0, 50)
    calm_weapon_exp = weapon_exp_from_combat(
        6,
        player_action_count=2,
        player_level=50,
        opponent_level=50,
        damage_dealt=0,
        damage_taken=0,
        opponent_max_hp=1000,
        player_max_hp=1000,
    )
    pressured_weapon_exp = weapon_exp_from_combat(
        6,
        player_action_count=2,
        player_level=50,
        opponent_level=50,
        damage_dealt=1000,
        damage_taken=500,
        opponent_max_hp=1000,
        player_max_hp=1000,
    )
    hard_weapon_exp = weapon_exp_from_combat(
        6,
        player_action_count=2,
        player_level=50,
        opponent_level=58,
        damage_dealt=1000,
        damage_taken=500,
        opponent_max_hp=1000,
        player_max_hp=1000,
    )
    boss_weapon_exp = weapon_exp_from_combat(
        6,
        player_action_count=2,
        player_level=50,
        opponent_level=58,
        damage_dealt=1000,
        damage_taken=500,
        opponent_max_hp=1000,
        player_max_hp=1000,
        battle_factor=1.3,
    )
    no_action_weapon_exp = weapon_exp_from_combat(
        2,
        player_action_count=0,
        player_level=30,
        opponent_level=35,
        damage_dealt=0,
        damage_taken=400,
        opponent_max_hp=1000,
        player_max_hp=1000,
    )
    assert pressured_weapon_exp > calm_weapon_exp
    assert hard_weapon_exp > pressured_weapon_exp
    assert boss_weapon_exp > hard_weapon_exp
    assert no_action_weapon_exp >= WEAPON_EXP_PER_ACTION
    assert rest_recovery_rate(0) == 0.0
    assert rest_recovery_rate(REST_FAST_SECONDS) == 0.5
    assert rest_recovery_rate(REST_FULL_MINUTES * 60) == 1.0
    assert rest_recovery_rate(REST_FULL_MINUTES * 60 + 60) == 1.0
    assert PlayerService._rest_recover_bonus_text(1.04) == "，恢复增益 **104%**"
    assert PlayerService._rest_recover_bonus_text(1.035) == "，恢复增益 **103.5%**"
    assert PlayerService._rest_recover_bonus_text(0.96) == "，恢复增益 **96%**"
    assert PlayerService._rest_recover_bonus_text(1.0) == ""
    assert not sect_war_cycle_finished("2026-06-22", datetime(2026, 6, 19, 12, 0, 0))
    assert sect_war_cycle_finished("2026-06-22", datetime(2026, 6, 21, 0, 0, 0))
    assert sect_war_cycle_finished("2026-06-22", datetime(2026, 6, 22, 0, 0, 0))


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
    """检查玩家、签到、新手礼包和银行。"""

    player: PlayerService = services["player"]  # type: ignore[assignment]
    help_service: HelpService = services["help"]  # type: ignore[assignment]
    bank: BankService = services["bank"]  # type: ignore[assignment]
    user_group: UserGroupService = services["user_group"]  # type: ignore[assignment]

    _check_bank_interest_caps()
    _must_contain(help_service.command_guide(), "<指南 战斗:玩家对战>")
    _must_contain(help_service.command_guide("账户"), "<用户组>")
    _must_contain(help_service.command_guide("探险"), "<探险状态>")
    _must_contain(help_service.command_guide("探险"), "<结束探险>")
    _must_contain(help_service.command_guide("战斗"), "<抢劫 玩家名>")
    user_group_overview = user_group.overview()
    _must_contain(user_group_overview, "[用户组后台](")
    assert "网页登录：http" not in user_group_overview
    create_text = player.create("u1", "青衫客")
    _must_contain(create_text, "创建成功")
    _must_contain(create_text, "青岚短剑")
    assert "u1" not in create_text
    assert user_group.resolve_player_id("u1") == "u1"
    _must_contain(player.create("u9", "青衫客"), "名称已经被使用")
    _must_contain(player.create("u1", "青衫客"), "已经创建过用户")
    _must_contain(player.create("user_group_existing", "系舟客"), "创建成功")
    challenge = user_group.create_login_challenge()
    _must_contain(user_group.confirm_admin_login("u1", str(challenge["challenge_id"])), "用户组后台登录已确认")
    status = user_group.login_status(str(challenge["session_id"]))
    assert status["confirmed"] is True
    assert status["player_id"] == "u1"
    bind_code = user_group.create_bind_code(str(challenge["session_id"]))
    _must_contain(user_group.bind_user_group("u1_alt", str(bind_code["code"])), "用户组绑定成功")
    assert user_group.resolve_player_id("u1_alt") == "u1"
    identities = user_group.identities(str(challenge["session_id"]))
    assert {row["client_id"] for row in identities} == {"u1", "u1_alt"}
    second_bind = user_group.create_bind_code(str(challenge["session_id"]))
    _must_contain(
        user_group.bind_user_group("user_group_existing", str(second_bind["code"])),
        "当前账号已经创建过修仙用户",
    )
    user_group.cleanup_expired()
    assert user_group.db.fetch_one("SELECT 1 FROM user_group_bind_codes WHERE code = ?", (bind_code["code"],)) is None
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
    assert "天气：" not in profile_text
    assert "灵潮：" not in profile_text
    _must_contain(profile_text, "今日加成：")
    _must_contain(profile_text, "战斗日志：简要")
    _must_contain(profile_text, "青岚短剑")
    assert "未装备" not in profile_text
    status_text = player.status("u1")
    _must_contain(status_text, "当前武器：")
    _must_contain(status_text, "青岚短剑")
    _must_contain(status_text, "装备数值")
    _must_contain(status_text, "装备等级：血气")
    _must_contain(status_text, "镶嵌宝石：血气")
    _must_contain(status_text, "宝石特效：闪避")
    assert "当前武器：未装备" not in status_text
    player.db.execute("UPDATE player_weapons SET equipped = 0 WHERE holder_id = ?", ("u1",))
    recovered_status_text = player.status("u1")
    _must_contain(recovered_status_text, "青岚短剑")
    assert "当前武器：未装备" not in recovered_status_text
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
    currency_info = bank.currency("u1")
    _must_contain(currency_info, "货币")
    _must_contain(currency_info, "随身原石")
    _must_contain(currency_info, "银行原石")
    _must_contain(currency_info, "合计：")
    _must_contain(currency_info, "<银行>")
    bank_info = bank.info("u1")
    _must_contain(bank_info, "银行")
    _must_contain(bank_info, "待结息：")
    _must_contain(bank_info, "下级：二星")
    _must_contain(bank_info, "<银行结息>")
    player.add_stones("u1", 10_000)
    _must_contain(bank.info("u1"), "<存入货币 ")
    _must_contain(bank.deposit("u1", 1000), "已存入：原石")
    _must_contain(bank.info("u1"), "<取出货币 1000>")
    _must_contain(bank.withdraw("u1", 100), "已取出：原石")
    player.db.execute(
        """
        UPDATE bank_accounts
        SET last_interest_day = ?, daily_interest_claimed = 999
        WHERE client_id = ?
        """,
        ((date.fromisoformat(business_day()) - timedelta(days=1)).isoformat(), "u1"),
    )
    _must_contain(bank.info("u1"), "今日利息：**原石 0/8000**")
    player.db.execute("UPDATE players SET hp = 0, mp = 0, status = '空闲' WHERE client_id = 'u1'")
    _must_contain(player.rest("u1"), "满 1 分钟")
    _must_contain(player.end_rest("u1"), "至少需要休息")
    _advance_rest_seconds(player, "u1", REST_FAST_SECONDS)
    _must_contain(player.end_rest("u1"), "休息结束")
    half_rest_row = player.player("u1")
    assert half_rest_row
    half_hp = int(half_rest_row["hp"])
    half_mp = int(half_rest_row["mp"])
    assert half_hp >= int(half_rest_row["max_hp"] * 0.5)
    assert half_mp >= int(half_rest_row["max_mp"] * 0.5)
    assert half_hp < int(half_rest_row["max_hp"])
    assert half_mp < int(half_rest_row["max_mp"])
    _must_contain(player.rest("u1"), "满 1 分钟")
    _advance_rest_seconds(player, "u1", REST_FAST_SECONDS)
    chained_rest_text = player.end_rest("u1")
    _must_contain(chained_rest_text, "休息结束")
    chained_rest_row = player.player("u1")
    assert chained_rest_row
    second_max_hp = int(half_rest_row["max_hp"])
    second_max_mp = int(half_rest_row["max_mp"])
    second_missing = second_max_hp - half_hp + second_max_mp - half_mp
    second_base_rate = rest_recovery_rate(REST_FAST_SECONDS * 2)
    second_recover_multiplier = max(0.0, 1 + float(player.equipment_bonuses("u1").get("recover_bonus", 0)))
    second_recover_rate = max(0.0, min(1.0, second_base_rate * second_recover_multiplier))
    second_hp = player._rest_recover_value(0, half_hp, second_max_hp, second_recover_rate)
    second_mp = player._rest_recover_value(0, half_mp, second_max_mp, second_recover_rate)
    second_gain = second_hp - half_hp + second_mp - half_mp
    second_rate = round(second_gain / second_missing * 100) if second_missing > 0 else 100
    _must_contain(chained_rest_text, f"恢复效率 **{second_rate}%**")
    assert int(chained_rest_row["hp"]) < int(chained_rest_row["max_hp"])
    assert int(chained_rest_row["mp"]) < int(chained_rest_row["max_mp"])
    player.db.execute(
        """
        INSERT INTO fixed_equipment_inlays (client_id, slot, hole_no, gem_id, level)
        VALUES ('u1', '饰品', 1, 'huichun feicui', 1)
        """,
    )
    with player.db.transaction() as conn:
        conn.execute("UPDATE players SET hp = 0, mp = 0, status = '空闲' WHERE client_id = 'u1'")
        player.reset_rest_window_conn(conn, "u1", 0, 0)
    reset_row = player.player("u1")
    assert reset_row and int(reset_row["rest_window_elapsed_seconds"]) == 0
    _must_contain(player.rest("u1"), "满 1 分钟")
    _advance_rest_seconds(player, "u1", REST_FULL_MINUTES * 60)
    full_rest_text = player.end_rest("u1")
    _must_contain(full_rest_text, "恢复效率 **100%**")
    recover_multiplier = max(0.0, 1 + float(player.equipment_bonuses("u1").get("recover_bonus", 0)))
    expected_recover_bonus_text = PlayerService._rest_recover_bonus_text(recover_multiplier)
    _must_contain(full_rest_text, expected_recover_bonus_text)
    row = player.player("u1")
    assert row and int(row["hp"]) == int(row["max_hp"]) and int(row["mp"]) == int(row["max_mp"])
    with player.db.transaction() as conn:
        conn.execute("UPDATE players SET hp = 0, mp = 0, status = '空闲' WHERE client_id = 'u1'")
        player.reset_rest_window_conn(conn, "u1", 0, 0)
    _must_contain(player.rest("u1"), "满 1 分钟")
    _advance_rest_seconds(player, "u1", REST_FAST_SECONDS)
    recover_multiplier = max(0.0, 1 + float(player.equipment_bonuses("u1").get("recover_bonus", 0)))
    expected_recover_bonus_text = PlayerService._rest_recover_bonus_text(recover_multiplier)
    boosted_row = player.player("u1")
    assert boosted_row
    boosted_max_hp = int(boosted_row["max_hp"])
    boosted_max_mp = int(boosted_row["max_mp"])
    boosted_recover_rate = max(0.0, min(1.0, rest_recovery_rate(REST_FAST_SECONDS) * recover_multiplier))
    boosted_hp = player._rest_recover_value(0, 0, boosted_max_hp, boosted_recover_rate)
    boosted_mp = player._rest_recover_value(0, 0, boosted_max_mp, boosted_recover_rate)
    boosted_rate = round((boosted_hp + boosted_mp) / (boosted_max_hp + boosted_max_mp) * 100)
    boosted_rest_text = player.end_rest("u1")
    _must_contain(boosted_rest_text, f"恢复效率 **{boosted_rate}%**")
    _must_contain(boosted_rest_text, expected_recover_bonus_text)
    assert "恢复增益 **100%**" not in boosted_rest_text
    assert "恢复增益 **-" not in boosted_rest_text


def _check_bank_interest_caps() -> None:
    """银行日上限覆盖满库存 24 小时利息，并保持高星级总量更高。"""

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


def _check_sect(services: dict[str, object]) -> None:
    """检查宗门建立和到山门加入。"""

    sect: SectService = services["sect"]  # type: ignore[assignment]
    player: PlayerService = services["player"]  # type: ignore[assignment]
    sect._is_member_locked = lambda value=None: False  # type: ignore[method-assign]

    _must_contain(sect.overview("u1"), "你还没有宗门")
    _must_contain(sect.create("u1", "0 0 青云宗"), "已有系统保留地点")
    create_text = sect.create("u1", "-49 -49 青云宗")
    _must_contain(create_text, "宗门创建成功")
    _must_contain(create_text, "山门坐标：(-49,-49)")
    overview_text = sect.overview("u1")
    _must_contain(overview_text, "宗门：青云宗")
    _must_contain(overview_text, "山门：青云宗山门 (-49,-49)")
    _must_contain(overview_text, "宗主：青衫客")
    _must_contain(overview_text, "身份：宗主")
    _must_contain(overview_text, "成员：1")
    row = sect.db.fetch_one("SELECT * FROM sects WHERE name = ?", ("青云宗",))
    assert row is not None
    assert row["master_client_id"] == "u1"
    assert row["founder_id"] == "u1"
    member = sect.db.fetch_one("SELECT role FROM sect_members WHERE client_id = ?", ("u1",))
    assert member and member["role"] == "宗主"
    _must_contain(sect.create("u1", "-48 -49 紫霄宗"), "你已经有宗门")

    player.create("sect_u2", "白鹿客")
    _must_contain(sect.join("sect_u2", "青云宗"), "需要到山门所在地")
    sect.db.execute(
        "UPDATE players SET location_name = '青云宗山门', x = -49, y = -49 WHERE client_id = ?",
        ("sect_u2",),
    )
    visitor_text = sect.overview("sect_u2")
    _must_contain(visitor_text, "这里是宗门：青云宗")
    _must_contain(visitor_text, "宗主：青衫客")
    _must_contain(visitor_text, "<加入宗门 青云宗>")
    _must_contain(visitor_text, "<宗门成员 青云宗:成员名册>")
    _must_contain(visitor_text, "<宗门大会>")
    _must_contain(visitor_text, "<宗门><地图>")
    _must_contain(sect.join("sect_u2", ""), "加入宗门 青云宗")
    _must_contain(sect.join("sect_u2", "青云宗"), "已加入宗门：青云宗")
    joined_text = sect.overview("sect_u2")
    _must_contain(joined_text, "宗门：青云宗")
    _must_contain(joined_text, "身份：成员")
    _must_contain(joined_text, "成员：2")
    _must_contain(joined_text, "<宗门成员>")
    members_text = sect.members("sect_u2", "")
    _must_contain(members_text, "宗门成员")
    _must_contain(members_text, "宗门：青云宗｜成员 2 人")
    _must_contain(members_text, "宗主：青衫客·初入仙途 LV1")
    _must_contain(members_text, "1. 青衫客·初入仙途 LV1｜宗主｜本期贡献 0（0.0%）")
    _must_contain(members_text, "白鹿客·无 LV1｜成员｜本期贡献 0（0.0%）")
    _must_contain(sect.create("sect_u2", "-48 -49 紫霄宗"), "你已经有宗门")

    player.create("sect_u3", "白石客")
    _must_contain(sect.members("sect_u3", "青云宗"), "宗门：青云宗｜成员 2 人")
    _must_contain(sect.create("sect_u2", "-49 -49 紫霄宗"), "已经有宗门")
    _must_contain(sect.create("sect_u3", "-48 -49 青云宗"), "宗门名 青云宗 已被使用")
    _must_contain(sect.create("sect_u3", "101 0 越界宗"), "超出当前地图范围")
    _must_contain(sect.create("sect_u3", "100 100 紫霄宗"), "宗门创建成功")


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
    before_stones = player.player("u1")["raw_stones"]  # type: ignore[index]
    _must_contain(ring.use_item("u1", "福袋"), "原石 ")
    after_stones = player.player("u1")["raw_stones"]  # type: ignore[index]
    assert 10_000 <= after_stones - before_stones <= 30_000

    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "fudai", 3)
    before_stones = player.player("u1")["raw_stones"]  # type: ignore[index]
    _must_contain(ring.use_item("u1", "福袋 3"), "使用 福袋 x3 成功")
    after_stones = player.player("u1")["raw_stones"]  # type: ignore[index]
    assert 30_000 <= after_stones - before_stones <= 90_000
    assert not ring.db.fetch_one(
        "SELECT 1 FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
        ("u1", "fudai"),
    )

    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "fudai", 2)
    before_stones = player.player("u1")["raw_stones"]  # type: ignore[index]
    _must_contain(ring.use_item("u1", "福袋 3"), "纳戒里没有足够的 福袋 x3")
    after_stones = player.player("u1")["raw_stones"]  # type: ignore[index]
    assert after_stones == before_stones
    row = ring.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
        ("u1", "fudai"),
    )
    assert row and row["quantity"] == 2

    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "xisuiye", 1)
        ring.add_ring_conn(conn, "u1", "fengren_shu", 1)
    _must_contain(ring.use_item("u1", "洗髓液"), "不能直接使用")
    _must_contain(ring.use_item("u1", "风刃书"), "不能直接使用")
    _must_contain(ring.remold_physique("u1"), "体质重塑")
    row = player.player("u1")
    assert row and row["physique_id"]
    physique = player.db.fetch_one(
        "SELECT physique_value FROM physique_defs WHERE physique_id = ?",
        (row["physique_id"],),
    )
    assert physique and int(row["physique_value"]) == int(physique["physique_value"])


def _check_insurance_box(services: dict[str, object]) -> None:
    """检查保险箱冻结背包、纳戒、宝石和备用武器。"""

    backpack: CoreService = services["treasure"]  # type: ignore[assignment]
    ring: RingService = services["ring"]  # type: ignore[assignment]
    insurance: InsuranceBoxService = services["insurance"]  # type: ignore[assignment]
    trade: TradeService = services["trade"]  # type: ignore[assignment]
    weapon: WeaponService = services["weapon"]  # type: ignore[assignment]

    with insurance.db.transaction() as conn:
        conn.execute("DELETE FROM backpack_items WHERE client_id = ? AND item_id = ?", ("u1", "loot_yao_1"))
        conn.execute("DELETE FROM ring_items WHERE client_id = ? AND ring_item_id IN ('xueqidan', 'fengren_shu')", ("u1",))
        conn.execute("DELETE FROM gem_items WHERE client_id = ? AND gem_id = ?", ("u1", "huxinyu"))
        insurance.add_backpack_conn(conn, "u1", "loot_yao_1", 2)
        insurance.add_ring_conn(conn, "u1", "xueqidan", 2)
        insurance.add_ring_conn(conn, "u1", "fengren_shu", 1)
        insurance.add_gem_conn(conn, "u1", "huxinyu", 2, 1)

    _must_contain(insurance.deposit("u1", "古妖丹 1"), "已存入保险箱")
    _must_contain(insurance.deposit("u1", "血契丹 1"), "已存入保险箱")
    _must_contain(insurance.deposit("u1", "风刃书 1"), "已存入保险箱")
    _must_contain(insurance.deposit("u1", "护心玉 2级 1"), "已存入保险箱")
    list_text = insurance.list_items("u1")
    _must_contain(list_text, "箱内物品已冻结")
    _must_contain(list_text, "古妖丹 x1")
    _must_contain(list_text, "血契丹 x1")
    _must_contain(list_text, "风刃书 x1")
    _must_contain(list_text, "护心玉 2级 x1")

    _must_contain(trade.sell_any("u1", "古妖丹 2"), "背包中 古妖丹 数量不足")
    _must_contain(ring.use_item("u1", "血契丹 2"), "纳戒里没有足够的 血契丹 x2")
    held_book = insurance.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
        ("u1", "fengren_shu"),
    )
    assert held_book is None or int(held_book["quantity"]) == 0

    weapon_id = weapon.create_weapon("u1", "qinglan_duanjian", "凡品", 40, equipped=False)
    _must_contain(insurance.deposit("u1", f"武器#{weapon_id}"), "已存入保险箱")
    assert weapon.weapon("u1", weapon_id) is None
    _must_contain(trade.sell_any("u1", f"武器#{weapon_id} 1"), "没有找到武器")
    _must_contain(weapon.enchant("u1", f"武器#{weapon_id} 风刃书"), "没有找到这把武器")

    _must_contain(insurance.withdraw("u1", "古妖丹 1"), "已取出到背包")
    _must_contain(insurance.withdraw("u1", "血契丹 1"), "已取出到纳戒")
    _must_contain(insurance.withdraw("u1", "风刃书 1"), "已取出到纳戒")
    _must_contain(insurance.withdraw("u1", "护心玉 2级 1"), "已取出到纳戒")
    _must_contain(insurance.withdraw("u1", f"武器#{weapon_id}"), "已取出到武器库")
    assert weapon.weapon("u1", weapon_id) is not None
    _must_contain(backpack.info("u1", "古妖丹"), "存放：背包")
    _must_contain(insurance.list_items("u1"), "保险箱为空")
    insurance.db.execute(
        "DELETE FROM gem_items WHERE client_id = ? AND gem_id = ? AND level = ?",
        ("u1", "huxinyu", 2),
    )


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
    assert result["exp"] == 0
    assert "经验+0" in result["summary"]
    combat.db.execute(
        "UPDATE players SET hp = max_hp, mp = max_mp WHERE client_id = ?",
        ("u1",),
    )


def _check_equipment(services: dict[str, object]) -> None:
    """检查装备升级和宝石镶嵌。"""

    equipment: EquipmentService = services["equipment"]  # type: ignore[assignment]
    ring: RingService = services["ring"]  # type: ignore[assignment]
    trade: TradeService = services["trade"]  # type: ignore[assignment]

    with equipment.db.transaction() as conn:
        conn.execute("UPDATE players SET raw_stones = raw_stones + 50000 WHERE client_id = ?", ("u1",))
        equipment.add_ring_conn(conn, "u1", "huxinyu", 1)
        equipment.add_ring_conn(conn, "u1", "huxinyu", 1)
        equipment.add_ring_conn(conn, "u1", "jucai zijing", 1)
        equipment.add_ring_conn(conn, "u1", "xuangui shi", 1)
        equipment.add_ring_conn(conn, "u1", "kaikongqi", 6)
    equipment_text = equipment.list_equipment("u1")
    _must_contain(equipment_text, "头部")
    assert equipment_text.find("头部") < equipment_text.find("左手") < equipment_text.find("右手")
    _must_contain(equipment_text, "装备等级：")
    _must_contain(equipment_text, "镶嵌宝石：")
    _must_contain(equipment_text, "宝石特效：")
    _must_contain(equipment_text, "<孔位>")
    _must_contain(equipment_text, "<宝石>")
    _must_contain(equipment.upgrade("u1", "头部"), "升级成功")
    _must_contain(equipment.inlay("u1", "头部 1 护心玉"), "镶嵌成功")
    head_holes = equipment.holes("u1", "头部")
    _must_contain(head_holes, "<宝石升级 头部 1:升级1孔>")
    _must_not_contain(head_holes, "<宝石升级 头部 2:升级2孔>")
    _must_contain(equipment.inlay("u1", "左手 2 聚财紫晶"), "镶嵌成功")
    _must_contain(equipment.inlay("u1", "头部 4 玄龟石"), "当前只开启到 3 号孔")
    _must_contain(ring.open_equipment_hole("u1", "头部"), "开孔成功")
    _must_contain(equipment.inlay("u1", "头部 4 玄龟石"), "镶嵌成功")
    _must_contain(equipment.inlay("u1", "头部 2 护心玉"), "镶嵌成功")
    _must_contain(equipment.upgrade_inlay("u1", "护心玉"), "需要用装备位和孔位号定位")
    for _ in range(5):
        _must_contain(ring.open_equipment_hole("u1", "头部"), "开孔成功")
    _must_contain(ring.open_equipment_hole("u1", "头部"), "已经达到 9 孔上限")
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
    before_recycle = equipment.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    _must_contain(trade.sell_any("u1", "护心玉 2级 1"), "回收成功")
    after_recycle = equipment.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_recycle and after_recycle
    gained = int(after_recycle["raw_stones"]) - int(before_recycle["raw_stones"])
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
    before_gem_batch = equipment.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    gem_batch_text = trade.sell_all("u1", "宝石")
    _must_contain(gem_batch_text, "宝石批量回收")
    _must_contain(gem_batch_text, "护心玉 2级")
    after_gem_batch = equipment.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_gem_batch and after_gem_batch
    assert int(after_gem_batch["raw_stones"]) > int(before_gem_batch["raw_stones"])
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
        "SELECT weapon_id FROM player_weapons WHERE holder_id = ? ORDER BY weapon_id LIMIT 1",
        ("u1",),
    )
    assert weapon_row is not None
    weapon_id = int(weapon_row["weapon_id"])

    with inscription.db.transaction() as conn:
        _add_feathers_conn(conn, "u1", 4)
        inscription.add_ring_conn(conn, "u1", "fengren_shu", 1)
        conn.execute(
            "UPDATE player_weapons SET level = 20, max_level = 45 WHERE holder_id = ? AND weapon_id = ?",
            ("u1", weapon_id),
    )

    text = inscription.fixed_equipment("u1", "头部 青云冠")
    _must_contain(text, "铭刻成功：青云冠（头部）")
    _must_not_contain(text, "->")
    _must_contain(equipment.list_equipment("u1"), "青云冠（头部）")
    _must_contain(player.profile("u1"), "青云冠（头部）")
    with inscription.db.transaction() as conn:
        _add_feathers_conn(conn, "u1", 1)
    text = inscription.fixed_equipment("u1", "饰品 月华沉梦")
    _must_contain(text, "铭刻成功：月华沉梦（饰品）")
    _must_not_contain(text, "->")
    profile_text = player.profile("u1")
    _must_contain(profile_text, "月华沉梦（饰品）")
    assert not any("右脚" in line and "月华沉梦" in line for line in profile_text.splitlines())
    text = inscription.weapon("u1", f"武器#{weapon_id} 青云剑")
    _must_contain(text, "铭刻成功：青云剑（青岚短剑）")
    _must_not_contain(text, "->")
    _must_contain(weapon.list_weapons("u1"), "青云剑（青岚短剑）")
    text = inscription.skill("u1", f"武器#{weapon_id} 青云斩")
    _must_contain(text, "铭刻成功：青云剑（青岚短剑）的青云斩（风刃斩）")
    _must_not_contain(text, "->")
    _must_contain(weapon.list_weapons("u1"), "青云斩（风刃斩）")
    _must_contain(player.profile("u1"), "青云斩（风刃斩）")
    _must_contain(weapon.enchant("u1", f"{weapon_id} 风刃书"), "附魔成功")
    text = inscription.enchant("u1", f"武器#{weapon_id} 1 青云破")
    _must_contain(text, "铭刻成功：青云剑（青岚短剑）的青云破（风刃书）")
    _must_not_contain(text, "->")
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
    u1_weapon_before = duel.db.fetch_one("SELECT weapon_id, exp FROM player_weapons WHERE holder_id = 'u1' AND equipped = 1")
    u2_weapon_before = duel.db.fetch_one("SELECT weapon_id, exp FROM player_weapons WHERE holder_id = 'u2' AND equipped = 1")
    _must_contain(duel.duel("u1", "白衣客 1000"), "发起决斗")
    duel_result = duel.accept_duel("u2", "青衫客")
    _must_contain(duel_result, "决斗结算")
    _must_contain(duel_result, "决斗结束")
    _must_not_contain(duel_result, "武器经验")
    u1_weapon_after = duel.db.fetch_one("SELECT exp FROM player_weapons WHERE weapon_id = ?", (u1_weapon_before["weapon_id"],))
    u2_weapon_after = duel.db.fetch_one("SELECT exp FROM player_weapons WHERE weapon_id = ?", (u2_weapon_before["weapon_id"],))
    assert int(u1_weapon_after["exp"]) == int(u1_weapon_before["exp"])
    assert int(u2_weapon_after["exp"]) == int(u2_weapon_before["exp"])
    duel_body = _payload_text(duel_result)
    assert "一、战斗明细" not in duel_body
    assert "技能：" not in duel_body
    assert "行动 **" not in duel_body
    assert "u1" not in duel_body
    assert "u2" not in duel_body
    _must_contain(duel.accept_duel("u2", "青衫客"), "没有找到待接受")

    _must_contain(player.battle_log("u2", "开启"), "详细")
    _must_contain(duel.duel("u1", "白衣客 100"), "发起决斗")
    detail_duel_result = duel.accept_duel("u2", "青衫客")
    _must_contain(detail_duel_result, "战斗日志")
    _must_contain(detail_duel_result, "zhandou-rizhi/duel")
    _must_contain(detail_duel_result, "detail=1")
    _must_not_contain(detail_duel_result, "武器经验")
    _must_contain(player.battle_log("u2", "关闭"), "简要")

    before = player.player("u1")["raw_stones"]  # type: ignore[index]
    _must_contain(duel.duel("u1", "白衣客 500"), "发起决斗")
    frozen = player.player("u1")["raw_stones"]  # type: ignore[index]
    assert before - frozen == 500
    duel.db.execute(
        "UPDATE duel_requests SET expires_at = ? WHERE status = '等待'",
        ("2000-01-01 00:00:00",),
    )
    _must_contain(duel.accept_duel("u2", "青衫客"), "没有找到待接受")
    refunded = player.player("u1")["raw_stones"]  # type: ignore[index]
    assert refunded == before

    _must_contain(duel.spar("u1", "白衣客"), "发起切磋")
    duel.db.execute("UPDATE players SET status = '探险中' WHERE client_id = 'u1'")
    spar_result = duel.accept_spar("u2", "青衫客")
    _must_contain(spar_result, "切磋结束")
    _must_not_contain(spar_result, "武器经验")
    assert not duel.db.fetch_one("SELECT 1 FROM duel_requests WHERE mode = 'spar' AND status = '等待'")

    _must_contain(duel.spar("u1", "白衣客"), "发起切磋")
    pending_records = duel.records("u2")
    _must_contain(pending_records, "待处理对战请求")
    _must_contain(pending_records, "青衫客 向你发起切磋")
    _must_contain(pending_records, "接受切磋 青衫客")
    _must_contain(pending_records, "拒绝切磋 青衫客")
    duel.db.execute("UPDATE players SET status = '空闲' WHERE client_id = 'u1'")
    _must_contain(duel.reject_spar("u2", "青衫客"), "已拒绝")

    duel.db.execute("UPDATE players SET status = '休息中' WHERE client_id = 'u1'")
    _must_contain(duel.duel("u1", "白衣客 100"), "双方都需要处于空闲状态")
    duel.db.execute("UPDATE players SET status = '空闲' WHERE client_id = 'u1'")

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
        "events": [{"win": True, "drop_item_id": "loot_yao_1", "hp_left": 30, "mp_left": 10, "actions": []}],
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
    _must_contain(robbery_text, "古妖丹")
    _must_contain(robbery_text, "复仇触发")
    _must_contain(robbery_text, "武器经验")
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
    assert duel.db.fetch_one("SELECT quantity FROM backpack_items WHERE client_id = 'u1' AND item_id = 'loot_yao_1'")
    with duel.db.transaction() as conn:
        conn.execute("DELETE FROM exploration_records WHERE client_id = 'u2' AND claimed = 0")
        conn.execute("DELETE FROM backpack_items WHERE client_id = 'u1' AND item_id = 'loot_yao_1'")
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
        conn.execute("INSERT INTO bank_accounts (client_id, last_settle_at) VALUES ('deleted_user', '2000-01-01T00:00:00')")
        conn.execute("INSERT INTO ring_items (client_id, ring_item_id, quantity) VALUES ('deleted_user', 'xueqidan', 1)")
        conn.execute("INSERT INTO fixed_equipment (client_id, slot, level) VALUES ('deleted_user', '头部', 0)")
        conn.execute(
            "INSERT INTO fixed_equipment_inlays (client_id, slot, hole_no, gem_id, level) VALUES ('deleted_user', '头部', 1, 'huxinyu', 1)"
        )
        conn.execute(
            "INSERT INTO player_titles (client_id, title, reason, active, obtained_at, updated_at) VALUES ('deleted_user', '旧称号', '', 1, '2000-01-01T00:00:00', '2000-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO player_journals (client_id, milestone_key, text, created_at) VALUES ('deleted_user', 'old', '旧日记', '2000-01-01T00:00:00')"
        )
        conn.execute(
            "INSERT INTO player_lifetime_stats (client_id, stat_key, stat_value, updated_at) VALUES ('deleted_user', 'old', 1, '2000-01-01T00:00:00')"
        )
        conn.execute(
            """
            INSERT INTO player_weapons
            (weapon_id, holder_id, weapon_def_id, level, max_level, quality, created_at)
            VALUES (999991, 'deleted_user', 'qinglan_duanjian', 1, 40, '凡品', '2000-01-01T00:00:00')
            """
        )
        conn.execute(
            "INSERT INTO weapon_enchant_names (weapon_id, slot_no, custom_name) VALUES (999991, 1, '旧附魔名')"
        )
        conn.execute(
            """
            INSERT INTO player_weapons
            (weapon_id, holder_id, weapon_def_id, level, max_level, quality, created_at)
            VALUES (999992, '__vault__:u1', 'qinglan_duanjian', 1, 40, '凡品', '2000-01-01T00:00:00')
            """
        )
        conn.execute("INSERT INTO vault_weapons (client_id, weapon_id, stored_at) VALUES ('u1', 999992, '2000-01-01T00:00:00')")
        conn.execute(
            """
            INSERT INTO player_weapons
            (weapon_id, holder_id, weapon_def_id, level, max_level, quality, created_at)
            VALUES (999993, '__second_hand__:1', 'qinglan_duanjian', 1, 40, '凡品', '2000-01-01T00:00:00')
            """
        )
    duel.cleanup_battle_records(force=True)
    assert not duel.db.fetch_one("SELECT 1 FROM combat_logs WHERE summary = '旧战斗'")
    assert not duel.db.fetch_one("SELECT 1 FROM duel_records WHERE summary = '旧决斗'")
    assert not duel.db.fetch_one("SELECT 1 FROM robbery_records WHERE loot_text = '旧抢劫'")
    assert not duel.db.fetch_one("SELECT 1 FROM exploration_records WHERE result = '{}'")
    assert not duel.db.fetch_one("SELECT 1 FROM bank_accounts WHERE client_id = 'deleted_user'")
    assert not duel.db.fetch_one("SELECT 1 FROM ring_items WHERE client_id = 'deleted_user'")
    assert not duel.db.fetch_one("SELECT 1 FROM fixed_equipment WHERE client_id = 'deleted_user'")
    assert not duel.db.fetch_one("SELECT 1 FROM fixed_equipment_inlays WHERE client_id = 'deleted_user'")
    assert not duel.db.fetch_one("SELECT 1 FROM player_titles WHERE client_id = 'deleted_user'")
    assert not duel.db.fetch_one("SELECT 1 FROM player_journals WHERE client_id = 'deleted_user'")
    assert not duel.db.fetch_one("SELECT 1 FROM player_lifetime_stats WHERE client_id = 'deleted_user'")
    assert not duel.db.fetch_one("SELECT 1 FROM player_weapons WHERE weapon_id = 999991")
    assert not duel.db.fetch_one("SELECT 1 FROM weapon_enchant_names WHERE weapon_id = 999991")
    assert duel.db.fetch_one("SELECT 1 FROM player_weapons WHERE weapon_id = 999992")
    assert duel.db.fetch_one("SELECT 1 FROM vault_weapons WHERE weapon_id = 999992")
    assert duel.db.fetch_one("SELECT 1 FROM player_weapons WHERE weapon_id = 999993")


def _check_second_hand_ring(services: dict[str, object]) -> None:
    """检查纳戒物品可以按名称、数量和总价交易。"""

    player: PlayerService = services["player"]  # type: ignore[assignment]
    ring: RingService = services["ring"]  # type: ignore[assignment]
    second_hand: SecondHandService = services["second_hand"]  # type: ignore[assignment]

    player.add_stones("u2", 100_000)
    with ring.db.transaction() as conn:
        ring.add_ring_conn(conn, "u1", "xueqidan", 1)

    before = ring.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
        ("u2", "xueqidan"),
    )
    before_quantity = int(before["quantity"]) if before else 0

    _must_contain(second_hand.sell("u1", "血契丹 1 500"), "上架成功")
    market_text = second_hand.list_items("u2")
    _must_contain(market_text, "血契丹 x1")
    assert "u1" not in market_text
    _must_contain(second_hand.buy("u2", "青衫客"), "购买成功")
    notification_keys = {item.key for item in collect_notifications("u1", second_hand.db)}
    assert "second_hand_sale" in notification_keys
    receipt_text = second_hand.list_items("u1")
    _must_contain(receipt_text, "二手成交回执")
    _must_contain(receipt_text, "血契丹 x1")
    _must_contain(receipt_text, "到账")
    _must_contain(receipt_text, "手续费")
    notification_keys = {item.key for item in collect_notifications("u1", second_hand.db)}
    assert "second_hand_sale" not in notification_keys

    after = ring.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
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

    player.create_player("u3", "灰衣客")
    only_id = weapon.create_weapon("u3", "qinglan_duanjian", "凡品", 40, equipped=False)
    weapon.db.execute(
        "DELETE FROM player_weapons WHERE holder_id = ? AND weapon_id != ?",
        ("u3", only_id),
    )
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
    trade: TradeService = services["trade"]  # type: ignore[assignment]

    map_text = explore.current_location("u1")
    _must_contain(map_text, "地图·当前位置")
    _must_contain(map_text, "商路城池")
    _must_contain(map_text, "本地特产")
    _must_contain(map_text, "城池 Lv.")
    with explore.db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO treasure_maps
            (city_name, status, x, y, current_price, weapon_def_id, weapon_name, weapon_max_level, generated_at, expires_at, result)
            VALUES ('天枢城', '可拾取', 0, 0, 12000, 'qinglan_duanjian', '青岚短剑', 70, ?, ?, '{}')
            """,
            (ts(), ts(now() + timedelta(days=1))),
        )
    treasure_map_text = explore.current_location("u1")
    _must_contain(treasure_map_text, "藏宝图")
    _must_contain(treasure_map_text, "领取藏宝图")
    explore.db.execute("DELETE FROM treasure_maps WHERE status = '可拾取' AND x = 0 AND y = 0")

    location_text = explore.locations("u1")
    _must_contain(location_text, "探险地图")
    _must_contain(location_text, "普通城池")
    _must_contain(location_text, "特殊秘境")
    _must_contain(location_text, "星陨墟")
    _must_contain(location_text, "太虚秘境")
    _must_contain(location_text, "动态映身｜怪物随进入者变化")
    _must_not_contain(location_text, "太虚秘境 (-6,-49)｜动态映身｜推荐")
    _must_contain(location_text, "<导航 天枢城>")
    for row in explore.db.fetch_all("SELECT name FROM exploration_locations"):
        _must_contain(location_text, str(row["name"]))

    _must_contain(weapon.list_weapons("u1"), "青岚短剑")
    first_weapon = weapon.db.fetch_one(
        "SELECT weapon_id FROM player_weapons WHERE holder_id = ? ORDER BY weapon_id LIMIT 1",
        ("u1",),
    )
    assert first_weapon is not None
    detail_text = weapon.detail("u1", str(first_weapon["weapon_id"]))
    _must_contain(detail_text, "武器详情")
    _must_contain(detail_text, "模板：")
    _must_contain(detail_text, "定位：")
    _must_contain(detail_text, "速度：")
    _must_contain(detail_text, "蓄势基准：")
    default_detail_text = weapon.detail("u1", "")
    _must_contain(default_detail_text, "武器详情")
    assert "格式不正确" not in default_detail_text
    before_default_upgrade = weapon.weapon("u1", int(first_weapon["weapon_id"]))
    assert before_default_upgrade is not None
    before_level = int(before_default_upgrade["level"])
    weapon.db.execute(
        "UPDATE players SET raw_stones = raw_stones + 100000 WHERE client_id = ?",
        ("u1",),
    )
    default_upgrade_text = weapon.upgrade("u1", "")
    _must_contain(default_upgrade_text, "升级成功")
    after_default_upgrade = weapon.weapon("u1", int(first_weapon["weapon_id"]))
    assert after_default_upgrade is not None
    assert int(after_default_upgrade["level"]) == before_level + 1
    recycle_weapon_id = weapon.create_weapon("u1", "qinglan_duanjian", "良品", 45, equipped=False)
    _must_contain(weapon.switch("u1", f"武器#{recycle_weapon_id}"), "已切换武器")
    switched_weapon = weapon.db.fetch_one(
        "SELECT equipped FROM player_weapons WHERE holder_id = ? AND weapon_id = ?",
        ("u1", recycle_weapon_id),
    )
    assert switched_weapon and int(switched_weapon["equipped"]) == 1
    _must_contain(weapon.switch("u1", f"武器#{first_weapon['weapon_id']}"), "已切换武器")
    before_recycle = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    _must_contain(trade.sell_any("u1", f"{recycle_weapon_id} 1"), "回收成功")
    after_recycle = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_recycle and after_recycle
    assert int(after_recycle["raw_stones"]) > int(before_recycle["raw_stones"])
    assert weapon.weapon("u1", recycle_weapon_id) is None
    record = weapon.db.fetch_one(
        "SELECT total_price FROM weapon_recycle_records WHERE client_id = ? AND business_day = ?",
        ("u1", business_day()),
    )
    assert record and int(record["total_price"]) == int(after_recycle["raw_stones"]) - int(before_recycle["raw_stones"])

    batch_weapon_id_1 = weapon.create_weapon("u1", "qinglan_duanjian", "良品", 45, equipped=False)
    batch_weapon_id_2 = weapon.create_weapon("u1", "pojun_qiang", "凡品", 40, equipped=False)
    before_batch = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    batch_text = trade.sell_all("u1", "武器")
    _must_contain(batch_text, "武器批量回收")
    _must_contain(batch_text, weapon_id_label(batch_weapon_id_1))
    _must_contain(batch_text, weapon_id_label(batch_weapon_id_2))
    after_batch = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_batch and after_batch
    assert int(after_batch["raw_stones"]) > int(before_batch["raw_stones"])
    assert weapon.weapon("u1", batch_weapon_id_1) is None
    assert weapon.weapon("u1", batch_weapon_id_2) is None

    with weapon.db.transaction() as conn:
        weapon.add_ring_conn(conn, "u1", "fengren_shu", 3)
        conn.execute(
            "UPDATE players SET location_name = '藏经阁', x = 120, y = 820 WHERE client_id = ?",
            ("u1",),
        )
    enchant_weapon_id = weapon.create_weapon("u1", "qinglan_duanjian", "凡品", 40, equipped=False)
    weapon.db.execute(
        "UPDATE player_weapons SET level = 10, exp = ? WHERE holder_id = ? AND weapon_id = ?",
        (weapon_exp_for_level(10), "u1", enchant_weapon_id),
    )
    _must_contain(weapon.enchant("u1", f"武器#{enchant_weapon_id} 风刃书"), "附魔成功")
    split_ref_weapon_id = weapon.create_weapon("u1", "pojun_qiang", "凡品", 40, equipped=False)
    weapon.db.execute(
        "UPDATE player_weapons SET level = 10, exp = ? WHERE holder_id = ? AND weapon_id = ?",
        (weapon_exp_for_level(10), "u1", split_ref_weapon_id),
    )
    _must_contain(weapon.enchant("u1", f"武器 {split_ref_weapon_id} 风刃书"), "附魔成功")
    before_book_recycle = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    before_book = weapon.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
        ("u1", "fengren_shu"),
    )
    before_book_quantity = int(before_book["quantity"]) if before_book else 0
    _must_contain(trade.sell_any("u1", "风刃书 1"), "回收成功")
    after_book_recycle = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_book_recycle and after_book_recycle
    book_gained = int(after_book_recycle["raw_stones"]) - int(before_book_recycle["raw_stones"])
    assert book_gained > 0
    book_left = weapon.db.fetch_one(
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
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
    before_book_batch = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    book_batch_text = trade.sell_all("u1", "技能书")
    _must_contain(book_batch_text, "技能书批量回收")
    _must_contain(book_batch_text, "破甲书")
    after_book_batch = weapon.db.fetch_one("SELECT raw_stones FROM players WHERE client_id = ?", ("u1",))
    assert before_book_batch and after_book_batch
    assert int(after_book_batch["raw_stones"]) > int(before_book_batch["raw_stones"])
    assert not weapon.db.fetch_one(
        """
        SELECT 1
        FROM ring_items r
        JOIN ring_item_defs e ON e.ring_item_id = r.ring_item_id
        WHERE r.client_id = ? AND e.category_key = 'book'
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
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
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
        "SELECT quantity FROM ring_items WHERE client_id = ? AND ring_item_id = ?",
        ("u1", "xueqidan"),
    )
    after_hp_medicine_quantity = int(after_hp_medicine["quantity"]) if after_hp_medicine else 0
    assert after_hp_medicine_quantity < before_hp_medicine_quantity
    status_text = explore.status("u1")
    _must_contain(status_text, "探险状态")
    _must_contain(status_text, "预计武器经验")
    _must_contain(explore.claim("u1"), "30 分钟冷却")
    explore.db.execute(
        "UPDATE exploration_records SET ready_at = ? WHERE client_id = ?",
        ("2000-01-01T00:00:00", "u1"),
    )
    explore.db.execute(
        """
        UPDATE players
        SET rest_window_started_at = ?,
            rest_window_hp = 3,
            rest_window_mp = 4,
            rest_window_elapsed_seconds = 120
        WHERE client_id = ?
        """,
        ("2000-01-01T00:00:00", "u1"),
    )
    explore.db.execute("UPDATE players SET battle_log_detail = 1 WHERE client_id = ?", ("u1",))
    claim_text = explore.claim("u1")
    _must_contain(claim_text, "探险结束")
    assert "领取动作" not in claim_text
    _must_contain(claim_text, "战斗日志")
    _must_contain(claim_text, "zhandou-rizhi/explore")
    _must_contain(claim_text, "detail=1")
    _must_contain(claim_text, "武器经验")
    _must_not_contain(claim_text, "战斗摘要")
    _must_not_contain(claim_text, "我方技能")
    _must_not_contain(claim_text, "行动 **")
    player_snapshot = explore.player("u1")
    assert player_snapshot is not None
    assert int(player_snapshot["rest_window_elapsed_seconds"]) == 0
    assert int(player_snapshot["rest_window_hp"]) == int(player_snapshot["hp"])
    assert int(player_snapshot["rest_window_mp"]) == int(player_snapshot["mp"])
    current = now()
    secret_result = dump_json(
        {
            "dead": False,
            "bag_full": False,
            "medicine_used": {},
            "events": [],
            "secret_realm": {"name": "测试秘境", "desc": "测试", "duration_seconds": ENCOUNTER_SECONDS},
            "player_snapshot": explore._player_snapshot(player_snapshot),
            "duration_seconds": ENCOUNTER_SECONDS,
        }
    )
    with explore.db.transaction() as conn:
        conn.execute(
            """
            UPDATE players
            SET status = '空闲',
                rest_window_started_at = ?,
                rest_window_hp = 3,
                rest_window_mp = 4,
                rest_window_elapsed_seconds = 120
            WHERE client_id = ?
            """,
            ("2000-01-01T00:00:00", "u1"),
        )
        conn.execute(
            """
            INSERT INTO exploration_records
            (client_id, location_name, status, started_at, ready_at, result)
            VALUES (?, ?, '探险中', ?, ?, ?)
            """,
            ("u1", "太虚秘境", "2000-01-01T00:00:00", "2000-01-01T00:01:30", secret_result),
        )
    secret_claim_text = explore.claim("u1")
    _must_contain(secret_claim_text, "太虚秘境结束")
    _must_contain(secret_claim_text, "战斗日志")
    _must_not_contain(secret_claim_text, "秘境战斗摘要")
    _must_not_contain(secret_claim_text, "行动 **")
    secret_player_snapshot = explore.player("u1")
    assert secret_player_snapshot is not None
    assert int(secret_player_snapshot["rest_window_elapsed_seconds"]) == 120
    assert int(secret_player_snapshot["rest_window_hp"]) == 3
    assert int(secret_player_snapshot["rest_window_mp"]) == 4
    secret_rows = [explore.item_def(explore._roll_secret_realm_location_drop()) for _ in range(20)]
    secret_categories = {row["category"] for row in secret_rows if row}
    assert secret_categories
    assert secret_categories <= {"古物", "战利品", "建设"}
    stale_started_at = current - timedelta(minutes=EXPLORE_MINUTES + 1)
    stale_ready_at = current + timedelta(minutes=111)
    stale_result = dump_json(
        {
            "dead": False,
            "bag_full": False,
            "medicine_used": {},
            "events": [],
            "player_snapshot": explore._player_snapshot(player_snapshot),
            "duration_seconds": EXPLORE_MINUTES * 60,
        }
    )
    with explore.db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO exploration_records
            (client_id, location_name, status, started_at, ready_at, result)
            VALUES (?, ?, '探险中', ?, ?, ?)
            """,
            ("u1", "青岚坊", ts(stale_started_at), ts(stale_ready_at), stale_result),
        )
    stale_status_text = explore.status("u1")
    _must_contain(stale_status_text, "可领取")
    assert "111 分钟" not in stale_status_text
    stale_claim_text = explore.claim("u1")
    _must_contain(stale_claim_text, "探险结束")
    assert "111 分钟" not in str(stale_claim_text)
    explore.db.execute("UPDATE players SET battle_log_detail = 0 WHERE client_id = ?", ("u1",))
    explore.db.execute(
        "UPDATE players SET location_name = '天枢城', x = 0, y = 0 WHERE client_id = ?",
        ("u1",),
    )


def _check_trade_and_treasure(services: dict[str, object]) -> None:
    """检查商场和修仙物品详情查询。"""

    trade: TradeService = services["trade"]  # type: ignore[assignment]
    explore: ExplorationService = services["explore"]  # type: ignore[assignment]
    treasure: ItemInfoService = services["treasure"]  # type: ignore[assignment]

    _must_contain(explore.locations("u1"), "天枢城")
    _must_contain(explore.locations("u1"), "特产：")
    _must_contain(trade.navigate("u1", "铸剑阁"), "已到达")
    _must_contain(explore.current_location("u1"), "回收建筑")
    _must_contain(trade.navigate("u1", "琢玉楼"), "已到达")
    _must_contain(explore.current_location("u1"), "宝石")
    _must_contain(trade.navigate("u1", "藏经阁"), "已到达")
    _must_contain(explore.current_location("u1"), "技能书")
    _must_contain(trade.navigate("u1", "天枢城"), "已到达")
    with trade.db.transaction() as conn:
        trade.add_backpack_conn(conn, "u1", "world_med_xueqidan_1", 2)
    _must_contain(trade.sell_any("u1", "血藤籽 2"), "城池吸收")
    recommend_text = trade.recommend("u1")
    _must_contain(recommend_text, "商场购买")
    _must_contain(recommend_text, "导航")
    _must_contain(recommend_text, "商场出售")
    missing_market_text = trade.market_price("u1", "不存在的货")
    _must_contain(missing_market_text, "探险列表")
    _must_not_contain(missing_market_text, "商场详情")
    _must_contain(trade.buy("u1", "风骨玉 1"), "不出售")
    player = trade.player("u1")
    assert player is not None
    options = trade._trade_options("u1", player)
    assert options, "商场推荐应该至少给出一条可盈利路线"
    recommended_options = trade._recommended_trade_options("u1", player)
    assert recommended_options, "商场推荐应该至少给出一条展示路线"
    unique_targets = {str(row["target"]) for row in recommended_options[:3]}
    assert len(unique_targets) >= min(3, len({str(row["target"]) for row in options})), recommended_options[:3]
    option = recommended_options[0]
    trade_item = str(option["item_name"])
    trade_quantity = int(option["quantity"])
    trade_target = str(option["target"])
    _must_contain(trade.buy("u1", f"{trade_item} {trade_quantity}"), "购买成功")
    _must_contain(trade.navigate("u1", trade_target), "已到达")
    _must_contain(trade.sell("u1", f"{trade_item} {trade_quantity}"), "出售成功")
    with trade.db.transaction() as conn:
        market_state = trade._trade_market_state_conn(conn, "u1")
        min_quantity, min_net = trade_daily_reward_thresholds(market_state["player_soft_line"])
        stat = conn.execute(
            """
            SELECT
                COALESCE(SUM(effective_quantity), 0) AS quantity,
                COALESCE(SUM(effective_profit), 0) AS net_profit
            FROM trade_records
            WHERE client_id = ? AND business_day = ? AND action = 'sell'
            """,
            ("u1", business_day()),
        ).fetchone()
        quantity = int(stat["quantity"] if stat else 0)
        net_profit = int(stat["net_profit"] if stat else 0)
        if quantity < min_quantity and net_profit < min_net:
            add_quantity = max(0, min_quantity - quantity)
            add_net = max(0, min_net - net_profit)
            conn.execute(
                """
                INSERT INTO trade_records
                (client_id, action, item_id, quantity, effective_quantity, fatigue_quantity,
                 total_price, fee, effective_profit, fatigue_profit, location_name, business_day, created_at)
                VALUES (?, 'sell', ?, ?, ?, 0, ?, 0, ?, 0, ?, ?, ?)
                """,
                (
                    "u1",
                    option["item_id"],
                    max(1, add_quantity),
                    max(1, add_quantity),
                    max(1, add_net),
                    max(1, add_net),
                    trade_target,
                    business_day(),
                    ts(),
                ),
            )
    notification_keys = {item.key for item in collect_notifications("u1", trade.db)}
    assert "trade_reward" in notification_keys
    reward_text = trade.daily_reward("u1")
    _must_contain(reward_text, "跑商奖励领取成功")
    _must_contain(reward_text, "净利润")
    notification_keys = {item.key for item in collect_notifications("u1", trade.db)}
    assert "trade_reward" not in notification_keys
    _must_contain(trade.daily_reward("u1"), "已经领取")
    trade_curve_text = trade.trade_curve("u1")
    _must_contain(trade_curve_text, "跑商收益曲线")
    _must_contain(trade_curve_text, "利润倍率")
    _must_contain(trade_curve_text, "不限制买卖")
    _must_contain(trade_curve_text, "纯经济货物")
    _must_contain(trade_curve_text, "散商倍率")
    old_livelihood_item = trade.item_def_by_name("城隍香")
    normal_item = trade.item_def_by_name("星官旧简")
    assert normal_item is not None
    assert old_livelihood_item is None or not int(old_livelihood_item["tradeable"])
    normal_buy, _normal_sell = trade.price("天枢城", normal_item["item_id"])
    normal_raw_home_buy = int(normal_item["base_price"] * 0.82 * 1.0 * 1.18 * 1.04)
    assert normal_buy >= normal_raw_home_buy
    with trade.db.transaction() as conn:
        market_state = trade._trade_market_state_conn(conn, "u1")
        conn.execute(
            """
            INSERT INTO trade_records
            (client_id, action, item_id, quantity, effective_quantity, fatigue_quantity,
             total_price, fee, effective_profit, fatigue_profit, location_name, business_day, created_at)
            VALUES (?, 'sell', ?, ?, ?, 0, ?, 0, ?, 0, ?, ?, ?)
            """,
            (
                "u1",
                normal_item["item_id"],
                market_state["player_soft_line"] * 8,
                market_state["player_soft_line"] * 8,
                1,
                1,
                "星陨墟",
                business_day(),
                ts(),
            ),
        )
        trade.add_backpack_conn(conn, "u1", normal_item["item_id"], 1)
        conn.execute(
            """
            INSERT OR REPLACE INTO trade_buy_locks
            (client_id, item_id, location_name, location_id, last_buy_at, last_buy_price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("u1", normal_item["item_id"], "天枢城", "city_tianshu", "2000-01-01T00:00:00", normal_buy),
        )
        hot_state = trade._trade_market_state_conn(conn, "u1")
        expected_normal_used = market_state["player_used"] + market_state["player_soft_line"] * 8
    assert trade._trade_profit_rate_for_quantity(hot_state, 1) < 1.0
    assert hot_state["player_used"] == expected_normal_used
    hot_sell_text = trade.sell("u1", "星官旧简 1")
    _must_contain(hot_sell_text, "出售成功")
    _must_contain(hot_sell_text, "散商低收益")
    pure_economy_text = treasure.info("u1", "星官旧简")
    _must_contain(pure_economy_text, "星官旧简")
    _must_contain(pure_economy_text, "归属：纯经济")
    _must_contain(pure_economy_text, "流向：商场买卖")
    medicine_material_text = treasure.info("u1", "血藤籽")
    _must_contain(medicine_material_text, "归属：药路 / 血契丹")
    _must_contain(medicine_material_text, "流向：出售/自动出售，转入当前城池状态")
    loot_text = treasure.info("u1", "古妖丹")
    _must_contain(loot_text, "归属：战利品 / 妖类")
    _must_contain(loot_text, "流向：出售/自动出售，流入特殊收购与战备蓄能")
    _must_contain(treasure.info("u1", "福袋"), "存放：纳戒")
    _must_contain(treasure.info("u1", "淬锋丹"), "纳戒专属命令：武器升限")
    _must_contain(treasure.info("u1", "青岚短剑"), "武器模板")
    _must_contain(treasure.info("u1", "风刃斩"), "武器自带技能")
    _must_contain(treasure.info("u1", "风刃书"), "附魔效果")
    _must_contain(treasure.info("u1", "凡体"), "体质资料")
    for table in (
        "item_defs",
        "ring_item_defs",
        "weapon_defs",
        "weapon_skill_defs",
        "weapon_enchants",
        "physique_defs",
    ):
        for row in treasure.db.fetch_all(f"SELECT name FROM {table}"):
            text = treasure.info("u1", row["name"])
            _must_contain(text, row["name"])
            assert "没有找到修仙物品" not in text
    _must_contain(trade.navigate("u1", f"{WORLD_COORD_MIN} {WORLD_COORD_MIN}"), "已到达")
    _must_contain(trade.navigate("u1", f"{WORLD_COORD_MAX} {WORLD_COORD_MAX}"), "已到达")
    _must_contain(trade.navigate("u1", "101 0"), "坐标超出修仙界范围")
    _must_contain(trade.navigate("u1", "镇妖司"), "已到达")
    _must_contain(trade.buy("u1", "星官旧简 1"), "当前位置不是商场城池")
    with trade.db.transaction() as conn:
        trade.add_backpack_conn(conn, "u1", "loot_yao_1", 101)
    _must_contain(trade.sell_any("u1", "古妖丹 1"), "战利品出售成功")
    _must_contain(trade.special_sell("u1", "古妖丹 100"), "战利品出售成功")
    with trade.db.transaction() as conn:
        trade.add_backpack_conn(conn, "u1", "loot_yao_2", 2)
        trade.add_backpack_conn(conn, "u1", "loot_mo_1", 1)
    before_special_auto = trade.player("u1")
    assert before_special_auto is not None
    origin_name = str(before_special_auto["location_name"])
    origin_x = int(before_special_auto["x"])
    origin_y = int(before_special_auto["y"])
    special_auto_text = trade.auto_sell("u1")
    _must_contain(special_auto_text, "战利品自动出售")
    _must_contain(special_auto_text, "特殊收购点")
    _must_contain(special_auto_text, f"回到原位置：{origin_name} ({origin_x},{origin_y})")
    _must_contain(special_auto_text, f"<导航 {origin_x} {origin_y}:回原处>")
    _must_contain(trade.records("u1"), "战利品自动出售")
    explore: ExplorationService = services["explore"]  # type: ignore[assignment]
    _must_contain(explore.start("u1"), "当前位置不是探险地点")


def _check_level_cap_discards(services: dict[str, object]) -> None:
    """所有经验型等级到达上限后丢弃溢出，不为未来上限缓存。"""

    core: CoreService = services["player"]  # type: ignore[assignment]
    weapon: WeaponService = services["weapon"]  # type: ignore[assignment]
    trade: TradeService = services["trade"]  # type: ignore[assignment]

    player_cap_exp = player_exp_for_level(MAX_LEVEL)
    with core.db.transaction() as conn:
        conn.execute(
            "UPDATE players SET level = ?, exp = ? WHERE client_id = ?",
            (MAX_LEVEL, player_cap_exp, "u1"),
        )
        old_level, new_level = core.add_exp_conn(conn, "u1", 999999999)
        row = conn.execute("SELECT level, exp FROM players WHERE client_id = ?", ("u1",)).fetchone()
        assert old_level == MAX_LEVEL and new_level == MAX_LEVEL
        assert int(row["level"]) == MAX_LEVEL
        assert int(row["exp"]) == player_cap_exp

        weapon.ensure_starter_weapon("u1")
        weapon_row = conn.execute(
            "SELECT weapon_id, max_level FROM player_weapons WHERE holder_id = ? ORDER BY equipped DESC, weapon_id LIMIT 1",
            ("u1",),
        ).fetchone()
        assert weapon_row is not None
        weapon_id = int(weapon_row["weapon_id"])
        weapon_cap_exp = weapon_exp_for_level(int(weapon_row["max_level"]))
        conn.execute(
            "UPDATE player_weapons SET level = max_level, exp = ? WHERE holder_id = ? AND weapon_id = ?",
            (weapon_cap_exp, "u1", weapon_id),
        )
        gained = weapon.add_weapon_exp_conn(conn, "u1", weapon_id, 999999)
        capped_weapon = conn.execute("SELECT level, max_level, exp FROM player_weapons WHERE weapon_id = ?", (weapon_id,)).fetchone()
        assert gained == 0
        assert int(capped_weapon["level"]) == int(capped_weapon["max_level"])
        assert int(capped_weapon["exp"]) == weapon_cap_exp

        sect_row = conn.execute("SELECT sect_id FROM sect_members WHERE client_id = ?", ("u1",)).fetchone()
        assert sect_row is not None
        sect_id = int(sect_row["sect_id"])
        conn.execute(
            """
            UPDATE sect_stats
            SET level = 100, exp = 123456
            WHERE sect_id = ?
            """,
            (sect_id,),
        )
        merit_result = record_sect_merit_conn(conn, "u1", "影响力", 999999, source="cap_test")
        sect_stats = conn.execute("SELECT level, exp, influence_merit FROM sect_stats WHERE sect_id = ?", (sect_id,)).fetchone()
        assert merit_result["level"] == 100
        assert int(sect_stats["level"]) == 100
        assert int(sect_stats["exp"]) == 0
        assert int(sect_stats["influence_merit"]) >= 999999

        conn.execute(
            "UPDATE city_world_states SET city_level = 107, build_exp = 123456 WHERE location_id = ?",
            ("city_tianshu",),
        )
        trade.add_backpack_conn(conn, "u1", "world_build_jichu_1", 1)

    _must_contain(trade.sell_any("u1", "古城砖 1"), "城池吸收")
    city = trade.db.fetch_one("SELECT city_level, build_exp FROM city_world_states WHERE location_id = ?", ("city_tianshu",))
    assert int(city["city_level"]) == 107
    assert int(city["build_exp"]) == 0


def _lingxi_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端开局凭证、且已超过最短局时的灵溪结算数据。"""

    config = lingxi_fishing_config(dongtian)
    assert config["game_key"] == "lingxi-fishing"
    assert config["game_token"]
    round_info = start_lingxi_fishing(dongtian, {"gameToken": config["game_token"]})
    old_issued_at = ts(now() - timedelta(seconds=LINGXI_GAME_DURATION_SECONDS + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _lingpai_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端牌序、且已超过最短局时的灵牌记忆结算数据。"""

    config = lingpai_memory_config(dongtian)
    assert config["game_key"] == "lingpai-memory"
    assert config["game_token"]
    round_info = start_lingpai_memory(dongtian, {"gameToken": config["game_token"]})
    assert len(round_info["cards"]) == 16
    old_issued_at = ts(now() - timedelta(seconds=DONGTIAN_ROUND_MIN_SECONDS + 91))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _lingquan_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端开局凭证、且已超过最短局时的灵泉结算数据。"""

    config = lingquan_ten_drop_config(dongtian)
    assert config["game_key"] == "lingquan-ten-drop"
    assert config["game_token"]
    round_info = start_lingquan_ten_drop(dongtian, {"gameToken": config["game_token"]})
    reported_elapsed = max(0, int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds") or 0))
    elapsed_seconds = max(DONGTIAN_ROUND_MIN_SECONDS + 1, min(reported_elapsed, 300))
    old_issued_at = ts(now() - timedelta(seconds=elapsed_seconds + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _bianling_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端色阶、且已超过最短局时的辨灵试色结算数据。"""

    config = bianling_color_config(dongtian)
    assert config["game_key"] == "bianling-color"
    assert config["game_token"]
    round_info = start_bianling_color(dongtian, {"gameToken": config["game_token"]})
    assert len(round_info["stages"]) == 45
    reported_elapsed = max(0, int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds") or 0))
    elapsed_seconds = max(DONGTIAN_ROUND_MIN_SECONDS + 1, min(reported_elapsed, 60))
    old_issued_at = ts(now() - timedelta(seconds=elapsed_seconds + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _lingguo_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端开局凭证、且已超过最短局时的灵果结算数据。"""

    config = lingguo_sum_ten_config(dongtian)
    assert config["game_key"] == "lingguo-sum-ten"
    assert config["game_token"]
    round_info = start_lingguo_sum_ten(dongtian, {"gameToken": config["game_token"]})
    assert round_info["difficulty"]["key"] in {"qingtian", "ningxin", "suowei"}
    reported_elapsed = max(0, int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds") or 0))
    elapsed_seconds = max(DONGTIAN_ROUND_MIN_SECONDS + 1, min(reported_elapsed, 150))
    old_issued_at = ts(now() - timedelta(seconds=elapsed_seconds + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _hedan_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端开局凭证、且已超过最短局时的合丹炉结算数据。"""

    config = hedan_furnace_config(dongtian)
    assert config["game_key"] == "hedan-furnace"
    assert config["game_token"]
    round_info = start_hedan_furnace(dongtian, {"gameToken": config["game_token"]})
    assert round_info["difficulty"]["key"] in {"wenhuo", "zhenhuo", "jiehuo"}
    reported_elapsed = max(0, int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds") or 0))
    elapsed_seconds = max(DONGTIAN_ROUND_MIN_SECONDS + 1, min(reported_elapsed, 150))
    old_issued_at = ts(now() - timedelta(seconds=elapsed_seconds + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _suixing_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端开局凭证、且已超过最短局时的碎星结算数据。"""

    config = suixing_qieyu_config(dongtian)
    assert config["game_key"] == "suixing-qieyu"
    assert config["game_token"]
    round_info = start_suixing_qieyu(dongtian, {"gameToken": config["game_token"]})
    reported_elapsed = max(0, int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds") or 0))
    elapsed_seconds = max(DONGTIAN_ROUND_MIN_SECONDS + 1, min(reported_elapsed, 90))
    old_issued_at = ts(now() - timedelta(seconds=elapsed_seconds + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _jianfeng_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端开局凭证、且已超过最短局时的剑锋结算数据。"""

    config = jianfeng_chazhen_config(dongtian)
    assert config["game_key"] == "jianfeng-chazhen"
    assert config["game_token"]
    round_info = start_jianfeng_chazhen(dongtian, {"gameToken": config["game_token"]})
    reported_elapsed = max(0, int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds") or 0))
    elapsed_seconds = max(DONGTIAN_ROUND_MIN_SECONDS + 1, min(reported_elapsed, 90))
    old_issued_at = ts(now() - timedelta(seconds=elapsed_seconds + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _zhuiyuan_finish_payload(dongtian: DongtianService, payload: dict[str, Any]) -> dict[str, Any]:
    """生成一份带服务端开局凭证、且已超过最短局时的坠渊结算数据。"""

    config = zhuiyuan_hundred_floor_config(dongtian)
    assert config["game_key"] == "zhuiyuan-hundred-floor"
    assert config["game_token"]
    round_info = start_zhuiyuan_hundred_floor(dongtian, {"gameToken": config["game_token"]})
    reported_elapsed = max(0, int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds") or 0))
    elapsed_seconds = max(DONGTIAN_ROUND_MIN_SECONDS + 1, min(reported_elapsed, 90))
    old_issued_at = ts(now() - timedelta(seconds=elapsed_seconds + 1))
    dongtian.db.execute(
        "UPDATE dongtian_rounds SET issued_at = ? WHERE session_id = ?",
        (old_issued_at, round_info["session_id"]),
    )
    result = dict(payload)
    result.update(
        {
            "gameToken": config["game_token"],
            "sessionId": round_info["session_id"],
            "roundToken": round_info["round_token"],
        }
    )
    return result


def _dongtian_request(cookies: dict[str, str] | None = None) -> Request:
    """构造最小 HTTP 请求，用来测试洞天启动 token cookie。"""

    headers: list[tuple[bytes, bytes]] = []
    if cookies:
        cookie_text = "; ".join(f"{key}={value}" for key, value in cookies.items())
        headers.append((b"cookie", cookie_text.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/xiuxian/dongtian/hedan-furnace/config",
            "query_string": b"",
            "headers": headers,
            "client": ("testclient", 0),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def _check_dongtian_refresh_token_lock(dongtian: DongtianService) -> None:
    """检查刷新页面不能换启动 token，也不能借新 token 结算旧局。"""

    for title, config_func in (
        ("灵溪垂钓", lingxi_fishing_config),
        ("灵牌记忆", lingpai_memory_config),
        ("灵泉十滴", lingquan_ten_drop_config),
        ("辨灵试色", bianling_color_config),
        ("灵果凑十", lingguo_sum_ten_config),
        ("合丹炉", hedan_furnace_config),
        ("坠渊百层", zhuiyuan_hundred_floor_config),
        ("碎星切玉", suixing_qieyu_config),
        ("剑锋插阵", jianfeng_chazhen_config),
    ):
        first_config = config_func(dongtian)
        reused_config = config_func(dongtian, first_config["game_token"])
        assert first_config["game_token"], title
        assert first_config["reused_game_token"] is False, title
        assert reused_config["game_token"] == first_config["game_token"], title
        assert reused_config["reused_game_token"] is True, title

    fruit_config = lingguo_sum_ten_config(dongtian)
    fruit_round_a = start_lingguo_sum_ten(dongtian, {"gameToken": fruit_config["game_token"]})
    fruit_round_b = start_lingguo_sum_ten(dongtian, {"gameToken": fruit_config["game_token"]})
    assert fruit_round_a["difficulty"]["key"] == fruit_round_b["difficulty"]["key"]
    try:
        finish_lingguo_sum_ten(
            dongtian,
            {
                "gameToken": fruit_config["game_token"],
                "sessionId": fruit_round_a["session_id"],
                "roundToken": fruit_round_a["round_token"],
                "score": 20,
                "clearedCells": 20,
                "validClears": 2,
                "elapsedSeconds": 20,
            },
        )
        raise AssertionError("同一启动凭证不应并发保留多局未结算单局")
    except ValueError as exc:
        _must_contain(str(exc), "无效")

    furnace_config = hedan_furnace_config(dongtian)
    furnace_round_a = start_hedan_furnace(dongtian, {"gameToken": furnace_config["game_token"]})
    furnace_round_b = start_hedan_furnace(dongtian, {"gameToken": furnace_config["game_token"]})
    assert furnace_round_a["session_id"] != furnace_round_b["session_id"]
    assert furnace_round_a["difficulty"]["key"] in {"wenhuo", "zhenhuo", "jiehuo"}
    assert furnace_round_b["difficulty"]["key"] in {"wenhuo", "zhenhuo", "jiehuo"}

    memory_config = lingpai_memory_config(dongtian)
    memory_round_a = start_lingpai_memory(dongtian, {"gameToken": memory_config["game_token"]})
    memory_round_b = start_lingpai_memory(dongtian, {"gameToken": memory_config["game_token"]})
    assert memory_round_a["session_id"] != memory_round_b["session_id"]
    assert memory_round_a["cards"] != memory_round_b["cards"]

    color_config = bianling_color_config(dongtian)
    color_round_a = start_bianling_color(dongtian, {"gameToken": color_config["game_token"]})
    color_round_b = start_bianling_color(dongtian, {"gameToken": color_config["game_token"]})
    assert color_round_a["session_id"] != color_round_b["session_id"]
    assert color_round_a["stages"] != color_round_b["stages"]

    cookie_name = dongtian_routes_module._game_token_cookie_name("hedan-furnace")
    cookie_response = Response()
    dongtian_routes_module._config_with_cookie(
        _dongtian_request(),
        cookie_response,
        "hedan-furnace",
        furnace_config,
    )
    set_cookie = cookie_response.headers.get("set-cookie", "")
    assert cookie_name in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Path=/xiuxian/dongtian/hedan-furnace" in set_cookie

    cookie_request = _dongtian_request({cookie_name: furnace_config["game_token"]})
    cookie_token = dongtian_routes_module._game_token_cookie(cookie_request, "hedan-furnace")
    reused_furnace_config = hedan_furnace_config(dongtian, cookie_token)
    no_refresh_cookie = Response()
    dongtian_routes_module._config_with_cookie(
        cookie_request,
        no_refresh_cookie,
        "hedan-furnace",
        reused_furnace_config,
    )
    assert reused_furnace_config["game_token"] == furnace_config["game_token"]
    assert reused_furnace_config["reused_game_token"] is True
    assert no_refresh_cookie.headers.get("set-cookie") is None

    old_config = hedan_furnace_config(dongtian)
    old_round = start_hedan_furnace(dongtian, {"gameToken": old_config["game_token"]})
    new_config = hedan_furnace_config(dongtian)
    assert old_config["game_token"] != new_config["game_token"]
    try:
        finish_hedan_furnace(
            dongtian,
            {
                "gameToken": new_config["game_token"],
                "sessionId": old_round["session_id"],
                "roundToken": old_round["round_token"],
                "score": 100,
                "maxTile": 64,
                "mergeCount": 5,
                "moveCount": 12,
                "elapsedSeconds": 30,
            },
        )
        raise AssertionError("新启动凭证不应能结算旧单局凭证")
    except ValueError as exc:
        _must_contain(str(exc), "校验失败")


def _check_dongtian(services: dict[str, object]) -> None:
    """检查洞天福地入口、兑换码、转赠和收益曲线。"""

    dongtian: DongtianService = services["dongtian"]  # type: ignore[assignment]
    player: PlayerService = services["player"]  # type: ignore[assignment]
    _check_dongtian_refresh_token_lock(dongtian)

    original_static_dir = dongtian_service_module.DONGTIAN_STATIC_DIR
    with TemporaryDirectory() as temp_dir:
        game_dir = Path(temp_dir) / "fishing-demo"
        game_dir.mkdir(parents=True)
        (game_dir / "index.html").write_text(
            "<!doctype html><html><head><title>灵溪垂钓</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        fruit_dir = Path(temp_dir) / "lingguo-demo"
        fruit_dir.mkdir(parents=True)
        (fruit_dir / "index.html").write_text(
            "<!doctype html><html><head><title>灵果凑十</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        memory_dir = Path(temp_dir) / "lingpai-demo"
        memory_dir.mkdir(parents=True)
        (memory_dir / "index.html").write_text(
            "<!doctype html><html><head><title>灵牌记忆</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        color_dir = Path(temp_dir) / "bianling-demo"
        color_dir.mkdir(parents=True)
        (color_dir / "index.html").write_text(
            "<!doctype html><html><head><title>辨灵试色</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        furnace_dir = Path(temp_dir) / "hedan-demo"
        furnace_dir.mkdir(parents=True)
        (furnace_dir / "index.html").write_text(
            "<!doctype html><html><head><title>合丹炉</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        zhuiyuan_dir = Path(temp_dir) / "zhuiyuan-demo"
        zhuiyuan_dir.mkdir(parents=True)
        (zhuiyuan_dir / "index.html").write_text(
            "<!doctype html><html><head><title>坠渊百层</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        suixing_dir = Path(temp_dir) / "suixing-demo"
        suixing_dir.mkdir(parents=True)
        (suixing_dir / "index.html").write_text(
            "<!doctype html><html><head><title>碎星切玉</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        jianfeng_dir = Path(temp_dir) / "jianfeng-demo"
        jianfeng_dir.mkdir(parents=True)
        (jianfeng_dir / "index.html").write_text(
            "<!doctype html><html><head><title>剑锋插阵</title></head><body>demo</body></html>",
            encoding="utf-8",
        )
        dongtian_service_module.DONGTIAN_STATIC_DIR = Path(temp_dir)
        try:
            entry_text = dongtian.games("u1")
            _must_contain(entry_text, "[灵溪垂钓](")
            _must_contain(entry_text, "/static/dongtian/fishing-demo/index.html")
            _must_contain(entry_text, "[灵果凑十](")
            _must_contain(entry_text, "/static/dongtian/lingguo-demo/index.html")
            _must_contain(entry_text, "[灵牌记忆](")
            _must_contain(entry_text, "/static/dongtian/lingpai-demo/index.html")
            _must_contain(entry_text, "[辨灵试色](")
            _must_contain(entry_text, "/static/dongtian/bianling-demo/index.html")
            _must_contain(entry_text, "[合丹炉](")
            _must_contain(entry_text, "/static/dongtian/hedan-demo/index.html")
            _must_contain(entry_text, "[坠渊百层](")
            _must_contain(entry_text, "/static/dongtian/zhuiyuan-demo/index.html")
            _must_contain(entry_text, "[碎星切玉](")
            _must_contain(entry_text, "/static/dongtian/suixing-demo/index.html")
            _must_contain(entry_text, "[剑锋插阵](")
            _must_contain(entry_text, "/static/dongtian/jianfeng-demo/index.html")

            try:
                finish_lingxi_fishing(dongtian, {"score": 1, "caughtFish": []})
                raise AssertionError("缺少洞天凭证的结算不应成功")
            except ValueError as exc:
                _must_contain(str(exc), "凭证")

            fishing_payload = _lingxi_finish_payload(
                dongtian,
                {
                    "score": 9999,
                    "caughtFish": [
                        {"typeNameEn": "goldenDragon", "score": 1800},
                        {"typeNameEn": "shark", "score": 1600},
                        {"typeNameEn": "swordfish", "score": 900},
                        {"typeNameEn": "blueCrucian", "score": 500},
                    ],
                },
            )
            fishing_finish = finish_lingxi_fishing(
                dongtian,
                fishing_payload,
            )
            assert fishing_finish["game_key"] == "lingxi-fishing"
            assert fishing_finish["game_title"] == "灵溪垂钓"
            assert fishing_finish["accepted_score"] == 255
            assert fishing_finish["caught_count"] == 4
            assert any(line.startswith("基础原石 +") for line in fishing_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in fishing_finish["rewards"])
            tampered_fishing_payload = dict(fishing_payload)
            tampered_fishing_payload.update({"score": 1, "caughtFish": []})
            fishing_retry = finish_lingxi_fishing(dongtian, tampered_fishing_payload)
            assert fishing_retry["code"] == fishing_finish["code"]
            assert fishing_retry["reissued"] is True
            assert fishing_retry["accepted_score"] == 255
            assert fishing_retry["caught_count"] == 4

            empty_fishing_payload = _lingxi_finish_payload(
                dongtian,
                {
                    "score": 9999,
                    "caughtFish": [],
                },
            )
            empty_fishing_finish = finish_lingxi_fishing(
                dongtian,
                empty_fishing_payload,
            )
            assert empty_fishing_finish["accepted_score"] == 0
            assert empty_fishing_finish["caught_count"] == 0

            memory_payload = _lingpai_finish_payload(
                dongtian,
                {
                    "matchedPairs": 99,
                    "flipCount": 999,
                    "elapsedSeconds": 90,
                    "completed": True,
                },
            )
            memory_finish = finish_lingpai_memory(dongtian, memory_payload)
            assert memory_finish["game_key"] == "lingpai-memory"
            assert memory_finish["game_title"] == "灵牌记忆"
            assert 0 < memory_finish["accepted_score"] <= 1000
            assert memory_finish["matched_pairs"] == 8
            assert memory_finish["flip_count"] == 120
            assert memory_finish["completed"] is True
            assert any(line.startswith("基础原石 +") for line in memory_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in memory_finish["rewards"])
            memory_retry = finish_lingpai_memory(dongtian, memory_payload)
            assert memory_retry["code"] == memory_finish["code"]
            assert memory_retry["reissued"] is True

            ten_drop_payload = _lingquan_finish_payload(
                dongtian,
                {
                    "score": 9999,
                    "levelsCleared": 99,
                    "totalBursts": 9999,
                    "maxChain": 999,
                    "dropsLeft": 88,
                    "elapsedSeconds": 300,
                    "endReason": "timeout",
                },
            )
            ten_drop_finish = finish_lingquan_ten_drop(dongtian, ten_drop_payload)
            assert ten_drop_finish["game_key"] == "lingquan-ten-drop"
            assert ten_drop_finish["game_title"] == "灵泉十滴"
            assert ten_drop_finish["accepted_score"] == 5000
            assert ten_drop_finish["levels_cleared"] == 30
            assert ten_drop_finish["total_bursts"] == 900
            assert ten_drop_finish["max_chain"] == 180
            assert any(line.startswith("基础原石 +") for line in ten_drop_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in ten_drop_finish["rewards"])
            ten_drop_retry = finish_lingquan_ten_drop(dongtian, ten_drop_payload)
            assert ten_drop_retry["code"] == ten_drop_finish["code"]
            assert ten_drop_retry["reissued"] is True

            color_payload = _bianling_finish_payload(
                dongtian,
                {
                    "levelsPassed": 999,
                    "mistakes": 99,
                    "elapsedSeconds": 60,
                    "highestLayer": 99,
                },
            )
            color_finish = finish_bianling_color(dongtian, color_payload)
            assert color_finish["game_key"] == "bianling-color"
            assert color_finish["game_title"] == "辨灵试色"
            assert 0 <= color_finish["accepted_score"] <= 1200
            assert color_finish["levels_passed"] <= 45
            assert color_finish["mistakes"] == 20
            assert color_finish["highest_layer"] <= 6
            assert any(line.startswith("基础原石 +") for line in color_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in color_finish["rewards"])
            color_retry = finish_bianling_color(dongtian, color_payload)
            assert color_retry["code"] == color_finish["code"]
            assert color_retry["reissued"] is True

            fruit_payload = _lingguo_finish_payload(
                dongtian,
                {
                    "score": 9999,
                    "clearedCells": 999,
                    "validClears": 999,
                    "elapsedSeconds": 150,
                },
            )
            fruit_finish = finish_lingguo_sum_ten(dongtian, fruit_payload)
            assert fruit_finish["game_key"] == "lingguo-sum-ten"
            assert fruit_finish["game_title"] == "灵果凑十"
            assert 0 < fruit_finish["accepted_score"] <= 260
            assert fruit_finish["cleared_cells"] <= 320
            assert fruit_finish["valid_clears"] <= 120
            assert fruit_finish["difficulty"] in {"清甜局", "凝神局", "锁味局"}
            assert any(line.startswith("基础原石 +") for line in fruit_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in fruit_finish["rewards"])
            fruit_retry = finish_lingguo_sum_ten(dongtian, fruit_payload)
            assert fruit_retry["code"] == fruit_finish["code"]
            assert fruit_retry["reissued"] is True

            furnace_payload = _hedan_finish_payload(
                dongtian,
                {
                    "score": 9999,
                    "maxTile": 9999,
                    "mergeCount": 999,
                    "moveCount": 999,
                    "elapsedSeconds": 150,
                },
            )
            furnace_finish = finish_hedan_furnace(dongtian, furnace_payload)
            assert furnace_finish["game_key"] == "hedan-furnace"
            assert furnace_finish["game_title"] == "合丹炉"
            assert furnace_finish["accepted_score"] == 4200
            assert furnace_finish["max_tile"] == 4096
            assert furnace_finish["merge_count"] <= 220
            assert furnace_finish["move_count"] <= 240
            assert furnace_finish["difficulty"] in {"文火炉", "真火炉", "劫火炉"}
            assert any(line.startswith("基础原石 +") for line in furnace_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in furnace_finish["rewards"])
            furnace_retry = finish_hedan_furnace(dongtian, furnace_payload)
            assert furnace_retry["code"] == furnace_finish["code"]
            assert furnace_retry["reissued"] is True

            zhuiyuan_payload = _zhuiyuan_finish_payload(
                dongtian,
                {
                    "layers": 999,
                    "score": 9999,
                    "elapsedSeconds": 90,
                    "deathReason": "timeout",
                    "frameCount": 99999,
                },
            )
            zhuiyuan_finish = finish_zhuiyuan_hundred_floor(dongtian, zhuiyuan_payload)
            assert zhuiyuan_finish["game_key"] == "zhuiyuan-hundred-floor"
            assert zhuiyuan_finish["game_title"] == "坠渊百层"
            assert 0 < zhuiyuan_finish["accepted_score"] <= 3600
            assert 0 < zhuiyuan_finish["accepted_layers"] <= 180
            assert zhuiyuan_finish["elapsed_seconds"] <= 90
            assert any(line.startswith("基础原石 +") for line in zhuiyuan_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in zhuiyuan_finish["rewards"])
            zhuiyuan_retry = finish_zhuiyuan_hundred_floor(dongtian, zhuiyuan_payload)
            assert zhuiyuan_retry["code"] == zhuiyuan_finish["code"]
            assert zhuiyuan_retry["reissued"] is True

            suixing_payload = _suixing_finish_payload(
                dongtian,
                {
                    "score": 9999,
                    "cubesSliced": 999,
                    "strongCubes": 99,
                    "slowmoCubes": 99,
                    "maxCombo": 999,
                    "misses": 99,
                    "elapsedSeconds": 90,
                    "endReason": "timeout",
                },
            )
            suixing_finish = finish_suixing_qieyu(dongtian, suixing_payload)
            assert suixing_finish["game_key"] == "suixing-qieyu"
            assert suixing_finish["game_title"] == "碎星切玉"
            assert 0 < suixing_finish["accepted_score"] <= 3600
            assert suixing_finish["cubes_sliced"] <= 240
            assert suixing_finish["max_combo"] <= 140
            assert any(line.startswith("基础原石 +") for line in suixing_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in suixing_finish["rewards"])
            suixing_retry = finish_suixing_qieyu(dongtian, suixing_payload)
            assert suixing_retry["code"] == suixing_finish["code"]
            assert suixing_retry["reissued"] is True

            jianfeng_payload = _jianfeng_finish_payload(
                dongtian,
                {
                    "score": 9999,
                    "swordsInserted": 999,
                    "formationsBroken": 99,
                    "gapHits": 99,
                    "maxCombo": 999,
                    "burstSwords": 999,
                    "misses": 99,
                    "elapsedSeconds": 90,
                    "endReason": "mistake_limit",
                },
            )
            jianfeng_finish = finish_jianfeng_chazhen(dongtian, jianfeng_payload)
            assert jianfeng_finish["game_key"] == "jianfeng-chazhen"
            assert jianfeng_finish["game_title"] == "剑锋插阵"
            assert 0 < jianfeng_finish["accepted_score"] <= 3000
            assert jianfeng_finish["swords_inserted"] <= 150
            assert jianfeng_finish["formations_broken"] <= 36
            assert jianfeng_finish["gap_hits"] <= 48
            assert jianfeng_finish["max_combo"] <= 90
            assert any(line.startswith("基础原石 +") for line in jianfeng_finish["reward_preview"])
            assert not any(reward.get("key") in {"kaikongqi", "cuifengdan"} for reward in jianfeng_finish["rewards"])
            jianfeng_retry = finish_jianfeng_chazhen(dongtian, jianfeng_payload)
            assert jianfeng_retry["code"] == jianfeng_finish["code"]
            assert jianfeng_retry["reissued"] is True

            normal_payload = _lingxi_finish_payload(
                dongtian,
                {
                    "score": 370,
                    "caughtFish": [
                        *[{"typeNameEn": "clownfish", "score": 5} for _ in range(9)],
                        *[{"typeNameEn": "blueCrucian", "score": 10} for _ in range(5)],
                        *[{"typeNameEn": "goldfish", "score": 15} for _ in range(4)],
                        *[{"typeNameEn": "pufferfish", "score": 20} for _ in range(3)],
                        *[{"typeNameEn": "swordfish", "score": 40} for _ in range(2)],
                        {"typeNameEn": "shark", "score": 75},
                    ],
                },
            )
            normal_finish = finish_lingxi_fishing(
                dongtian,
                normal_payload,
            )
            assert normal_finish["accepted_score"] == 370
            assert "基础原石 +136" in normal_finish["reward_preview"]
            assert "基础经验 +11" in normal_finish["reward_preview"]
            assert any("微光" in line and "药胚" in line for line in normal_finish["reward_preview"])
            assert len([reward for reward in normal_finish["rewards"] if reward.get("type") == "medicine_embryo"]) == 1

            issued = dongtian.issue_code(
                "fishing-demo",
                "灵溪垂钓",
                [
                    {"type": "currency", "quantity": 100},
                    {"type": "exp", "quantity": 30},
                    {"type": "ring_item", "key": "xueqidan", "quantity": 2},
                    {"type": "wish_token", "quantity": 1},
                    {"type": "ring_item", "key": "kaikongqi", "quantity": 1},
                ],
                score=123,
                meta={"fish": "青鳞鱼"},
            )
            assert issued["game_key"] == "fishing-demo"
            assert not any(reward.get("key") == "kaikongqi" for reward in issued["rewards"])
            assert not any(reward.get("key") == "xueqidan" for reward in issued["rewards"])

            before_player = player.player("u1")
            assert before_player is not None
            redeem_text = dongtian.redeem("u1", str(issued["code"]))
            _must_contain(redeem_text, "灵溪垂钓 的异世回响")
            _must_contain(redeem_text, "洞天收益系数：资源 100%｜药胚稳定 100%")
            _must_contain(redeem_text, "原石 +100")
            _must_contain(redeem_text, "经验 +30")
            _must_contain(redeem_text, "纳戒获得 流光签 x1")
            assert "开孔器" not in redeem_text
            assert "血契丹" not in redeem_text
            after_player = player.player("u1")
            assert after_player is not None
            assert int(after_player["raw_stones"]) >= int(before_player["raw_stones"]) + 100
            _must_contain(dongtian.redeem("u1", str(issued["code"])), "已经被兑换过")

            issued_embryo = dongtian.issue_code(
                "fishing-demo",
                "灵溪垂钓",
                [
                    {"type": "currency", "quantity": 1000},
                    {"type": "medicine_embryo", "key": "dim_blood", "quantity": 2},
                ],
                score=456,
            )
            second_text = dongtian.redeem("u1", str(issued_embryo["code"]))
            _must_contain(second_text, "洞天收益系数：资源 94.8%｜药胚稳定 100%")
            _must_contain(second_text, "原石 +947")
            assert second_text.count("药胚成形：血契丹 x1") == 2
            assert dongtian_medicine_embryo_rate(0) == 1.0
            assert dongtian_medicine_embryo_rate(2) == 1.0
            assert dongtian_medicine_embryo_rate(21) == 0.24

            records_text = dongtian.records("u1")
            _must_contain(records_text, "今日已兑换：**2** 次")
            _must_contain(records_text, "当前资源收益系数：**90.1%**")
            _must_contain(records_text, "今日药息点：**2**")
            _must_contain(records_text, "灵溪垂钓｜分数 456｜原石 +947")
        finally:
            dongtian_service_module.DONGTIAN_STATIC_DIR = original_static_dir


def _check_history(services: dict[str, object]) -> None:
    """检查修仙早报和人物志里的公开反映层。"""

    history: XiuxianHistoryService = services["history"]  # type: ignore[assignment]

    text = history.newspaper("u1")
    _must_contain(text, "修仙早报")
    assert "天地气象" not in text
    assert "今日天气" not in text
    assert "今日灵潮" not in text
    assert "全服生效" not in text
    _must_contain(text, "城池建设")
    _must_contain(text, "药路最紧")
    _must_contain(text, "民生最盛")

    chronicle_text = history.chronicle("u1")
    _must_contain(chronicle_text, "史册分卷")
    _must_contain(chronicle_text, "最近大事")

    for command in ("人物史榜", "宗门史榜", "城池史榜", "战斗名局", "商路奇闻", "异界虫洞录"):
        volume_text = history.history_volume("u1", command)
        _must_contain(volume_text, command)

    profile_text = history.profile("u1", "青衫客")
    _must_contain(profile_text, "青衫客人物志")
    _must_contain(profile_text, "世界流转")
    _must_contain(profile_text, "主要流向")


def _check_wormhole(services: dict[str, object]) -> None:
    """检查异界虫洞的开启、挑战和领奖。"""

    wormhole: WormholeService = services["wormhole"]  # type: ignore[assignment]

    assert wormhole._daily_event_limit(0) == WORMHOLE_DAILY_MIN_LIMIT
    assert wormhole._daily_event_limit(1) == WORMHOLE_DAILY_MIN_LIMIT
    assert wormhole._daily_event_limit(4) == 2
    assert wormhole._daily_event_limit(5) == 3
    assert wormhole._daily_event_limit(20) == 6
    assert wormhole._daily_event_limit(40) == WORMHOLE_DAILY_MAX_LIMIT

    with wormhole.db.transaction() as conn:
        conn.execute("DELETE FROM wormhole_notices")
        conn.execute("DELETE FROM wormhole_participants")
        conn.execute("DELETE FROM wormholes")
    empty_wormhole_status = wormhole.status("u1")
    _must_contain(empty_wormhole_status, "当前没有开启")
    _must_not_contain(empty_wormhole_status, "<导航 ")
    event = wormhole._open_event("u1", "test", "天枢城")
    wormhole.db.execute(
        "UPDATE players SET location_name = ?, x = ?, y = ?, hp = max_hp, mp = max_mp, status = '探险中' WHERE client_id = ?",
        (event["location_name"], event["x"], event["y"], "u1"),
    )
    wormhole_status_text = wormhole.status("u1")
    _must_contain(wormhole_status_text, "异界虫洞")
    _must_contain(wormhole_status_text, "世界平均水平")
    _must_contain(wormhole_status_text, "今日出现")
    _must_contain(wormhole_status_text, f"<导航 {event['location_name']}>")
    _must_contain(wormhole_status_text, "<挑战虫洞>")
    _must_not_contain(wormhole_status_text, "等级：")
    _must_contain(wormhole.ranking("u1"), "暂无挑战记录")
    _must_contain(wormhole.challenge("u1"), "行商化身")
    wormhole.db.execute("UPDATE players SET status = '空闲' WHERE client_id = ?", ("u1",))
    wormhole.db.execute("UPDATE players SET battle_log_detail = 1 WHERE client_id = ?", ("u1",))
    wormhole.db.execute(
        """
        UPDATE players
        SET rest_window_started_at = ?,
            rest_window_hp = 1,
            rest_window_mp = 2,
            rest_window_elapsed_seconds = 300
        WHERE client_id = ?
        """,
        ("2000-01-01T00:00:00", "u1"),
    )
    original_wormhole_fight = wormhole._fight_boss
    try:
        def _move_player_during_wormhole_fight(player: dict, event_row: dict) -> dict:
            result = original_wormhole_fight(player, event_row)
            wormhole.db.execute("UPDATE players SET status = '探险中' WHERE client_id = ?", ("u1",))
            return result

        wormhole._fight_boss = _move_player_during_wormhole_fight  # type: ignore[method-assign]
        interrupted_text = wormhole.challenge("u1")
    finally:
        wormhole._fight_boss = original_wormhole_fight  # type: ignore[method-assign]
        wormhole.db.execute("UPDATE players SET status = '空闲' WHERE client_id = ?", ("u1",))
    _must_contain(interrupted_text, "本体正在探险")
    assert (
        wormhole.db.fetch_one(
            "SELECT 1 FROM wormhole_challenge_records WHERE wormhole_id = ? AND client_id = ?",
            (event["wormhole_id"], "u1"),
        )
        is None
    )
    challenge_text = wormhole.challenge("u1")
    _must_contain(challenge_text, "挑战虫洞")
    _must_contain(challenge_text, "战斗日志")
    _must_contain(challenge_text, "zhandou-rizhi/wormhole")
    _must_contain(challenge_text, "detail=1")
    wormhole_record = wormhole.db.fetch_one(
        "SELECT result FROM wormhole_challenge_records WHERE wormhole_id = ? AND client_id = ? ORDER BY record_id DESC LIMIT 1",
        (event["wormhole_id"], "u1"),
    )
    assert wormhole_record is not None
    assert "actions" in str(wormhole_record["result"])
    after_wormhole_challenge = wormhole.player("u1")
    assert after_wormhole_challenge is not None
    assert int(after_wormhole_challenge["rest_window_elapsed_seconds"]) == 0
    assert int(after_wormhole_challenge["rest_window_hp"]) == int(after_wormhole_challenge["hp"])
    assert int(after_wormhole_challenge["rest_window_mp"]) == int(after_wormhole_challenge["mp"])
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
    _must_contain(kill_text, "战斗日志")
    _must_not_contain(kill_text, "我方技能")
    _must_not_contain(kill_text, "Boss技能")
    _must_not_contain(kill_text, "行动 **")
    assert "二、最终结算" not in _payload_text(kill_text)
    reward_text = wormhole.reward("u1")
    _must_contain(reward_text, "虫洞奖励")
    _must_contain(reward_text, "结果：已击杀")
    assert "开孔器" not in reward_text
    assert "铭刻之羽" not in reward_text
    assert "异界残片" not in reward_text
    assert "兑换" not in reward_text

    with wormhole.db.transaction() as conn:
        conn.execute("DELETE FROM wormhole_notices")
        conn.execute("DELETE FROM wormhole_participants")
        conn.execute("DELETE FROM wormholes")
        cursor = conn.execute(
            """
            INSERT INTO wormholes (
                boss_name, boss_kind, location_name, x, y,
                level, max_hp, hp, attack, defense, difficulty,
                opened_by, source, status, opened_at, closes_at, killed_at, result
            )
            VALUES (
                '退去虫洞', 'test', '天枢城', 0, 0,
                10, 10000, 8000, 50, 10, 1.0,
                'system', 'test', '已退去', '2000-01-01T00:00:00', '2000-01-01T01:00:00', NULL, '{"boss_flow":"重击破防"}'
            )
            """
        )
        retreat_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO wormhole_participants
            (wormhole_id, client_id, damage, challenge_count, last_challenge_at, reward_claimed, created_at, updated_at)
            VALUES (?, 'u1', 2000, 1, '2000-01-01T00:10:00', 0, '2000-01-01T00:10:00', '2000-01-01T00:10:00')
            """,
            (retreat_id,),
        )
    retreat_reward = wormhole.reward("u1")
    _must_contain(retreat_reward, "结果：已退去")
    _must_contain(retreat_reward, "贡献：20.0%")
    _must_not_contain(retreat_reward, "贡献：100.0%")

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
    seasonal_skill = seasonal_skill_for_event(event)
    seasonal_skill_names = {str(config["name"]) for config in SEASONAL_SKILL_TEMPLATES.values()}
    common_boss_skill_names = {"妖影撕咬", "游魂缠身", "阴魂噬念", "魔焰灼心", "古卫镇压"}
    assert seasonal_skill["name"] in seasonal_skill_names
    assert seasonal_skill["name"] not in common_boss_skill_names
    captured_boss_call: dict[str, Any] = {}
    original_fight_boss = seasonal_boss.combat_core.fight_boss
    try:
        def _capture_seasonal_boss_fight(player_arg: dict, _event_arg: dict, **kwargs: Any) -> dict[str, Any]:
            captured_boss_call.update(kwargs)
            return {
                "damage": 1,
                "hp_left": int(player_arg["hp"]),
                "mp_left": int(player_arg["mp"]),
                "skill_times": 0,
                "boss_skill_times": 0,
                "weapon_id": 0,
                "weapon_exp": 0,
                "highest_damage": 0,
                "actions": [],
            }

        seasonal_boss.combat_core.fight_boss = _capture_seasonal_boss_fight  # type: ignore[method-assign]
        player_row = seasonal_boss.player("u1")
        assert player_row is not None
        seasonal_boss._fight_boss(player_row, event)
    finally:
        seasonal_boss.combat_core.fight_boss = original_fight_boss  # type: ignore[method-assign]
    assert captured_boss_call["boss_kind"] == SEASONAL_BOSS_KIND
    assert captured_boss_call["enemy_skill"]["name"] == seasonal_skill["name"]
    seasonal_boss.db.execute(
        "UPDATE seasonal_boss_events SET business_day = ?, hp = 1 WHERE event_id = ?",
        (seasonal_boss._business_date().isoformat(), event["event_id"]),
    )
    seasonal_boss.db.execute(
        "UPDATE players SET status = '探险中', hp = max_hp, mp = max_mp WHERE client_id = ?",
        ("u1",),
    )

    seasonal_status_text = seasonal_boss.status("u1")
    _must_contain(seasonal_status_text, "折柳青郎")
    _must_contain(seasonal_status_text, "世界平均水平")
    _must_not_contain(seasonal_status_text, "等级：")
    _must_contain(seasonal_boss.ranking("u1"), "暂无挑战记录")
    _must_contain(seasonal_boss.challenge("u1"), "行商化身")
    seasonal_boss.db.execute("UPDATE players SET status = '空闲' WHERE client_id = ?", ("u1",))
    seasonal_boss.db.execute(
        "UPDATE seasonal_boss_events SET closes_at = ? WHERE event_id = ?",
        (ts(now() + timedelta(minutes=10)), event["event_id"]),
    )
    seasonal_boss.db.execute(
        """
        INSERT INTO seasonal_boss_participants
        (event_id, client_id, damage, challenge_count, last_challenge_at, reward_claimed, created_at, updated_at)
        VALUES (?, 'u1', 1, 1, ?, 0, ?, ?)
        """,
        (
            event["event_id"],
            ts(now() - timedelta(minutes=5)),
            ts(now() - timedelta(minutes=5)),
            ts(now() - timedelta(minutes=5)),
        ),
    )
    late_cooldown_text = seasonal_boss.challenge("u1")
    _must_contain(late_cooldown_text, "首领仍在")
    _must_contain(late_cooldown_text, "赶不上本轮")
    seasonal_boss.db.execute(
        "DELETE FROM seasonal_boss_participants WHERE event_id = ? AND client_id = ?",
        (event["event_id"], "u1"),
    )
    seasonal_boss.db.execute(
        "UPDATE seasonal_boss_events SET closes_at = ? WHERE event_id = ?",
        (ts(now() + timedelta(hours=1)), event["event_id"]),
    )
    seasonal_boss.db.execute("UPDATE players SET battle_log_detail = 1 WHERE client_id = ?", ("u1",))
    seasonal_boss.db.execute(
        """
        UPDATE players
        SET rest_window_started_at = ?,
            rest_window_hp = 1,
            rest_window_mp = 2,
            rest_window_elapsed_seconds = 300
        WHERE client_id = ?
        """,
        ("2000-01-01T00:00:00", "u1"),
    )
    original_boss_fight = seasonal_boss._fight_boss
    try:
        def _move_player_during_boss_fight(player: dict, event_row: dict) -> dict:
            result = original_boss_fight(player, event_row)
            seasonal_boss.db.execute("UPDATE players SET status = '探险中' WHERE client_id = ?", ("u1",))
            return result

        seasonal_boss._fight_boss = _move_player_during_boss_fight  # type: ignore[method-assign]
        interrupted_text = seasonal_boss.challenge("u1")
    finally:
        seasonal_boss._fight_boss = original_boss_fight  # type: ignore[method-assign]
        seasonal_boss.db.execute("UPDATE players SET status = '空闲' WHERE client_id = ?", ("u1",))
    _must_contain(interrupted_text, "行商化身")
    assert (
        seasonal_boss.db.fetch_one(
            "SELECT 1 FROM boss_challenge_records WHERE event_id = ? AND client_id = ?",
            (event["event_id"], "u1"),
        )
        is None
    )
    challenge_text = seasonal_boss.challenge("u1")
    _must_contain(challenge_text, "已被送回岁时深处")
    _must_contain(challenge_text, "战斗日志")
    _must_contain(challenge_text, "zhandou-rizhi/boss")
    _must_contain(challenge_text, "detail=1")
    _must_not_contain(challenge_text, "我方技能")
    _must_not_contain(challenge_text, "首领技能")
    _must_not_contain(challenge_text, "行动 **")
    boss_record = seasonal_boss.db.fetch_one(
        "SELECT result FROM boss_challenge_records WHERE event_id = ? AND client_id = ? ORDER BY record_id DESC LIMIT 1",
        (event["event_id"], "u1"),
    )
    assert boss_record is not None
    assert "actions" in str(boss_record["result"])
    after_boss_challenge = seasonal_boss.player("u1")
    assert after_boss_challenge is not None
    assert int(after_boss_challenge["rest_window_elapsed_seconds"]) == 0
    assert int(after_boss_challenge["rest_window_hp"]) == int(after_boss_challenge["hp"])
    assert int(after_boss_challenge["rest_window_mp"]) == int(after_boss_challenge["mp"])
    seasonal_boss.db.execute("UPDATE players SET battle_log_detail = 0 WHERE client_id = ?", ("u1",))
    _must_contain(seasonal_boss.challenge("u1"), "不能继续挑战")
    old_boss_random = seasonal_boss_service_module.random.random
    try:
        seasonal_boss_service_module.random.random = lambda: 0.0
        reward_text = seasonal_boss.reward("u1")
    finally:
        seasonal_boss_service_module.random.random = old_boss_random
    _must_contain(reward_text, "岁时情劫奖励")
    _must_contain(reward_text, "结果：已击破")
    _must_contain(reward_text, "首领权重：普通节气")
    _must_contain(reward_text, "珍贵抽取")
    _must_contain(reward_text, "宗门增益：珍贵掉落")
    assert any(text in reward_text for text in ("开孔器", "洗髓液", "铭刻之羽", "宝石获得", "纳戒获得", "获得武器"))
    assert reward_text.count("获得铭刻之羽") <= 1

    with seasonal_boss.db.transaction() as conn:
        conn.execute("DELETE FROM seasonal_boss_participants")
        conn.execute("DELETE FROM seasonal_boss_events")
        cursor = conn.execute(
            """
            INSERT INTO seasonal_boss_events (
                business_day, boss_key, event_type, weight_type, boss_name, title,
                scene, story, farewell, feather_text, location_name, atmosphere,
                level, max_hp, hp, attack, defense, difficulty,
                status, opened_at, closes_at, killed_at, result
            )
            VALUES (
                '2099-02-05', 'test_retreat', '每日旧愿', '每日旧愿', '退去旧愿',
                '迟归旧愿', '一段用于测试的旧愿。', '它只剩半口气，却没有被击破。',
                '旧愿退去。', '一枚测试铭刻之羽。', '天枢城', '[]',
                10, 10000, 7500, 50, 10, 1.0,
                '已退去', '2000-01-01T00:00:00', '2000-01-02T04:00:00', NULL, '{"reason":"timeout"}'
            )
            """
        )
        retreat_event_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO seasonal_boss_participants
            (event_id, client_id, damage, challenge_count, last_challenge_at, reward_claimed, created_at, updated_at)
            VALUES (?, 'u1', 2500, 1, '2000-01-01T00:10:00', 0, '2000-01-01T00:10:00', '2000-01-01T00:10:00')
            """,
            (retreat_event_id,),
        )
    retreat_reward = seasonal_boss.reward("u1")
    _must_contain(retreat_reward, "结果：已退去")
    _must_contain(retreat_reward, "你为本次旧愿留下 25.0% 伤痕，位列第1")
    _must_not_contain(retreat_reward, "你为本次旧愿留下 100.0% 伤痕")

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
