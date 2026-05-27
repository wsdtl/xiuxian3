"""修仙模块 SQLite 数据层。

当前模块按最新 schema 运行；小版本字段变更会优先迁移，无法迁移时才重建修仙库。
"""

from __future__ import annotations

import json
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Iterator

from .constants import EQUIPMENT_SLOTS, SCHEMA_VERSION


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


ITEM_DEFS = (
    ("yaodan", "妖丹", "怪物战利品", "良品", 2, 50, 0, 0, 800, {}, "镇妖司高价收购。"),
    ("yaogu", "妖骨", "怪物战利品", "凡品", 3, 50, 0, 0, 300, {}, "镇妖司收购。"),
    ("mohe", "魔核", "怪物战利品", "珍品", 2, 30, 0, 0, 1600, {}, "伏魔殿高价收购。"),
    ("yinhunzhu", "阴魂珠", "怪物战利品", "良品", 1, 50, 0, 0, 900, {}, "鬼市高价收购。"),
    ("jiaolin", "蛟鳞", "怪物战利品", "珍品", 2, 30, 0, 0, 2200, {}, "龙渊阁高价收购。"),
    ("shoujin", "兽筋", "怪物战利品", "良品", 2, 50, 0, 0, 650, {}, "万兽盟收购。"),
    ("junhunyin", "军魂印", "怪物战利品", "稀品", 1, 10, 0, 0, 4500, {}, "破军营高价收购。"),
    ("yaoxue", "妖血", "怪物战利品", "凡品", 1, 50, 0, 0, 260, {}, "镇妖司收购。"),
    ("yaopi", "妖皮", "怪物战利品", "凡品", 2, 50, 0, 0, 340, {}, "镇妖司收购。"),
    ("yaotong", "妖瞳", "怪物战利品", "良品", 1, 40, 0, 0, 760, {}, "镇妖司高价收购。"),
    ("yaohun_suipian", "妖魂碎片", "怪物战利品", "良品", 1, 40, 0, 0, 980, {}, "镇妖司高价收购。"),
    ("mojiao", "魔角", "怪物战利品", "良品", 2, 40, 0, 0, 920, {}, "伏魔殿收购。"),
    ("moxue", "魔血", "怪物战利品", "良品", 1, 40, 0, 0, 880, {}, "伏魔殿收购。"),
    ("mopi", "魔皮", "怪物战利品", "良品", 2, 40, 0, 0, 840, {}, "伏魔殿收购。"),
    ("mozhao", "魔爪", "怪物战利品", "珍品", 2, 30, 0, 0, 1800, {}, "伏魔殿高价收购。"),
    ("moyanhui", "魔焰灰", "怪物战利品", "珍品", 1, 30, 0, 0, 1500, {}, "伏魔殿高价收购。"),
    ("guihuo", "鬼火", "怪物战利品", "凡品", 1, 50, 0, 0, 280, {}, "鬼市收购。"),
    ("canhunfan", "残魂幡", "怪物战利品", "良品", 2, 40, 0, 0, 900, {}, "鬼市高价收购。"),
    ("baigupian", "白骨片", "怪物战利品", "凡品", 2, 50, 0, 0, 320, {}, "鬼市收购。"),
    ("mingzhi", "冥纸", "怪物战利品", "凡品", 1, 50, 0, 0, 240, {}, "鬼市收购。"),
    ("yuanqiping", "怨气瓶", "怪物战利品", "良品", 1, 40, 0, 0, 860, {}, "鬼市高价收购。"),
    ("longxu", "龙须", "怪物战利品", "珍品", 1, 30, 0, 0, 2400, {}, "龙渊阁高价收购。"),
    ("longxueshi", "龙血石", "怪物战利品", "稀品", 1, 20, 0, 0, 5200, {}, "龙渊阁高价收购。"),
    ("shouya", "兽牙", "怪物战利品", "凡品", 2, 50, 0, 0, 300, {}, "万兽盟收购。"),
    ("shougu", "兽骨", "怪物战利品", "凡品", 3, 50, 0, 0, 360, {}, "万兽盟收购。"),
    ("shoupi", "兽皮", "怪物战利品", "凡品", 3, 50, 0, 0, 420, {}, "万兽盟收购。"),
    ("shoujiao", "兽角", "怪物战利品", "良品", 2, 40, 0, 0, 780, {}, "万兽盟高价收购。"),
    ("shouxin", "兽心", "怪物战利品", "良品", 1, 40, 0, 0, 920, {}, "万兽盟高价收购。"),
    ("pojia_pian", "破甲片", "怪物战利品", "良品", 2, 40, 0, 0, 820, {}, "破军营收购。"),
    ("canbingfu", "残兵符", "怪物战利品", "良品", 1, 40, 0, 0, 760, {}, "破军营收购。"),
    ("zhanqi_suibu", "战旗碎布", "怪物战利品", "良品", 1, 40, 0, 0, 720, {}, "破军营收购。"),
    ("xiuxuetie", "锈血铁", "怪物战利品", "珍品", 3, 30, 0, 0, 1700, {}, "破军营高价收购。"),
    ("duanrenpian", "断刃片", "怪物战利品", "珍品", 2, 30, 0, 0, 1600, {}, "破军营高价收购。"),
)


EQUIPMENT_ITEM_DEFS = (
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
        "打开后按等级段随机获得一笔源石。",
    ),
    ("xueqidan", "血契丹", "恢复类", "凡品", 1, "玩家", {"hp_ratio": 0.25}, "恢复 25% 血气。"),
    ("yinmingcao", "阴冥草", "恢复类", "凡品", 1, "玩家", {"mp_ratio": 0.25}, "恢复 25% 精神。"),
    ("huichunlu", "回春露", "恢复类", "良品", 1, "玩家", {"hp_ratio": 0.45}, "恢复 45% 血气。"),
    ("ningshenlu", "凝神露", "恢复类", "良品", 1, "玩家", {"mp_ratio": 0.45}, "恢复 45% 精神。"),
    ("shenggudan", "生骨丹", "恢复类", "珍品", 1, "玩家", {"hp_ratio": 0.7}, "恢复 70% 血气。"),
    ("yanghundan", "养魂丹", "恢复类", "珍品", 1, "玩家", {"mp_ratio": 0.7}, "恢复 70% 精神。"),
    ("kaikongqi", "开孔器", "消耗品", "珍品", 0, "装备", {}, "装备开孔材料，通过岁时情劫首领奖励获得。"),
    ("xisuiye", "洗髓液", "消耗品", "珍品", 0, "玩家", {"wash_physique": 1}, "岁时情劫首领和异界虫洞掉落的洗髓消耗品，通过洗髓命令消耗。"),
    ("fengren_shu", "风刃书", "技能书", "良品", 0, "武器", {"enchant_id": "fengren_shu"}, "提高命中稳定。"),
    ("poxie_shu", "破甲书", "技能书", "良品", 0, "武器", {"enchant_id": "poxie_shu"}, "提高穿透。"),
    ("huichun_shu", "回春书", "技能书", "良品", 0, "武器", {"enchant_id": "huichun_shu"}, "命中后轻微回血。"),
    ("xuandun_shu", "玄盾书", "技能书", "珍品", 0, "武器", {"enchant_id": "xuandun_shu"}, "释放后提高承伤。"),
    ("xueqi_shu", "血契书", "技能书", "良品", 0, "武器", {"enchant_id": "xueqi_shu"}, "命中后按伤害回血。"),
    ("duannian_shu", "断念书", "技能书", "良品", 0, "武器", {"enchant_id": "duannian_shu"}, "压制敌人精神恢复。"),
    ("chuanyun_shu", "穿云书", "技能书", "珍品", 0, "武器", {"enchant_id": "chuanyun_shu"}, "提高穿透伤害。"),
    ("yueshi_shu", "月蚀书", "技能书", "珍品", 0, "武器", {"enchant_id": "yueshi_shu"}, "降低敌人防御。"),
    ("zhuixing_shu", "追星书", "技能书", "良品", 0, "武器", {"enchant_id": "zhuixing_shu"}, "增加多段轻击概率。"),
    ("zhenyue_shu", "镇岳书", "技能书", "珍品", 0, "武器", {"enchant_id": "zhenyue_shu"}, "释放后短暂减伤。"),
    ("wuxiang_shu", "无相书", "技能书", "稀品", 0, "武器", {"enchant_id": "wuxiang_shu"}, "蓄势提高技能威力，但触发更慢。"),
    ("bengshan_shu", "崩山书", "技能书", "珍品", 0, "武器", {"enchant_id": "bengshan_shu"}, "强化重击爆发，但触发更慢。"),
    ("shaying_shu", "沙影书", "技能书", "良品", 0, "武器", {"enchant_id": "shaying_shu"}, "提高连击稳定性。"),
    ("liuguang_shu", "流光书", "技能书", "良品", 0, "武器", {"enchant_id": "liuguang_shu"}, "加快武器技能触发。"),
    ("xingluo_shu", "星落书", "技能书", "珍品", 0, "武器", {"enchant_id": "xingluo_shu"}, "提高连击追加伤害。"),
    ("duanhai_shu", "断海书", "技能书", "珍品", 0, "武器", {"enchant_id": "duanhai_shu"}, "提高单次技能爆发，但触发更慢。"),
    ("jueying_shu", "绝影书", "技能书", "珍品", 0, "武器", {"enchant_id": "jueying_shu"}, "提高闪避。"),
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


TRADE_LOCATIONS = (
    ("天枢城", 0, 0, "星纹玉简,天枢铜钱,灵契纸,城隍香,白玉绳,古器残片"),
    ("青岚坊", 120, 420, "青岚玉,青竹简,风纹纸,竹灵简,岚光砂,轻羽绸"),
    ("赤霞港", 460, -80, "赤霞珠,火纹贝,霞光绸,赤盐,炎晶片,潮火鱼"),
    ("玄铁岭", -420, 200, "玄铁矿,黑曜砂,山铜,铁木炭,岩心石,锻炉灰"),
    ("万药谷", -260, 520, "万药籽,药王锄,灵蜂蜜,药香泥,丹炉灰,药篓藤"),
    ("云梦泽", 240, -360, "云梦贝,水镜草,幻雾珠,泽兰,梦纹鱼,雾纹纱"),
    ("流沙海市", -520, -260, "流沙晶,沙金,风蚀骨,驼铃草,月牙砂,毒云石"),
    ("寒霜关", -40, 580, "寒霜石,冰魄花,雪纹铁,霜盐,冷玉髓,寒魄草"),
    ("雷泽城", 400, 360, "雷泽鼓,雷纹木,电光砂,鸣蛇鳞,紫雷石,震雷符"),
    ("碧潮岛", 560, -420, "碧潮珊瑚,潮汐珠,海心藻,水府残玉,龙骨片,海兽牙"),
    ("丹霞镇", -180, -460, "丹砂,赤云石,火绒布,朱雀羽,炉心炭,丹霞瓷"),
    ("灵木寨", -520, 500, "灵木心,藤甲片,木纹珠,鹿角牌,花纹木盒,青藤绳"),
    ("镜湖城", 180, 180, "镜湖玉,水镜牌,月影纱,清心铃,银鳞片,映月杯"),
    ("幽篁林", -360, 40, "幽篁笛,竹露,墨竹卷,静心香,翠竹符,影叶"),
    ("星陨墟", 60, -620, "星陨石,星砂瓶,星辉片,残碑拓,陨铁片,无相竹"),
    ("玉京台", 0, 700, "玉京符诏,白玉冠,云纹佩,天香锦,仙鹤羽,金缕册"),
    ("黑水渡", 620, 120, "黑水珠,墨鳞甲,渡魂灯,玄水瓶,夜航图,乌木桨"),
    ("百兽原", -640, -80, "兽骨牌,狼毫笔,虎纹皮,灵角,兽魂铃,草原玉"),
)


TRADE_ITEM_DEFS = {
    "星纹玉简": ("文书", "良品", 3, 50, 900, "天枢城书院常用玉简，适合卖往需要文书契据的城镇。"),
    "天枢铜钱": ("货币", "凡品", 2, 80, 520, "天枢城铸钱局旧钱，分量稳定，远地也认。"),
    "灵契纸": ("文书", "良品", 1, 80, 680, "可写灵契的纸材，商户和宗门都消耗。"),
    "城隍香": ("香料", "良品", 1, 60, 740, "祭庙香料，礼仪重地需求更高。"),
    "白玉绳": ("玉石", "良品", 1, 60, 620, "白玉细绳，多用于礼器和佩饰。"),
    "古器残片": ("古器", "珍品", 3, 30, 1180, "旧器碎片，古玩商和考据修士会高价收。"),
    "青岚玉": ("玉石", "良品", 2, 50, 780, "青岚坊山玉，色清质轻。"),
    "青竹简": ("竹器", "凡品", 2, 80, 460, "青竹制成的书简，轻便耐用。"),
    "风纹纸": ("文书", "凡品", 1, 80, 560, "带风纹的纸材，适合符契抄写。"),
    "竹灵简": ("竹器", "良品", 2, 60, 680, "灵竹削成的简册，竹木城寨更认货。"),
    "岚光砂": ("沙货", "良品", 2, 50, 720, "青岚山风口细砂，炼器可作辅料。"),
    "轻羽绸": ("纺织", "良品", 1, 60, 900, "轻如羽的绸料，宫台和湖城需求不错。"),
    "赤霞珠": ("玉石", "良品", 2, 50, 860, "赤霞港暖色珠材，可作饰品。"),
    "火纹贝": ("海货", "凡品", 2, 60, 640, "贝壳带火纹，港口和海岛常用。"),
    "霞光绸": ("纺织", "良品", 1, 60, 900, "霞色绸料，适合卖到礼仪和服饰需求高的地方。"),
    "赤盐": ("盐鲜", "凡品", 3, 80, 420, "赤霞港晒盐，重但好走量。"),
    "炎晶片": ("丹材", "良品", 2, 50, 980, "温热晶片，丹炉和锻炉都用得上。"),
    "潮火鱼": ("水产", "凡品", 3, 50, 580, "赤霞港近海鱼货，新鲜时价更好。"),
    "玄铁矿": ("矿材", "良品", 5, 40, 760, "玄铁岭主矿，重货，远运才有利润。"),
    "黑曜砂": ("矿材", "凡品", 4, 50, 620, "黑曜矿砂，炼器铺常收。"),
    "山铜": ("矿材", "良品", 5, 40, 880, "山中赤铜，锻造需求稳定。"),
    "铁木炭": ("燃料", "凡品", 4, 60, 540, "铁木烧成的炭，丹炉和锻炉通用。"),
    "岩心石": ("矿材", "良品", 5, 30, 950, "岩心中取出的硬石，重而值钱。"),
    "锻炉灰": ("燃料", "凡品", 3, 60, 420, "旧炉灰，炼器辅料，低价走量。"),
    "万药籽": ("药材", "良品", 1, 99, 520, "万药谷常见药籽，轻货好带。"),
    "药王锄": ("工具", "良品", 3, 40, 860, "药农常用灵锄，药谷外也稀罕。"),
    "灵蜂蜜": ("药材", "良品", 1, 60, 760, "灵蜂采药成蜜，药修和食肆都收。"),
    "药香泥": ("药材", "凡品", 3, 60, 460, "带药香的泥土，培育灵植常用。"),
    "丹炉灰": ("丹材", "凡品", 2, 60, 420, "废炉灰，可作低阶丹材。"),
    "药篓藤": ("木材", "凡品", 2, 70, 500, "编药篓的藤条，木寨和药谷互通。"),
    "云梦贝": ("水产", "良品", 2, 50, 680, "云梦泽水贝，纹理如雾。"),
    "水镜草": ("药材", "良品", 1, 70, 620, "水面映影的灵草，药修常收。"),
    "幻雾珠": ("幻材", "珍品", 1, 30, 980, "凝雾成珠，幻术材料。"),
    "泽兰": ("药材", "凡品", 1, 80, 520, "泽地香草，轻货好走。"),
    "梦纹鱼": ("水产", "良品", 2, 50, 720, "鱼鳞有梦纹，湖泽城镇爱收。"),
    "雾纹纱": ("纺织", "良品", 1, 50, 880, "雾纹轻纱，远销玉京和镜湖。"),
    "流沙晶": ("沙货", "良品", 3, 50, 760, "流沙中淘出的晶粒，耐磨耐热。"),
    "沙金": ("矿材", "良品", 3, 40, 950, "沙海淘金，价高但重。"),
    "风蚀骨": ("沙货", "凡品", 3, 50, 620, "风沙磨出的骨片，异地少见。"),
    "驼铃草": ("药材", "凡品", 1, 70, 560, "驼队识路草，药效温和。"),
    "月牙砂": ("沙货", "良品", 2, 50, 720, "月牙形细砂，符墨可用。"),
    "毒云石": ("矿材", "良品", 3, 40, 880, "带毒云纹的石材，炼器需谨慎。"),
    "寒霜石": ("寒材", "良品", 3, 50, 780, "寒霜关冷石，可保寒气。"),
    "冰魄花": ("药材", "珍品", 1, 30, 900, "冰中开花，药谷和寒关都认。"),
    "雪纹铁": ("矿材", "良品", 4, 40, 860, "带雪纹的铁材，韧性不错。"),
    "霜盐": ("盐鲜", "凡品", 3, 80, 480, "寒地霜盐，易存易卖。"),
    "冷玉髓": ("寒材", "珍品", 2, 30, 1050, "冷玉内髓，清心定神。"),
    "寒魄草": ("药材", "良品", 1, 50, 620, "寒地灵草，精神类丹方常用。"),
    "雷泽鼓": ("雷材", "珍品", 4, 30, 1300, "雷泽城法鼓，声中带雷。"),
    "雷纹木": ("木材", "良品", 3, 50, 760, "雷击不焦的木材，符器常用。"),
    "电光砂": ("雷材", "良品", 2, 50, 880, "砂中偶有电光，炼器辅材。"),
    "鸣蛇鳞": ("兽材", "珍品", 2, 30, 1050, "鸣蛇脱鳞，可入符器。"),
    "紫雷石": ("雷材", "珍品", 4, 30, 1500, "紫雷凝石，高阶雷器材料。"),
    "震雷符": ("符箓", "良品", 1, 40, 980, "雷泽城常见符货，轻而值钱。"),
    "碧潮珊瑚": ("海货", "珍品", 3, 30, 1180, "碧潮岛珊瑚，色泽通透。"),
    "潮汐珠": ("海货", "良品", 2, 40, 980, "随潮涨落而明暗变化。"),
    "海心藻": ("水产", "凡品", 1, 80, 560, "海心处采来的灵藻，轻货。"),
    "水府残玉": ("古器", "珍品", 3, 30, 1350, "水府旧玉，古玩商喜欢。"),
    "龙骨片": ("龙材", "珍品", 3, 20, 1500, "疑似龙骨碎片，价高量少。"),
    "海兽牙": ("兽材", "良品", 2, 40, 920, "海兽尖牙，可制器。"),
    "丹砂": ("丹材", "凡品", 2, 70, 560, "丹霞镇常见丹砂，炼丹基础货。"),
    "赤云石": ("丹材", "良品", 3, 50, 820, "赤云纹石，炉火稳定。"),
    "火绒布": ("纺织", "凡品", 1, 60, 640, "耐火绒布，丹房常用。"),
    "朱雀羽": ("丹材", "珍品", 1, 20, 1500, "朱羽如火，稀有丹材。"),
    "炉心炭": ("燃料", "凡品", 3, 60, 520, "炉心余炭，火力温和。"),
    "丹霞瓷": ("瓷器", "良品", 2, 40, 880, "丹霞镇烧制的瓷器，适合礼赠。"),
    "灵木心": ("木材", "珍品", 3, 30, 950, "灵木中心材，器修常收。"),
    "藤甲片": ("木材", "良品", 2, 50, 740, "藤甲拆片，轻而坚韧。"),
    "木纹珠": ("木材", "良品", 1, 60, 620, "木纹凝珠，可作饰物。"),
    "鹿角牌": ("兽材", "良品", 2, 50, 680, "鹿角磨成的牌片，百兽原也收。"),
    "花纹木盒": ("木材", "凡品", 2, 60, 520, "雕花木盒，走礼品路线。"),
    "青藤绳": ("木材", "凡品", 1, 80, 420, "青藤搓绳，低价轻货。"),
    "镜湖玉": ("湖产", "良品", 2, 50, 920, "镜湖底玉，水润明净。"),
    "水镜牌": ("湖产", "良品", 2, 50, 780, "可映水纹的小牌。"),
    "月影纱": ("纺织", "良品", 1, 50, 980, "月影下织成的纱，玉京需求高。"),
    "清心铃": ("礼器", "良品", 1, 50, 720, "铃音清心，修士常佩。"),
    "银鳞片": ("水产", "良品", 2, 50, 860, "银鳞鱼脱片，可入器。"),
    "映月杯": ("礼器", "珍品", 2, 30, 1120, "杯中映月，礼器市场喜欢。"),
    "幽篁笛": ("竹器", "良品", 1, 50, 820, "幽篁林竹笛，声音清远。"),
    "竹露": ("药材", "凡品", 1, 80, 460, "竹叶夜露，药效清淡。"),
    "墨竹卷": ("文书", "良品", 2, 50, 720, "墨竹制卷，可书符文。"),
    "静心香": ("香料", "良品", 1, 60, 640, "静心用香，城镇消耗稳定。"),
    "翠竹符": ("符箓", "良品", 1, 50, 780, "翠竹刻符，轻货高价。"),
    "影叶": ("药材", "凡品", 1, 80, 560, "夜色中才显纹理的竹叶。"),
    "星陨石": ("星材", "珍品", 5, 20, 1700, "星陨墟主材，重而昂贵。"),
    "星砂瓶": ("星材", "珍品", 2, 30, 1180, "瓶中星砂，可作阵材。"),
    "星辉片": ("星材", "良品", 2, 40, 980, "带星辉的薄片，炼器常收。"),
    "残碑拓": ("古器", "良品", 1, 40, 860, "古碑拓片，文修和古玩商需要。"),
    "陨铁片": ("矿材", "珍品", 4, 30, 1450, "陨铁碎片，武器工坊高价收。"),
    "无相竹": ("竹器", "珍品", 3, 30, 1250, "星陨墟异竹，质地奇特。"),
    "玉京符诏": ("宫货", "珍品", 1, 30, 1600, "玉京台符诏，权贵往来常用。"),
    "白玉冠": ("宫货", "珍品", 2, 30, 1400, "白玉制冠，礼器和宫货兼具。"),
    "云纹佩": ("玉石", "良品", 1, 40, 1180, "云纹玉佩，远销各地。"),
    "天香锦": ("纺织", "良品", 1, 40, 980, "带天香的锦料，礼服常用。"),
    "仙鹤羽": ("宫货", "珍品", 1, 30, 1500, "仙鹤羽饰，轻而稀有。"),
    "金缕册": ("文书", "珍品", 2, 30, 1300, "金线装册，文书礼器两用。"),
    "黑水珠": ("渡货", "良品", 2, 50, 820, "黑水渡水珠，颜色沉亮。"),
    "墨鳞甲": ("兽材", "珍品", 3, 30, 1100, "墨鳞制甲片，防具工坊常收。"),
    "渡魂灯": ("古器", "珍品", 2, 30, 1350, "渡魂用灯，鬼市和古玩商都爱。"),
    "玄水瓶": ("水产", "良品", 2, 50, 760, "能盛玄水的瓶器。"),
    "夜航图": ("文书", "凡品", 1, 60, 640, "黑水渡夜航路线图。"),
    "乌木桨": ("木材", "凡品", 4, 50, 480, "乌木船桨，重货低价。"),
    "兽骨牌": ("兽材", "凡品", 2, 60, 620, "兽骨磨牌，草原常货。"),
    "狼毫笔": ("文书", "凡品", 1, 60, 560, "狼毫制笔，书院和商会都能卖。"),
    "虎纹皮": ("兽材", "良品", 3, 40, 900, "虎纹兽皮，防具和装饰都用。"),
    "灵角": ("兽材", "珍品", 2, 30, 1180, "灵兽角，器修爱收。"),
    "兽魂铃": ("礼器", "珍品", 2, 30, 1350, "能安兽魂的铃，稀有礼器。"),
    "草原玉": ("玉石", "良品", 2, 50, 760, "草原河滩玉，质朴耐看。"),
}


TRADE_LOCATION_DEMANDS = {
    "天枢城": {"文书": 1.16, "礼器": 1.12, "宫货": 1.08, "古器": 1.12},
    "青岚坊": {"竹器": 1.15, "木材": 1.12, "纺织": 1.08, "药材": 1.06},
    "赤霞港": {"水产": 1.15, "盐鲜": 1.12, "海货": 1.08, "丹材": 1.08},
    "玄铁岭": {"矿材": 1.18, "燃料": 1.10, "锻材": 1.14},
    "万药谷": {"药材": 1.18, "香料": 1.08, "木材": 1.06, "丹材": 1.08},
    "云梦泽": {"水产": 1.14, "幻材": 1.15, "纺织": 1.10, "药材": 1.06},
    "流沙海市": {"沙货": 1.18, "矿材": 1.08, "药材": 1.05},
    "寒霜关": {"寒材": 1.18, "矿材": 1.08, "药材": 1.06, "盐鲜": 1.05},
    "雷泽城": {"雷材": 1.20, "符箓": 1.10, "木材": 1.05},
    "碧潮岛": {"海货": 1.18, "水产": 1.10, "龙材": 1.12, "兽材": 1.06},
    "丹霞镇": {"丹材": 1.18, "燃料": 1.10, "瓷器": 1.08},
    "灵木寨": {"木材": 1.18, "兽材": 1.08, "竹器": 1.06},
    "镜湖城": {"湖产": 1.16, "玉石": 1.10, "纺织": 1.08, "礼器": 1.06},
    "幽篁林": {"竹器": 1.18, "香料": 1.10, "文书": 1.08, "符箓": 1.08},
    "星陨墟": {"星材": 1.20, "矿材": 1.08, "古器": 1.10},
    "玉京台": {"宫货": 1.20, "礼器": 1.12, "纺织": 1.08, "文书": 1.08},
    "黑水渡": {"渡货": 1.18, "水产": 1.08, "古器": 1.08, "兽材": 1.06},
    "百兽原": {"兽材": 1.18, "文书": 1.05, "玉石": 1.06},
}


SPECIAL_BUYERS = (
    ("镇妖司", "yaodan,yaogu,yaoxue,yaopi,yaotong,yaohun_suipian", 3.0, 40, 40),
    ("伏魔殿", "mohe,mojiao,moxue,mopi,mozhao,moyanhui", 3.0, -760, 360),
    ("鬼市", "yinhunzhu,guihuo,canhunfan,baigupian,mingzhi,yuanqiping", 3.0, 700, -240),
    ("龙渊阁", "jiaolin,longxu,longxueshi", 3.0, 760, -520),
    ("万兽盟", "shoujin,shouya,shougu,shoupi,shoujiao,shouxin", 2.5, -760, -120),
    ("破军营", "junhunyin,pojia_pian,canbingfu,zhanqi_suibu,xiuxuetie,duanrenpian", 3.2, 260, 760),
)


RECYCLE_LOCATIONS = (
    ("weapon", "铸剑阁", 1.2, -120, 760, "专收探险所得备用武器，回收价稳定但受每日回收曲线影响。"),
    ("gem", "琢玉楼", 1.15, 320, 760, "专收未镶嵌宝石，擅长鉴定灵玉、拆解碎宝。"),
    ("book", "藏经阁", 1.1, 120, 820, "专收未附魔技能书，负责整理残卷、术法和旧拓本。"),
)


MONSTER_DEFS = (
    ("qinglang", "青狼妖", 5, "妖", 90, 15, 8, "yaogu", 0.45),
    ("huyao", "狐妖", 8, "妖", 120, 18, 10, "yaoxue", 0.42),
    ("shanzhu", "山猪兽", 12, "兽", 160, 24, 12, "shouya", 0.4),
    ("baigui", "白骨鬼", 16, "鬼", 190, 29, 16, "baigupian", 0.38),
    ("shayan", "沙魇", 18, "妖", 210, 32, 18, "yinhunzhu", 0.35),
    ("mopi_jiang", "魔皮将", 24, "魔", 290, 40, 24, "mopi", 0.36),
    ("xuanling", "玄铁傀", 28, "傀", 360, 46, 32, "pojia_pian", 0.35),
    ("guijiang", "鬼火将", 32, "鬼", 400, 54, 34, "guihuo", 0.38),
    ("hanpo", "寒魄鬼", 38, "鬼", 480, 62, 42, "yinhunzhu", 0.4),
    ("tiejia_bing", "铁甲残兵", 44, "兵", 560, 74, 48, "pojia_pian", 0.36),
    ("leishou", "雷兽", 52, "兽", 720, 88, 55, "shoujin", 0.35),
    ("yaotong_niao", "妖瞳鸦", 58, "妖", 790, 98, 60, "yaotong", 0.34),
    ("jiaolong", "蛟龙残影", 68, "龙", 980, 120, 70, "jiaolin", 0.32),
    ("longxu_ying", "龙须影", 74, "龙", 1120, 138, 78, "longxu", 0.3),
    ("mohun", "魔魂将", 82, "魔", 1300, 160, 88, "mohe", 0.36),
    ("moyan_shi", "魔焰使", 88, "魔", 1480, 185, 96, "moyanhui", 0.32),
    ("pojun", "破军残将", 95, "兵", 1700, 210, 110, "junhunyin", 0.3),
    ("duanren_jiang", "断刃军魂", 100, "兵", 1900, 235, 122, "duanrenpian", 0.28),
)


WEAPON_SKILLS = (
    ("fengren", "风刃斩", "轻快单体伤害，命中稳定", 6, 3, 1.15),
    ("bengshan", "崩山击", "重击高伤，略带破防", 10, 4, 1.45),
    ("huichun", "回春刺", "造成伤害后少量回血", 7, 5, 1.05),
    ("shaying", "沙影连斩", "连续两段轻伤害", 7, 3, 1.1),
    ("zhuixing", "追星连弩", "多段轻伤害", 12, 4, 1.18),
    ("xueying", "血影割", "造成伤害后按比例回血", 9, 4, 1.2),
    ("pojun", "破军刺", "高穿透单体伤害", 12, 5, 1.42),
    ("wuxiang", "无相剑气", "稳定高伤害", 15, 6, 1.5),
    ("liehun", "裂魂音", "伤害并削弱精神", 10, 5, 1.28),
    ("yueshi", "月蚀斩", "伤害并降低防御", 11, 5, 1.34),
    ("xuandun", "玄盾击", "伤害并获得护盾", 8, 5, 1.15),
    ("zhenyue", "镇岳压", "高伤并短暂减伤", 13, 6, 1.45),
    ("duannian", "断念击", "伤害并压制精神恢复", 10, 5, 1.26),
    ("chuanyun", "穿云破", "高穿透稳定伤害", 12, 5, 1.4),
    ("liuguang", "流光刺", "高速穿刺并提高命中", 9, 4, 1.22),
    ("xingluo", "星落", "多段高伤害", 13, 6, 1.45),
    ("qiankun", "乾坤震", "高稳定伤害", 16, 7, 1.55),
    ("duanhai", "断海劈", "高伤单体劈砍", 13, 5, 1.42),
    ("jueying", "绝影刺", "高速刺击并提高闪避", 9, 4, 1.24),
)


WEAPON_DEFS = (
    ("qinglan_duanjian", "青岚短剑", "青岚坊", 18, "fengren", "剑"),
    ("xuantie_zhongji", "玄铁重戟", "玄铁岭", 36, "bengshan", "戟"),
    ("wanyao_tengzhang", "万药藤杖", "万药谷", 16, "huichun", "杖"),
    ("liusha_feiren", "流沙飞刃", "流沙海市", 20, "shaying", "飞刃"),
    ("zhuixing_nu", "追星弩", "星陨墟", 29, "zhuixing", "弩"),
    ("xuehe_bi", "血河匕", "寒霜关", 28, "xueying", "匕"),
    ("pojun_qiang", "破军枪", "雷泽城", 38, "pojun", "枪"),
    ("wuxiang_zhujian", "无相竹剑", "青岚坊", 27, "wuxiang", "剑"),
    ("zhenhun_ling", "镇魂铃", "寒霜关", 21, "liehun", "铃"),
    ("yueshi_wandao", "月蚀弯刀", "寒霜关", 32, "yueshi", "刀"),
    ("xuangui_dunren", "玄龟盾刃", "碧潮岛", 25, "xuandun", "盾刃"),
    ("zhenyue_fu", "镇岳斧", "玄铁岭", 40, "zhenyue", "斧"),
    ("duannian_zhang", "断念杖", "云梦泽", 23, "duannian", "杖"),
    ("chuanyun_lingqiang", "穿云灵枪", "星陨墟", 37, "chuanyun", "枪"),
    ("liuguang_xijian", "流光细剑", "天枢城", 28, "liuguang", "剑"),
    ("xingluo_fachen", "星落拂尘", "星陨墟", 39, "xingluo", "拂尘"),
    ("qiankun_pan", "乾坤盘", "天枢城", 45, "qiankun", "盘"),
    ("duanhai_jian", "断海剑", "碧潮岛", 33, "duanhai", "剑"),
    ("jueying_feijian", "绝影飞剑", "流沙海市", 32, "jueying", "剑"),
)


WEAPON_ENCHANTS = (
    ("fengren_shu", "风刃书", {"hit_bonus": 0.08}, 2),
    ("poxie_shu", "破甲书", {"pierce_bonus": 0.07}, 3),
    ("huichun_shu", "回春书", {"life_steal": 0.04}, 2),
    ("xuandun_shu", "玄盾书", {"shield_bonus": 0.08}, 2),
    ("xueqi_shu", "血契书", {"life_steal": 0.07}, 3),
    ("duannian_shu", "断念书", {"mp_suppress": 0.12}, 3),
    ("chuanyun_shu", "穿云书", {"pierce_bonus": 0.1}, 4),
    ("yueshi_shu", "月蚀书", {"defense_suppress": 0.08}, 4),
    ("zhuixing_shu", "追星书", {"combo_bonus": 0.07}, 4),
    ("zhenyue_shu", "镇岳书", {"damage_reduce": 0.06}, 4),
    ("wuxiang_shu", "无相书", {"skill_power_bonus": 0.16, "interval_delta": 1}, 5),
    ("bengshan_shu", "崩山书", {"heavy_bonus": 0.12, "interval_delta": 1}, 4),
    ("shaying_shu", "沙影书", {"combo_bonus": 0.05}, 2),
    ("liuguang_shu", "流光书", {"interval_delta": -1}, 3),
    ("xingluo_shu", "星落书", {"combo_damage_bonus": 0.18}, 5),
    ("duanhai_shu", "断海书", {"single_hit_bonus": 0.14, "interval_delta": 1}, 4),
    ("jueying_shu", "绝影书", {"dodge_bonus": 0.04}, 4),
)


class XiuxianDB:
    """修仙玩法数据库访问对象。"""

    def __init__(self, db_path: str | Path = "xiuxian.db") -> None:
        self.db_path = Path(db_path)
        self.conn: sqlite3.Connection | None = None
        self.initialized = False
        self.lock = RLock()

    def init(self) -> None:
        """连接数据库；schema 不匹配时优先迁移，无法迁移才重建。"""

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
                if not self._migrate_schema(current_version):
                    self._drop_tables()
            self._create_tables()
            self._seed_data()
            self._validate_seed_data()
            self._set_schema_version()
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

    def _migrate_schema(self, current_version: int | None) -> bool:
        """按版本补充新字段，避免小 schema 变更重建整库。"""

        if current_version is None:
            return False

        migrated_version = current_version
        if migrated_version == 2026052502 and SCHEMA_VERSION >= 2026052601:
            self._add_column_if_missing(
                "players",
                "battle_log_detail",
                "INTEGER NOT NULL DEFAULT 0",
            )
            migrated_version = 2026052601
        if migrated_version == 2026052601 and SCHEMA_VERSION == 2026052602:
            migrated_version = 2026052602
        return migrated_version == SCHEMA_VERSION

    def _add_column_if_missing(self, table: str, column: str, column_def: str) -> None:
        """表字段不存在时补列。"""

        assert self.conn is not None
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        if any(row["name"] == column for row in rows):
            return
        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
        self.conn.commit()

    def _drop_tables(self) -> None:
        """删除旧 schema 表。"""

        assert self.conn is not None
        self.conn.executescript(
            """
            DROP TABLE IF EXISTS schema_meta;
            DROP TABLE IF EXISTS physique_defs;
            DROP TABLE IF EXISTS players;
            DROP TABLE IF EXISTS source_vaults;
            DROP TABLE IF EXISTS backpack_items;
            DROP TABLE IF EXISTS ring_items;
            DROP TABLE IF EXISTS gem_items;
            DROP TABLE IF EXISTS item_defs;
            DROP TABLE IF EXISTS equipment_item_defs;
            DROP TABLE IF EXISTS second_hand_listings;
            DROP TABLE IF EXISTS second_hand_records;
            DROP TABLE IF EXISTS trade_locations;
            DROP TABLE IF EXISTS trade_goods;
            DROP TABLE IF EXISTS trade_prices;
            DROP TABLE IF EXISTS trade_inventory;
            DROP TABLE IF EXISTS trade_records;
            DROP TABLE IF EXISTS trade_daily_rewards;
            DROP TABLE IF EXISTS trade_limits;
            DROP TABLE IF EXISTS special_buyers;
            DROP TABLE IF EXISTS recycle_locations;
            DROP TABLE IF EXISTS weapon_recycle_locations;
            DROP TABLE IF EXISTS weapon_recycle_records;
            DROP TABLE IF EXISTS gem_recycle_records;
            DROP TABLE IF EXISTS book_recycle_records;
            DROP TABLE IF EXISTS exploration_locations;
            DROP TABLE IF EXISTS exploration_records;
            DROP TABLE IF EXISTS drop_tables;
            DROP TABLE IF EXISTS monster_defs;
            DROP TABLE IF EXISTS weapon_defs;
            DROP TABLE IF EXISTS weapon_skill_defs;
            DROP TABLE IF EXISTS player_weapons;
            DROP TABLE IF EXISTS weapon_enchants;
            DROP TABLE IF EXISTS weapon_enchant_names;
            DROP TABLE IF EXISTS fixed_equipment;
            DROP TABLE IF EXISTS inlay_defs;
            DROP TABLE IF EXISTS gem_defs;
            DROP TABLE IF EXISTS fixed_equipment_inlays;
            DROP TABLE IF EXISTS inscription_feathers;
            DROP TABLE IF EXISTS seasonal_boss_reward_rates;
            DROP TABLE IF EXISTS seasonal_boss_events;
            DROP TABLE IF EXISTS seasonal_boss_participants;
            DROP TABLE IF EXISTS duel_requests;
            DROP TABLE IF EXISTS duel_records;
            DROP TABLE IF EXISTS robbery_records;
            DROP TABLE IF EXISTS player_hatreds;
            DROP TABLE IF EXISTS combat_logs;
            DROP TABLE IF EXISTS wormholes;
            DROP TABLE IF EXISTS wormhole_participants;
            DROP TABLE IF EXISTS wormhole_notices;
            DROP TABLE IF EXISTS game_logs;
            DROP TABLE IF EXISTS player_journals;
            DROP TABLE IF EXISTS player_titles;
            DROP TABLE IF EXISTS player_lifetime_stats;
            DROP TABLE IF EXISTS daily_fortunes;
            DROP TABLE IF EXISTS daily_newspapers;
            DROP TABLE IF EXISTS weapon_legends;
            DROP TABLE IF EXISTS trade_heat;
            DROP TABLE IF EXISTS bag_items;
            DROP TABLE IF EXISTS treasures;
            DROP TABLE IF EXISTS market_listings;
            DROP TABLE IF EXISTS market_records;
            """
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
                physique INTEGER NOT NULL DEFAULT 0,
                base_attack INTEGER NOT NULL DEFAULT 5,
                defense INTEGER NOT NULL DEFAULT 0,
                source_stones INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT '空闲',
                status_until_at TEXT,
                location_name TEXT NOT NULL DEFAULT '天枢城',
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

            CREATE TABLE IF NOT EXISTS source_vaults (
                client_id TEXT PRIMARY KEY,
                level INTEGER NOT NULL DEFAULT 1,
                balance INTEGER NOT NULL DEFAULT 0,
                last_settle_at TEXT NOT NULL,
                last_interest_day TEXT,
                daily_interest INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS backpack_items (
                client_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, item_id)
            );

            CREATE TABLE IF NOT EXISTS ring_items (
                client_id TEXT NOT NULL,
                equipment_item_id TEXT NOT NULL,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, equipment_item_id)
            );

            CREATE TABLE IF NOT EXISTS gem_items (
                client_id TEXT NOT NULL,
                gem_id TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 1,
                quantity INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, gem_id, level)
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

            CREATE TABLE IF NOT EXISTS equipment_item_defs (
                equipment_item_id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                quality TEXT NOT NULL,
                usable INTEGER NOT NULL DEFAULT 0,
                target_type TEXT NOT NULL DEFAULT '玩家',
                effect TEXT NOT NULL DEFAULT '{}',
                desc TEXT NOT NULL DEFAULT ''
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
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_locations (
                name TEXT PRIMARY KEY,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                specialties TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_goods (
                item_id TEXT PRIMARY KEY,
                home_location TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_prices (
                location_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                buy_price INTEGER NOT NULL,
                sell_price INTEGER NOT NULL,
                business_day TEXT NOT NULL,
                PRIMARY KEY (location_name, item_id, business_day)
            );

            CREATE TABLE IF NOT EXISTS trade_heat (
                location_name TEXT NOT NULL,
                item_id TEXT NOT NULL,
                business_day TEXT NOT NULL,
                buy_count INTEGER NOT NULL DEFAULT 0,
                sell_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (location_name, item_id, business_day)
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
                business_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trade_daily_rewards (
                client_id TEXT NOT NULL,
                business_day TEXT NOT NULL,
                sell_quantity INTEGER NOT NULL,
                net_income INTEGER NOT NULL,
                reward INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (client_id, business_day)
            );

            CREATE TABLE IF NOT EXISTS trade_limits (
                client_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
                last_buy_at TEXT NOT NULL,
                last_buy_price INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (client_id, item_id, location_name)
            );

            CREATE TABLE IF NOT EXISTS special_buyers (
                buyer_name TEXT PRIMARY KEY,
                item_ids TEXT NOT NULL,
                price_factor REAL NOT NULL,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recycle_locations (
                name TEXT PRIMARY KEY,
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
                business_day TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS exploration_locations (
                name TEXT PRIMARY KEY,
                recommended_level INTEGER NOT NULL,
                min_level INTEGER NOT NULL,
                max_level INTEGER NOT NULL,
                desc TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS exploration_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                location_name TEXT NOT NULL,
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
                base_attack INTEGER NOT NULL,
                skill_id TEXT NOT NULL,
                weapon_type TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS player_weapons (
                weapon_id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                weapon_def_id TEXT NOT NULL,
                level INTEGER NOT NULL DEFAULT 0,
                max_level INTEGER NOT NULL,
                quality TEXT NOT NULL,
                attack INTEGER NOT NULL,
                skill_id TEXT NOT NULL,
                enchant_slots INTEGER NOT NULL DEFAULT 0,
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
            CREATE INDEX IF NOT EXISTS idx_ring_client ON ring_items(client_id);
            CREATE INDEX IF NOT EXISTS idx_gem_client ON gem_items(client_id);
            CREATE INDEX IF NOT EXISTS idx_physique_level ON physique_defs(level, physique_value);
            CREATE INDEX IF NOT EXISTS idx_trade_records_client ON trade_records(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_trade_daily_rewards_day ON trade_daily_rewards(business_day);
            CREATE INDEX IF NOT EXISTS idx_trade_heat_day ON trade_heat(business_day, location_name, item_id);
            CREATE INDEX IF NOT EXISTS idx_weapon_recycle_day ON weapon_recycle_records(client_id, business_day);
            CREATE INDEX IF NOT EXISTS idx_gem_recycle_day ON gem_recycle_records(client_id, business_day);
            CREATE INDEX IF NOT EXISTS idx_book_recycle_day ON book_recycle_records(client_id, business_day);
            CREATE INDEX IF NOT EXISTS idx_exploration_client ON exploration_records(client_id, claimed);
            CREATE INDEX IF NOT EXISTS idx_inscription_feathers_client ON inscription_feathers(client_id, feather_id);
            CREATE INDEX IF NOT EXISTS idx_seasonal_boss_status ON seasonal_boss_events(status, closes_at);
            CREATE INDEX IF NOT EXISTS idx_seasonal_boss_participants_client ON seasonal_boss_participants(client_id, reward_claimed);
            CREATE INDEX IF NOT EXISTS idx_duel_to_client ON duel_requests(to_client_id, status);
            CREATE INDEX IF NOT EXISTS idx_robbery_record_target ON robbery_records(exploration_record_id, target_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_robbery_record_once ON robbery_records(exploration_record_id, robber_id);
            CREATE INDEX IF NOT EXISTS idx_player_hatreds_target ON player_hatreds(to_client_id, hate_value);
            CREATE INDEX IF NOT EXISTS idx_wormholes_status ON wormholes(status, closes_at);
            CREATE INDEX IF NOT EXISTS idx_wormhole_participants_client ON wormhole_participants(client_id, reward_claimed);
            CREATE INDEX IF NOT EXISTS idx_game_logs_client ON game_logs(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_player_journals_client ON player_journals(client_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_player_titles_client ON player_titles(client_id, active);
            CREATE INDEX IF NOT EXISTS idx_player_lifetime_stats_key ON player_lifetime_stats(stat_key, stat_value);
            CREATE INDEX IF NOT EXISTS idx_daily_fortunes_day ON daily_fortunes(business_day);
            CREATE INDEX IF NOT EXISTS idx_weapon_legends_owner ON weapon_legends(current_owner_id);
            """
        )
        self.conn.commit()

    def _seed_data(self) -> None:
        """写入基础配置数据。"""

        assert self.conn is not None
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO physique_defs
            (physique_id, name, grade, kind, level, physique_value, effect, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row[:-2], json.dumps(row[-2], ensure_ascii=False), row[-1]) for row in PHYSIQUE_DEFS],
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
            INSERT OR REPLACE INTO equipment_item_defs
            (equipment_item_id, name, category, quality, usable, target_type, effect, desc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [(*row[:-2], json.dumps(row[-2], ensure_ascii=False), row[-1]) for row in EQUIPMENT_ITEM_DEFS],
        )
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
        self.conn.executemany(
            "INSERT OR REPLACE INTO trade_locations (name, x, y, specialties) VALUES (?, ?, ?, ?)",
            TRADE_LOCATIONS,
        )
        for _location, _x, _y, specialties in TRADE_LOCATIONS:
            for name in specialties.split(","):
                trade_def = TRADE_ITEM_DEFS.get(name)
                if not trade_def:
                    raise RuntimeError(f"跑商特产缺少定价：{_location}/{name}")
                trade_type, quality, weight, stack_limit, base_price, desc = trade_def
                item = self.conn.execute("SELECT item_id FROM item_defs WHERE name = ?", (name,)).fetchone()
                item_id = item["item_id"] if item else "trade_" + hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
                effect = json.dumps(
                    {"trade_type": trade_type, "home_location": _location},
                    ensure_ascii=False,
                )
                self.conn.execute(
                    """
                    INSERT INTO item_defs
                    (item_id, name, category, quality, weight, stack_limit, tradeable, usable, base_price, effect, desc)
                    VALUES (?, ?, '地点特产', ?, ?, ?, 1, 0, ?, ?, ?)
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
                    (item_id, name, quality, weight, stack_limit, base_price, effect, desc),
                )
        trade_goods = []
        for location, _x, _y, specialties in TRADE_LOCATIONS:
            for name in specialties.split(","):
                item = self.conn.execute("SELECT item_id FROM item_defs WHERE name = ?", (name,)).fetchone()
                if item:
                    trade_goods.append((item["item_id"], location))
        self.conn.executemany(
            "INSERT OR REPLACE INTO trade_goods (item_id, home_location) VALUES (?, ?)",
            trade_goods,
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO special_buyers
            (buyer_name, item_ids, price_factor, x, y)
            VALUES (?, ?, ?, ?, ?)
            """,
            SPECIAL_BUYERS,
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO recycle_locations
            (recycle_type, name, price_factor, x, y, desc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            RECYCLE_LOCATIONS,
        )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO monster_defs
            (monster_id, name, level, kind, hp, attack, defense, drop_item_id, drop_chance)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            MONSTER_DEFS,
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
            (weapon_def_id, name, drop_location, base_attack, skill_id, weapon_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            WEAPON_DEFS,
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
            "INSERT OR IGNORE INTO exploration_locations (name, recommended_level, min_level, max_level, desc) VALUES (?, ?, ?, ?, ?)",
            (
                ("天枢城", 1, 1, 12, "城外浅野，适合刚入门的道友。"),
                ("青岚坊", 1, 1, 20, "新手常去的灵林。"),
                ("赤霞港", 10, 8, 28, "水火气息交错。"),
                ("玄铁岭", 20, 18, 45, "傀儡和矿脉并存。"),
                ("万药谷", 25, 20, 50, "药香浓重，妖兽不少。"),
                ("云梦泽", 30, 25, 55, "幻雾弥漫。"),
                ("流沙海市", 40, 35, 70, "风沙和妖物都不少。"),
                ("寒霜关", 50, 45, 80, "寒气极重，鬼物出没。"),
                ("雷泽城", 60, 55, 90, "雷兽和残阵密布。"),
                ("碧潮岛", 65, 60, 95, "水族和海兽盘踞。"),
                ("星陨墟", 75, 70, 100, "高等级探险地。"),
            ),
        )
        self.conn.commit()

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

        names = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM item_defs").fetchall()
        }
        equipment_names = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM equipment_item_defs").fetchall()
        }
        duplicated_names = names & equipment_names
        if duplicated_names:
            missing.append(f"背包物品和纳戒物品重名：{','.join(sorted(duplicated_names))}")

        gem_rows = self.conn.execute(
            "SELECT name, effect FROM equipment_item_defs WHERE category = '宝石'"
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
            for name in specialties.split(","):
                if name not in TRADE_ITEM_DEFS:
                    missing.append(f"跑商特产缺少定价：{location}/{name}")
                if name not in names:
                    missing.append(f"跑商特产未落背包物品定义：{location}/{name}")
        trade_names = {
            name
            for _location, _x, _y, specialties in TRADE_LOCATIONS
            for name in specialties.split(",")
        }
        extra_trade_defs = set(TRADE_ITEM_DEFS) - trade_names
        if extra_trade_defs:
            missing.append(f"跑商定价未被地点使用：{','.join(sorted(extra_trade_defs))}")

        item_ids = {
            row["item_id"]
            for row in self.conn.execute("SELECT item_id FROM item_defs").fetchall()
        }
        for buyer_name, item_ids_text, _factor, _x, _y in SPECIAL_BUYERS:
            for item_id in item_ids_text.split(","):
                if item_id not in item_ids:
                    missing.append(f"特殊收购物不存在：{buyer_name}/{item_id}")

        for monster_id, _name, *_rest, drop_item_id, _chance in MONSTER_DEFS:
            if drop_item_id and drop_item_id not in item_ids:
                missing.append(f"怪物掉落物不存在：{monster_id}/{drop_item_id}")

        skill_ids = {
            row["skill_id"]
            for row in self.conn.execute("SELECT skill_id FROM weapon_skill_defs").fetchall()
        }
        for weapon_def_id, _name, _location, _attack, skill_id, _weapon_type in WEAPON_DEFS:
            if skill_id not in skill_ids:
                missing.append(f"武器技能不存在：{weapon_def_id}/{skill_id}")

        enchant_ids = {
            row["enchant_id"]
            for row in self.conn.execute("SELECT enchant_id FROM weapon_enchants").fetchall()
        }
        rows = self.conn.execute(
            "SELECT equipment_item_id, name, effect FROM equipment_item_defs WHERE category = '技能书'"
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


__all__ = ["XiuxianDB", "db"]
