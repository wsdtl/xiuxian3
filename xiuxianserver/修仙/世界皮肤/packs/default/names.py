# 世界皮肤包名称数据文件。
# 这是“受限 Python 数据文件”，不是可执行插件：加载器只会读取 NAMES 这个字面量字典。
# 左侧键名是系统稳定 ID，例如 city_tianshu、xueqidan、liuguang_xijian，不要改。
# 右侧中文字符串才是皮肤包展示名，正常换风格时主要改这些中文值。
# 只允许写字典、列表、字符串、数字这类字面量；不要添加 import、函数调用、变量拼接或运行时代码。
# 岁时情劫剧情和铭刻之羽不在世界皮肤包里；但首领奖励掉落到的通用物品、武器、宝石会跟随本文件显示。

NAMES = {
    # 地点体系：系统自带的保留地点、普通城池、秘境、特殊收购点、回收建筑都在这里换名。
    "places": {
        # 11 个普通城池。它们同时承担跑商、探险、城池状态、武器产地、藏宝图、虫洞锚点等职责。
        # 每个 city_xxx 是稳定城池 ID；改皮肤时只改 name 和下属物品/武器的中文名。
        "cities": {
            # 单个城池配置示例，后面的城池结构都一样。
            "city_tianshu": {
                # 城池显示名：地图、导航、跑商、探险、城池回收归属都会显示这个名字。
                "name": "天枢城",
                # 地貌显示名：只用于地图、百科和地点描述，不参与任何数值规则。
                "terrain": "城镇",
                # 系统职责标签：代码按这些标签识别地点用途，正常换皮不要改。
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                # 城池特产：每个普通城池固定 3 个纯经济跑商货，只用于地域差价和商路流动。
                # 只改右侧商品名；左侧 trade_city_xxx_序号 是稳定货物 ID。
                "trade_goods": {
                    "trade_city_tianshu_01": "星官旧简",
                    "trade_city_tianshu_02": "白契纸",
                    "trade_city_tianshu_03": "旧朝钱"
                },
                # 城池武器：该城可产出的特色武器池，藏宝图稀品武器也会参考这里。
                # 武器键名不要改；name 是武器显示名；innate_skill 是这把武器天生绑定的技能显示。
                "weapons": {
                    "liuguang_xijian": {
                        "name": "流光细剑",
                        "innate_skill": {
                            # skill_id 是稳定技能 ID，战斗逻辑认它；name 才是玩家看到的技能名。
                            "skill_id": "liuguang",
                            "name": "流光刺"
                        }
                    },
                    "qiankun_pan": {
                        "name": "乾坤盘",
                        "innate_skill": {
                            "skill_id": "qiankun",
                            "name": "乾坤震"
                        }
                    },
                    "tianji_yuling": {
                        "name": "天机玉令",
                        "innate_skill": {
                            "skill_id": "tianji",
                            "name": "天机扣弦"
                        }
                    },
                    "xingheng_fuchen": {
                        "name": "星衡拂尘",
                        "innate_skill": {
                            "skill_id": "xingheng",
                            "name": "星衡拂尘"
                        }
                    },
                    "qingxin_ling": {
                        "name": "清心铃",
                        "innate_skill": {
                            "skill_id": "qingxin",
                            "name": "清心定铃"
                        }
                    },
                    "yujing_fujian": {
                        "name": "玉京符剑",
                        "innate_skill": {
                            "skill_id": "yujing",
                            "name": "玉京敕剑"
                        }
                    },
                    "tianxiang_ling": {
                        "name": "天香铃",
                        "innate_skill": {
                            "skill_id": "tianxiang",
                            "name": "天香护铃"
                        }
                    }
                }
            },
            "city_qinglan": {
                "name": "青岚坊",
                "terrain": "森林",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_qinglan_01": "风骨玉",
                    "trade_city_qinglan_02": "听风纸",
                    "trade_city_qinglan_03": "雨竹简"
                },
                "weapons": {
                    "qinglan_duanjian": {
                        "name": "青岚短剑",
                        "innate_skill": {
                            "skill_id": "fengren",
                            "name": "风刃斩"
                        }
                    },
                    "wuxiang_zhujian": {
                        "name": "无相竹剑",
                        "innate_skill": {
                            "skill_id": "wuxiang",
                            "name": "无相剑气"
                        }
                    },
                    "lanzhao_feiren": {
                        "name": "岚照飞刃",
                        "innate_skill": {
                            "skill_id": "lanzhao",
                            "name": "岚照回旋"
                        }
                    },
                    "qingzhu_dunren": {
                        "name": "青竹盾刃",
                        "innate_skill": {
                            "skill_id": "qingzhu_dun",
                            "name": "青竹回守"
                        }
                    },
                    "qingteng_bi": {
                        "name": "青藤匕",
                        "innate_skill": {
                            "skill_id": "qingteng",
                            "name": "青藤缠刺"
                        }
                    },
                    "youhuang_ling": {
                        "name": "幽篁竹铃",
                        "innate_skill": {
                            "skill_id": "youhuang",
                            "name": "幽篁清音"
                        }
                    },
                    "mozhu_jian": {
                        "name": "墨竹剑",
                        "innate_skill": {
                            "skill_id": "mozhu",
                            "name": "墨竹点影"
                        }
                    }
                }
            },
            "city_chixia": {
                "name": "赤霞港",
                "terrain": "港湾",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_chixia_01": "晚潮珠",
                    "trade_city_chixia_02": "火纹贝",
                    "trade_city_chixia_03": "舶牙牌"
                },
                "weapons": {
                    "chixia_duandao": {
                        "name": "赤霞短刀",
                        "innate_skill": {
                            "skill_id": "chixia",
                            "name": "赤霞燃斩"
                        }
                    },
                    "chaohuo_qiang": {
                        "name": "潮火枪",
                        "innate_skill": {
                            "skill_id": "chaohuo",
                            "name": "潮火贯日"
                        }
                    },
                    "yanbei_nu": {
                        "name": "炎贝弩",
                        "innate_skill": {
                            "skill_id": "yanbei",
                            "name": "炎贝连弩"
                        }
                    },
                    "yandu_wandao": {
                        "name": "焰毒弯刀",
                        "innate_skill": {
                            "skill_id": "yandu",
                            "name": "焰毒缠刃"
                        }
                    },
                    "dansha_feiren": {
                        "name": "丹砂飞刃",
                        "innate_skill": {
                            "skill_id": "dansha",
                            "name": "丹砂点火"
                        }
                    },
                    "zhuyan_dao": {
                        "name": "朱焰刀",
                        "innate_skill": {
                            "skill_id": "zhuyan",
                            "name": "朱焰断浪"
                        }
                    },
                    "chilian_wandao": {
                        "name": "赤炼弯刀",
                        "innate_skill": {
                            "skill_id": "chilian",
                            "name": "赤炼毒火"
                        }
                    }
                }
            },
            "city_xuantie": {
                "name": "玄铁岭",
                "terrain": "山岭",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_xuantie_01": "山铜契",
                    "trade_city_xuantie_02": "黑矿票",
                    "trade_city_xuantie_03": "老炉印"
                },
                "weapons": {
                    "xuantie_zhongji": {
                        "name": "玄铁重戟",
                        "innate_skill": {
                            "skill_id": "bengshan",
                            "name": "崩山击"
                        }
                    },
                    "zhenyue_fu": {
                        "name": "镇岳斧",
                        "innate_skill": {
                            "skill_id": "zhenyue",
                            "name": "镇岳压"
                        }
                    },
                    "heiyao_dunren": {
                        "name": "黑曜盾刃",
                        "innate_skill": {
                            "skill_id": "heiyao",
                            "name": "黑曜格挡"
                        }
                    },
                    "fanyue_pan": {
                        "name": "返岳盘",
                        "innate_skill": {
                            "skill_id": "fanyue",
                            "name": "返岳震"
                        }
                    },
                    "luxin_fu": {
                        "name": "炉心斧",
                        "innate_skill": {
                            "skill_id": "luxin",
                            "name": "炉心崩火"
                        }
                    },
                    "lingjiao_ji": {
                        "name": "灵角战戟",
                        "innate_skill": {
                            "skill_id": "lingjiao",
                            "name": "灵角破阵"
                        }
                    },
                    "guming_dunren": {
                        "name": "骨鸣盾刃",
                        "innate_skill": {
                            "skill_id": "guming",
                            "name": "骨鸣反阵"
                        }
                    }
                }
            },
            "city_wanyao": {
                "name": "万药谷",
                "terrain": "药谷",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_wanyao_01": "谷市筹",
                    "trade_city_wanyao_02": "灵圃帖",
                    "trade_city_wanyao_03": "青囊账"
                },
                "weapons": {
                    "wanyao_tengzhang": {
                        "name": "万药藤杖",
                        "innate_skill": {
                            "skill_id": "huichun",
                            "name": "回春刺"
                        }
                    },
                    "lingfeng_bi": {
                        "name": "灵蜂匕",
                        "innate_skill": {
                            "skill_id": "lingfeng",
                            "name": "灵蜂针"
                        }
                    },
                    "yaowang_fuchen": {
                        "name": "药王拂尘",
                        "innate_skill": {
                            "skill_id": "yaowang",
                            "name": "药王拂尘"
                        }
                    },
                    "fengwang_ling": {
                        "name": "蜂王铃",
                        "innate_skill": {
                            "skill_id": "fengwang",
                            "name": "蜂王镇音"
                        }
                    },
                    "lingmu_zhang": {
                        "name": "灵木杖",
                        "innate_skill": {
                            "skill_id": "lingmu",
                            "name": "灵木回环"
                        }
                    },
                    "luming_qiang": {
                        "name": "鹿鸣枪",
                        "innate_skill": {
                            "skill_id": "luming",
                            "name": "鹿鸣突阵"
                        }
                    },
                    "zhupo_zhang": {
                        "name": "竹魄杖",
                        "innate_skill": {
                            "skill_id": "zhupo",
                            "name": "竹魄断神"
                        }
                    }
                }
            },
            "city_yunmeng": {
                "name": "云梦泽",
                "terrain": "水泽",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_yunmeng_01": "雾泽贝",
                    "trade_city_yunmeng_02": "蜃雾珠",
                    "trade_city_yunmeng_03": "水市牌"
                },
                "weapons": {
                    "duannian_zhang": {
                        "name": "断念杖",
                        "innate_skill": {
                            "skill_id": "duannian",
                            "name": "断念击"
                        }
                    },
                    "mengwu_ling": {
                        "name": "梦雾铃",
                        "innate_skill": {
                            "skill_id": "mengwu",
                            "name": "梦雾摄心"
                        }
                    },
                    "shuijing_jian": {
                        "name": "水镜剑",
                        "innate_skill": {
                            "skill_id": "shuijing",
                            "name": "水镜回剑"
                        }
                    },
                    "nimeng_deng": {
                        "name": "溺梦灯",
                        "innate_skill": {
                            "skill_id": "nimeng",
                            "name": "溺梦照影"
                        }
                    },
                    "jinghu_xijian": {
                        "name": "镜湖细剑",
                        "innate_skill": {
                            "skill_id": "jinghu",
                            "name": "镜湖回剑"
                        }
                    },
                    "heishui_bi": {
                        "name": "黑水匕",
                        "innate_skill": {
                            "skill_id": "heishui",
                            "name": "黑水潜刺"
                        }
                    },
                    "duhun_deng": {
                        "name": "渡魂灯",
                        "innate_skill": {
                            "skill_id": "duhun",
                            "name": "渡魂照影"
                        }
                    }
                }
            },
            "city_liusha": {
                "name": "流沙海市",
                "terrain": "荒漠",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_liusha_01": "走沙晶",
                    "trade_city_liusha_02": "驼铃金",
                    "trade_city_liusha_03": "驼队牌"
                },
                "weapons": {
                    "liusha_feiren": {
                        "name": "流沙飞刃",
                        "innate_skill": {
                            "skill_id": "shaying",
                            "name": "沙影连斩"
                        }
                    },
                    "jueying_feijian": {
                        "name": "绝影飞剑",
                        "innate_skill": {
                            "skill_id": "jueying",
                            "name": "绝影刺"
                        }
                    },
                    "duyun_wandao": {
                        "name": "毒云弯刀",
                        "innate_skill": {
                            "skill_id": "duyun",
                            "name": "毒云蚀骨"
                        }
                    },
                    "shajin_dao": {
                        "name": "沙烬刀",
                        "innate_skill": {
                            "skill_id": "shajin",
                            "name": "沙烬割"
                        }
                    },
                    "yingye_feiren": {
                        "name": "影叶飞刃",
                        "innate_skill": {
                            "skill_id": "yingye",
                            "name": "影叶截脉"
                        }
                    },
                    "langhao_feiren": {
                        "name": "狼毫飞刃",
                        "innate_skill": {
                            "skill_id": "langhao",
                            "name": "狼毫游猎"
                        }
                    }
                }
            },
            "city_hanshuang": {
                "name": "寒霜关",
                "terrain": "雪原",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_hanshuang_01": "冷玉髓",
                    "trade_city_hanshuang_02": "雪关牒",
                    "trade_city_hanshuang_03": "霜市帖"
                },
                "weapons": {
                    "xuehe_bi": {
                        "name": "血河匕",
                        "innate_skill": {
                            "skill_id": "xueying",
                            "name": "血影割"
                        }
                    },
                    "zhenhun_ling": {
                        "name": "镇魂铃",
                        "innate_skill": {
                            "skill_id": "liehun",
                            "name": "裂魂音"
                        }
                    },
                    "yueshi_wandao": {
                        "name": "月蚀弯刀",
                        "innate_skill": {
                            "skill_id": "yueshi",
                            "name": "月蚀斩"
                        }
                    },
                    "hanyan_fuchen": {
                        "name": "寒焰拂尘",
                        "innate_skill": {
                            "skill_id": "hanyan",
                            "name": "寒焰拂"
                        }
                    },
                    "yuehen_bi": {
                        "name": "月痕匕",
                        "innate_skill": {
                            "skill_id": "yuehen",
                            "name": "月痕潜刺"
                        }
                    },
                    "chenyuan_dao": {
                        "name": "沉渊刀",
                        "innate_skill": {
                            "skill_id": "chenyuan",
                            "name": "沉渊血火"
                        }
                    }
                }
            },
            "city_leize": {
                "name": "雷泽城",
                "terrain": "雷泽",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_leize_01": "伏雷鼓",
                    "trade_city_leize_02": "惊雷符",
                    "trade_city_leize_03": "旧雷令"
                },
                "weapons": {
                    "pojun_qiang": {
                        "name": "破军枪",
                        "innate_skill": {
                            "skill_id": "pojun",
                            "name": "破军刺"
                        }
                    },
                    "leiguang_duanren": {
                        "name": "雷光短刃",
                        "innate_skill": {
                            "skill_id": "leiguang",
                            "name": "雷光乱刃"
                        }
                    },
                    "zidian_fu": {
                        "name": "紫电斧",
                        "innate_skill": {
                            "skill_id": "zidian",
                            "name": "紫电裂山"
                        }
                    },
                    "leihou_dunren": {
                        "name": "雷吼盾刃",
                        "innate_skill": {
                            "skill_id": "leihou",
                            "name": "雷吼格"
                        }
                    },
                    "guigen_dunren": {
                        "name": "归根盾刃",
                        "innate_skill": {
                            "skill_id": "guigen",
                            "name": "归根守"
                        }
                    },
                    "shouhun_ling": {
                        "name": "兽魂铃",
                        "innate_skill": {
                            "skill_id": "shouhun",
                            "name": "兽魂震铃"
                        }
                    }
                }
            },
            "city_bichao": {
                "name": "碧潮岛",
                "terrain": "海岛",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_bichao_01": "青潮珊",
                    "trade_city_bichao_02": "月汐珠",
                    "trade_city_bichao_03": "水府玉"
                },
                "weapons": {
                    "xuangui_dunren": {
                        "name": "玄龟盾刃",
                        "innate_skill": {
                            "skill_id": "xuandun",
                            "name": "玄盾击"
                        }
                    },
                    "duanhai_jian": {
                        "name": "断海剑",
                        "innate_skill": {
                            "skill_id": "duanhai",
                            "name": "断海劈"
                        }
                    },
                    "chaoxi_fuchen": {
                        "name": "潮汐拂尘",
                        "innate_skill": {
                            "skill_id": "chaoxi",
                            "name": "潮汐牵引"
                        }
                    },
                    "cangming_ji": {
                        "name": "沧溟战戟",
                        "innate_skill": {
                            "skill_id": "cangming",
                            "name": "沧溟破潮"
                        }
                    },
                    "yingyue_pan": {
                        "name": "映月盘",
                        "innate_skill": {
                            "skill_id": "yingyue",
                            "name": "映月镇潮"
                        }
                    },
                    "wumu_dunren": {
                        "name": "乌木盾刃",
                        "innate_skill": {
                            "skill_id": "wumu",
                            "name": "乌木沉舟"
                        }
                    }
                }
            },
            "city_xingyun": {
                "name": "星陨墟",
                "terrain": "遗迹",
                "roles": [
                    "trade",
                    "exploration",
                    "city_state",
                    "weapon_origin",
                    "treasure_map",
                    "wormhole_anchor"
                ],
                "trade_goods": {
                    "trade_city_xingyun_01": "星砂瓶",
                    "trade_city_xingyun_02": "陨碑拓",
                    "trade_city_xingyun_03": "观星券"
                },
                "weapons": {
                    "zhuixing_nu": {
                        "name": "追星弩",
                        "innate_skill": {
                            "skill_id": "zhuixing",
                            "name": "追星连弩"
                        }
                    },
                    "chuanyun_lingqiang": {
                        "name": "穿云灵枪",
                        "innate_skill": {
                            "skill_id": "chuanyun",
                            "name": "穿云破"
                        }
                    },
                    "xingluo_fachen": {
                        "name": "星落拂尘",
                        "innate_skill": {
                            "skill_id": "xingluo",
                            "name": "星落"
                        }
                    },
                    "yunxing_pan": {
                        "name": "陨星盘",
                        "innate_skill": {
                            "skill_id": "yunxing",
                            "name": "陨星定盘"
                        }
                    },
                    "jinlu_pan": {
                        "name": "金缕天盘",
                        "innate_skill": {
                            "skill_id": "jinlu",
                            "name": "金缕封天"
                        }
                    },
                    "zhuxie_qiang": {
                        "name": "诛邪枪",
                        "innate_skill": {
                            "skill_id": "zhuxie",
                            "name": "诛邪贯阵"
                        }
                    }
                }
            }
        },
        # 特殊秘境地点：目前太虚秘境是动态特殊战斗点，不按普通城池显示推荐等级。
        "realm": {
            "realm_taixu": {
                "name": "太虚秘境",
                "terrain": "秘境",
                "roles": [
                    "secret_realm",
                    "dynamic_battle"
                ]
            }
        },
        # 特殊收购点：用于战备/战利品去路等系统收购，不是普通跑商城池。
        # 这些地点属于系统保留地点，玩家宗门不能建在这些坐标上。
        "buyers": {
            "buyer_zhenyaosi": {
                "name": "镇妖司",
                "terrain": "城镇",
                "roles": [
                    "special_buyer",
                    "war_prep"
                ]
            },
            "buyer_fumodian": {
                "name": "伏魔殿",
                "terrain": "遗迹",
                "roles": [
                    "special_buyer",
                    "war_prep"
                ]
            },
            "buyer_guishi": {
                "name": "鬼市",
                "terrain": "阴市",
                "roles": [
                    "special_buyer",
                    "war_prep"
                ]
            },
            "buyer_longyuan": {
                "name": "龙渊阁",
                "terrain": "水泽",
                "roles": [
                    "special_buyer",
                    "war_prep"
                ]
            },
            "buyer_wanshou": {
                "name": "万兽盟",
                "terrain": "草原",
                "roles": [
                    "special_buyer",
                    "war_prep"
                ]
            },
            "buyer_pojun": {
                "name": "破军营",
                "terrain": "军营",
                "roles": [
                    "special_buyer",
                    "war_prep"
                ]
            }
        },
        # 回收建筑：武器、宝石、技能书等纳戒物品的专门回收地点。
        # 背包世界物资走城池回收，纳戒高价值物品走这里的专业回收。
        "recycles": {
            "recycle_weapon": {
                "name": "铸剑阁",
                "terrain": "山岭",
                "roles": [
                    "recycle"
                ]
            },
            "recycle_gem": {
                "name": "琢玉楼",
                "terrain": "湖泽",
                "roles": [
                    "recycle"
                ]
            },
            "recycle_book": {
                "name": "藏经阁",
                "terrain": "城镇",
                "roles": [
                    "recycle"
                ]
            }
        }
    },
    # 世界物资：探险/秘境/跑商/回收体系里的“世界流动物品”。
    # 这些物品不是玩家装备，主要通过回收流入城池或特殊系统，影响后续世界状态。
    "world_items": {
        # 药路物资：药材、丹材、燃料。跑商结算时影响当地恢复药补给和顺药概率。
        "medicine": {
            # 药材：偏自然采集来源，和恢复药补给的基础来源相关。
            "material": {
                "world_med_xueqidan_1": "血藤籽",
                "world_med_xueqidan_2": "赤契砂",
                "world_med_yinmingcao_1": "阴冥芽",
                "world_med_yinmingcao_2": "寒魄霜",
                "world_med_huichunlu_1": "回春露草",
                "world_med_huichunlu_2": "蜂王浆",
                "world_med_ningshenlu_1": "水镜草",
                "world_med_ningshenlu_2": "静神兰"
            },
            # 丹材：偏炼制辅料，强化药品生成质量和补给稳定性。
            "catalyst": {
                "world_med_shenggudan_1": "生骨泥",
                "world_med_shenggudan_2": "赤骨石",
                "world_med_yanghundan_1": "养魂叶",
                "world_med_yanghundan_2": "朱羽引"
            },
            # 燃料：偏炼炉消耗，影响药品补给效率，不直接当恢复药使用。
            "fuel": {
                "world_med_xueqidan_3": "伏火炭",
                "world_med_yinmingcao_3": "冷炉灰",
                "world_med_huichunlu_3": "温木炭",
                "world_med_ningshenlu_3": "清炉烟",
                "world_med_shenggudan_3": "炎晶片",
                "world_med_yanghundan_3": "醒魂草"
            }
        },
        # 民生物资：城池百万凡人生存刚需。价格不受普通价格曲线压制，回收后提升民生恩赐。
        # 民生越高，后续“极·技能书”等无负面高阶产物概率越容易被世界抬起来。
        "life": {
            "chengshi": {
                "world_life_chengshi_1": "遗田灵粟",
                "world_life_chengshi_2": "月井麦",
                "world_life_chengshi_3": "地乳豆",
                "world_life_chengshi_4": "青髓薯",
                "world_life_chengshi_5": "玉壳谷"
            },
            "yanxian": {
                "world_life_yanxian_1": "赤潮盐",
                "world_life_yanxian_2": "寒泉盐",
                "world_life_yanxian_3": "灵藻干",
                "world_life_yanxian_4": "银鳞脯",
                "world_life_yanxian_5": "荒兽腊"
            },
            "shuijing": {
                "world_life_shuijing_1": "净泉砂",
                "world_life_shuijing_2": "澄水石",
                "world_life_shuijing_3": "清浊炭",
                "world_life_shuijing_4": "避瘴灰",
                "world_life_shuijing_5": "甘露瓮"
            },
            "yibei": {
                "world_life_yibei_1": "雪蚕絮",
                "world_life_yibei_2": "火绒麻",
                "world_life_yibei_3": "青藤线",
                "world_life_yibei_4": "暖玉棉",
                "world_life_yibei_5": "寒兽毡"
            },
            "ranan": {
                "world_life_ranan_1": "地肺炭",
                "world_life_ranan_2": "长明油",
                "world_life_ranan_3": "萤芯草",
                "world_life_ranan_4": "雷松脂",
                "world_life_ranan_5": "驱疫香"
            }
        },
        # 建设物资：城池升级经验的主要来源。回收到哪个城池，就给哪个城池建设成长。
        # 城池等级提升后影响半径扩大，并对范围内宗门提供地利类增益。
        "build": {
            "jichu": {
                "world_build_jichu_1": "古城砖",
                "world_build_jichu_2": "青罡石",
                "world_build_jichu_3": "玄灰泥",
                "world_build_jichu_4": "铁木梁",
                "world_build_jichu_5": "鳞纹瓦"
            },
            "chengfang": {
                "world_build_chengfang_1": "镇妖石",
                "world_build_chengfang_2": "破邪木",
                "world_build_chengfang_3": "惊妖铃",
                "world_build_chengfang_4": "兽纹拒马",
                "world_build_chengfang_5": "玄铁闸"
            },
            "shuihuo": {
                "world_build_shuihuo_1": "净渠玉",
                "world_build_shuihuo_2": "寒泉管",
                "world_build_shuihuo_3": "避火砂",
                "world_build_shuihuo_4": "引雷桩",
                "world_build_shuihuo_5": "锁潮箍"
            },
            "zhenji": {
                "world_build_zhenji_1": "护城砖",
                "world_build_zhenji_2": "聚灵砂",
                "world_build_zhenji_3": "封妖灰",
                "world_build_zhenji_4": "辟邪钉",
                "world_build_zhenji_5": "镇宅锁"
            },
            "huashi": {
                "world_build_huashi_1": "琉光檐",
                "world_build_huashi_2": "玉兽环",
                "world_build_huashi_3": "云纹壁",
                "world_build_huashi_4": "月庭灯",
                "world_build_huashi_5": "金纹坊"
            }
        },
        # 古物物资：古界遗迹相关物品，携带不同量级的神秘物质。
        # 城池周期性吸收古物蓄能，达到阈值后会牵引藏宝图和城池特色稀品武器。
        "relic": {
            "weiyun": {
                "world_relic_weiyun_1": "灰月碎币",
                "world_relic_weiyun_2": "旧王庭徽",
                "world_relic_weiyun_3": "星门断钥",
                "world_relic_weiyun_4": "白塔残页",
                "world_relic_weiyun_5": "雾海铜铃",
                "world_relic_weiyun_6": "失语镜砂",
                "world_relic_weiyun_7": "眠龙骨片",
                "world_relic_weiyun_8": "空舟铆钉"
            },
            "zhongyun": {
                "world_relic_zhongyun_1": "灰烬圣杯",
                "world_relic_zhongyun_2": "银环星图",
                "world_relic_zhongyun_3": "界树枯种",
                "world_relic_zhongyun_4": "无面王冠",
                "world_relic_zhongyun_5": "夜航罗盘",
                "world_relic_zhongyun_6": "封门魔典",
                "world_relic_zhongyun_7": "逆潮沙漏",
                "world_relic_zhongyun_8": "龙眠石碑"
            },
            "houyun": {
                "world_relic_houyun_1": "群星命轮",
                "world_relic_houyun_2": "旧神冠冕",
                "world_relic_houyun_3": "界门王钥",
                "world_relic_houyun_4": "终焉圣杯",
                "world_relic_houyun_5": "万象禁书",
                "world_relic_houyun_6": "昼夜双镜",
                "world_relic_houyun_7": "天灾方舟",
                "world_relic_houyun_8": "原初界标"
            }
        },
        # 战利品物资：战斗后掉落的怪物/敌军材料，主要流向特殊收购和战备虫洞。
        # 后续接特殊战斗、限时悬赏、首领线索时优先从这些稳定 ID 扩展。
        "loot": {
            "yao": {
                "loot_yao_1": "古妖丹",
                "loot_yao_2": "妖脊骨",
                "loot_yao_3": "妖煞血",
                "loot_yao_4": "妖甲皮",
                "loot_yao_5": "妖瞳珠",
                "loot_yao_6": "妖魂晶"
            },
            "mo": {
                "loot_mo_1": "魔魇核",
                "loot_mo_2": "魔煞角",
                "loot_mo_3": "魔烬血",
                "loot_mo_4": "魔纹皮",
                "loot_mo_5": "裂魔爪",
                "loot_mo_6": "魔焰灰"
            },
            "gui": {
                "loot_gui_1": "阴魂珠",
                "loot_gui_2": "鬼火芯",
                "loot_gui_3": "残魂幡",
                "loot_gui_4": "白骨片",
                "loot_gui_5": "冥路纸",
                "loot_gui_6": "怨气瓶"
            },
            "long": {
                "loot_long_1": "蛟逆鳞",
                "loot_long_2": "龙须丝",
                "loot_long_3": "龙血石"
            },
            "shou": {
                "loot_shou_1": "荒兽筋",
                "loot_shou_2": "凶兽牙",
                "loot_shou_3": "荒兽骨",
                "loot_shou_4": "兽纹皮",
                "loot_shou_5": "灵兽角",
                "loot_shou_6": "兽魄心"
            },
            "bing": {
                "loot_bing_1": "军魂印",
                "loot_bing_2": "破甲片",
                "loot_bing_3": "残兵符",
                "loot_bing_4": "血战旗",
                "loot_bing_5": "锈血铁",
                "loot_bing_6": "断寒刃"
            }
        }
    },
    # 纳戒物品：玩家随身高价值物品，和普通背包世界物资分开。
    # 铭刻之羽固定排除在世界皮肤包外；下面这些通用纳戒物品会跟随皮肤包显示。
    "ring": {
        # 恢复药和福袋：自动用药、探险掉落、奖励结算会显示这些名字。
        "recovery": {
            "fudai": "福袋",
            "xueqidan": "血契丹",
            "yinmingcao": "阴冥草",
            "huichunlu": "回春露",
            "ningshenlu": "凝神露",
            "shenggudan": "生骨丹",
            "yanghundan": "养魂丹"
        },
        # 宝石：装备镶嵌和宝石回收使用。键名稳定，显示名可换。
        "gems": {
            "huxinyu": "护心玉",
            "xuangui shi": "玄龟石",
            "shanbi fozhu": "闪避佛珠",
            "mingxin fozhu": "明心佛珠",
            "huichun feicui": "回春翡翠",
            "qingxin manao": "清心玛瑙",
            "qingshen shuijing": "轻身水晶",
            "jucai zijing": "聚财紫晶",
            "kangbao fuwen": "抗暴符文"
        },
        # 特殊纳戒物品：有独立用途或独立命令入口，不走普通“使用物品”。
        # 开孔器用于装备开孔，洗髓液用于体质刷新，淬锋丹用于武器上限提升，流光签用于祈愿。
        "special": {
            "kaikongqi": "开孔器",
            "xisuiye": "洗髓液",
            "cuifengdan": "淬锋丹",
            "liuguang_qian": "流光签"
        }
    },
    # 武器公共展示：城池武器本体在 places.cities.*.weapons，这里放技能书和武器类型名。
    "weapons": {
        # 技能书：普通/极·技能书共用稳定键；显示名会同步影响纳戒物品和附魔展示。
        # “极·”代表无负面效果且正向效果更强，是否出现由业务概率控制，不靠名字判断。
        "skill_books": {
            "fengren_shu": "风刃书",
            "extreme_fengren_shu": "极·风刃书",
            "shaying_shu": "沙影书",
            "extreme_shaying_shu": "极·沙影书",
            "liuguang_shu": "流光书",
            "extreme_liuguang_shu": "极·流光书",
            "zhuixing_shu": "追星书",
            "extreme_zhuixing_shu": "极·追星书",
            "poxie_shu": "破甲书",
            "extreme_poxie_shu": "极·破甲书",
            "bengshan_shu": "崩山书",
            "extreme_bengshan_shu": "极·崩山书",
            "chuanyun_shu": "穿云书",
            "extreme_chuanyun_shu": "极·穿云书",
            "zhenyue_shu": "镇岳书",
            "extreme_zhenyue_shu": "极·镇岳书",
            "zhuoxin_shu": "灼心书",
            "extreme_zhuoxin_shu": "极·灼心书",
            "xueyu_shu": "血雨书",
            "extreme_xueyu_shu": "极·血雨书",
            "duyun_shu": "毒云书",
            "extreme_duyun_shu": "极·毒云书",
            "canyan_shu": "残焰书",
            "extreme_canyan_shu": "极·残焰书",
            "duannian_shu": "断念书",
            "extreme_duannian_shu": "极·断念书",
            "zhenhun_shu": "镇魂书",
            "extreme_zhenhun_shu": "极·镇魂书",
            "tianji_shu": "天机书",
            "extreme_tianji_shu": "极·天机书",
            "mengwu_shu": "梦雾书",
            "extreme_mengwu_shu": "极·梦雾书",
            "huichun_shu": "回春书",
            "extreme_huichun_shu": "极·回春书",
            "xuandun_shu": "玄盾书",
            "extreme_xuandun_shu": "极·玄盾书",
            "xueqi_shu": "血契书",
            "extreme_xueqi_shu": "极·血契书",
            "lingmu_shu": "灵木书",
            "extreme_lingmu_shu": "极·灵木书",
            "fanzhen_shu": "反震书",
            "extreme_fanzhen_shu": "极·反震书",
            "guiren_shu": "归刃书",
            "extreme_guiren_shu": "极·归刃书",
            "jieshi_shu": "借势书",
            "extreme_jieshi_shu": "极·借势书",
            "xuanyao_shu": "玄曜书",
            "extreme_xuanyao_shu": "极·玄曜书",
            "wuxiang_shu": "无相书",
            "extreme_wuxiang_shu": "极·无相书",
            "duanhai_shu": "断海书",
            "extreme_duanhai_shu": "极·断海书",
            "jueying_shu": "绝影书",
            "extreme_jueying_shu": "极·绝影书",
            "pojun_shu": "破军书",
            "extreme_pojun_shu": "极·破军书",
            "xingluo_shu": "星落书",
            "extreme_xingluo_shu": "极·星落书",
            "qiankun_shu": "乾坤书",
            "extreme_qiankun_shu": "极·乾坤书",
            "pozhen_shu": "破阵书",
            "extreme_pozhen_shu": "极·破阵书",
            "yujing_shu": "玉京书",
            "extreme_yujing_shu": "极·玉京书",
            "yueshi_shu": "月蚀书",
            "extreme_yueshi_shu": "极·月蚀书",
            "jinghu_shu": "镜湖书",
            "extreme_jinghu_shu": "极·镜湖书",
            "yingye_shu": "影叶书",
            "extreme_yingye_shu": "极·影叶书",
            "qingxin_shu": "清心书",
            "extreme_qingxin_shu": "极·清心书"
        },
        # 武器类型：只改显示标签。战斗流派和数值仍按内部 weapon_type_key 判断。
        "types": {
            "axe": "斧",
            "balanced": "均衡",
            "bell": "铃",
            "blade": "飞刃",
            "crossbow": "弩",
            "dagger": "匕",
            "disc": "盘",
            "halberd": "戟",
            "saber": "刀",
            "shield_blade": "盾刃",
            "spear": "枪",
            "staff": "杖",
            "sword": "剑",
            "whisk": "拂尘"
        }
    },
    # 生物和战斗显示：怪物、体质、敌方类别、敌方技能的名字都在这里换。
    # 这些名称参与文本和战斗日志展示；数值、AI、掉落不靠中文名判断。
    "actors": {
        # 普通探险怪物名。
        "monsters": {
            "qinglang": "青狼妖",
            "huyao": "狐妖",
            "shanzhu": "山猪兽",
            "baigui": "白骨鬼",
            "shayan": "沙魇",
            "mopi_jiang": "魔皮将",
            "xuanling": "玄铁傀",
            "guijiang": "鬼火将",
            "hanpo": "寒魄鬼",
            "tiejia_bing": "铁甲残兵",
            "leishou": "雷兽",
            "yaotong_niao": "妖瞳鸦",
            "jiaolong": "蛟龙残影",
            "longxu_ying": "龙须影",
            "mohun": "魔魂将",
            "moyan_shi": "魔焰使",
            "pojun": "破军残将",
            "duanren_jiang": "断刃军魂"
        },
        # 玩家体质：只替换 name / grade / kind / desc；稳定 ID、体质值、数值效果不进包。
        "physiques": {
            "fanti": {
                "name": "凡体",
                "grade": "凡阶",
                "kind": "均衡",
                "desc": "平平无奇，却也最稳，所有玩家默认从这里开始。",
            },
            "qingfeng_lingti": {
                "name": "清风灵体",
                "grade": "灵阶",
                "kind": "身法",
                "desc": "气息轻灵，稍微更容易避开伤害。",
            },
            "houde_lingti": {
                "name": "厚土灵体",
                "grade": "灵阶",
                "kind": "体修",
                "desc": "根基厚实，早期防御更稳。",
            },
            "lingquan_ti": {
                "name": "灵泉体",
                "grade": "灵阶",
                "kind": "恢复",
                "desc": "体内如有活泉，休息恢复更好。",
            },
            "tiegu_ti": {
                "name": "铁骨体",
                "grade": "灵阶",
                "kind": "防御",
                "desc": "骨骼坚韧，承伤更稳。",
            },
            "mingxin_ti": {
                "name": "明心体",
                "grade": "灵阶",
                "kind": "精神",
                "desc": "心神清明，精神上限略高。",
            },
            "qianye_lingti": {
                "name": "千叶灵体",
                "grade": "灵阶",
                "kind": "木灵",
                "desc": "生机细密，血气和恢复都有一点优势。",
            },
            "qingmu_xuanti": {
                "name": "青木玄体",
                "grade": "玄阶",
                "kind": "木灵",
                "desc": "偏生机恢复，跑商手续费略吃亏。",
            },
            "xuanbing_linggu": {
                "name": "玄冰灵骨",
                "grade": "玄阶",
                "kind": "冰脉",
                "desc": "防御冷硬，恢复稍慢。",
            },
            "chixia_lingti": {
                "name": "赤霞灵体",
                "grade": "玄阶",
                "kind": "火阳",
                "desc": "血气旺盛，精神上限略低。",
            },
            "leiwenzhanti": {
                "name": "雷纹战体",
                "grade": "玄阶",
                "kind": "雷法",
                "desc": "身法迅疾，生活经营不太细致。",
            },
            "yuyue_ti": {
                "name": "玉月体",
                "grade": "玄阶",
                "kind": "月华",
                "desc": "精神与恢复突出，血气略薄。",
            },
            "jianxin_xuangu": {
                "name": "剑心玄骨",
                "grade": "玄阶",
                "kind": "剑骨",
                "desc": "适合冒险寻机，身板略薄。",
            },
            "longxiang_baoti": {
                "name": "龙象宝体",
                "grade": "地阶",
                "kind": "体修",
                "desc": "血厚防稳，跑商不灵活。",
            },
            "xinghe_lingti": {
                "name": "星河灵体",
                "grade": "地阶",
                "kind": "星命",
                "desc": "擅长探险寻宝，防御略低。",
            },
            "taiyin_yuti": {
                "name": "太阴玉体",
                "grade": "地阶",
                "kind": "月华",
                "desc": "恢复和精神很强，血气偏薄。",
            },
            "taiyang_yanti": {
                "name": "太阳炎体",
                "grade": "地阶",
                "kind": "火阳",
                "desc": "血气极盛，恢复和跑商略差。",
            },
            "canghai_daoti": {
                "name": "沧海道体",
                "grade": "地阶",
                "kind": "水脉",
                "desc": "精神绵长、恢复平顺，防御偏弱。",
            },
            "wuyue_baoti": {
                "name": "五岳宝体",
                "grade": "地阶",
                "kind": "山岳",
                "desc": "防御厚重，精神和探险灵活性较差。",
            },
            "hunyuan_daoti": {
                "name": "玄黄镇岳体",
                "grade": "天阶",
                "kind": "山岳",
                "desc": "极端守御体质，精神与跑商是短板。",
            },
            "wugou_xianji": {
                "name": "琉璃无垢体",
                "grade": "天阶",
                "kind": "仙肌",
                "desc": "恢复与精神突出，正面承伤略弱。",
            },
            "wanxiang_lingtai": {
                "name": "千幻游身体",
                "grade": "天阶",
                "kind": "身法",
                "desc": "闪避和探险极强，血防明显偏薄。",
            },
            "zifu_tianti": {
                "name": "紫府明神体",
                "grade": "天阶",
                "kind": "精神",
                "desc": "精神海宽广，血气不是优势。",
            },
            "qianqiu_jianmai": {
                "name": "千秋剑脉",
                "grade": "天阶",
                "kind": "剑骨",
                "desc": "适合险地寻剑，恢复不算出色。",
            },
            "shenxiao_leiti": {
                "name": "神霄雷体",
                "grade": "天阶",
                "kind": "雷法",
                "desc": "迅烈难伤，恢复和跑商都粗糙。",
            },
            "xiantian_daotai": {
                "name": "先天药胎",
                "grade": "圣阶",
                "kind": "恢复",
                "desc": "恢复近乎夸张，但肉身承压偏弱。",
            },
            "canglong_shengti": {
                "name": "苍龙圣体",
                "grade": "圣阶",
                "kind": "龙脉",
                "desc": "血气如海，精神和经营能力是短板。",
            },
            "jiuyao_shengti": {
                "name": "九曜星命体",
                "grade": "圣阶",
                "kind": "星命",
                "desc": "天生会找机会，适合探险和跑商，血防较薄。",
            },
            "bumie_jinshen": {
                "name": "不灭金身",
                "grade": "圣阶",
                "kind": "金身",
                "desc": "最硬的防御路线，精神、探险和跑商都笨重。",
            },
            "taixu_xianmai": {
                "name": "太虚仙脉",
                "grade": "圣阶",
                "kind": "虚空",
                "desc": "飘忽难捉，探险极强，但正面血防很低。",
            },
            "hongmeng_xuanti": {
                "name": "归墟玄体",
                "grade": "圣阶",
                "kind": "虚空",
                "desc": "精神深不可测，却不适合硬扛和经营。",
            },
        },
        # 敌方类别短名：战斗日志里用于概括敌人来源或类型。
        "enemy_kinds": {
            "ancient_guard": "古卫",
            "beast": "兽",
            "default": "凶煞",
            "demon": "魔",
            "demon_general": "魔将",
            "dragon": "龙",
            "dragon_shadow": "龙影",
            "ghost": "鬼",
            "puppet": "傀",
            "soldier": "兵",
            "wandering_soul": "游魂",
            "yao": "妖",
            "yaojun": "妖君"
        },
        # 敌方技能名：公共战斗核心使用，首领/虫洞/秘境只复用战斗结果和日志展示。
        "enemy_skills": {
            "enemy_skill_yao_bite": "妖影撕咬",
            "enemy_skill_yaojun_shadow": "妖君裂影",
            "enemy_skill_beast_charge": "蛮兽冲撞",
            "enemy_skill_dragon_breath": "龙息压顶",
            "enemy_skill_dragon_shadow_breath": "龙影吐息",
            "enemy_skill_ghost_bite": "阴魂噬念",
            "enemy_skill_wandering_soul_bind": "游魂缠身",
            "enemy_skill_demon_flame": "魔焰灼心",
            "enemy_skill_demon_general_break": "魔将破阵",
            "enemy_skill_soldier_armor_break": "残兵破甲",
            "enemy_skill_ancient_guard_suppress": "古卫镇压",
            "enemy_skill_puppet_crush": "傀儡重压",
            "enemy_skill_default": "凶煞一击"
        }
    },
    # 异界虫洞：虫洞 Boss、异界法则、战备 Boss 和战备词缀显示名。
    # 虫洞难度等数值仍由活跃度和业务逻辑决定，皮肤包只负责名字。
    "wormhole": {
        # 普通虫洞 Boss 名称。流派由业务随机，不再用中文名推断。
        "bosses": {
            "worm_boss_01": "千刃界游王",
            "worm_boss_02": "陨炉泰坦",
            "worm_boss_03": "赤瘟炼狱君",
            "worm_boss_04": "缄魂巫皇",
            "worm_boss_05": "苍根不死王",
            "worm_boss_06": "回盾镜魔",
            "worm_boss_07": "断星斩王",
            "worm_boss_08": "星环仲裁者"
        },
        # 异界法则/流派显示：描述本次 Boss 的战斗倾向。
        "flows": {
            "worm_flow_swift": "高频连击",
            "worm_flow_heavy": "重击破防",
            "worm_flow_dot": "持续伤害",
            "worm_flow_control": "压制控制",
            "worm_flow_survival": "生存续航",
            "worm_flow_counter": "反击护身",
            "worm_flow_execute": "斩杀收割",
            "worm_flow_leader": "首领协作"
        },
        # 战备虫洞 Boss：特殊收购点蓄势后可能牵引出的战备敌人。
        "war_prep_bosses": {
            "war_boss_zhenyaosi_01": "百臂青妖王",
            "war_boss_zhenyaosi_02": "裂巢迅影后",
            "war_boss_zhenyaosi_03": "万爪潮主",
            "war_boss_fumodian_01": "黑铠破界魔",
            "war_boss_fumodian_02": "焚契魔侯",
            "war_boss_fumodian_03": "坠岳魔君",
            "war_boss_guishi_01": "无灯冥契主",
            "war_boss_guishi_02": "缚魂夜巫",
            "war_boss_guishi_03": "纸城鬼王",
            "war_boss_longyuan_01": "逆鳞界龙君",
            "war_boss_longyuan_02": "潮骸古蛟",
            "war_boss_longyuan_03": "星渊断角龙",
            "war_boss_wanshou_01": "荒骨兽神",
            "war_boss_wanshou_02": "苍鬃不死兽",
            "war_boss_wanshou_03": "万蹄裂阵王",
            "war_boss_pojun_01": "星甲破阵帅",
            "war_boss_pojun_02": "断旗兵主",
            "war_boss_pojun_03": "铁潮军魂王"
        },
        # 战备词缀：用于描述虫洞/战备事件的状态修饰。
        "war_prep_affixes": {
            "war_prep_affix_exposed_nest": "残巢已露",
            "war_prep_affix_half_open_gate": "旧门半开",
            "war_prep_affix_war_marks": "战痕回涌",
            "war_prep_affix_warm_embers": "余烬未冷",
            "war_prep_affix_gathering_enemies": "群敌聚形",
            "war_prep_affix_unstable_rift": "裂口不稳"
        }
    },
    # 太虚秘境：秘境环境名和环境描述。秘境强度动态计算，详情页不展示固定等级。
    "secret_realm": {
        # 环境会影响秘境怪物倾向，desc 是玩家看到的说明文本。
        "environments": {
            "secret_env_youming_wind": {
                "name": "幽冥风",
                "desc": "阴风压魂，怪物精神压迫更重。"
            },
            "secret_env_mirror_sky": {
                "name": "镜天影",
                "desc": "镜影错乱，遭遇强度起伏更大。"
            },
            "secret_env_dragon_bone_dust": {
                "name": "龙骨尘",
                "desc": "龙骨尘暴翻涌，怪物血防更厚。"
            },
            "secret_env_star_fire_rain": {
                "name": "星火雨",
                "desc": "星火落如雨，怪物攻势更烈。"
            },
            "secret_env_returning_tide": {
                "name": "归墟潮",
                "desc": "归墟潮汐反复，战斗更拖长。"
            }
        }
    },
    # 系统显示名：品质、货币、等级显示。
    # 这里会影响大量文本，所以换皮前要重点审计是否和整体世界观一致。
    "system": {
        # 品质名：武器等物品品质显示。只改展示，不改掉落概率和品质数值。
        "quality": {
            "quality_common": "凡品",
            "quality_good": "良品",
            "quality_rare": "珍品",
            "quality_epic": "稀品"
        },
        # 货币名：玩家看到的货币显示。内部字段仍固定为 raw_stones。
        "currency": {
            "raw_stones": "原石"
        },
        # 等级显示：人物、怪物、战斗日志等和战力比较相关的等级文本。
        # 非生物建筑等级仍保持业务侧固定表达，不强行套这里。
        "levels": {
            "1": "LV1",
            "2": "LV2",
            "3": "LV3",
            "4": "LV4",
            "5": "LV5",
            "6": "LV6",
            "7": "LV7",
            "8": "LV8",
            "9": "LV9",
            "10": "LV10",
            "11": "LV11",
            "12": "LV12",
            "13": "LV13",
            "14": "LV14",
            "15": "LV15",
            "16": "LV16",
            "17": "LV17",
            "18": "LV18",
            "19": "LV19",
            "20": "LV20",
            "21": "LV21",
            "22": "LV22",
            "23": "LV23",
            "24": "LV24",
            "25": "LV25",
            "26": "LV26",
            "27": "LV27",
            "28": "LV28",
            "29": "LV29",
            "30": "LV30",
            "31": "LV31",
            "32": "LV32",
            "33": "LV33",
            "34": "LV34",
            "35": "LV35",
            "36": "LV36",
            "37": "LV37",
            "38": "LV38",
            "39": "LV39",
            "40": "LV40",
            "41": "LV41",
            "42": "LV42",
            "43": "LV43",
            "44": "LV44",
            "45": "LV45",
            "46": "LV46",
            "47": "LV47",
            "48": "LV48",
            "49": "LV49",
            "50": "LV50",
            "51": "LV51",
            "52": "LV52",
            "53": "LV53",
            "54": "LV54",
            "55": "LV55",
            "56": "LV56",
            "57": "LV57",
            "58": "LV58",
            "59": "LV59",
            "60": "LV60",
            "61": "LV61",
            "62": "LV62",
            "63": "LV63",
            "64": "LV64",
            "65": "LV65",
            "66": "LV66",
            "67": "LV67",
            "68": "LV68",
            "69": "LV69",
            "70": "LV70",
            "71": "LV71",
            "72": "LV72",
            "73": "LV73",
            "74": "LV74",
            "75": "LV75",
            "76": "LV76",
            "77": "LV77",
            "78": "LV78",
            "79": "LV79",
            "80": "LV80",
            "81": "LV81",
            "82": "LV82",
            "83": "LV83",
            "84": "LV84",
            "85": "LV85",
            "86": "LV86",
            "87": "LV87",
            "88": "LV88",
            "89": "LV89",
            "90": "LV90",
            "91": "LV91",
            "92": "LV92",
            "93": "LV93",
            "94": "LV94",
            "95": "LV95",
            "96": "LV96",
            "97": "LV97",
            "98": "LV98",
            "99": "LV99",
            "100": "LV100"
        }
    }
}
