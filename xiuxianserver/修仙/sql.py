"""修仙模块 SQLite 数据层。

当前模块只按最新 schema 运行；空库可以初始化，已有库版本不一致时直接中止，
避免误伤真实玩家数据。
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Iterator

from .common import (
    CURRENCY_DEFS,
    ENEMY_SKILL_DEFS,
    PLAYER_LEVEL_DEFS,
    QUALITY_DEFS,
    QUALITY_EPIC,
    RING_CATEGORY_KEYS,
    WEAPON_TYPE_ATTACK_BASE_FACTORS,
    enemy_kind_key,
    quality_key,
    ring_category_key,
    set_currency_label_overrides,
    set_enemy_skill_label_overrides,
    set_player_level_label_overrides,
    set_quality_label_overrides,
    ts,
    weapon_type_key,
)
from .constants import DEFAULT_LOCATION_ID, EQUIPMENT_SLOTS, SCHEMA_VERSION, WISH_TOKEN_ITEM_ID, WORLD_COORD_MAX, WORLD_COORD_MIN
from .runtime_cache import clear_runtime_caches


PHYSIQUE_DEFS = (
    ("fanti", "凡体", "凡阶", "均衡", 0, 0, {}, "平平无奇，却也最稳，所有玩家默认从这里开始。"),
    ("qingfeng_lingti", "清风灵体", "灵阶", "身法", 1, 2, {"dodge_bonus": 0.01}, "气息轻灵，稍微更容易避开伤害。"),
    ("houde_lingti", "厚土灵体", "灵阶", "体修", 1, 2, {"defense_bonus": 4}, "根基厚实，早期防御更稳。"),
    ("lingquan_ti", "灵泉体", "灵阶", "恢复", 2, 3, {"recover_bonus": 0.03}, "体内如有活泉，休息恢复更好。"),
    ("tiegu_ti", "铁骨体", "灵阶", "防御", 2, 3, {"crit_resist_bonus": 0.012}, "骨骼坚韧，承伤更稳。"),
    ("mingxin_ti", "明心体", "灵阶", "精神", 3, 4, {"max_mp_bonus": 24}, "心神清明，精神上限略高。"),
    ("qianye_lingti", "千叶灵体", "灵阶", "木灵", 3, 4, {"max_hp_bonus": 28, "recover_bonus": 0.015}, "生机细密，血气和恢复都有一点优势。"),
    ("qingmu_xuanti", "青木玄体", "玄阶", "木灵", 4, 6, {"max_hp_bonus": 55, "recover_bonus": 0.035, "trade_bonus": -0.004}, "偏生机恢复，跑商手续费略吃亏。"),
    ("xuanbing_linggu", "玄冰灵骨", "玄阶", "冰脉", 4, 6, {"defense_bonus": 18, "crit_resist_bonus": 0.02, "recover_bonus": -0.01}, "防御冷硬，恢复稍慢。"),
    ("chixia_lingti", "赤霞灵体", "玄阶", "火阳", 5, 7, {"max_hp_bonus": 85, "max_mp_bonus": -20}, "血气旺盛，精神上限略低。"),
    ("leiwenzhanti", "雷纹战体", "玄阶", "雷法", 5, 8, {"dodge_bonus": 0.022, "crit_resist_bonus": 0.012, "trade_bonus": -0.006}, "身法迅疾，生活经营不太细致。"),
    ("yuyue_ti", "玉月体", "玄阶", "月华", 6, 9, {"max_mp_bonus": 80, "recover_bonus": 0.035, "max_hp_bonus": -25}, "精神与恢复突出，血气略薄。"),
    ("jianxin_xuangu", "剑心玄骨", "玄阶", "剑骨", 6, 10, {"dodge_bonus": 0.018, "explore_bonus": 0.025, "max_hp_bonus": -30}, "适合冒险寻机，身板略薄。"),
    ("longxiang_baoti", "龙象宝体", "地阶", "体修", 7, 13, {"max_hp_bonus": 170, "defense_bonus": 28, "trade_bonus": -0.012}, "血厚防稳，跑商不灵活。"),
    ("xinghe_lingti", "星河灵体", "地阶", "星命", 7, 14, {"explore_bonus": 0.055, "max_mp_bonus": 110, "defense_bonus": -8}, "擅长探险寻宝，防御略低。"),
    ("taiyin_yuti", "太阴玉体", "地阶", "月华", 8, 15, {"recover_bonus": 0.085, "max_mp_bonus": 130, "max_hp_bonus": -55}, "恢复和精神很强，血气偏薄。"),
    ("taiyang_yanti", "太阳炎体", "地阶", "火阳", 8, 16, {"max_hp_bonus": 230, "recover_bonus": -0.025, "trade_bonus": -0.008}, "血气极盛，恢复和跑商略差。"),
    ("canghai_daoti", "沧海道体", "地阶", "水脉", 9, 17, {"max_mp_bonus": 170, "recover_bonus": 0.065, "defense_bonus": -10}, "精神绵长、恢复平顺，防御偏弱。"),
    ("wuyue_baoti", "五岳宝体", "地阶", "山岳", 9, 18, {"defense_bonus": 55, "crit_resist_bonus": 0.04, "max_mp_bonus": -60, "explore_bonus": -0.012}, "防御厚重，精神和探险灵活性较差。"),
    ("hunyuan_daoti", "玄黄镇岳体", "天阶", "山岳", 10, 22, {"defense_bonus": 80, "crit_resist_bonus": 0.055, "max_mp_bonus": -90, "trade_bonus": -0.015}, "极端守御体质，精神与跑商是短板。"),
    ("wugou_xianji", "琉璃无垢体", "天阶", "仙肌", 10, 23, {"recover_bonus": 0.13, "max_mp_bonus": 190, "defense_bonus": -20}, "恢复与精神突出，正面承伤略弱。"),
    ("wanxiang_lingtai", "千幻游身体", "天阶", "身法", 11, 25, {"dodge_bonus": 0.055, "explore_bonus": 0.075, "max_hp_bonus": -100, "defense_bonus": -18}, "闪避和探险极强，血防明显偏薄。"),
    ("zifu_tianti", "紫府明神体", "天阶", "精神", 11, 27, {"max_mp_bonus": 260, "recover_bonus": 0.07, "max_hp_bonus": -90}, "精神海宽广，血气不是优势。"),
    ("qianqiu_jianmai", "千秋剑脉", "天阶", "剑骨", 12, 29, {"explore_bonus": 0.08, "dodge_bonus": 0.035, "recover_bonus": -0.03}, "适合险地寻剑，恢复不算出色。"),
    ("shenxiao_leiti", "神霄雷体", "天阶", "雷法", 12, 30, {"dodge_bonus": 0.045, "crit_resist_bonus": 0.05, "recover_bonus": -0.04, "trade_bonus": -0.015}, "迅烈难伤，恢复和跑商都粗糙。"),
    ("xiantian_daotai", "先天药胎", "圣阶", "恢复", 13, 35, {"recover_bonus": 0.2, "max_mp_bonus": 280, "defense_bonus": -45, "max_hp_bonus": -120}, "恢复近乎夸张，但肉身承压偏弱。"),
    ("canglong_shengti", "苍龙圣体", "圣阶", "龙脉", 13, 38, {"max_hp_bonus": 380, "recover_bonus": 0.08, "trade_bonus": -0.02, "max_mp_bonus": -120}, "血气如海，精神和经营能力是短板。"),
    ("jiuyao_shengti", "九曜星命体", "圣阶", "星命", 14, 42, {"explore_bonus": 0.12, "trade_bonus": 0.006, "max_hp_bonus": -160, "defense_bonus": -30}, "天生会找机会，适合探险和跑商，血防较薄。"),
    ("bumie_jinshen", "不灭金身", "圣阶", "金身", 14, 45, {"defense_bonus": 120, "crit_resist_bonus": 0.08, "max_mp_bonus": -160, "explore_bonus": -0.025, "trade_bonus": -0.02}, "最硬的防御路线，精神、探险和跑商都笨重。"),
    ("taixu_xianmai", "太虚仙脉", "圣阶", "虚空", 15, 48, {"dodge_bonus": 0.085, "explore_bonus": 0.11, "max_hp_bonus": -220, "defense_bonus": -45}, "飘忽难捉，探险极强，但正面血防很低。"),
    ("hongmeng_xuanti", "归墟玄体", "圣阶", "虚空", 15, 50, {"dodge_bonus": 0.075, "max_mp_bonus": 340, "recover_bonus": -0.06, "max_hp_bonus": -180, "trade_bonus": -0.02}, "精神深不可测，却不适合硬扛和经营。"),
)


WORLD_MATERIAL_GROUPS = (
    ("药路", "med", "血契丹", "xueqidan", ("血藤籽", "赤契砂", "伏火炭"), ("凡品", "良品", "凡品"), 1, 80, 260, "古界药圃、残破丹坊和旧炉火种带出的药路物资，用来解释血契丹补给来源。"),
    ("药路", "med", "阴冥草", "yinmingcao", ("阴冥芽", "寒魄霜", "冷炉灰"), ("凡品", "良品", "凡品"), 1, 80, 260, "阴湿遗迹和废炉灰烬里收出的药路物资，用来解释阴冥草补给来源。"),
    ("药路", "med", "回春露", "huichunlu", ("回春露草", "蜂王浆", "温木炭"), ("凡品", "良品", "凡品"), 1, 80, 300, "旧灵田、古蜂巢和温炉余火带出的药路物资，用来解释回春露补给来源。"),
    ("药路", "med", "凝神露", "ningshenlu", ("水镜草", "静神兰", "清炉烟"), ("凡品", "良品", "凡品"), 1, 80, 300, "清气遗草和古炉残烟带出的药路物资，用来解释凝神露补给来源。"),
    ("药路", "med", "生骨丹", "shenggudan", ("生骨泥", "赤骨石", "炎晶片"), ("良品", "良品", "珍品"), 3, 50, 560, "遗迹骨池、赤骨矿脉和爆炉炎晶带出的药路物资，用来解释生骨丹补给来源。"),
    ("药路", "med", "养魂丹", "yanghundan", ("养魂叶", "朱羽引", "醒魂草"), ("良品", "珍品", "良品"), 1, 60, 580, "旧魂园、朱羽残影和荒坟灵草带出的药路物资，用来解释养魂丹补给来源。"),
    ("民生", "life", "城食", "chengshi", ("遗田灵粟", "月井麦", "地乳豆", "青髓薯", "玉壳谷"), "凡品", 4, 120, 180, "古界废田里可被凡城粮仓吸收的城食物资，量大、耐用、能稳住许多张嘴。"),
    ("民生", "life", "盐鲜", "yanxian", ("赤潮盐", "寒泉盐", "灵藻干", "银鳞脯", "荒兽腊"), "凡品", 3, 120, 190, "古潮、寒泉和荒兽巢带出的盐鲜物资，是凡城日常和军营伙食的刚需。"),
    ("民生", "life", "水净", "shuijing", ("净泉砂", "澄水石", "清浊炭", "避瘴灰", "甘露瓮"), "凡品", 3, 120, 200, "古渠、旧井和避瘴设施里带出的水净物资，用来维持城池饮水和灾后稳定。"),
    ("民生", "life", "衣被", "yibei", ("雪蚕絮", "火绒麻", "青藤线", "暖玉棉", "寒兽毡"), "凡品", 2, 120, 210, "遗迹巢穴和古界灵田里带出的衣被物资，凡人过冬、行军和安置灾民都要用。"),
    ("民生", "life", "燃安", "ranan", ("地肺炭", "长明油", "萤芯草", "雷松脂", "驱疫香"), "良品", 2, 100, 320, "古炉、雷木和旧祠香库带出的燃安物资，能照明、取暖、驱疫和稳住夜巡。"),
    ("建设", "build", "基础", "jichu", ("古城砖", "青罡石", "玄灰泥", "铁木梁", "鳞纹瓦"), "良品", 7, 80, 420, "古界断城和旧山门拆出的基础建材，能让凡城修得更结实。"),
    ("建设", "build", "城防", "chengfang", ("镇妖石", "破邪木", "惊妖铃", "兽纹拒马", "玄铁闸"), "良品", 7, 60, 620, "残阵城墙和镇妖设施里带出的城防物资，后续服务抗妖、防灾和据点守备。"),
    ("建设", "build", "水火", "shuihuo", ("净渠玉", "寒泉管", "避火砂", "引雷桩", "锁潮箍"), "良品", 5, 60, 560, "古渠、火库、雷桩和潮闸里带出的水火物资，后续服务城市运转和灾害治理。"),
    ("建设", "build", "阵基", "zhenji", ("护城砖", "聚灵砂", "封妖灰", "辟邪钉", "镇宅锁"), "良品", 4, 80, 520, "旧护城阵和封妖阵里带出的阵基物资，后续服务设施升级和地标建设。"),
    ("建设", "build", "华饰", "huashi", ("琉光檐", "玉兽环", "云纹壁", "月庭灯", "金纹坊"), "珍品", 5, 50, 900, "古界宗门门面上拆出的华饰物资，既撑门面，也能提升地方繁荣。"),
    ("古物", "relic", "微蕴", "weiyun", ("灰月碎币", "旧王庭徽", "星门断钥", "白塔残页", "雾海铜铃", "失语镜砂", "眠龙骨片", "空舟铆钉"), "良品", 1, 40, 1300, "含少量神秘物质的古界旧物，卖给懂行修仙者或回收势力。"),
    ("古物", "relic", "中蕴", "zhongyun", ("灰烬圣杯", "银环星图", "界树枯种", "无面王冠", "夜航罗盘", "封门魔典", "逆潮沙漏", "龙眠石碑"), "珍品", 2, 30, 3100, "含中量神秘物质的古界遗珍，名字和重量都足够让修仙者认真验货。"),
    ("古物", "relic", "厚蕴", "houyun", ("群星命轮", "旧神冠冕", "界门王钥", "终焉圣杯", "万象禁书", "昼夜双镜", "天灾方舟", "原初界标"), "稀品", 3, 10, 7600, "含大量神秘物质的古界重宝，主要用于高价回收和后续神秘物质闭环。"),
    ("战利品", "loot", "妖类", "yao", ("古妖丹", "妖脊骨", "妖煞血", "妖甲皮", "妖瞳珠", "妖魂晶"), ("良品", "凡品", "凡品", "凡品", "良品", "良品"), 2, 50, 760, "古界妖物身上剥离的战斗掉落，主要供镇妖司特殊收购。"),
    ("战利品", "loot", "魔类", "mo", ("魔魇核", "魔煞角", "魔烬血", "魔纹皮", "裂魔爪", "魔焰灰"), ("珍品", "良品", "良品", "良品", "珍品", "珍品"), 2, 40, 920, "魔影和魔物残躯里取出的战斗掉落，主要供伏魔殿特殊收购。"),
    ("战利品", "loot", "鬼类", "gui", ("阴魂珠", "鬼火芯", "残魂幡", "白骨片", "冥路纸", "怨气瓶"), ("良品", "凡品", "良品", "凡品", "凡品", "良品"), 1, 50, 620, "鬼物和阴魂遗留的战斗掉落，主要供鬼市特殊收购。"),
    ("战利品", "loot", "龙类", "long", ("蛟逆鳞", "龙须丝", "龙血石"), ("珍品", "珍品", "稀品"), 1, 30, 2300, "古龙残裔和蛟影留下的战斗掉落，主要供龙渊阁特殊收购。"),
    ("战利品", "loot", "兽类", "shou", ("荒兽筋", "凶兽牙", "荒兽骨", "兽纹皮", "灵兽角", "兽魄心"), ("良品", "凡品", "凡品", "凡品", "良品", "良品"), 3, 50, 620, "荒兽和灵兽残躯中取得的战斗掉落，主要供万兽盟特殊收购。"),
    ("战利品", "loot", "兵戈类", "bing", ("军魂印", "破甲片", "残兵符", "血战旗", "锈血铁", "断寒刃"), ("稀品", "良品", "良品", "良品", "珍品", "珍品"), 2, 40, 820, "遗迹战场、残兵怨灵和旧甲刃留下的战斗掉落，主要供破军营特殊收购。"),
)


def _material_quality(quality: str | tuple[str, ...], index: int) -> str:
    """按组配置取物资品级。"""

    if isinstance(quality, tuple):
        return quality_key(quality[min(index, len(quality) - 1)])
    return quality_key(quality)


def _material_item_id(category_code: str, subtype_code: str, index: int) -> str:
    """生成稳定 ASCII 物资 id；战利品 id 单独短一点，方便掉落池引用。"""

    if category_code == "loot":
        return f"loot_{subtype_code}_{index + 1}"
    return f"world_{category_code}_{subtype_code}_{index + 1}"


WORLD_CATEGORY_KEYS = {
    "纯经济": "trade",
    "药路": "medicine",
    "民生": "life",
    "建设": "build",
    "古物": "relic",
    "战利品": "loot",
}


def world_category_key(category: str) -> str:
    """世界物资规则大类；展示名可换皮，业务规则只认这个稳定键。"""

    return WORLD_CATEGORY_KEYS.get(str(category or "").strip(), str(category or "").strip())


def _medicine_material_role(category: str, subtype_code: str, index: int) -> str:
    """药路物资稳定用途；换皮后不能靠展示名后缀判断燃料。"""

    if world_category_key(category) != "medicine":
        return ""
    if index == 2:
        return "fuel"
    if subtype_code in {"shenggudan", "yanghundan"}:
        return "catalyst"
    return "material"


def _build_world_items() -> tuple[tuple[str, str, str, str, int, int, int, int, int, dict[str, str], str], ...]:
    """把六大类世界物资设定展开为 item_defs 行。"""

    rows = []
    for category, category_code, subtype, subtype_code, names, quality, weight, stack_limit, base_price, desc in WORLD_MATERIAL_GROUPS:
        for index, name in enumerate(names):
            effect = {
                "world_category": category,
                "world_category_key": world_category_key(category),
                "world_subtype": subtype,
                "world_subtype_key": subtype_code,
            }
            material_role = _medicine_material_role(category, subtype_code, index)
            if material_role:
                effect["medicine_material_role"] = material_role
            rows.append(
                (
                    _material_item_id(category_code, subtype_code, index),
                    name,
                    category,
                    _material_quality(quality, index),
                    int(weight),
                    int(stack_limit),
                    0,
                    0,
                    int(base_price) + index * 40,
                    effect,
                    f"{name}：{desc}",
                )
            )
    return tuple(rows)


ITEM_DEFS = _build_world_items()


RING_ITEM_DEFS = (
    (
        "fudai",
        "福袋",
        "恢复类",
        "良品",
        1,
        "玩家",
        {
            "random_stones_segments": [
                {"min_level": 1, "max_level": 20, "min": 10000, "max": 30000},
                {"min_level": 21, "max_level": 50, "min": 20000, "max": 60000},
                {"min_level": 51, "max_level": 80, "min": 40000, "max": 90000},
                {"min_level": 81, "max_level": 100, "min": 70000, "max": 150000},
            ],
        },
        "打开后按等级段随机获得一笔货币。",
    ),
    ("xueqidan", "血契丹", "恢复类", "凡品", 1, "玩家", {"hp_ratio": 0.25}, "恢复 25% 血气。"),
    ("yinmingcao", "阴冥草", "恢复类", "凡品", 1, "玩家", {"mp_ratio": 0.25}, "恢复 25% 精神。"),
    ("huichunlu", "回春露", "恢复类", "良品", 1, "玩家", {"hp_ratio": 0.45}, "恢复 45% 血气。"),
    ("ningshenlu", "凝神露", "恢复类", "良品", 1, "玩家", {"mp_ratio": 0.45}, "恢复 45% 精神。"),
    ("shenggudan", "生骨丹", "恢复类", "珍品", 1, "玩家", {"hp_ratio": 0.7}, "恢复 70% 血气。"),
    ("yanghundan", "养魂丹", "恢复类", "珍品", 1, "玩家", {"mp_ratio": 0.7}, "恢复 70% 精神。"),
    ("kaikongqi", "开孔器", "消耗品", "珍品", 0, "装备", {}, "装备开孔材料，通过岁时情劫首领奖励获得。"),
    ("xisuiye", "洗髓液", "消耗品", "珍品", 0, "玩家", {"wash_physique": 1}, "岁时情劫首领和异界虫洞掉落的体质重塑消耗品，通过体质重塑命令消耗。"),
    ("cuifengdan", "淬锋丹", "专属道具", "稀品", 0, "武器", {"weapon_max_level_delta": 1, "weapon_max_level_cap": 100}, "宗门大会奖励。进入纳戒后通过武器升限消耗，使指定武器等级上限 +1，最高 100。"),
    (WISH_TOKEN_ITEM_ID, "流光签", "专属道具", "良品", 0, "祈愿", {"wish_draws": 1}, "探险中低概率获得的祈愿凭据。进入纳戒后通过祈愿命令消耗，每枚可祈愿一次。"),
    ("fengren_shu", "风刃书", "技能书", "良品", 0, "武器", {"enchant_id": "fengren_shu"}, "高频连击流派。技能蓄势更快、命中更稳，但单次威力下降。"),
    ("shaying_shu", "沙影书", "技能书", "良品", 0, "武器", {"enchant_id": "shaying_shu"}, "高频连击流派。更容易追加连击，但连击伤害偏低。"),
    ("liuguang_shu", "流光书", "技能书", "良品", 0, "武器", {"enchant_id": "liuguang_shu"}, "高频连击流派。技能节奏更快，但单次爆发降低。"),
    ("zhuixing_shu", "追星书", "技能书", "良品", 0, "武器", {"enchant_id": "zhuixing_shu"}, "高频连击流派。命中和连击更稳定，但技能威力略低。"),
    ("poxie_shu", "破甲书", "技能书", "良品", 0, "武器", {"enchant_id": "poxie_shu"}, "重击破防流派。提高防御穿透，但技能蓄势变慢。"),
    ("bengshan_shu", "崩山书", "技能书", "珍品", 0, "武器", {"enchant_id": "bengshan_shu"}, "重击破防流派。强化重击威力，但技能蓄势变慢、精神消耗更高。"),
    ("chuanyun_shu", "穿云书", "技能书", "珍品", 0, "武器", {"enchant_id": "chuanyun_shu"}, "重击破防流派。穿透和单次伤害更高，但精神消耗明显提高。"),
    ("zhenyue_shu", "镇岳书", "技能书", "珍品", 0, "武器", {"enchant_id": "zhenyue_shu"}, "重击破防流派。重击时更稳，并带少量减伤，但出手节奏变沉。"),
    ("zhuoxin_shu", "灼心书", "技能书", "良品", 0, "武器", {"enchant_id": "zhuoxin_shu"}, "持续伤害流派。附加灼烧，短战爆发较弱。"),
    ("xueyu_shu", "血雨书", "技能书", "良品", 0, "武器", {"enchant_id": "xueyu_shu"}, "持续伤害流派。附加流血，但自身承伤略差。"),
    ("duyun_shu", "毒云书", "技能书", "珍品", 0, "武器", {"enchant_id": "duyun_shu"}, "持续伤害流派。灼烧和流血兼备，但技能威力下降。"),
    ("canyan_shu", "残焰书", "技能书", "珍品", 0, "武器", {"enchant_id": "canyan_shu"}, "持续伤害流派。残火提高终段爆发，但蓄势变慢。"),
    ("duannian_shu", "断念书", "技能书", "良品", 0, "武器", {"enchant_id": "duannian_shu"}, "压制控制流派。削弱对方精神，但直接伤害略低。"),
    ("zhenhun_shu", "镇魂书", "技能书", "珍品", 0, "武器", {"enchant_id": "zhenhun_shu"}, "压制控制流派。压精神并扰乱行动条，但技能威力下降。"),
    ("tianji_shu", "天机书", "技能书", "珍品", 0, "武器", {"enchant_id": "tianji_shu"}, "压制控制流派。行动条压制更强，但技能蓄势变慢。"),
    ("mengwu_shu", "梦雾书", "技能书", "良品", 0, "武器", {"enchant_id": "mengwu_shu"}, "压制控制流派。压精神和压防兼具，但爆发不足。"),
    ("huichun_shu", "回春书", "技能书", "良品", 0, "武器", {"enchant_id": "huichun_shu"}, "生存续航流派。造成伤害后轻微回血，但技能威力下降。"),
    ("xuandun_shu", "玄盾书", "技能书", "珍品", 0, "武器", {"enchant_id": "xuandun_shu"}, "生存续航流派。释放技能后护身更强，但蓄势变慢。"),
    ("xueqi_shu", "血契书", "技能书", "良品", 0, "武器", {"enchant_id": "xueqi_shu"}, "生存续航流派。吸血更高，但自身承伤更重。"),
    ("lingmu_shu", "灵木书", "技能书", "珍品", 0, "武器", {"enchant_id": "lingmu_shu"}, "生存续航流派。吸血和减伤兼具，但技能威力下降。"),
    ("fanzhen_shu", "反震书", "技能书", "良品", 0, "武器", {"enchant_id": "fanzhen_shu"}, "反击护身流派。护身被击中后小额反击，但技能威力下降。"),
    ("guiren_shu", "归刃书", "技能书", "珍品", 0, "武器", {"enchant_id": "guiren_shu"}, "反击护身流派。护身后借势回击，但技能蓄势变慢。"),
    ("jieshi_shu", "借势书", "技能书", "良品", 0, "武器", {"enchant_id": "jieshi_shu"}, "反击护身流派。反击更疼，但自身承伤略重。"),
    ("xuanyao_shu", "玄曜书", "技能书", "稀品", 0, "武器", {"enchant_id": "xuanyao_shu"}, "反击护身流派。反击和减伤兼具，但单次爆发不足。"),
    ("wuxiang_shu", "无相书", "技能书", "稀品", 0, "武器", {"enchant_id": "wuxiang_shu"}, "斩杀收割流派。提高技能威力，但触发更慢、精神消耗更高。"),
    ("duanhai_shu", "断海书", "技能书", "珍品", 0, "武器", {"enchant_id": "duanhai_shu"}, "斩杀收割流派。提高单次技能爆发，但触发更慢。"),
    ("jueying_shu", "绝影书", "技能书", "珍品", 0, "武器", {"enchant_id": "jueying_shu"}, "斩杀收割流派。闪避和收割兼顾，但技能威力略低。"),
    ("pojun_shu", "破军书", "技能书", "珍品", 0, "武器", {"enchant_id": "pojun_shu"}, "斩杀收割流派。穿透和单次爆发更高，但蓄势变慢。"),
    ("xingluo_shu", "星落书", "技能书", "珍品", 0, "武器", {"enchant_id": "xingluo_shu"}, "首领协作流派。连击贡献更高，但自身承伤略差。"),
    ("qiankun_shu", "乾坤书", "技能书", "稀品", 0, "武器", {"enchant_id": "qiankun_shu"}, "首领协作流派。压行动条并提高承伤稳定，但蓄势较慢。"),
    ("pozhen_shu", "破阵书", "技能书", "珍品", 0, "武器", {"enchant_id": "pozhen_shu"}, "首领协作流派。穿透和压防更强，但技能节奏变沉。"),
    ("yujing_shu", "玉京书", "技能书", "珍品", 0, "武器", {"enchant_id": "yujing_shu"}, "首领协作流派。命中和技能威力更稳，但精神消耗很高。"),
    ("yueshi_shu", "月蚀书", "技能书", "珍品", 0, "武器", {"enchant_id": "yueshi_shu"}, "决斗扰乱流派。压低对方防御，但直接威力略低。"),
    ("jinghu_shu", "镜湖书", "技能书", "良品", 0, "武器", {"enchant_id": "jinghu_shu"}, "决斗扰乱流派。闪避和命中更稳，但单次爆发不足。"),
    ("yingye_shu", "影叶书", "技能书", "良品", 0, "武器", {"enchant_id": "yingye_shu"}, "决斗扰乱流派。扰乱行动条并附带流血，但技能威力下降。"),
    ("qingxin_shu", "清心书", "技能书", "珍品", 0, "武器", {"enchant_id": "qingxin_shu"}, "决斗扰乱流派。削精神并提高承伤稳定，但单次爆发不足。"),
    ("huxinyu", "护心玉", "宝石", "凡品", 0, "装备", {"max_hp_bonus": 30}, "提高血气上限。"),
    ("xuangui shi", "玄龟石", "宝石", "凡品", 0, "装备", {"defense_bonus": 10}, "提高防御。"),
    ("shanbi fozhu", "闪避佛珠", "宝石", "良品", 0, "装备", {"dodge_bonus": 0.02}, "提高闪避。"),
    ("mingxin fozhu", "明心佛珠", "宝石", "良品", 0, "装备", {"mp_bonus": 30}, "提高精神上限。"),
    ("huichun feicui", "回春翡翠", "宝石", "良品", 0, "装备", {"recover_bonus": 0.04}, "提高休息和恢复效果。"),
    ("qingxin manao", "清心玛瑙", "宝石", "良品", 0, "装备", {"max_mp_bonus": 45}, "提高精神上限。"),
    ("qingshen shuijing", "轻身水晶", "宝石", "珍品", 0, "装备", {"explore_bonus": 0.03}, "提高探险效率。"),
    ("jucai zijing", "聚财紫晶", "宝石", "珍品", 0, "装备", {"trade_bonus": 0.02}, "小幅提高跑商收益。"),
    ("kangbao fuwen", "抗暴符文", "宝石", "稀品", 0, "装备", {"crit_resist_bonus": 0.04}, "提高抗暴和承伤稳定性。"),
)


def _extreme_book_effect(effect: dict[str, float]) -> dict[str, float]:
    """极版技能书去负面，并把正面数值提升 20%。"""

    upgraded: dict[str, float] = {}
    for key, value in effect.items():
        if not isinstance(value, int | float):
            continue
        if key == "interval_delta":
            if value < 0:
                upgraded[key] = value
            continue
        if value <= 0:
            continue
        upgraded[key] = round(float(value) * 1.2, 4)
    return upgraded


def _extreme_book_mp_delta(mp_delta: int) -> int:
    """极版技能书去掉额外精神消耗；若未来有减耗词条，则强化减耗。"""

    value = int(mp_delta)
    if value >= 0:
        return 0
    return int(round(value * 1.2))


def _extreme_book_defs() -> tuple[tuple[str, str, str, str, int, str, dict[str, str], str], ...]:
    """为每本普通技能书生成极版纳戒物品。"""

    rows = []
    for ring_item_id, name, category, _quality, _usable, target_type, effect, desc in RING_ITEM_DEFS:
        if ring_category_key(category) != "book":
            continue
        rows.append(
            (
                f"extreme_{ring_item_id}",
                f"极·{name}",
                category,
                QUALITY_EPIC,
                0,
                target_type,
                {"enchant_id": f"extreme_{ring_item_id}", "base_enchant_id": ring_item_id},
                f"民生恩赐中偶得的极版技能书。无负面效果，正面效果比原版提高 20%。原流派：{desc}",
            )
        )
    return tuple(rows)


EXTREME_BOOK_DEFS = _extreme_book_defs()


WISH_DEFAULT_POOL_ID = "default_liuguang"
WISH_VOUCHERS = (
    ("liuguang_voucher", "流光凭证"),
    ("yuanqi_voucher", "缘契凭证"),
    ("xingming_voucher", "星命凭证"),
    ("guixu_voucher", "归墟凭证"),
    ("tianqi_voucher", "天启凭证"),
)
WISH_DEFAULT_PRIZES = (
    ("currency_500", WISH_DEFAULT_POOL_ID, "currency", "raw_stones", "原石 500", 500, 1000, "{}"),
    ("currency_1500", WISH_DEFAULT_POOL_ID, "currency", "raw_stones", "原石 1500", 1500, 600, "{}"),
    ("currency_5000", WISH_DEFAULT_POOL_ID, "currency", "raw_stones", "原石 5000", 5000, 200, "{}"),
    ("exp_200", WISH_DEFAULT_POOL_ID, "exp", "player_exp", "经验 200", 200, 1400, "{}"),
    ("exp_600", WISH_DEFAULT_POOL_ID, "exp", "player_exp", "经验 600", 600, 800, "{}"),
    ("exp_1500", WISH_DEFAULT_POOL_ID, "exp", "player_exp", "经验 1500", 1500, 300, "{}"),
    ("ring_xueqidan_2", WISH_DEFAULT_POOL_ID, "ring_item", "xueqidan", "血契丹 x2", 2, 650, "{}"),
    ("ring_yinmingcao_2", WISH_DEFAULT_POOL_ID, "ring_item", "yinmingcao", "阴冥草 x2", 2, 650, "{}"),
    ("ring_huichunlu_1", WISH_DEFAULT_POOL_ID, "ring_item", "huichunlu", "回春露", 1, 450, "{}"),
    ("ring_ningshenlu_1", WISH_DEFAULT_POOL_ID, "ring_item", "ningshenlu", "凝神露", 1, 450, "{}"),
    ("ring_shenggudan_1", WISH_DEFAULT_POOL_ID, "ring_item", "shenggudan", "生骨丹", 1, 150, "{}"),
    ("ring_yanghundan_1", WISH_DEFAULT_POOL_ID, "ring_item", "yanghundan", "养魂丹", 1, 150, "{}"),
    ("world_med_xueqidan_2", WISH_DEFAULT_POOL_ID, "backpack_item", "world_med_xueqidan_1", "药路物资 x2", 2, 450, "{}"),
    ("world_med_yinmingcao_2", WISH_DEFAULT_POOL_ID, "backpack_item", "world_med_yinmingcao_1", "药路物资 x2", 2, 450, "{}"),
    ("world_life_chengshi_3", WISH_DEFAULT_POOL_ID, "backpack_item", "world_life_chengshi_1", "民生物资 x3", 3, 400, "{}"),
    ("world_build_jichu_2", WISH_DEFAULT_POOL_ID, "backpack_item", "world_build_jichu_1", "建设物资 x2", 2, 350, "{}"),
    ("world_relic_weiyun_1", WISH_DEFAULT_POOL_ID, "backpack_item", "world_relic_weiyun_1", "古物 x1", 1, 350, "{}"),
    ("voucher_liuguang", WISH_DEFAULT_POOL_ID, "voucher", "liuguang_voucher", "流光凭证", 1, 240, "{}"),
    ("voucher_yuanqi", WISH_DEFAULT_POOL_ID, "voucher", "yuanqi_voucher", "缘契凭证", 1, 240, "{}"),
    ("voucher_xingming", WISH_DEFAULT_POOL_ID, "voucher", "xingming_voucher", "星命凭证", 1, 240, "{}"),
    ("voucher_guixu", WISH_DEFAULT_POOL_ID, "voucher", "guixu_voucher", "归墟凭证", 1, 240, "{}"),
    ("voucher_tianqi", WISH_DEFAULT_POOL_ID, "voucher", "tianqi_voucher", "天启凭证", 1, 240, "{}"),
)


SEASONAL_BOSS_REWARD_RATES = (
    (
        "每日旧愿",
        0.025,
        0.012,
        0.015,
        0.010,
        0.080,
        0.030,
        0.015,
        "普通日首领，主要提供日常参与感，珍贵物品只保留低概率惊喜。",
    ),
    (
        "普通节气",
        0.050,
        0.020,
        0.025,
        0.014,
        0.100,
        0.040,
        0.020,
        "二十四节气首领，奖励略高于普通日。",
    ),
    (
        "普通传统节日",
        0.070,
        0.025,
        0.030,
        0.018,
        0.120,
        0.050,
        0.025,
        "普通传统节日首领，珍贵物品概率小幅提高。",
    ),
    (
        "高权重传统节日",
        0.100,
        0.035,
        0.040,
        0.025,
        0.150,
        0.065,
        0.035,
        "春节、元宵、端午、七夕、中秋、重阳等高权重节日。",
    ),
)


TRADE_SPECIALTY_GROUPS = (
    ("city_tianshu", "天枢城", 0, 0, (("trade_city_tianshu_01", "星官旧简"), ("trade_city_tianshu_02", "白契纸"), ("trade_city_tianshu_03", "旧朝钱"))),
    ("city_qinglan", "青岚坊", 8, 22, (("trade_city_qinglan_01", "风骨玉"), ("trade_city_qinglan_02", "听风纸"), ("trade_city_qinglan_03", "雨竹简"))),
    ("city_chixia", "赤霞港", 31, -6, (("trade_city_chixia_01", "晚潮珠"), ("trade_city_chixia_02", "火纹贝"), ("trade_city_chixia_03", "舶牙牌"))),
    ("city_xuantie", "玄铁岭", -28, 12, (("trade_city_xuantie_01", "山铜契"), ("trade_city_xuantie_02", "黑矿票"), ("trade_city_xuantie_03", "老炉印"))),
    ("city_wanyao", "万药谷", -18, 32, (("trade_city_wanyao_01", "谷市筹"), ("trade_city_wanyao_02", "灵圃帖"), ("trade_city_wanyao_03", "青囊账"))),
    ("city_yunmeng", "云梦泽", 18, -24, (("trade_city_yunmeng_01", "雾泽贝"), ("trade_city_yunmeng_02", "蜃雾珠"), ("trade_city_yunmeng_03", "水市牌"))),
    ("city_liusha", "流沙海市", -35, -18, (("trade_city_liusha_01", "走沙晶"), ("trade_city_liusha_02", "驼铃金"), ("trade_city_liusha_03", "驼队牌"))),
    ("city_hanshuang", "寒霜关", -3, 39, (("trade_city_hanshuang_01", "冷玉髓"), ("trade_city_hanshuang_02", "雪关牒"), ("trade_city_hanshuang_03", "霜市帖"))),
    ("city_leize", "雷泽城", 29, 24, (("trade_city_leize_01", "伏雷鼓"), ("trade_city_leize_02", "惊雷符"), ("trade_city_leize_03", "旧雷令"))),
    ("city_bichao", "碧潮岛", 38, -32, (("trade_city_bichao_01", "青潮珊"), ("trade_city_bichao_02", "月汐珠"), ("trade_city_bichao_03", "水府玉"))),
    ("city_xingyun", "星陨墟", 5, -43, (("trade_city_xingyun_01", "星砂瓶"), ("trade_city_xingyun_02", "陨碑拓"), ("trade_city_xingyun_03", "观星券"))),
)


TRADE_LOCATIONS = tuple(
    (location, x, y, ",".join(name for _item_id, name in specialties))
    for _location_id, location, x, y, specialties in TRADE_SPECIALTY_GROUPS
)

TRADE_LOCATION_IDS_BY_NAME = {
    location: location_id
    for location_id, location, _x, _y, _specialties in TRADE_SPECIALTY_GROUPS
}
TRADE_LOCATION_NAMES_BY_ID = {
    location_id: location
    for location_id, location, _x, _y, _specialties in TRADE_SPECIALTY_GROUPS
}
TRADE_ITEM_IDS_BY_NAME = {
    name: item_id
    for _location_id, _location, _x, _y, specialties in TRADE_SPECIALTY_GROUPS
    for item_id, name in specialties
}
TRADE_ITEM_HOME_LOCATION_IDS_BY_NAME = {
    name: location_id
    for location_id, _location, _x, _y, specialties in TRADE_SPECIALTY_GROUPS
    for _item_id, name in specialties
}


def trade_item_id(name: str) -> str:
    """跑商纯经济物品 id 使用稳定槽位；显示名可随世界皮肤包替换。"""

    clean = str(name).strip()
    return TRADE_ITEM_IDS_BY_NAME.get(clean) or "trade_" + hashlib.md5(clean.encode("utf-8")).hexdigest()[:12]


def _trade_item_def(location: str, location_index: int, item_index: int, name: str) -> tuple[str, str, int, int, int, str]:
    """生成纯经济特产定义。"""

    trade_type = ("trade_luxury", "trade_contract", "trade_ticket")[item_index]
    quality = quality_key(("良品", "良品", "凡品")[item_index])
    weight = (2, 1, 1)[item_index] + (1 if item_index == 0 and location_index % 3 == 0 else 0)
    stack_limit = (50, 70, 80)[item_index]
    base_price = (900, 760, 600)[item_index] + location_index * 35
    desc = f"{location}流通的地方特产：{name}。它只服务本界商路差价和地区供需，不从探险或秘境掉落。"
    return (trade_type, quality, weight, stack_limit, base_price, desc)


TRADE_ITEM_DEFS = {
    name: _trade_item_def(location, location_index, item_index, name)
    for location_index, (_location_id, location, _x, _y, specialties) in enumerate(TRADE_SPECIALTY_GROUPS)
    for item_index, (_item_id, name) in enumerate(specialties)
}


WORLD_ITEM_IDS = tuple(row[0] for row in ITEM_DEFS) + tuple(trade_item_id(name) for name in TRADE_ITEM_DEFS)


TRADE_LOCATION_DEMANDS = {
    "city_tianshu": {"trade_luxury": 0.98, "trade_contract": 1.18, "trade_ticket": 1.04},
    "city_qinglan": {"trade_luxury": 1.20, "trade_contract": 1.02, "trade_ticket": 0.90},
    "city_chixia": {"trade_luxury": 0.92, "trade_contract": 1.07, "trade_ticket": 1.20},
    "city_xuantie": {"trade_luxury": 1.21, "trade_contract": 0.91, "trade_ticket": 1.03},
    "city_wanyao": {"trade_luxury": 1.01, "trade_contract": 1.20, "trade_ticket": 0.96},
    "city_yunmeng": {"trade_luxury": 1.05, "trade_contract": 0.94, "trade_ticket": 1.19},
    "city_liusha": {"trade_luxury": 1.12, "trade_contract": 0.88, "trade_ticket": 1.21},
    "city_hanshuang": {"trade_luxury": 1.22, "trade_contract": 1.00, "trade_ticket": 0.89},
    "city_leize": {"trade_luxury": 0.97, "trade_contract": 1.22, "trade_ticket": 1.06},
    "city_bichao": {"trade_luxury": 0.93, "trade_contract": 1.08, "trade_ticket": 1.22},
    "city_xingyun": {"trade_luxury": 1.12, "trade_contract": 1.18, "trade_ticket": 1.00},
}


TRADE_FORBIDDEN_SPECIALTY_TYPES = {"药材", "丹材", "燃料", "纺织", "水产", "盐鲜", "香料"}
TRADE_GROUP_BY_TYPE = {
    "trade": "trade",
    "trade_luxury": "trade",
    "trade_contract": "trade",
    "trade_ticket": "trade",
}


def trade_group_for_type(trade_type: str) -> str:
    """当前跑商特产使用稳定规则组 trade；展示名仍叫纯经济。"""

    return TRADE_GROUP_BY_TYPE.get(trade_type, "")


SPECIAL_BUYER_DEFS = (
    ("buyer_zhenyaosi", "镇妖司", "loot_yao_1,loot_yao_2,loot_yao_3,loot_yao_4,loot_yao_5,loot_yao_6", 3.0, 4, 4),
    ("buyer_fumodian", "伏魔殿", "loot_mo_1,loot_mo_2,loot_mo_3,loot_mo_4,loot_mo_5,loot_mo_6", 3.0, -31, 21),
    ("buyer_guishi", "鬼市", "loot_gui_1,loot_gui_2,loot_gui_3,loot_gui_4,loot_gui_5,loot_gui_6", 3.0, 34, -17),
    ("buyer_longyuan", "龙渊阁", "loot_long_1,loot_long_2,loot_long_3", 3.0, 41, -35),
    ("buyer_wanshou", "万兽盟", "loot_shou_1,loot_shou_2,loot_shou_3,loot_shou_4,loot_shou_5,loot_shou_6", 2.5, -39, -12),
    ("buyer_pojun", "破军营", "loot_bing_1,loot_bing_2,loot_bing_3,loot_bing_4,loot_bing_5,loot_bing_6", 3.2, 22, 36),
)
SPECIAL_BUYERS = tuple(
    (name, item_ids, price_factor, x, y)
    for _location_id, name, item_ids, price_factor, x, y in SPECIAL_BUYER_DEFS
)
SPECIAL_BUYER_IDS_BY_NAME = {
    name: location_id
    for location_id, name, _item_ids, _price_factor, _x, _y in SPECIAL_BUYER_DEFS
}
SPECIAL_BUYER_NAMES_BY_ID = {
    location_id: name
    for location_id, name, _item_ids, _price_factor, _x, _y in SPECIAL_BUYER_DEFS
}


WAR_PREP_SEED = {
    "buyer_zhenyaosi": ("镇妖战备", "yao"),
    "buyer_fumodian": ("伏魔战备", "mo"),
    "buyer_guishi": ("阴契战备", "gui"),
    "buyer_longyuan": ("龙渊战备", "long"),
    "buyer_wanshou": ("驭兽战备", "shou"),
    "buyer_pojun": ("破军战备", "bing"),
}


RECYCLE_LOCATION_DEFS = (
    ("recycle_weapon", "weapon", "铸剑阁", 1.2, -12, 18, "专收探险所得备用武器，回收价稳定但受每日回收曲线影响。"),
    ("recycle_gem", "gem", "琢玉楼", 1.15, 17, 15, "专收未镶嵌宝石，擅长鉴定灵玉、拆解碎宝。"),
    ("recycle_book", "book", "藏经阁", 1.1, 3, 29, "专收未附魔技能书，负责整理残卷、术法和旧拓本。"),
)
RECYCLE_LOCATIONS = tuple(
    (recycle_type, name, price_factor, x, y, desc)
    for _location_id, recycle_type, name, price_factor, x, y, desc in RECYCLE_LOCATION_DEFS
)
RECYCLE_LOCATION_IDS_BY_NAME = {
    name: location_id
    for location_id, _recycle_type, name, _price_factor, _x, _y, _desc in RECYCLE_LOCATION_DEFS
}
RECYCLE_LOCATION_NAMES_BY_ID = {
    location_id: name
    for location_id, _recycle_type, name, _price_factor, _x, _y, _desc in RECYCLE_LOCATION_DEFS
}


EXPLORATION_LOCATIONS = (
    ("天枢城", 0, 0, 1, 1, 12, "城外浅野，适合刚入门的道友。"),
    ("青岚坊", 8, 22, 1, 1, 20, "新手常去的灵林。"),
    ("赤霞港", 31, -6, 10, 8, 28, "水火气息交错。"),
    ("玄铁岭", -28, 12, 20, 18, 45, "傀儡和矿脉并存。"),
    ("万药谷", -18, 32, 25, 20, 50, "药香浓重，妖兽不少。"),
    ("云梦泽", 18, -24, 30, 25, 55, "幻雾弥漫。"),
    ("流沙海市", -35, -18, 40, 35, 70, "风沙和妖物都不少。"),
    ("寒霜关", -3, 39, 50, 45, 80, "寒气极重，鬼物出没。"),
    ("雷泽城", 29, 24, 60, 55, 90, "雷兽和残阵密布。"),
    ("碧潮岛", 38, -32, 65, 60, 95, "水族和海兽盘踞。"),
    ("星陨墟", 5, -43, 75, 70, 100, "高等级探险地。"),
    ("太虚秘境", -6, -49, 90, 1, 100, "动态映身秘境，少量经验，主产1-8级宝石和全池武器。"),
)

SECRET_REALM_IDS_BY_NAME = {"太虚秘境": "realm_taixu"}
SECRET_REALM_NAMES_BY_ID = {value: key for key, value in SECRET_REALM_IDS_BY_NAME.items()}
SYSTEM_LOCATION_IDS_BY_NAME = {
    **TRADE_LOCATION_IDS_BY_NAME,
    **SECRET_REALM_IDS_BY_NAME,
    **SPECIAL_BUYER_IDS_BY_NAME,
    **RECYCLE_LOCATION_IDS_BY_NAME,
}
SYSTEM_LOCATION_NAMES_BY_ID = {
    **TRADE_LOCATION_NAMES_BY_ID,
    **SECRET_REALM_NAMES_BY_ID,
    **SPECIAL_BUYER_NAMES_BY_ID,
    **RECYCLE_LOCATION_NAMES_BY_ID,
}


def location_id_for_name(name: object) -> str:
    """读取系统保留地点稳定 id；荒地和宗门返回空串。"""

    return SYSTEM_LOCATION_IDS_BY_NAME.get(str(name or "").strip(), "")


def location_name_for_id(location_id: object) -> str:
    """读取系统保留地点当前显示名。"""

    return SYSTEM_LOCATION_NAMES_BY_ID.get(str(location_id or "").strip(), "")


WORLD_TERRAINS = {
    "city_tianshu": "城镇",
    "city_qinglan": "森林",
    "city_chixia": "港湾",
    "city_xuantie": "山岭",
    "city_wanyao": "药谷",
    "city_yunmeng": "水泽",
    "city_liusha": "荒漠",
    "city_hanshuang": "雪原",
    "city_leize": "雷泽",
    "city_bichao": "海岛",
    "city_xingyun": "遗迹",
    "realm_taixu": "秘境",
    "buyer_zhenyaosi": "城镇",
    "buyer_fumodian": "遗迹",
    "buyer_guishi": "阴市",
    "buyer_longyuan": "水泽",
    "buyer_wanshou": "草原",
    "buyer_pojun": "军营",
    "recycle_weapon": "山岭",
    "recycle_gem": "湖泽",
    "recycle_book": "城镇",
}


MONSTER_DEFS = (
    ("qinglang", "青狼妖", 5, "妖", 90, 15, 8, "loot_yao_2", 0.45),
    ("huyao", "狐妖", 8, "妖", 120, 18, 10, "loot_yao_3", 0.42),
    ("shanzhu", "山猪兽", 12, "兽", 160, 24, 12, "loot_shou_2", 0.4),
    ("baigui", "白骨鬼", 16, "鬼", 190, 29, 16, "loot_gui_4", 0.38),
    ("shayan", "沙魇", 18, "妖", 210, 32, 18, "loot_yao_5", 0.35),
    ("mopi_jiang", "魔皮将", 24, "魔", 290, 40, 24, "loot_mo_4", 0.36),
    ("xuanling", "玄铁傀", 28, "傀", 360, 46, 32, "loot_bing_2", 0.35),
    ("guijiang", "鬼火将", 32, "鬼", 400, 54, 34, "loot_gui_2", 0.38),
    ("hanpo", "寒魄鬼", 38, "鬼", 480, 62, 42, "loot_gui_1", 0.4),
    ("tiejia_bing", "铁甲残兵", 44, "兵", 560, 74, 48, "loot_bing_2", 0.36),
    ("leishou", "雷兽", 52, "兽", 720, 88, 55, "loot_shou_1", 0.35),
    ("yaotong_niao", "妖瞳鸦", 58, "妖", 790, 98, 60, "loot_yao_5", 0.34),
    ("jiaolong", "蛟龙残影", 68, "龙", 980, 120, 70, "loot_long_1", 0.32),
    ("longxu_ying", "龙须影", 74, "龙", 1120, 138, 78, "loot_long_2", 0.3),
    ("mohun", "魔魂将", 82, "魔", 1300, 160, 88, "loot_mo_1", 0.36),
    ("moyan_shi", "魔焰使", 88, "魔", 1480, 185, 96, "loot_mo_6", 0.32),
    ("pojun", "破军残将", 95, "兵", 1700, 210, 110, "loot_bing_1", 0.3),
    ("duanren_jiang", "断刃军魂", 100, "兵", 1900, 235, 122, "loot_bing_6", 0.28),
)


WEAPON_SKILLS = (
    ("liuguang", "流光刺", "高速穿刺，命中稳定，适合轻快剑路。", 9, 4, 1.14),
    ("qiankun", "乾坤震", "法器镇压，单次沉重，并扰乱行动条。", 16, 7, 1.50),
    ("tianji", "天机扣弦", "玉令牵机，压低对手行动节奏。", 9, 4, 1.12),
    ("fengren", "风刃斩", "低耗快斩，命中稳定，单次伤害不极端。", 6, 3, 1.08),
    ("wuxiang", "无相剑气", "慢蓄高伤，适合稳定收割。", 15, 6, 1.50),
    ("lanzhao", "岚照回旋", "飞刃回旋，多段游斗并轻微打断。", 7, 3, 1.06),
    ("chixia", "赤霞燃斩", "赤霞燃刃，给敌人留下灼烧。", 9, 4, 1.16),
    ("chaohuo", "潮火贯日", "火潮贯穿，兼具穿透与灼烧。", 12, 5, 1.32),
    ("yanbei", "炎贝连弩", "远程连射，命中稳定，适合多段压血。", 11, 4, 1.14),
    ("bengshan", "崩山击", "重兵破甲，单次沉重但节奏偏慢。", 11, 5, 1.42),
    ("zhenyue", "镇岳压", "重斧镇压，伤害高并短暂护身。", 14, 6, 1.42),
    ("heiyao", "黑曜格挡", "盾刃格挡后反击，攻守都稳。", 9, 5, 1.10),
    ("huichun", "回春刺", "藤杖回春，造成伤害后回复血气。", 7, 5, 1.02),
    ("lingfeng", "灵蜂针", "蜂针急刺，高频吸血，单次偏轻。", 6, 3, 1.02),
    ("yaowang", "药王拂尘", "拂尘引药气，长战续航更稳。", 10, 5, 1.08),
    ("duannian", "断念击", "断念入梦，伤害并削弱精神。", 10, 5, 1.16),
    ("mengwu", "梦雾摄心", "梦雾摄心，压精神并扰乱行动。", 9, 4, 1.10),
    ("shuijing", "水镜回剑", "镜光折返，命中和闪避都更稳。", 8, 4, 1.12),
    ("shaying", "沙影连斩", "沙影双斩，连击频繁但单段偏轻。", 7, 3, 1.05),
    ("jueying", "绝影刺", "绝影高速刺击，出手后身形更活。", 9, 4, 1.16),
    ("duyun", "毒云蚀骨", "毒云蚀骨，灼烧和流血持续压血。", 10, 5, 1.20),
    ("xueying", "血影割", "血影割裂，伤害后吸血。", 9, 4, 1.12),
    ("liehun", "裂魂音", "铃音裂魂，压制敌方精神。", 10, 5, 1.18),
    ("yueshi", "月蚀斩", "月蚀斩落，伤害并压低防御。", 11, 5, 1.28),
    ("pojun", "破军刺", "破军突进，高穿透单体伤害。", 12, 5, 1.36),
    ("leiguang", "雷光乱刃", "雷光乱闪，高频打断行动条。", 8, 3, 1.08),
    ("zidian", "紫电裂山", "紫电裂山，重击爆发并破防。", 15, 6, 1.48),
    ("xuandun", "玄盾击", "玄龟护身，出手后获得护身。", 8, 5, 1.08),
    ("duanhai", "断海劈", "断海一击，单次爆发很高。", 13, 5, 1.38),
    ("chaoxi", "潮汐牵引", "潮汐牵引，拖慢敌人节奏。", 10, 5, 1.16),
    ("dansha", "丹砂点火", "丹砂点火，快速附加灼烧。", 8, 4, 1.10),
    ("zhuyan", "朱焰断浪", "朱焰断浪，火势越燃越重。", 12, 5, 1.30),
    ("luxin", "炉心崩火", "炉心崩火，慢速重击并附加灼烧。", 15, 6, 1.46),
    ("qingteng", "青藤缠刺", "青藤缠刺，轻微吸血并扰乱行动。", 7, 4, 1.04),
    ("lingmu", "灵木回环", "灵木回环，护身和续航兼具。", 9, 5, 1.06),
    ("luming", "鹿鸣突阵", "鹿鸣突阵，穿透并冲散敌势。", 12, 5, 1.30),
    ("jinghu", "镜湖回剑", "镜湖回剑，命中稳定并提高闪避。", 8, 4, 1.12),
    ("qingxin", "清心定铃", "清心定铃，扰神并稳住自身承伤。", 9, 4, 1.08),
    ("yingyue", "映月镇潮", "映月镇潮，慢速法器压制。", 15, 6, 1.44),
    ("youhuang", "幽篁清音", "幽篁清音，命中稳定并扰乱心神。", 8, 4, 1.08),
    ("mozhu", "墨竹点影", "墨竹点影，连击中带流血。", 9, 4, 1.14),
    ("yingye", "影叶截脉", "影叶截脉，高频打断并附带流血。", 8, 3, 1.06),
    ("zhuixing", "追星连弩", "远程多段点杀，命中稳定。", 11, 4, 1.16),
    ("chuanyun", "穿云破", "灵枪穿云，高穿透稳定伤害。", 12, 5, 1.34),
    ("xingluo", "星落", "星辉多段落下，长战贡献高。", 13, 6, 1.36),
    ("yujing", "玉京敕剑", "玉京敕令入剑，命中和穿透都稳。", 10, 4, 1.20),
    ("tianxiang", "天香护铃", "天香护身，低伤但续航更稳。", 9, 5, 1.06),
    ("jinlu", "金缕封天", "金缕封天，沉重法器压制。", 16, 7, 1.48),
    ("heishui", "黑水潜刺", "潜刺带血，出手后身形更难捉。", 8, 3, 1.08),
    ("duhun", "渡魂照影", "渡魂照影，吸取血气并压精神。", 10, 5, 1.12),
    ("wumu", "乌木沉舟", "乌木沉舟，盾刃护身并撞乱节奏。", 10, 5, 1.14),
    ("langhao", "狼毫游猎", "狼毫游猎，轻快连击且命中稳定。", 7, 3, 1.06),
    ("shouhun", "兽魂震铃", "兽魂震铃，扰乱行动并稳住承伤。", 9, 4, 1.12),
    ("lingjiao", "灵角破阵", "灵角破阵，战戟穿透并爆发。", 13, 5, 1.38),
    ("xingheng", "星衡拂尘", "星衡落辉，长战贡献稳定。", 12, 5, 1.24),
    ("qingzhu_dun", "青竹回守", "青竹借势，护身后可反打。", 8, 5, 1.06),
    ("yandu", "焰毒缠刃", "焰毒缠刃，灼烧和流血一并压血。", 10, 5, 1.18),
    ("fanyue", "返岳震", "山岳回震，受击后借势反击。", 12, 6, 1.28),
    ("fengwang", "蜂王镇音", "蜂王振音，吸血并扰乱精神。", 8, 4, 1.06),
    ("nimeng", "溺梦照影", "溺梦照影，压精神并拖慢行动。", 10, 5, 1.12),
    ("shajin", "沙烬割", "沙烬割裂，残火与流血并行。", 9, 4, 1.14),
    ("hanyan", "寒焰拂", "寒焰拂尘，冷火附骨并持续流血。", 11, 5, 1.16),
    ("leihou", "雷吼格", "雷吼格挡，护身反震并扰乱节奏。", 10, 5, 1.12),
    ("cangming", "沧溟破潮", "沧溟破潮，长战破阵贡献更高。", 13, 5, 1.34),
    ("chilian", "赤炼毒火", "赤炼毒火，灼烧流血兼具但节奏偏沉。", 12, 5, 1.22),
    ("guigen", "归根守", "归根守势，护身续航并可反击。", 9, 5, 1.08),
    ("yuehen", "月痕潜刺", "月痕潜刺，闪身扰乱后收割残血。", 8, 3, 1.08),
    ("zhupo", "竹魄断神", "竹魄入梦，削精神并降低防势。", 10, 5, 1.14),
    ("yunxing", "陨星定盘", "陨星定盘，沉重镇压并适合首领长战。", 16, 7, 1.46),
    ("zhuxie", "诛邪贯阵", "诛邪贯阵，高穿透并偏向终段爆发。", 13, 5, 1.36),
    ("chenyuan", "沉渊血火", "沉渊血火，潜流灼血，拖得越久越痛。", 11, 5, 1.20),
    ("guming", "骨鸣反阵", "骨鸣反阵，护身反击并稳住承伤。", 11, 5, 1.16),
)


WEAPON_DEFS = (
    ("liuguang_xijian", "流光细剑", "天枢城", 28, "liuguang", "剑"),
    ("qiankun_pan", "乾坤盘", "天枢城", 45, "qiankun", "盘"),
    ("tianji_yuling", "天机玉令", "天枢城", 24, "tianji", "铃"),
    ("xingheng_fuchen", "星衡拂尘", "天枢城", 31, "xingheng", "拂尘"),
    ("qinglan_duanjian", "青岚短剑", "青岚坊", 18, "fengren", "剑"),
    ("wuxiang_zhujian", "无相竹剑", "青岚坊", 27, "wuxiang", "剑"),
    ("lanzhao_feiren", "岚照飞刃", "青岚坊", 22, "lanzhao", "飞刃"),
    ("qingzhu_dunren", "青竹盾刃", "青岚坊", 24, "qingzhu_dun", "盾刃"),
    ("chixia_duandao", "赤霞短刀", "赤霞港", 24, "chixia", "刀"),
    ("chaohuo_qiang", "潮火枪", "赤霞港", 34, "chaohuo", "枪"),
    ("yanbei_nu", "炎贝弩", "赤霞港", 30, "yanbei", "弩"),
    ("yandu_wandao", "焰毒弯刀", "赤霞港", 29, "yandu", "刀"),
    ("xuantie_zhongji", "玄铁重戟", "玄铁岭", 36, "bengshan", "戟"),
    ("zhenyue_fu", "镇岳斧", "玄铁岭", 40, "zhenyue", "斧"),
    ("heiyao_dunren", "黑曜盾刃", "玄铁岭", 30, "heiyao", "盾刃"),
    ("fanyue_pan", "返岳盘", "玄铁岭", 39, "fanyue", "盘"),
    ("wanyao_tengzhang", "万药藤杖", "万药谷", 16, "huichun", "杖"),
    ("lingfeng_bi", "灵蜂匕", "万药谷", 20, "lingfeng", "匕"),
    ("yaowang_fuchen", "药王拂尘", "万药谷", 26, "yaowang", "拂尘"),
    ("fengwang_ling", "蜂王铃", "万药谷", 22, "fengwang", "铃"),
    ("duannian_zhang", "断念杖", "云梦泽", 23, "duannian", "杖"),
    ("mengwu_ling", "梦雾铃", "云梦泽", 21, "mengwu", "铃"),
    ("shuijing_jian", "水镜剑", "云梦泽", 29, "shuijing", "剑"),
    ("nimeng_deng", "溺梦灯", "云梦泽", 27, "nimeng", "铃"),
    ("liusha_feiren", "流沙飞刃", "流沙海市", 20, "shaying", "飞刃"),
    ("jueying_feijian", "绝影飞剑", "流沙海市", 32, "jueying", "剑"),
    ("duyun_wandao", "毒云弯刀", "流沙海市", 31, "duyun", "刀"),
    ("shajin_dao", "沙烬刀", "流沙海市", 28, "shajin", "刀"),
    ("xuehe_bi", "血河匕", "寒霜关", 28, "xueying", "匕"),
    ("zhenhun_ling", "镇魂铃", "寒霜关", 21, "liehun", "铃"),
    ("yueshi_wandao", "月蚀弯刀", "寒霜关", 32, "yueshi", "刀"),
    ("hanyan_fuchen", "寒焰拂尘", "寒霜关", 30, "hanyan", "拂尘"),
    ("pojun_qiang", "破军枪", "雷泽城", 38, "pojun", "枪"),
    ("leiguang_duanren", "雷光短刃", "雷泽城", 23, "leiguang", "匕"),
    ("zidian_fu", "紫电斧", "雷泽城", 42, "zidian", "斧"),
    ("leihou_dunren", "雷吼盾刃", "雷泽城", 32, "leihou", "盾刃"),
    ("xuangui_dunren", "玄龟盾刃", "碧潮岛", 25, "xuandun", "盾刃"),
    ("duanhai_jian", "断海剑", "碧潮岛", 33, "duanhai", "剑"),
    ("chaoxi_fuchen", "潮汐拂尘", "碧潮岛", 27, "chaoxi", "拂尘"),
    ("cangming_ji", "沧溟战戟", "碧潮岛", 36, "cangming", "戟"),
    ("dansha_feiren", "丹砂飞刃", "赤霞港", 21, "dansha", "飞刃"),
    ("zhuyan_dao", "朱焰刀", "赤霞港", 33, "zhuyan", "刀"),
    ("luxin_fu", "炉心斧", "玄铁岭", 39, "luxin", "斧"),
    ("chilian_wandao", "赤炼弯刀", "赤霞港", 30, "chilian", "刀"),
    ("qingteng_bi", "青藤匕", "青岚坊", 19, "qingteng", "匕"),
    ("lingmu_zhang", "灵木杖", "万药谷", 25, "lingmu", "杖"),
    ("luming_qiang", "鹿鸣枪", "万药谷", 34, "luming", "枪"),
    ("guigen_dunren", "归根盾刃", "雷泽城", 27, "guigen", "盾刃"),
    ("jinghu_xijian", "镜湖细剑", "云梦泽", 26, "jinghu", "剑"),
    ("qingxin_ling", "清心铃", "天枢城", 21, "qingxin", "铃"),
    ("yingyue_pan", "映月盘", "碧潮岛", 38, "yingyue", "盘"),
    ("yuehen_bi", "月痕匕", "寒霜关", 23, "yuehen", "匕"),
    ("youhuang_ling", "幽篁竹铃", "青岚坊", 20, "youhuang", "铃"),
    ("mozhu_jian", "墨竹剑", "青岚坊", 28, "mozhu", "剑"),
    ("yingye_feiren", "影叶飞刃", "流沙海市", 22, "yingye", "飞刃"),
    ("zhupo_zhang", "竹魄杖", "万药谷", 25, "zhupo", "杖"),
    ("zhuixing_nu", "追星弩", "星陨墟", 29, "zhuixing", "弩"),
    ("chuanyun_lingqiang", "穿云灵枪", "星陨墟", 37, "chuanyun", "枪"),
    ("xingluo_fachen", "星落拂尘", "星陨墟", 39, "xingluo", "拂尘"),
    ("yunxing_pan", "陨星盘", "星陨墟", 43, "yunxing", "盘"),
    ("yujing_fujian", "玉京符剑", "天枢城", 30, "yujing", "剑"),
    ("tianxiang_ling", "天香铃", "天枢城", 23, "tianxiang", "铃"),
    ("jinlu_pan", "金缕天盘", "星陨墟", 44, "jinlu", "盘"),
    ("zhuxie_qiang", "诛邪枪", "星陨墟", 36, "zhuxie", "枪"),
    ("heishui_bi", "黑水匕", "云梦泽", 22, "heishui", "匕"),
    ("duhun_deng", "渡魂灯", "云梦泽", 26, "duhun", "铃"),
    ("wumu_dunren", "乌木盾刃", "碧潮岛", 31, "wumu", "盾刃"),
    ("chenyuan_dao", "沉渊刀", "寒霜关", 30, "chenyuan", "刀"),
    ("langhao_feiren", "狼毫飞刃", "流沙海市", 20, "langhao", "飞刃"),
    ("shouhun_ling", "兽魂铃", "雷泽城", 24, "shouhun", "铃"),
    ("lingjiao_ji", "灵角战戟", "玄铁岭", 37, "lingjiao", "戟"),
    ("guming_dunren", "骨鸣盾刃", "玄铁岭", 31, "guming", "盾刃"),
)


WEAPON_ENCHANTS = (
    ("fengren_shu", "风刃书", {"hit_bonus": 0.10, "interval_delta": -1, "skill_power_bonus": -0.08}, 1),
    ("shaying_shu", "沙影书", {"combo_bonus": 0.12, "combo_damage_bonus": -0.08}, 1),
    ("liuguang_shu", "流光书", {"interval_delta": -1, "single_hit_bonus": -0.06}, 2),
    ("zhuixing_shu", "追星书", {"combo_bonus": 0.10, "hit_bonus": 0.04, "skill_power_bonus": -0.07}, 2),
    ("poxie_shu", "破甲书", {"pierce_bonus": 0.09, "interval_delta": 1}, 2),
    ("bengshan_shu", "崩山书", {"heavy_bonus": 0.14, "interval_delta": 1}, 4),
    ("chuanyun_shu", "穿云书", {"pierce_bonus": 0.12, "single_hit_bonus": 0.06}, 5),
    ("zhenyue_shu", "镇岳书", {"damage_reduce": 0.08, "heavy_bonus": 0.08, "interval_delta": 1}, 3),
    ("zhuoxin_shu", "灼心书", {"burn_rate": 0.16, "skill_power_bonus": -0.08}, 2),
    ("xueyu_shu", "血雨书", {"bleed_rate": 0.16, "damage_reduce": -0.03}, 2),
    ("duyun_shu", "毒云书", {"burn_rate": 0.10, "bleed_rate": 0.10, "skill_power_bonus": -0.10}, 3),
    ("canyan_shu", "残焰书", {"burn_rate": 0.08, "single_hit_bonus": 0.08, "interval_delta": 1}, 3),
    ("duannian_shu", "断念书", {"mp_suppress": 0.12, "skill_power_bonus": -0.06}, 2),
    ("zhenhun_shu", "镇魂书", {"mp_suppress": 0.10, "stun_rate": 0.08, "skill_power_bonus": -0.10}, 3),
    ("tianji_shu", "天机书", {"stun_rate": 0.12, "interval_delta": 1}, 2),
    ("mengwu_shu", "梦雾书", {"mp_suppress": 0.08, "defense_suppress": 0.05, "single_hit_bonus": -0.06}, 2),
    ("huichun_shu", "回春书", {"life_steal": 0.05, "skill_power_bonus": -0.08}, 2),
    ("xuandun_shu", "玄盾书", {"shield_bonus": 0.12, "interval_delta": 1}, 2),
    ("xueqi_shu", "血契书", {"life_steal": 0.09, "damage_reduce": -0.04}, 3),
    ("lingmu_shu", "灵木书", {"damage_reduce": 0.06, "life_steal": 0.04, "skill_power_bonus": -0.12}, 3),
    ("fanzhen_shu", "反震书", {"counter_rate": 0.14, "skill_power_bonus": -0.08}, 2),
    ("guiren_shu", "归刃书", {"counter_rate": 0.10, "shield_bonus": 0.10, "interval_delta": 1}, 3),
    ("jieshi_shu", "借势书", {"counter_rate": 0.22, "damage_reduce": -0.04}, 2),
    ("xuanyao_shu", "玄曜书", {"counter_rate": 0.16, "damage_reduce": 0.05, "single_hit_bonus": -0.08}, 4),
    ("wuxiang_shu", "无相书", {"skill_power_bonus": 0.16, "interval_delta": 1}, 5),
    ("duanhai_shu", "断海书", {"single_hit_bonus": 0.16, "interval_delta": 1}, 4),
    ("jueying_shu", "绝影书", {"dodge_bonus": 0.05, "single_hit_bonus": 0.05, "skill_power_bonus": -0.08}, 3),
    ("pojun_shu", "破军书", {"pierce_bonus": 0.08, "single_hit_bonus": 0.10, "interval_delta": 1}, 4),
    ("xingluo_shu", "星落书", {"combo_bonus": 0.06, "combo_damage_bonus": 0.18, "damage_reduce": -0.02}, 5),
    ("qiankun_shu", "乾坤书", {"stun_rate": 0.10, "damage_reduce": 0.05, "interval_delta": 1}, 5),
    ("pozhen_shu", "破阵书", {"pierce_bonus": 0.10, "defense_suppress": 0.06, "interval_delta": 1}, 5),
    ("yujing_shu", "玉京书", {"hit_bonus": 0.06, "skill_power_bonus": 0.08}, 6),
    ("yueshi_shu", "月蚀书", {"defense_suppress": 0.08, "skill_power_bonus": -0.05}, 3),
    ("jinghu_shu", "镜湖书", {"dodge_bonus": 0.04, "hit_bonus": 0.05, "single_hit_bonus": -0.08}, 3),
    ("yingye_shu", "影叶书", {"stun_rate": 0.08, "bleed_rate": 0.08, "skill_power_bonus": -0.10}, 3),
    ("qingxin_shu", "清心书", {"mp_suppress": 0.10, "damage_reduce": 0.04, "single_hit_bonus": -0.08}, 3),
)


class XiuxianDB:
    """修仙玩法数据库访问对象。"""

    def __init__(self, db_path: str | Path = "xiuxian.db") -> None:
        self.db_path = Path(db_path)
        self.conn: sqlite3.Connection | None = None
        self.initialized = False
        self.lock = RLock()

    def init(self) -> None:
        """连接数据库；已有库 schema 不匹配时拒绝启动，绝不自动清表。"""

        with self.lock:
            if self.conn is None:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self.conn.row_factory = sqlite3.Row
                self.conn.execute("PRAGMA foreign_keys = ON")
                self.initialized = False

            if self.initialized:
                return

            current_version = self._current_schema_version()
            if current_version != SCHEMA_VERSION:
                if current_version is None and not self._has_existing_tables():
                    pass
                else:
                    raise RuntimeError(
                        f"修仙数据库版本不匹配：current={current_version}, target={SCHEMA_VERSION}。"
                        "请先更换为最新数据库，服务端不会自动重建旧库。"
                    )
            self._create_tables()
            self._seed_data()
            self._apply_active_world_skin()
            self._validate_seed_data()
            self._set_schema_version()
            clear_runtime_caches(reason="db_initialized")
            self.initialized = True

    def close(self) -> None:
        """关闭数据库连接。"""

        with self.lock:
            if self.conn is not None:
                self.conn.close()
                self.conn = None
                self.initialized = False

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        """执行写入 SQL 并提交。"""

        with self.lock:
            self.init()
            assert self.conn is not None
            cursor = self.conn.execute(sql, tuple(params))
            self.conn.commit()
            return cursor

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        """批量执行写入 SQL 并提交。"""

        with self.lock:
            self.init()
            assert self.conn is not None
            self.conn.executemany(sql, rows)
            self.conn.commit()

    def fetch_one(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        """查询一条记录。"""

        with self.lock:
            self.init()
            assert self.conn is not None
            row = self.conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None

    def fetch_all(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        """查询多条记录。"""

        with self.lock:
            self.init()
            assert self.conn is not None
            rows = self.conn.execute(sql, tuple(params)).fetchall()
            return [dict(row) for row in rows]

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """提供事务上下文；用于扣钱和发货这类原子操作。"""

        with self.lock:
            self.init()
            assert self.conn is not None
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def _current_schema_version(self) -> int | None:
        """读取当前 schema 版本。"""

        assert self.conn is not None
        exists = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if not exists:
            return None
        row = self.conn.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
        if not row:
            return None
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return None

    def _has_existing_tables(self) -> bool:
        """判断数据库是否已经有业务表；空库可初始化，有旧表直接中止。"""

        assert self.conn is not None
        row = self.conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            LIMIT 1
            """
        ).fetchone()
        return bool(row)

    def _set_schema_version(self) -> None:
        """写入当前 schema 版本。"""

        assert self.conn is not None
        self.conn.execute(
            """
            INSERT INTO schema_meta (key, value)
            VALUES ('version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(SCHEMA_VERSION),),
        )
        self.conn.commit()

    def _create_tables(self) -> None:
        """创建正式落地表。"""

        assert self.conn is not None
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS world_skin_active (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                skin_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                desc TEXT NOT NULL DEFAULT '',
                switched_by TEXT NOT NULL DEFAULT '',
                switched_at TEXT NOT NULL,
                snapshot_id INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS world_skin_snapshots (
                snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                skin_id TEXT NOT NULL,
                version TEXT NOT NULL DEFAULT '',
                payload TEXT NOT NULL DEFAULT '{}',
                created_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS quality_labels (
                quality_key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS currency_labels (
                currency_key TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS player_level_labels (
                level INTEGER PRIMARY KEY,
                label TEXT NOT NULL,
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS physique_defs (
                physique_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                grade TEXT NOT NULL,
                kind TEXT NOT NULL,
                level INTEGER NOT NULL,
                physique_value INTEGER NOT NULL,
                effect TEXT NOT NULL DEFAULT '{}',
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS players (
                client_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                exp INTEGER NOT NULL DEFAULT 0,
                hp INTEGER NOT NULL DEFAULT 100,
                max_hp INTEGER NOT NULL DEFAULT 100,
                mp INTEGER NOT NULL DEFAULT 60,
                max_mp INTEGER NOT NULL DEFAULT 60,
                physique_id TEXT NOT NULL DEFAULT 'fanti',
                physique_value INTEGER NOT NULL DEFAULT 0,
                base_attack INTEGER NOT NULL DEFAULT 5,
                defense INTEGER NOT NULL DEFAULT 0,
                raw_stones INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT '空闲',
                rest_full_at TEXT,
                rest_window_started_at TEXT,
                rest_window_hp INTEGER NOT NULL DEFAULT 0,
                rest_window_mp INTEGER NOT NULL DEFAULT 0,
                rest_window_elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                location_name TEXT NOT NULL DEFAULT '天枢城',
                location_id TEXT NOT NULL DEFAULT 'city_tianshu',
                x INTEGER NOT NULL DEFAULT 0,
                y INTEGER NOT NULL DEFAULT 0,
                backpack_limit INTEGER NOT NULL DEFAULT 80,
                weight_limit INTEGER NOT NULL DEFAULT 500,
                auto_use_medicine INTEGER NOT NULL DEFAULT 1,
                battle_log_detail INTEGER NOT NULL DEFAULT 0,
                last_sign_date TEXT,
                newbie_claimed INTEGER NOT NULL DEFAULT 0,
                last_rename_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_groups (
                group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                primary_player_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_identities (
                identity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                client_id TEXT NOT NULL UNIQUE,
                is_primary INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(group_id) REFERENCES user_groups(group_id)
            );

            CREATE TABLE IF NOT EXISTS user_group_login_challenges (
                challenge_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL UNIQUE,
                player_id TEXT,
                confirmed_at TEXT,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_group_sessions (
                session_id TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_group_bind_codes (
                code TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                used_by_client_id TEXT,
                used_at TEXT,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bank_accounts (
                client_id TEXT PRIMARY KEY,
                star_level INTEGER NOT NULL DEFAULT 1,
                balance INTEGER NOT NULL DEFAULT 0,
                last_settle_at TEXT NOT NULL,
                last_interest_day TEXT,
                daily_interest_claimed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS backpack_items (
                client_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS ring_items (
                client_id TEXT NOT NULL,
                ring_item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, ring_item_id)
            );

            CREATE TABLE IF NOT EXISTS gem_items (
                client_id TEXT NOT NULL,
                gem_id TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, gem_id, level)
            );

            CREATE TABLE IF NOT EXISTS vault_items (
                client_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                item_id TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                quantity INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (client_id, item_type, item_id, level)
            );

            CREATE TABLE IF NOT EXISTS vault_weapons (
                client_id TEXT NOT NULL,
                weapon_id INTEGER NOT NULL PRIMARY KEY,
                stored_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS item_defs (
                item_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                quality TEXT NOT NULL,
                weight INTEGER NOT NULL DEFAULT 1,
                stack_limit INTEGER NOT NULL DEFAULT 99,
                tradeable INTEGER NOT NULL DEFAULT 0,
                usable INTEGER NOT NULL DEFAULT 0,
                base_price INTEGER NOT NULL DEFAULT 0,
                effect TEXT NOT NULL DEFAULT '{}',
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS ring_item_defs (
                ring_item_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                category_key TEXT NOT NULL,
                quality TEXT NOT NULL,
                usable INTEGER NOT NULL DEFAULT 0,
                target_type TEXT NOT NULL DEFAULT '玩家',
                effect TEXT NOT NULL DEFAULT '{}',
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS wish_pools (
                pool_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                cost_token_id TEXT NOT NULL,
                cost_token_quantity INTEGER NOT NULL DEFAULT 1,
                desc TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wish_prizes (
                prize_id TEXT PRIMARY KEY,
                pool_id TEXT NOT NULL,
                reward_type TEXT NOT NULL,
                reward_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                weight INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                payload_json TEXT NOT NULL DEFAULT '{}',
                desc TEXT NOT NULL DEFAULT '',
                FOREIGN KEY (pool_id) REFERENCES wish_pools(pool_id)
            );

            CREATE TABLE IF NOT EXISTS wish_draw_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                pool_id TEXT NOT NULL,
                prize_id TEXT NOT NULL,
                reward_type TEXT NOT NULL,
                reward_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                cost_token_id TEXT NOT NULL,
                cost_token_quantity INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wish_user_vouchers (
                player_id TEXT NOT NULL,
                voucher_key TEXT NOT NULL,
                display_name TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (player_id, voucher_key)
            );

            CREATE TABLE IF NOT EXISTS second_hand_listings (
                listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
                seller_id TEXT NOT NULL UNIQUE,
                item_type TEXT NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS second_hand_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                buyer_id TEXT NOT NULL,
                seller_id TEXT NOT NULL,
                item_type TEXT NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                fee INTEGER NOT NULL,
                seller_seen_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS world_locations (
                location_id TEXT PRIMARY KEY,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                terrain TEXT NOT NULL,
                features TEXT NOT NULL DEFAULT '[]',
                reserved INTEGER NOT NULL DEFAULT 0,
                desc TEXT NOT NULL DEFAULT '',
                UNIQUE(x, y),
                UNIQUE(name)
            );

            CREATE TABLE IF NOT EXISTS sects (
                sect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                location_name TEXT NOT NULL UNIQUE,
                location_x INTEGER NOT NULL,
                location_y INTEGER NOT NULL,
                founder_id TEXT NOT NULL UNIQUE,
                master_client_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                UNIQUE(location_x, location_y)
            );

            CREATE TABLE IF NOT EXISTS sect_members (
                client_id TEXT PRIMARY KEY,
                sect_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT '成员',
                joined_at TEXT NOT NULL,
                UNIQUE(sect_id, client_id)
            );

            CREATE TABLE IF NOT EXISTS sect_stats (
                sect_id INTEGER PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 1,
                exp INTEGER NOT NULL DEFAULT 0,
                influence_merit INTEGER NOT NULL DEFAULT 0,
                support_merit INTEGER NOT NULL DEFAULT 0,
                build_merit INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sect_merit_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sect_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                category TEXT NOT NULL,
                amount INTEGER NOT NULL,
                exp_gain INTEGER NOT NULL DEFAULT 0,
                source TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sect_war_cycles (
                cycle_start TEXT PRIMARY KEY,
                cycle_end TEXT NOT NULL,
                rewards_generated INTEGER NOT NULL DEFAULT 0,
                generated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sect_influence_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sect_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                action TEXT NOT NULL,
                influence INTEGER NOT NULL,
                item_value INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0,
                cycle_start TEXT NOT NULL,
                cycle_end TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(sect_id, cycle_start)
            );

            CREATE TABLE IF NOT EXISTS sect_war_rewards (
                reward_id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_start TEXT NOT NULL,
                cycle_end TEXT NOT NULL,
                sect_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                reward_type TEXT NOT NULL DEFAULT 'sect_random',
                ring_item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 1,
                claimed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                claimed_at TEXT,
                UNIQUE(cycle_start, client_id, reward_type, ring_item_id)
            );

            CREATE TABLE IF NOT EXISTS sect_contribution_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                sect_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                influence INTEGER NOT NULL,
                item_value INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0,
                cycle_start TEXT NOT NULL,
                cycle_end TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(sect_id, client_id, cycle_start)
            );

            CREATE TABLE IF NOT EXISTS trade_locations (
                location_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                specialties TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_goods (
                item_id TEXT PRIMARY KEY,
                home_location TEXT NOT NULL,
                home_location_id TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS trade_prices (
                location_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                buy_price INTEGER NOT NULL,
                sell_price INTEGER NOT NULL,
                business_day TEXT NOT NULL,
                PRIMARY KEY (location_id, item_id, business_day)
            );

            CREATE TABLE IF NOT EXISTS trade_heat (
                location_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                business_day TEXT NOT NULL,
                buy_count INTEGER NOT NULL DEFAULT 0,
                sell_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (location_id, item_id, business_day)
            );

            CREATE TABLE IF NOT EXISTS city_world_states (
                location_id TEXT PRIMARY KEY,
                location_name TEXT NOT NULL,
                city_level INTEGER NOT NULL DEFAULT 1,
                build_exp INTEGER NOT NULL DEFAULT 0,
                medicine_material INTEGER NOT NULL DEFAULT 0,
                medicine_catalyst INTEGER NOT NULL DEFAULT 0,
                medicine_fuel INTEGER NOT NULL DEFAULT 0,
                medicine_guard INTEGER NOT NULL DEFAULT 0,
                life_food INTEGER NOT NULL DEFAULT 0,
                life_salt INTEGER NOT NULL DEFAULT 0,
                life_water INTEGER NOT NULL DEFAULT 0,
                life_cloth INTEGER NOT NULL DEFAULT 0,
                life_fuel INTEGER NOT NULL DEFAULT 0,
                relic_energy INTEGER NOT NULL DEFAULT 0,
                last_settled_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS world_material_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                item_id TEXT NOT NULL,
                item_name TEXT NOT NULL,
                category TEXT NOT NULL,
                category_key TEXT NOT NULL DEFAULT '',
                subtype TEXT NOT NULL,
                subtype_key TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL,
                stones INTEGER NOT NULL,
                state_delta TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS treasure_maps (
                map_id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_name TEXT NOT NULL,
                city_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                x INTEGER,
                y INTEGER,
                current_price INTEGER NOT NULL DEFAULT 0,
                highest_bidder TEXT NOT NULL DEFAULT '',
                bid_count INTEGER NOT NULL DEFAULT 0,
                weapon_def_id TEXT NOT NULL DEFAULT '',
                weapon_name TEXT NOT NULL DEFAULT '',
                weapon_max_level INTEGER NOT NULL DEFAULT 0,
                owner_client_id TEXT NOT NULL DEFAULT '',
                owner_sect_id INTEGER NOT NULL DEFAULT 0,
                generated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                settled_at TEXT,
                result TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS treasure_map_bids (
                bid_id INTEGER PRIMARY KEY AUTOINCREMENT,
                map_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                amount INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS war_prep_states (
                location_id TEXT PRIMARY KEY,
                buyer_name TEXT NOT NULL,
                prep_name TEXT NOT NULL,
                loot_subtype TEXT NOT NULL,
                prep_value INTEGER NOT NULL DEFAULT 0,
                threshold INTEGER NOT NULL DEFAULT 900,
                pending INTEGER NOT NULL DEFAULT 0,
                pending_at TEXT,
                last_opened_at TEXT,
                last_settled_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                action TEXT NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                fee INTEGER NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                business_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_daily_rewards (
                client_id TEXT NOT NULL,
                business_day TEXT NOT NULL,
                sell_quantity INTEGER NOT NULL,
                net_profit INTEGER NOT NULL,
                reward INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (client_id, business_day)
            );

            CREATE TABLE IF NOT EXISTS trade_buy_locks (
                client_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL,
                last_buy_at TEXT NOT NULL,
                last_buy_price INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, item_id, location_id)
            );

            CREATE TABLE IF NOT EXISTS special_buyers (
                location_id TEXT PRIMARY KEY,
                buyer_name TEXT NOT NULL UNIQUE,
                item_ids TEXT NOT NULL,
                price_factor REAL NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recycle_locations (
                location_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                recycle_type TEXT NOT NULL,
                price_factor REAL NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS weapon_recycle_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                weapon_id INTEGER NOT NULL,
                weapon_name TEXT NOT NULL,
                quality TEXT NOT NULL,
                level INTEGER NOT NULL,
                max_level INTEGER NOT NULL,
                raw_value INTEGER NOT NULL,
                capped_value INTEGER NOT NULL,
                price_rate REAL NOT NULL,
                total_price INTEGER NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                business_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS gem_recycle_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                gem_id TEXT NOT NULL,
                gem_name TEXT NOT NULL,
                quality TEXT NOT NULL,
                level INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                raw_value INTEGER NOT NULL,
                capped_value INTEGER NOT NULL,
                price_rate REAL NOT NULL,
                total_price INTEGER NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                business_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS book_recycle_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                book_id TEXT NOT NULL,
                book_name TEXT NOT NULL,
                quality TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                raw_value INTEGER NOT NULL,
                capped_value INTEGER NOT NULL,
                price_rate REAL NOT NULL,
                total_price INTEGER NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                business_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exploration_locations (
                location_id TEXT PRIMARY KEY,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                name TEXT NOT NULL,
                recommended_level INTEGER NOT NULL,
                min_level INTEGER NOT NULL,
                max_level INTEGER NOT NULL,
                desc TEXT NOT NULL DEFAULT '',
                UNIQUE(x, y),
                UNIQUE(name)
            );

            CREATE TABLE IF NOT EXISTS exploration_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ready_at TEXT NOT NULL,
                finished_at TEXT,
                result TEXT NOT NULL DEFAULT '{}',
                claimed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS monster_defs (
                monster_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                level INTEGER NOT NULL,
                kind TEXT NOT NULL,
                kind_key TEXT NOT NULL DEFAULT '',
                hp INTEGER NOT NULL,
                attack INTEGER NOT NULL,
                defense INTEGER NOT NULL,
                drop_item_id TEXT,
                drop_chance REAL NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS weapon_skill_defs (
                skill_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                effect_desc TEXT NOT NULL,
                cost_mp INTEGER NOT NULL,
                interval INTEGER NOT NULL,
                power REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weapon_defs (
                weapon_def_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                drop_location TEXT NOT NULL,
                drop_location_id TEXT NOT NULL DEFAULT '',
                base_attack INTEGER NOT NULL,
                skill_id TEXT NOT NULL,
                weapon_type TEXT NOT NULL,
                weapon_type_key TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS player_weapons (
                weapon_id INTEGER PRIMARY KEY AUTOINCREMENT,
                holder_id TEXT NOT NULL,
                weapon_def_id TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                exp INTEGER NOT NULL DEFAULT 0,
                max_level INTEGER NOT NULL,
                quality TEXT NOT NULL,
                enchant_effects TEXT NOT NULL DEFAULT '[]',
                equipped INTEGER NOT NULL DEFAULT 0,
                custom_name TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weapon_enchants (
                enchant_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                effect TEXT NOT NULL,
                mp_delta INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS weapon_enchant_names (
                weapon_id INTEGER NOT NULL,
                slot_no INTEGER NOT NULL,
                custom_name TEXT NOT NULL,
                PRIMARY KEY (weapon_id, slot_no)
            );

            CREATE TABLE IF NOT EXISTS fixed_equipment (
                client_id TEXT NOT NULL,
                slot TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                hole_count INTEGER NOT NULL DEFAULT 3,
                custom_name TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (client_id, slot)
            );

            CREATE TABLE IF NOT EXISTS fixed_equipment_inlays (
                client_id TEXT NOT NULL,
                slot TEXT NOT NULL,
                hole_no INTEGER NOT NULL,
                gem_id TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (client_id, slot, hole_no)
            );

            CREATE TABLE IF NOT EXISTS inscription_feathers (
                feather_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                source_key TEXT NOT NULL,
                source_name TEXT NOT NULL,
                title TEXT NOT NULL,
                flavor_text TEXT NOT NULL,
                obtained_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seasonal_boss_reward_rates (
                weight_type TEXT PRIMARY KEY,
                feather_chance REAL NOT NULL,
                feather_rank_chance REAL NOT NULL,
                material_chance REAL NOT NULL,
                material_rank_chance REAL NOT NULL,
                gem_chance REAL NOT NULL,
                book_chance REAL NOT NULL,
                weapon_chance REAL NOT NULL,
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS seasonal_boss_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                business_day TEXT NOT NULL UNIQUE,
                boss_key TEXT NOT NULL,
                event_type TEXT NOT NULL,
                weight_type TEXT NOT NULL,
                boss_name TEXT NOT NULL,
                title TEXT NOT NULL,
                scene TEXT NOT NULL,
                story TEXT NOT NULL,
                farewell TEXT NOT NULL,
                feather_text TEXT NOT NULL,
                location_name TEXT NOT NULL,
                atmosphere TEXT NOT NULL DEFAULT '[]',
                level INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                hp INTEGER NOT NULL,
                attack INTEGER NOT NULL,
                defense INTEGER NOT NULL,
                difficulty REAL NOT NULL,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closes_at TEXT NOT NULL,
                killed_at TEXT,
                result TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS seasonal_boss_participants (
                event_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                damage INTEGER NOT NULL DEFAULT 0,
                challenge_count INTEGER NOT NULL DEFAULT 0,
                last_challenge_at TEXT,
                reward_claimed INTEGER NOT NULL DEFAULT 0,
                reward_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (event_id, client_id)
            );

            CREATE TABLE IF NOT EXISTS boss_challenge_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                damage INTEGER NOT NULL DEFAULT 0,
                hp_before INTEGER NOT NULL DEFAULT 0,
                hp_after INTEGER NOT NULL DEFAULT 0,
                killed INTEGER NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS duel_requests (
                duel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT NOT NULL,
                from_client_id TEXT NOT NULL,
                to_client_id TEXT NOT NULL,
                stake INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS duel_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                duel_id INTEGER,
                mode TEXT NOT NULL,
                from_client_id TEXT NOT NULL,
                to_client_id TEXT NOT NULL,
                winner_id TEXT,
                loser_id TEXT,
                stake INTEGER NOT NULL DEFAULT 0,
                fee INTEGER NOT NULL DEFAULT 0,
                summary TEXT NOT NULL DEFAULT '',
                result TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS robbery_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                exploration_record_id INTEGER NOT NULL,
                robber_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                winner_id TEXT NOT NULL DEFAULT '',
                success INTEGER NOT NULL DEFAULT 0,
                loot_text TEXT NOT NULL DEFAULT '',
                loot_json TEXT NOT NULL DEFAULT '[]',
                hate_before INTEGER NOT NULL DEFAULT 0,
                hate_used INTEGER NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT '{}',
                business_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS player_hatreds (
                from_client_id TEXT NOT NULL,
                to_client_id TEXT NOT NULL,
                hate_value INTEGER NOT NULL DEFAULT 0,
                robbery_count INTEGER NOT NULL DEFAULT 0,
                last_reason TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (from_client_id, to_client_id)
            );

            CREATE TABLE IF NOT EXISTS combat_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                target TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wormholes (
                wormhole_id INTEGER PRIMARY KEY AUTOINCREMENT,
                boss_name TEXT NOT NULL,
                boss_kind TEXT NOT NULL,
                location_name TEXT NOT NULL,
                location_id TEXT NOT NULL DEFAULT '',
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                level INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                hp INTEGER NOT NULL,
                attack INTEGER NOT NULL,
                defense INTEGER NOT NULL,
                difficulty REAL NOT NULL,
                opened_by TEXT NOT NULL,
                source TEXT NOT NULL,
                status TEXT NOT NULL,
                opened_at TEXT NOT NULL,
                closes_at TEXT NOT NULL,
                killed_at TEXT,
                result TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS wormhole_participants (
                wormhole_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                damage INTEGER NOT NULL DEFAULT 0,
                challenge_count INTEGER NOT NULL DEFAULT 0,
                last_challenge_at TEXT,
                reward_claimed INTEGER NOT NULL DEFAULT 0,
                reward_text TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (wormhole_id, client_id)
            );

            CREATE TABLE IF NOT EXISTS wormhole_challenge_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                wormhole_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                damage INTEGER NOT NULL DEFAULT 0,
                hp_before INTEGER NOT NULL DEFAULT 0,
                hp_after INTEGER NOT NULL DEFAULT 0,
                killed INTEGER NOT NULL DEFAULT 0,
                result TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS wormhole_notices (
                wormhole_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                last_notice_at TEXT NOT NULL,
                PRIMARY KEY (wormhole_id, client_id)
            );

            CREATE TABLE IF NOT EXISTS game_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dongtian_codes (
                code TEXT PRIMARY KEY,
                game_key TEXT NOT NULL,
                game_title TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                reward_json TEXT NOT NULL DEFAULT '[]',
                granted_json TEXT NOT NULL DEFAULT '[]',
                meta_json TEXT NOT NULL DEFAULT '{}',
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                claimed_by TEXT NOT NULL DEFAULT '',
                claimed_at TEXT,
                reward_rate REAL NOT NULL DEFAULT 1.0,
                medicine_rate REAL NOT NULL DEFAULT 1.0
            );

            CREATE TABLE IF NOT EXISTS dongtian_game_tokens (
                token_hash TEXT PRIMARY KEY,
                game_key TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dongtian_rounds (
                session_id TEXT PRIMARY KEY,
                game_key TEXT NOT NULL,
                game_token_hash TEXT NOT NULL DEFAULT '',
                round_token_hash TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                consumed_at TEXT,
                issued_code TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS yuanqi_codes (
                code TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                requested_story_id TEXT NOT NULL DEFAULT '',
                used_story_id TEXT NOT NULL DEFAULT '',
                used_at TEXT
            );

            CREATE TABLE IF NOT EXISTS player_journals (
                client_id TEXT NOT NULL,
                milestone_key TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (client_id, milestone_key)
            );

            CREATE TABLE IF NOT EXISTS player_titles (
                client_id TEXT NOT NULL,
                title TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 0,
                obtained_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (client_id, title)
            );

            CREATE TABLE IF NOT EXISTS player_lifetime_stats (
                client_id TEXT NOT NULL,
                stat_key TEXT NOT NULL,
                stat_value INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (client_id, stat_key)
            );

            CREATE TABLE IF NOT EXISTS daily_fortunes (
                client_id TEXT NOT NULL,
                business_day TEXT NOT NULL,
                fortune TEXT NOT NULL,
                effect TEXT NOT NULL DEFAULT '{}',
                flavor TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (client_id, business_day)
            );

            CREATE TABLE IF NOT EXISTS daily_newspapers (
                business_day TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS weapon_legends (
                weapon_id INTEGER PRIMARY KEY,
                original_owner_id TEXT NOT NULL,
                current_owner_id TEXT NOT NULL,
                monster_kills INTEGER NOT NULL DEFAULT 0,
                boss_challenges INTEGER NOT NULL DEFAULT 0,
                duel_wins INTEGER NOT NULL DEFAULT 0,
                highest_damage INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_backpack_client ON backpack_items(client_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_players_display_name ON players(display_name);
            CREATE INDEX IF NOT EXISTS idx_user_identities_group ON user_identities(group_id);
            CREATE INDEX IF NOT EXISTS idx_user_group_sessions_expires ON user_group_sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_user_group_bind_codes_player ON user_group_bind_codes(player_id, expires_at);
            CREATE INDEX IF NOT EXISTS idx_ring_client ON ring_items(client_id);
            CREATE INDEX IF NOT EXISTS idx_gem_client ON gem_items(client_id);
            CREATE INDEX IF NOT EXISTS idx_wish_prizes_pool ON wish_prizes(pool_id, enabled);
            CREATE INDEX IF NOT EXISTS idx_wish_draw_records_player ON wish_draw_records(player_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_wish_user_vouchers_player ON wish_user_vouchers(player_id, quantity);
            CREATE INDEX IF NOT EXISTS idx_second_hand_records_seller_seen ON second_hand_records(seller_id, seller_seen_at, created_at);
            CREATE INDEX IF NOT EXISTS idx_vault_items_client ON vault_items(client_id);
            CREATE INDEX IF NOT EXISTS idx_vault_weapons_client ON vault_weapons(client_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_player_weapons_one_equipped
            ON player_weapons(holder_id)
            WHERE equipped = 1;
            CREATE INDEX IF NOT EXISTS idx_physique_level ON physique_defs(level, physique_value);
            CREATE INDEX IF NOT EXISTS idx_trade_records_client ON trade_records(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_trade_records_location_id ON trade_records(location_id, business_day);
            CREATE INDEX IF NOT EXISTS idx_trade_daily_rewards_day ON trade_daily_rewards(business_day);
            CREATE INDEX IF NOT EXISTS idx_trade_heat_day ON trade_heat(business_day, location_id, item_id);
            CREATE INDEX IF NOT EXISTS idx_trade_heat_location_id ON trade_heat(business_day, location_id, item_id);
            CREATE INDEX IF NOT EXISTS idx_world_material_records_client ON world_material_records(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_world_material_records_location ON world_material_records(location_name, category, created_at);
            CREATE INDEX IF NOT EXISTS idx_world_material_records_location_id ON world_material_records(location_id, category, created_at);
            CREATE INDEX IF NOT EXISTS idx_treasure_maps_status ON treasure_maps(status, expires_at);
            CREATE INDEX IF NOT EXISTS idx_treasure_maps_city ON treasure_maps(city_name, status);
            CREATE INDEX IF NOT EXISTS idx_treasure_maps_city_id ON treasure_maps(city_id, status);
            CREATE INDEX IF NOT EXISTS idx_treasure_maps_coord ON treasure_maps(x, y, status);
            CREATE INDEX IF NOT EXISTS idx_treasure_bids_map ON treasure_map_bids(map_id, active, created_at);
            CREATE INDEX IF NOT EXISTS idx_war_prep_pending ON war_prep_states(pending, pending_at);
            CREATE INDEX IF NOT EXISTS idx_world_locations_category ON world_locations(category, terrain);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_world_locations_location_id ON world_locations(location_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_locations_location_id ON trade_locations(location_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_exploration_locations_location_id ON exploration_locations(location_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_special_buyers_location_id ON special_buyers(location_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_recycle_locations_location_id ON recycle_locations(location_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_city_world_states_location_id ON city_world_states(location_id) WHERE location_id != '';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_war_prep_states_location_id ON war_prep_states(location_id) WHERE location_id != '';
            CREATE INDEX IF NOT EXISTS idx_players_location_id ON players(location_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sects_master_client_id ON sects(master_client_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sects_founder_id ON sects(founder_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_sects_location_xy ON sects(location_x, location_y);
            CREATE INDEX IF NOT EXISTS idx_sect_members_sect_id ON sect_members(sect_id);
            CREATE INDEX IF NOT EXISTS idx_sect_merit_records_sect ON sect_merit_records(sect_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_sect_merit_records_client ON sect_merit_records(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_sect_merit_records_category ON sect_merit_records(category, created_at);
            CREATE INDEX IF NOT EXISTS idx_sect_influence_cycle ON sect_influence_records(cycle_start, sect_id);
            CREATE INDEX IF NOT EXISTS idx_sect_influence_client ON sect_influence_records(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_sect_rewards_client ON sect_war_rewards(client_id, claimed, cycle_start);
            CREATE INDEX IF NOT EXISTS idx_sect_contribution_cycle ON sect_contribution_records(cycle_start, sect_id, influence);
            CREATE INDEX IF NOT EXISTS idx_sect_contribution_client ON sect_contribution_records(client_id, cycle_start);
            CREATE INDEX IF NOT EXISTS idx_weapon_recycle_day ON weapon_recycle_records(client_id, business_day);
            CREATE INDEX IF NOT EXISTS idx_gem_recycle_day ON gem_recycle_records(client_id, business_day);
            CREATE INDEX IF NOT EXISTS idx_book_recycle_day ON book_recycle_records(client_id, business_day);
            CREATE INDEX IF NOT EXISTS idx_exploration_client ON exploration_records(client_id, claimed);
            CREATE INDEX IF NOT EXISTS idx_inscription_feathers_client ON inscription_feathers(client_id, feather_id);
            CREATE INDEX IF NOT EXISTS idx_seasonal_boss_status ON seasonal_boss_events(status, closes_at);
            CREATE INDEX IF NOT EXISTS idx_seasonal_boss_participants_client ON seasonal_boss_participants(client_id, reward_claimed);
            CREATE INDEX IF NOT EXISTS idx_boss_challenge_records_event ON boss_challenge_records(event_id, client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_duel_to_client ON duel_requests(to_client_id, status);
            CREATE INDEX IF NOT EXISTS idx_robbery_record_target ON robbery_records(exploration_record_id, target_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_robbery_record_once ON robbery_records(exploration_record_id, robber_id);
            CREATE INDEX IF NOT EXISTS idx_player_hatreds_target ON player_hatreds(to_client_id, hate_value);
            CREATE INDEX IF NOT EXISTS idx_wormholes_status ON wormholes(status, closes_at);
            CREATE INDEX IF NOT EXISTS idx_wormhole_participants_client ON wormhole_participants(client_id, reward_claimed);
            CREATE INDEX IF NOT EXISTS idx_wormhole_challenge_records_event ON wormhole_challenge_records(wormhole_id, client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_game_logs_client ON game_logs(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_dongtian_codes_claimed ON dongtian_codes(claimed_by, claimed_at);
            CREATE INDEX IF NOT EXISTS idx_dongtian_codes_expires ON dongtian_codes(expires_at, claimed_at);
            CREATE INDEX IF NOT EXISTS idx_dongtian_game_tokens_game ON dongtian_game_tokens(game_key, expires_at);
            CREATE INDEX IF NOT EXISTS idx_dongtian_game_tokens_expires ON dongtian_game_tokens(expires_at);
            CREATE INDEX IF NOT EXISTS idx_dongtian_rounds_game ON dongtian_rounds(game_key, expires_at, consumed_at);
            CREATE INDEX IF NOT EXISTS idx_dongtian_rounds_token ON dongtian_rounds(game_key, game_token_hash, consumed_at, expires_at);
            CREATE INDEX IF NOT EXISTS idx_dongtian_rounds_expires ON dongtian_rounds(expires_at, consumed_at);
            CREATE INDEX IF NOT EXISTS idx_yuanqi_codes_player ON yuanqi_codes(player_id, issued_at);
            CREATE INDEX IF NOT EXISTS idx_yuanqi_codes_expires ON yuanqi_codes(expires_at, used_at);
            CREATE INDEX IF NOT EXISTS idx_player_journals_client ON player_journals(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_player_titles_client ON player_titles(client_id, active);
            CREATE INDEX IF NOT EXISTS idx_player_lifetime_stats_key ON player_lifetime_stats(stat_key, stat_value);
            CREATE INDEX IF NOT EXISTS idx_daily_fortunes_day ON daily_fortunes(business_day);
            CREATE INDEX IF NOT EXISTS idx_weapon_legends_owner ON weapon_legends(current_owner_id);
            """
        )
        self.conn.commit()

    def _seed_world_locations(self) -> None:
        """写入系统保留地点；空地不入库，宗门、洞府和藏宝图按坐标稀疏占用。"""

        assert self.conn is not None
        points: dict[tuple[int, int], dict[str, Any]] = {}

        def add_point(
            location_id: str,
            name: str,
            x: int,
            y: int,
            category: str,
            feature: str,
            desc: str = "",
            reserved: int = 1,
        ) -> None:
            key = (int(x), int(y))
            terrain = WORLD_TERRAINS.get(location_id, "荒野")
            point = points.setdefault(
                key,
                {
                    "location_id": location_id,
                    "name": name,
                    "category": category,
                    "terrain": terrain,
                    "features": set(),
                    "reserved": int(reserved),
                    "desc": desc,
                },
            )
            if point["name"] != name:
                raise RuntimeError(f"世界点位坐标重复：{key}/{point['name']}/{name}")
            if point["location_id"] != location_id:
                raise RuntimeError(f"世界点位 ID 重复：{key}/{point['location_id']}/{location_id}")
            point["features"].add(feature)
            point["reserved"] = max(int(point["reserved"]), int(reserved))
            if desc and not point["desc"]:
                point["desc"] = desc

        for name, x, y, _specialties in TRADE_LOCATIONS:
            category = "主城" if location_id_for_name(name) == DEFAULT_LOCATION_ID else "坊市"
            add_point(location_id_for_name(name), name, x, y, category, "trade", reserved=1)
        for name, x, y, _recommended, _min_level, _max_level, desc in EXPLORATION_LOCATIONS:
            add_point(location_id_for_name(name), name, x, y, "探险点", "explore", desc, reserved=1)
        for buyer_name, _item_ids, _price_factor, x, y in SPECIAL_BUYERS:
            add_point(location_id_for_name(buyer_name), buyer_name, x, y, "特殊收购点", "special_buyer", reserved=1)
        for recycle_type, name, _price_factor, x, y, desc in RECYCLE_LOCATIONS:
            add_point(location_id_for_name(name), name, x, y, "回收建筑", f"recycle:{recycle_type}", desc, reserved=1)

        rows = [
            (
                str(point["location_id"]),
                x,
                y,
                str(point["name"]),
                str(point["category"]),
                str(point["terrain"]),
                json.dumps(sorted(point["features"]), ensure_ascii=False),
                int(point["reserved"]),
                str(point["desc"]),
            )
            for (x, y), point in sorted(points.items())
        ]
        self.conn.execute("DELETE FROM world_locations")
        self.conn.executemany(
            """
            INSERT INTO world_locations
            (location_id, x, y, name, category, terrain, features, reserved, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(location_id) DO UPDATE SET
                x = excluded.x,
                y = excluded.y,
                name = excluded.name,
                category = excluded.category,
                terrain = excluded.terrain,
                features = excluded.features,
                reserved = excluded.reserved,
                desc = excluded.desc
            """,
            rows,
        )

    def _seed_data(self) -> None:
        """写入基础配置数据。"""

        assert self.conn is not None
        self.conn.executemany(
            """
            INSERT INTO quality_labels (quality_key, label, desc)
            VALUES (?, ?, ?)
            ON CONFLICT(quality_key) DO UPDATE SET
                desc = excluded.desc
            """,
            [
                (
                    key,
                    str(data["label"]),
                    f"品质稳定键 {key}；倍率 {data['factor']}，排序 {data['rank']}，掉落权重 {data['drop_weight']}。",
                )
                for key, data in QUALITY_DEFS.items()
            ],
        )
        self.conn.executemany(
            """
            INSERT INTO currency_labels (currency_key, label, desc)
            VALUES (?, ?, ?)
            ON CONFLICT(currency_key) DO UPDATE SET
                desc = excluded.desc
            """,
            [
                (
                    key,
                    str(data["label"]),
                    str(data.get("desc") or ""),
                )
                for key, data in CURRENCY_DEFS.items()
            ],
        )
        self.conn.executemany(
            """
            INSERT INTO player_level_labels (level, label, desc)
            VALUES (?, ?, ?)
            ON CONFLICT(level) DO UPDATE SET
                desc = excluded.desc
            """,
            [
                (
                    level,
                    str(data["label"]),
                    str(data.get("desc") or ""),
                )
                for level, data in PLAYER_LEVEL_DEFS.items()
            ],
        )
        self._load_skin_labels()
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO physique_defs
            (physique_id, name, grade, kind, level, physique_value, effect, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row[:-2], json.dumps(row[-2], ensure_ascii=False), row[-1]) for row in PHYSIQUE_DEFS],
        )
        world_placeholders = ",".join("?" for _ in WORLD_ITEM_IDS)
        self.conn.execute(
            f"DELETE FROM item_defs WHERE item_id NOT IN ({world_placeholders})",
            WORLD_ITEM_IDS,
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO item_defs
            (item_id, name, category, quality, weight, stack_limit, tradeable, usable, base_price, effect, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row[:-2], json.dumps(row[-2], ensure_ascii=False), row[-1]) for row in ITEM_DEFS],
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO ring_item_defs
            (ring_item_id, name, category, category_key, quality, usable, target_type, effect, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row[0],
                    row[1],
                    row[2],
                    ring_category_key(row[2]),
                    quality_key(row[3]),
                    row[4],
                    row[5],
                    json.dumps(row[6], ensure_ascii=False),
                    row[7],
                )
                for row in RING_ITEM_DEFS
            ],
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO ring_item_defs
            (ring_item_id, name, category, category_key, quality, usable, target_type, effect, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row[0],
                    row[1],
                    row[2],
                    ring_category_key(row[2]),
                    quality_key(row[3]),
                    row[4],
                    row[5],
                    json.dumps(row[6], ensure_ascii=False),
                    row[7],
                )
                for row in EXTREME_BOOK_DEFS
            ],
        )
        self._seed_wish_data()
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO seasonal_boss_reward_rates
            (
                weight_type, feather_chance, feather_rank_chance,
                material_chance, material_rank_chance,
                gem_chance, book_chance, weapon_chance, desc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            SEASONAL_BOSS_REWARD_RATES,
        )
        self._seed_world_locations()
        self.conn.execute("DELETE FROM trade_locations")
        self.conn.executemany(
            """
            INSERT INTO trade_locations (location_id, name, x, y, specialties)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(location_id) DO UPDATE SET
                name = excluded.name,
                x = excluded.x,
                y = excluded.y,
                specialties = excluded.specialties
            """,
            [(location_id_for_name(name), name, x, y, specialties) for name, x, y, specialties in TRADE_LOCATIONS],
        )
        self._seed_city_world_states()
        trade_names = {
            name
            for _location, _x, _y, specialties in TRADE_LOCATIONS
            for name in specialties.split(",")
        }
        item_home_locations = {
            name: (_location, location_id_for_name(_location))
            for _location, _x, _y, specialties in TRADE_LOCATIONS
            for name in specialties.split(",")
        }
        for name, trade_def in TRADE_ITEM_DEFS.items():
            home_location, home_location_id = item_home_locations.get(name, ("", ""))
            tradeable = 1 if home_location else 0
            trade_type, quality, weight, stack_limit, base_price, desc = trade_def
            item_id = trade_item_id(name)
            effect = json.dumps(
                {
                    "world_category": "纯经济",
                    "world_category_key": "trade",
                    "world_subtype": home_location,
                    "world_subtype_key": home_location_id,
                    "trade_type": trade_type,
                    "trade_group": trade_group_for_type(trade_type),
                    "home_location": home_location,
                    "home_location_id": home_location_id,
                },
                ensure_ascii=False,
            )
            self.conn.execute(
                """
                INSERT INTO item_defs
                (item_id, name, category, quality, weight, stack_limit, tradeable, usable, base_price, effect, desc)
                VALUES (?, ?, '纯经济', ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(item_id) DO UPDATE SET
                    name = excluded.name,
                    category = excluded.category,
                    quality = excluded.quality,
                    weight = excluded.weight,
                    stack_limit = excluded.stack_limit,
                    tradeable = excluded.tradeable,
                    usable = excluded.usable,
                    base_price = excluded.base_price,
                    effect = excluded.effect,
                    desc = excluded.desc
                """,
                (item_id, name, quality, weight, stack_limit, tradeable, base_price, effect, desc),
            )
        trade_goods = []
        for location, _x, _y, specialties in TRADE_LOCATIONS:
            for name in specialties.split(","):
                item = self.conn.execute("SELECT item_id FROM item_defs WHERE name = ?", (name,)).fetchone()
                if item:
                    trade_goods.append((item["item_id"], location, location_id_for_name(location)))
        self.conn.execute("DELETE FROM trade_goods")
        self.conn.executemany(
            "INSERT OR REPLACE INTO trade_goods (item_id, home_location, home_location_id) VALUES (?, ?, ?)",
            trade_goods,
        )
        self.conn.executemany(
            """
            INSERT INTO special_buyers
            (location_id, buyer_name, item_ids, price_factor, x, y)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(location_id) DO UPDATE SET
                buyer_name = excluded.buyer_name,
                item_ids = excluded.item_ids,
                price_factor = excluded.price_factor,
                x = excluded.x,
                y = excluded.y
            """,
            [(location_id_for_name(buyer_name), buyer_name, item_ids, price_factor, x, y) for buyer_name, item_ids, price_factor, x, y in SPECIAL_BUYERS],
        )
        self._seed_war_prep_states()
        self.conn.executemany(
            """
            INSERT INTO recycle_locations
            (location_id, recycle_type, name, price_factor, x, y, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(location_id) DO UPDATE SET
                recycle_type = excluded.recycle_type,
                name = excluded.name,
                price_factor = excluded.price_factor,
                x = excluded.x,
                y = excluded.y,
                desc = excluded.desc
            """,
            [(location_id_for_name(name), recycle_type, name, price_factor, x, y, desc) for recycle_type, name, price_factor, x, y, desc in RECYCLE_LOCATIONS],
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO monster_defs
            (monster_id, name, level, kind, kind_key, hp, attack, defense, drop_item_id, drop_chance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (monster_id, name, level, kind, enemy_kind_key(kind), hp, attack, defense, drop_item_id, drop_chance)
                for monster_id, name, level, kind, hp, attack, defense, drop_item_id, drop_chance in MONSTER_DEFS
            ],
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO weapon_skill_defs
            (skill_id, name, effect_desc, cost_mp, interval, power)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            WEAPON_SKILLS,
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO weapon_defs
            (weapon_def_id, name, drop_location, drop_location_id, base_attack, skill_id, weapon_type, weapon_type_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (weapon_def_id, name, location, location_id_for_name(location), attack, skill_id, weapon_type, weapon_type_key(weapon_type))
                for weapon_def_id, name, location, attack, skill_id, weapon_type in WEAPON_DEFS
            ],
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO weapon_enchants
            (enchant_id, name, effect, mp_delta)
            VALUES (?, ?, ?, ?)
            """,
            [(row[0], row[1], json.dumps(row[2], ensure_ascii=False), row[3]) for row in WEAPON_ENCHANTS],
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO weapon_enchants
            (enchant_id, name, effect, mp_delta)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    f"extreme_{row[0]}",
                    f"极·{row[1]}",
                    json.dumps(_extreme_book_effect(row[2]), ensure_ascii=False),
                    _extreme_book_mp_delta(row[3]),
                )
                for row in WEAPON_ENCHANTS
            ],
        )
        self.conn.execute("DELETE FROM exploration_locations")
        self.conn.executemany(
            """
            INSERT INTO exploration_locations
            (location_id, name, x, y, recommended_level, min_level, max_level, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(location_id) DO UPDATE SET
                name = excluded.name,
                x = excluded.x,
                y = excluded.y,
                recommended_level = excluded.recommended_level,
                min_level = excluded.min_level,
                max_level = excluded.max_level,
                desc = excluded.desc
            """,
            [(location_id_for_name(name), name, x, y, recommended, min_level, max_level, desc) for name, x, y, recommended, min_level, max_level, desc in EXPLORATION_LOCATIONS],
        )
        self._sync_location_identity_columns()
        self._ensure_user_group_identities()
        self.conn.commit()

    def _ensure_user_group_identities(self) -> None:
        """确保每个已有角色都有一个用户组主身份。"""

        assert self.conn is not None
        self.conn.execute(
            """
            INSERT INTO user_groups (primary_player_id, created_at)
            SELECT p.client_id, datetime('now')
            FROM players AS p
            WHERE NOT EXISTS (
                SELECT 1
                FROM user_groups AS g
                WHERE g.primary_player_id = p.client_id
            )
            """
        )
        self.conn.execute(
            """
            INSERT INTO user_identities (group_id, client_id, is_primary, created_at)
            SELECT g.group_id, g.primary_player_id, 1, datetime('now')
            FROM user_groups AS g
            WHERE NOT EXISTS (
                SELECT 1
                FROM user_identities AS i
                WHERE i.client_id = g.primary_player_id
            )
            """
        )

    def _apply_active_world_skin(self) -> None:
        """热重启后重放当前世界皮肤，避免默认种子覆盖展示名。"""

        assert self.conn is not None
        try:
            from .world_skin import apply_active_world_skin_package

            apply_active_world_skin_package(self.conn)
        except ValueError as exc:
            raise RuntimeError(f"当前世界皮肤包无法应用：{exc}") from exc

    def _seed_city_world_states(self) -> None:
        """写入 11 个承接城池的世界物资状态。"""

        assert self.conn is not None
        current = tuple((location_id_for_name(location), location) for location, _x, _y, _specialties in TRADE_LOCATIONS)
        current_ids = tuple(location_id for location_id, _location in current)
        if current_ids:
            placeholders = ",".join("?" for _ in current_ids)
            self.conn.execute(
                f"DELETE FROM city_world_states WHERE location_id NOT IN ({placeholders})",
                current_ids,
            )
        for location_id, location in current:
            if not location_id:
                continue
            existing = self.conn.execute(
                "SELECT 1 FROM city_world_states WHERE location_id = ?",
                (location_id,),
            ).fetchone()
            if existing:
                self.conn.execute(
                    "UPDATE city_world_states SET location_name = ? WHERE location_id = ?",
                    (location, location_id),
                )
            else:
                self.conn.execute(
                    """
                    INSERT OR IGNORE INTO city_world_states
                    (location_id, location_name, last_settled_at, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (location_id, location, ts(), ts()),
                )

    def _seed_war_prep_states(self) -> None:
        """写入特殊收购势力的战备状态。"""

        assert self.conn is not None
        buyers = tuple((location_id_for_name(buyer_name), buyer_name) for buyer_name, _items, _factor, _x, _y in SPECIAL_BUYERS)
        buyer_ids = tuple(location_id for location_id, _buyer_name in buyers)
        if buyer_ids:
            placeholders = ",".join("?" for _ in buyer_ids)
            self.conn.execute(
                f"DELETE FROM war_prep_states WHERE location_id NOT IN ({placeholders})",
                buyer_ids,
            )
        rows = []
        for buyer_name, _items, _factor, _x, _y in SPECIAL_BUYERS:
            location_id = location_id_for_name(buyer_name)
            prep_name, loot_subtype = WAR_PREP_SEED.get(location_id, (f"{buyer_name}战备", "战利品"))
            rows.append((location_id, buyer_name, prep_name, loot_subtype, ts(), ts()))
        for location_id, buyer_name, prep_name, loot_subtype, created_at, updated_at in rows:
            existing = self.conn.execute(
                "SELECT 1 FROM war_prep_states WHERE location_id = ?",
                (location_id,),
            ).fetchone()
            if existing:
                self.conn.execute(
                    """
                    UPDATE war_prep_states
                    SET buyer_name = ?, prep_name = ?, loot_subtype = ?, updated_at = ?
                    WHERE location_id = ?
                    """,
                    (buyer_name, prep_name, loot_subtype, updated_at, location_id),
                )
            else:
                self.conn.execute(
                    """
                    INSERT INTO war_prep_states
                    (location_id, buyer_name, prep_name, loot_subtype, last_settled_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(location_id) DO UPDATE SET
                        buyer_name = excluded.buyer_name,
                        prep_name = excluded.prep_name,
                        loot_subtype = excluded.loot_subtype,
                        updated_at = excluded.updated_at
                    """,
                    (location_id, buyer_name, prep_name, loot_subtype, created_at, updated_at),
                )

    def _sync_location_identity_columns(self) -> None:
        """用稳定地点 ID 同步当前皮肤包的显示名。"""

        assert self.conn is not None

        def sync(table: str, name_column: str, id_column: str = "location_id") -> None:
            for current_name, location_id in SYSTEM_LOCATION_IDS_BY_NAME.items():
                self.conn.execute(
                    f"UPDATE {table} SET {id_column} = ? WHERE {id_column} = '' AND {name_column} = ?",
                    (location_id, current_name),
                )
            for location_id, current_name in SYSTEM_LOCATION_NAMES_BY_ID.items():
                self.conn.execute(
                    f"UPDATE {table} SET {name_column} = ? WHERE {id_column} = ?",
                    (current_name, location_id),
                )

        for table, name_column, id_column in (
            ("world_locations", "name", "location_id"),
            ("trade_locations", "name", "location_id"),
            ("exploration_locations", "name", "location_id"),
            ("special_buyers", "buyer_name", "location_id"),
            ("recycle_locations", "name", "location_id"),
            ("players", "location_name", "location_id"),
            ("city_world_states", "location_name", "location_id"),
            ("trade_prices", "location_name", "location_id"),
            ("trade_heat", "location_name", "location_id"),
            ("world_material_records", "location_name", "location_id"),
            ("trade_records", "location_name", "location_id"),
            ("trade_buy_locks", "location_name", "location_id"),
            ("weapon_recycle_records", "location_name", "location_id"),
            ("gem_recycle_records", "location_name", "location_id"),
            ("book_recycle_records", "location_name", "location_id"),
            ("exploration_records", "location_name", "location_id"),
            ("wormholes", "location_name", "location_id"),
        ):
            sync(table, name_column, id_column)

        for current_name, location_id in TRADE_LOCATION_IDS_BY_NAME.items():
            self.conn.execute(
                "UPDATE trade_goods SET home_location_id = ? WHERE home_location_id = '' AND home_location = ?",
                (location_id, current_name),
            )
        for location_id, current_name in TRADE_LOCATION_NAMES_BY_ID.items():
            self.conn.execute(
                "UPDATE trade_goods SET home_location = ? WHERE home_location_id = ?",
                (current_name, location_id),
            )
            self.conn.execute(
                "UPDATE treasure_maps SET city_name = ? WHERE city_id = ?",
                (current_name, location_id),
            )
        for current_name, location_id in TRADE_LOCATION_IDS_BY_NAME.items():
            self.conn.execute(
                "UPDATE treasure_maps SET city_id = ? WHERE city_id = '' AND city_name = ?",
                (location_id, current_name),
            )

    def _seed_wish_data(self) -> None:
        """写入祈愿默认奖池和奖品；已有奖池配置不覆盖，方便后续在库里调权重。"""

        assert self.conn is not None
        now_text = ts()
        self.conn.execute(
            """
            INSERT OR IGNORE INTO wish_pools
            (pool_id, name, enabled, cost_token_id, cost_token_quantity, desc, created_at, updated_at)
            VALUES (?, ?, 1, ?, 1, ?, ?, ?)
            """,
            (
                WISH_DEFAULT_POOL_ID,
                "流光祈愿",
                WISH_TOKEN_ITEM_ID,
                "消耗纳戒中的流光签进行祈愿；流光签由探险低概率掉落。",
                now_text,
                now_text,
            ),
        )
        self.conn.executemany(
            """
            INSERT OR IGNORE INTO wish_prizes
            (prize_id, pool_id, reward_type, reward_key, display_name, quantity, weight, enabled, payload_json, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, '')
            """,
            WISH_DEFAULT_PRIZES,
        )

    def _validate_seed_data(self) -> None:
        """检查配置引用是否都能落到真实表。

        修仙模块还没上线，发现缺失配置时直接报错，比静默生成错数据更容易修。
        """

        assert self.conn is not None
        missing: list[str] = []

        default_physique = self.conn.execute(
            "SELECT physique_id FROM physique_defs WHERE physique_id = 'fanti'"
        ).fetchone()
        if not default_physique:
            missing.append("默认体质不存在：fanti")
        high_without_effect = [
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM physique_defs WHERE level >= 10 AND effect = '{}'"
            ).fetchall()
        ]
        if high_without_effect:
            missing.append(f"高阶体质缺少专属特性：{','.join(high_without_effect)}")
        for row in self.conn.execute("SELECT name, effect FROM physique_defs").fetchall():
            try:
                json.loads(row["effect"] or "{}")
            except json.JSONDecodeError:
                missing.append(f"体质特性不是 JSON：{row['name']}")

        quality_rows = {
            row["quality_key"]: row["label"]
            for row in self.conn.execute("SELECT quality_key, label FROM quality_labels").fetchall()
        }
        for key in QUALITY_DEFS:
            label = str(quality_rows.get(key) or "").strip()
            if not label:
                missing.append(f"品质显示名缺失：{key}")
        for row in self.conn.execute("SELECT quality_key, label FROM quality_labels").fetchall():
            if row["quality_key"] not in QUALITY_DEFS:
                missing.append(f"未知品质稳定键：{row['quality_key']}/{row['label']}")

        currency_rows = {
            row["currency_key"]: row["label"]
            for row in self.conn.execute("SELECT currency_key, label FROM currency_labels").fetchall()
        }
        for key in CURRENCY_DEFS:
            label = str(currency_rows.get(key) or "").strip()
            if not label:
                missing.append(f"货币显示名缺失：{key}")
        for row in self.conn.execute("SELECT currency_key, label FROM currency_labels").fetchall():
            if row["currency_key"] not in CURRENCY_DEFS:
                missing.append(f"未知货币稳定键：{row['currency_key']}/{row['label']}")

        player_level_rows = {
            int(row["level"]): row["label"]
            for row in self.conn.execute("SELECT level, label FROM player_level_labels").fetchall()
        }
        for level in PLAYER_LEVEL_DEFS:
            label = str(player_level_rows.get(level) or "").strip()
            if not label:
                missing.append(f"等级显示名缺失：{level}")
        for row in self.conn.execute("SELECT level, label FROM player_level_labels").fetchall():
            level = int(row["level"])
            if level not in PLAYER_LEVEL_DEFS:
                missing.append(f"未知等级显示稳定值：{level}/{row['label']}")

        item_ids = {
            row["item_id"]
            for row in self.conn.execute("SELECT item_id FROM item_defs").fetchall()
        }
        names = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM item_defs").fetchall()
        }
        equipment_names = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM ring_item_defs").fetchall()
        }
        duplicated_names = names & equipment_names
        if duplicated_names:
            missing.append(f"背包物品和纳戒物品重名：{','.join(sorted(duplicated_names))}")

        valid_world_category_keys = {"trade", "medicine", "life", "build", "relic", "loot"}
        medicine_roles = {"material", "catalyst", "fuel"}
        for row in self.conn.execute("SELECT item_id, name, quality, tradeable, effect FROM item_defs").fetchall():
            item_id = str(row["item_id"])
            try:
                effect = json.loads(row["effect"] or "{}")
            except json.JSONDecodeError:
                missing.append(f"背包物品 effect 不是 JSON：{item_id}/{row['name']}")
                continue
            category_key = str(effect.get("world_category_key") or "").strip()
            subtype_key = str(effect.get("world_subtype_key") or "").strip()
            if category_key not in valid_world_category_keys:
                missing.append(f"世界物品稳定大类缺失或非法：{item_id}/{row['name']}/{category_key or '空'}")
            if category_key and not subtype_key:
                missing.append(f"世界物品稳定小类缺失：{item_id}/{row['name']}")
            if category_key == "trade" and not int(row["tradeable"]):
                missing.append(f"纯经济物品必须可跑商：{item_id}/{row['name']}")
            if category_key != "trade" and int(row["tradeable"]):
                missing.append(f"非纯经济物品不能标记为跑商货：{item_id}/{row['name']}/{category_key}")
            if category_key == "medicine" and str(effect.get("medicine_material_role") or "") not in medicine_roles:
                missing.append(f"药路物资缺少稳定药路角色：{item_id}/{row['name']}")
            if category_key == "trade" and str(effect.get("home_location_id") or "") not in TRADE_LOCATION_NAMES_BY_ID:
                missing.append(f"纯经济特产缺少合法产地 ID：{item_id}/{row['name']}/{effect.get('home_location_id')}")
            if quality_key(row["quality"]) != row["quality"]:
                missing.append(f"背包物品品质必须保存稳定键：{item_id}/{row['name']}/{row['quality']}")

        ring_item_ids: set[str] = set()
        for row in self.conn.execute("SELECT ring_item_id, name, category_key, quality FROM ring_item_defs").fetchall():
            item_id = str(row["ring_item_id"])
            ring_item_ids.add(item_id)
            if row["category_key"] not in RING_CATEGORY_KEYS:
                missing.append(f"纳戒物品分类稳定键非法：{item_id}/{row['name']}/{row['category_key']}")
            if quality_key(row["quality"]) != row["quality"]:
                missing.append(f"纳戒物品品质必须保存稳定键：{item_id}/{row['name']}/{row['quality']}")

        wish_pool_rows = self.conn.execute(
            "SELECT pool_id, name, enabled, cost_token_id, cost_token_quantity FROM wish_pools"
        ).fetchall()
        wish_pool_ids = {str(row["pool_id"]) for row in wish_pool_rows}
        enabled_wish_pools = {str(row["pool_id"]) for row in wish_pool_rows if int(row["enabled"] or 0)}
        for row in wish_pool_rows:
            pool_id = str(row["pool_id"])
            cost_token_id = str(row["cost_token_id"])
            if cost_token_id not in ring_item_ids:
                missing.append(f"祈愿奖池消耗物不存在：{pool_id}/{row['name']}/{cost_token_id}")
            if int(row["cost_token_quantity"] or 0) <= 0:
                missing.append(f"祈愿奖池消耗数量必须大于 0：{pool_id}/{row['name']}")

        valid_wish_reward_types = {"currency", "exp", "backpack_item", "ring_item", "voucher"}
        wish_voucher_keys = {key for key, _name in WISH_VOUCHERS}
        enabled_prize_weights = {pool_id: 0 for pool_id in enabled_wish_pools}
        for row in self.conn.execute(
            """
            SELECT prize_id, pool_id, reward_type, reward_key, display_name, quantity, weight, enabled, payload_json
            FROM wish_prizes
            """
        ).fetchall():
            prize_id = str(row["prize_id"])
            pool_id = str(row["pool_id"])
            reward_type = str(row["reward_type"])
            reward_key = str(row["reward_key"])
            if pool_id not in wish_pool_ids:
                missing.append(f"祈愿奖品指向不存在的奖池：{prize_id}/{pool_id}")
            if reward_type not in valid_wish_reward_types:
                missing.append(f"祈愿奖品类型非法：{prize_id}/{reward_type}")
            try:
                json.loads(row["payload_json"] or "{}")
            except json.JSONDecodeError:
                missing.append(f"祈愿奖品 payload_json 不是 JSON：{prize_id}/{row['display_name']}")
            if not int(row["enabled"] or 0):
                continue
            quantity = int(row["quantity"] or 0)
            weight = int(row["weight"] or 0)
            if quantity <= 0:
                missing.append(f"祈愿奖品数量必须大于 0：{prize_id}/{row['display_name']}")
            if weight <= 0:
                missing.append(f"祈愿奖品权重必须大于 0：{prize_id}/{row['display_name']}")
            if pool_id in enabled_prize_weights:
                enabled_prize_weights[pool_id] += max(0, weight)
            if reward_type == "currency" and reward_key not in CURRENCY_DEFS:
                missing.append(f"祈愿货币奖品指向未知货币：{prize_id}/{reward_key}")
            elif reward_type == "exp" and reward_key != "player_exp":
                missing.append(f"祈愿经验奖品稳定键非法：{prize_id}/{reward_key}")
            elif reward_type == "backpack_item" and reward_key not in item_ids:
                missing.append(f"祈愿背包奖品不存在：{prize_id}/{reward_key}")
            elif reward_type == "ring_item" and reward_key not in ring_item_ids:
                missing.append(f"祈愿纳戒奖品不存在：{prize_id}/{reward_key}")
            elif reward_type == "voucher" and reward_key not in wish_voucher_keys:
                missing.append(f"祈愿凭证奖品不存在：{prize_id}/{reward_key}")
        for pool_id, total_weight in enabled_prize_weights.items():
            if total_weight <= 0:
                missing.append(f"启用中的祈愿奖池没有可抽奖品：{pool_id}")

        coord_names: dict[tuple[int, int], str] = {}
        name_coords: dict[str, tuple[int, int]] = {}

        def check_point(name: str, x: int, y: int, source: str) -> None:
            point = (int(x), int(y))
            if not (WORLD_COORD_MIN <= point[0] <= WORLD_COORD_MAX and WORLD_COORD_MIN <= point[1] <= WORLD_COORD_MAX):
                missing.append(f"{source}坐标越界：{name}({point[0]},{point[1]})")
            old_name = coord_names.setdefault(point, name)
            if old_name != name:
                missing.append(f"世界点位坐标重复：{point}/{old_name}/{name}")
            old_point = name_coords.setdefault(name, point)
            if old_point != point:
                missing.append(f"世界点位名称重复但坐标不同：{name}/{old_point}/{point}")

        for name, x, y, _specialties in TRADE_LOCATIONS:
            check_point(name, x, y, "商场")
        for name, x, y, _recommended, _min_level, _max_level, _desc in EXPLORATION_LOCATIONS:
            check_point(name, x, y, "探险")
        trade_location_ids = {location_id_for_name(name) for name, _x, _y, _specialties in TRADE_LOCATIONS}
        explore_location_ids = {
            location_id_for_name(name)
            for name, _x, _y, _recommended, _min_level, _max_level, _desc in EXPLORATION_LOCATIONS
        }
        special_explore_ids = set(SECRET_REALM_NAMES_BY_ID)
        normal_explore_ids = explore_location_ids - special_explore_ids
        if trade_location_ids != normal_explore_ids:
            missing.append(
                "跑商地点必须与普通探险地点重合："
                f"跑商独有={','.join(sorted(trade_location_ids - normal_explore_ids)) or '无'}；"
                f"探险独有={','.join(sorted(normal_explore_ids - trade_location_ids)) or '无'}"
            )
        for buyer_name, _item_ids_text, _factor, x, y in SPECIAL_BUYERS:
            check_point(buyer_name, x, y, "特殊收购")
        for _recycle_type, name, _factor, x, y, _desc in RECYCLE_LOCATIONS:
            check_point(name, x, y, "回收")

        system_location_ids = {
            row["location_id"]
            for row in self.conn.execute("SELECT location_id FROM world_locations").fetchall()
        }
        for table, id_column in (
            ("trade_locations", "location_id"),
            ("exploration_locations", "location_id"),
            ("special_buyers", "location_id"),
            ("recycle_locations", "location_id"),
            ("city_world_states", "location_id"),
            ("war_prep_states", "location_id"),
        ):
            for row in self.conn.execute(f"SELECT DISTINCT {id_column} AS location_id FROM {table}").fetchall():
                if row["location_id"] not in system_location_ids:
                    missing.append(f"{table} 指向不存在的系统保留地点：{row['location_id']}")

        gem_rows = self.conn.execute(
            "SELECT name, effect FROM ring_item_defs WHERE category_key = 'gem'"
        ).fetchall()
        for row in gem_rows:
            try:
                effect = json.loads(row["effect"] or "{}")
            except json.JSONDecodeError:
                missing.append(f"宝石效果不是 JSON：{row['name']}")
                continue
            if not isinstance(effect, dict) or not effect:
                missing.append(f"宝石缺少有效属性：{row['name']}")

        for location, _x, _y, specialties in TRADE_LOCATIONS:
            specialty_names = [name.strip() for name in specialties.split(",") if name.strip()]
            if len(specialty_names) != 3:
                missing.append(f"跑商地点必须正好 3 个特产：{location}/{specialties}")
            for name in specialty_names:
                trade_def = TRADE_ITEM_DEFS.get(name)
                item_id = trade_item_id(name)
                if not trade_def:
                    missing.append(f"跑商特产缺少定价：{location}/{name}")
                    continue
                if item_id not in item_ids:
                    missing.append(f"跑商特产未落背包物品定义：{location}/{item_id}/{name}")
                trade_type = str(trade_def[0])
                if trade_type in TRADE_FORBIDDEN_SPECIALTY_TYPES:
                    missing.append(f"跑商特产不能使用旧民生类或药路类：{location}/{name}/{trade_type}")
                if trade_group_for_type(trade_type) != "trade":
                    missing.append(f"跑商特产必须是纯经济商品：{location}/{name}/{trade_type}")
        trade_names = {
            name
            for _location, _x, _y, specialties in TRADE_LOCATIONS
            for name in specialties.split(",")
        }
        for name, trade_def in TRADE_ITEM_DEFS.items():
            item_id = trade_item_id(name)
            if item_id not in item_ids:
                missing.append(f"纯经济特产定义未落背包物品定义：{item_id}/{name}")
            trade_type = str(trade_def[0])
            if name not in trade_names and trade_type in TRADE_FORBIDDEN_SPECIALTY_TYPES:
                missing.append(f"非入口纯经济特产不能复用药路或民生小类：{name}/{trade_type}")

        for buyer_name, item_ids_text, _factor, _x, _y in SPECIAL_BUYERS:
            for item_id in item_ids_text.split(","):
                if item_id not in item_ids:
                    missing.append(f"特殊收购物不存在：{buyer_name}/{item_id}")

        for monster_id, _name, *_rest, drop_item_id, _chance in MONSTER_DEFS:
            if drop_item_id and drop_item_id not in item_ids:
                missing.append(f"怪物掉落物不存在：{monster_id}/{drop_item_id}")

        for row in self.conn.execute("SELECT monster_id, name, kind_key FROM monster_defs").fetchall():
            if str(row["kind_key"] or "") not in ENEMY_SKILL_DEFS:
                missing.append(f"怪物类型稳定键非法：{row['monster_id']}/{row['name']}/{row['kind_key']}")

        skill_ids = {
            row["skill_id"]
            for row in self.conn.execute("SELECT skill_id FROM weapon_skill_defs").fetchall()
        }
        for weapon_def_id, _name, _location, _attack, skill_id, _weapon_type in WEAPON_DEFS:
            if skill_id not in skill_ids:
                missing.append(f"武器技能不存在：{weapon_def_id}/{skill_id}")
            if location_id_for_name(_location) not in normal_explore_ids:
                missing.append(f"武器掉落地点必须是普通探险地点：{weapon_def_id}/{_location}")
        for row in self.conn.execute("SELECT weapon_def_id, name, drop_location_id, weapon_type_key FROM weapon_defs").fetchall():
            if str(row["drop_location_id"] or "") not in normal_explore_ids:
                missing.append(f"武器掉落地点 ID 必须是普通探险地点：{row['weapon_def_id']}/{row['name']}/{row['drop_location_id']}")
            if str(row["weapon_type_key"] or "") not in WEAPON_TYPE_ATTACK_BASE_FACTORS:
                missing.append(f"武器类型稳定键非法：{row['weapon_def_id']}/{row['name']}/{row['weapon_type_key']}")

        enchant_ids = {
            row["enchant_id"]
            for row in self.conn.execute("SELECT enchant_id FROM weapon_enchants").fetchall()
        }
        rows = self.conn.execute(
            "SELECT ring_item_id, name, effect FROM ring_item_defs WHERE category_key = 'book'"
        ).fetchall()
        for row in rows:
            try:
                effect = json.loads(row["effect"] or "{}")
            except json.JSONDecodeError:
                missing.append(f"技能书效果不是 JSON：{row['name']}")
                continue
            enchant_id = effect.get("enchant_id")
            if enchant_id not in enchant_ids:
                missing.append(f"技能书附魔不存在：{row['name']}/{enchant_id}")

        if missing:
            raise RuntimeError("修仙基础配置错误：\n" + "\n".join(missing))

    def _load_skin_labels(self) -> None:
        """把当前皮肤的品质、货币和等级显示名注入公共展示函数。"""

        assert self.conn is not None
        quality_rows = self.conn.execute("SELECT quality_key, label FROM quality_labels").fetchall()
        set_quality_label_overrides({row["quality_key"]: row["label"] for row in quality_rows})
        currency_rows = self.conn.execute("SELECT currency_key, label FROM currency_labels").fetchall()
        set_currency_label_overrides({row["currency_key"]: row["label"] for row in currency_rows})
        player_level_rows = self.conn.execute("SELECT level, label FROM player_level_labels").fetchall()
        set_player_level_label_overrides({row["level"]: row["label"] for row in player_level_rows})
        active = self.conn.execute("SELECT skin_id FROM world_skin_active WHERE id = 1").fetchone()
        if active:
            from .world_skin import load_skin_package

            package = load_skin_package(str(active["skin_id"]))
            set_enemy_skill_label_overrides(package.names.get("actors", {}).get("enemy_skills"))

    def ensure_fixed_equipment(self, client_id: str) -> None:
        """确保玩家装备位存在。"""

        with self.lock:
            self.init()
            assert self.conn is not None
            self.conn.executemany(
                """
                INSERT OR IGNORE INTO fixed_equipment (client_id, slot, level)
                VALUES (?, ?, 0)
                """,
                [(client_id, slot) for slot in EQUIPMENT_SLOTS],
            )
            self.conn.commit()


db = XiuxianDB(Path(__file__).with_name("xiuxian.db"))


__all__ = ["XiuxianDB", "db", "world_category_key"]
