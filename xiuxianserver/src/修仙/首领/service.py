"""岁时情劫首领服务。

岁时情劫按每日 04:00 的业务日刷新。
节气和传统节日命中时，玩家发送首领相关命令才会懒加载生成当日首领。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import median
from typing import Any

from lunardate import LunarDate

from ..common import CoreService, dt, dump_json, hint, load_json, money, now, random, ts
from ..constants import (
    DAY_RESET_HOUR,
    MAX_LEVEL,
    SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES,
    SEASONAL_BOSS_MAX_CHALLENGES,
)
from ..rules import damage_after_defense, monster_exp
from ..sql import db
from ..weapon_core import service as weapon_service


@dataclass(frozen=True)
class BossDef:
    """一只岁时情劫的文字和基础配置。"""

    key: str
    name: str
    title: str
    scene: str
    story: str
    atmosphere: tuple[str, str, str]
    farewell: str
    feather_text: str
    location: str


def _boss(
    key: str,
    name: str,
    title: str,
    scene: str,
    story: str,
    atmosphere: tuple[str, str, str],
    farewell: str,
    feather_text: str,
    location: str,
) -> BossDef:
    """让下面的大段定义更短一些。"""

    return BossDef(key, name, title, scene, story, atmosphere, farewell, feather_text, location)


SOLAR_TERM_RULES = {
    "xiaohan": (1, 5.4055),
    "dahan": (1, 20.12),
    "lichun": (2, 3.87),
    "yushui": (2, 18.73),
    "jingzhe": (3, 5.63),
    "chunfen": (3, 20.646),
    "qingming": (4, 4.81),
    "guyu": (4, 20.1),
    "lixia": (5, 5.52),
    "xiaoman": (5, 21.04),
    "mangzhong": (6, 5.678),
    "xiazhi": (6, 21.37),
    "xiaoshu": (7, 7.108),
    "dashu": (7, 22.83),
    "liqiu": (8, 7.5),
    "chushu": (8, 23.13),
    "bailu": (9, 7.646),
    "qiufen": (9, 23.042),
    "hanlu": (10, 8.318),
    "shuangjiang": (10, 23.438),
    "lidong": (11, 7.438),
    "xiaoxue": (11, 22.36),
    "daxue": (12, 7.18),
    "dongzhi": (12, 21.94),
}


def _solar_term_day(year: int, month: int, constant: float) -> int:
    """用 21 世纪节气公式计算某年某节气在公历几号。"""

    century_year = year % 100
    if month <= 2:
        leap_count = max(0, (century_year - 1) // 4)
    else:
        leap_count = century_year // 4
    return int(century_year * 0.2422 + constant) - leap_count


def _solar_term_key(value: date) -> str:
    """判断当天是否命中二十四节气。"""

    for key, (month, constant) in SOLAR_TERM_RULES.items():
        if value.month == month and value.day == _solar_term_day(value.year, month, constant):
            return key
    return ""


LUNAR_FESTIVAL_DATES = {
    (1, 1): "chunjie",
    (1, 15): "yuanxiao",
    (2, 2): "longtaitou",
    (2, 12): "huazhao",
    (3, 3): "shangsi",
    (5, 5): "duanwu",
    (7, 7): "qixi",
    (7, 15): "zhongyuan",
    (8, 15): "zhongqiu",
    (9, 9): "chongyang",
    (10, 1): "hanyi",
    (10, 15): "xiayuan",
    (12, 8): "laba",
    (12, 23): "xiaonian",
}


HIGH_WEIGHT_FESTIVALS = {"chunjie", "yuanxiao", "duanwu", "qixi", "zhongqiu", "chongyang"}


BOSS_DEFS: dict[str, BossDef] = {
    "lichun": _boss(
        "lichun",
        "折柳青郎",
        "渡口送别的少年",
        "立春这日，渡口老柳先于百草发青。一个青衫少年站在柳下，指间折着新枝，像还在等一艘迟迟不归的船。",
        "他曾在立春送心爱的姑娘远行，折柳相赠，说等柳枝再青，她便该回来了。后来春风一年年吹过渡口，船却再没有靠岸。",
        ("柳絮还未飞起，渡口却像下了一场细雪。", "他抬眼看你，眼神干净得像还不知道结局。", "水声拍岸，像有一艘船永远差一点靠近。"),
        "折柳青郎把柳枝放进水里，任它漂向远方。",
        "水面浮起一枚淡青色的铭刻之羽，带着新柳和冷茶的气息。像一句少年没能亲口说出的：我一直在这里。",
        "旧渡口",
    ),
    "yushui": _boss(
        "yushui",
        "听雨灯娘",
        "窗前守灯的少女",
        "雨水入夜，旧巷尽头亮起一盏小灯。窗纸上映出少女侧影，她用手护着灯火，像怕风雨吹灭某人的归路。",
        "绣坊少女为远行人留灯，等第一场春雨后归舟靠岸。可布船沉在无人知晓的江湾，她却夜夜剪灯，夜夜听雨。",
        ("雨水顺着屋檐滴落，像一针一线缝进夜里。", "灯火照着她的脸，一半是少女，一半是旧雨。", "她怀里的绣帕没有绣完，并蒂莲只开了一朵。"),
        "灯娘轻轻吹熄灯火，窗纸上的影子终于淡去。",
        "灯盏旁落下一枚微湿的铭刻之羽，羽尖带着一点灯油香。像有人把一夜没敢熄灭的等待，交到了你手里。",
        "旧巷",
    ),
    "jingzhe": _boss(
        "jingzhe",
        "惊雷梦龙郎",
        "梦里养龙的少年",
        "惊蛰春雷滚过雷泽，泥水翻起细小银光。一个赤脚少年从雷声里醒来，身后拖着半条由梦化成的龙影。",
        "少年曾在梦里养出一缕小龙，答应惊蛰雷响后带它越过雷泽。可少年死在春雷之前，小龙便年年撞碎梦境来寻他。",
        ("雷光照亮他的脸，稚气未退，却满眼认真。", "龙影绕过你的兵刃，像一场还没醒完的梦。", "泥水映出的不是雷泽，而是病榻和旧窗。"),
        "少年摸了摸身后的龙影，轻声说：再等等，明年我们一定走。",
        "雷泽泥水中浮出一枚带细雷纹的铭刻之羽。羽上微微发热，像少年掌心捧过的一点梦。",
        "雷泽",
    ),
    "chunfen": _boss(
        "chunfen",
        "半影镜姑娘",
        "抱着半面镜的少女",
        "春分日，昼夜正平。日光照进废园时，一面断镜忽然映出少女的影子，她抱着镜子，像抱着一个再也拼不回的人。",
        "她与远行少年分镜为约，说归来时两半合圆。后来少年死在京中风雪里，另一半镜子再也没有回来。",
        ("她举起断镜，你的影子被照得只剩一半。", "园中花影分成明暗两边，谁也不肯越界。", "她问你：若一人不归，另一半誓言还算数吗？"),
        "断镜轻轻一颤，映出的少女影子慢慢模糊。",
        "镜光碎处，一枚半明半暗的铭刻之羽落下。羽面映不出人脸，只映出一场没有合圆的约定。",
        "废园",
    ),
    "qingming": _boss(
        "qingming",
        "纸衣书生",
        "死在归途的少年郎",
        "清明雨落，桥头纸灰贴着水面漂了一夜。一个纸衣书生站在桥边，怀里抱着一封被雨洇开的家书。",
        "少年高中后连夜归乡，想告诉未婚妻自己终于可以娶她。山雨断路，家书未寄，他便年年在桥头等灯。",
        ("纸灰落在你的肩上，竟有一点人的体温。", "他护着怀中家书，像护着世上最后一点喜讯。", "雨水打湿他的纸衣，露出下面早已不存在的少年骨。"),
        "纸衣书生向桥那头作了一揖，身影随纸灰飞远。",
        "桥边落下一枚灰白色铭刻之羽，沾着清明雨和淡淡墨香。像一封终于寄出的迟信。",
        "旧桥",
    ),
    "guyu": _boss(
        "guyu",
        "埋香花娘",
        "山中种花的姑娘",
        "谷雨时节，山田百花同时低头。泥土深处传来姑娘轻轻的歌声，像有人在为一场没有开始的婚礼铺花。",
        "她与采药少年约好谷雨后成亲，少年却为换红绸入山未归。她把红绸、花种和名字一起埋进泥里。",
        ("花香浓得像喜宴，却没有半点人声。", "她赤足踏过泥水，每一步都开出一朵未嫁的花。", "她袖中藏着半截红绸，颜色新得令人难过。"),
        "满山花香淡去，像一场迟迟没有办成的婚礼终于散席。",
        "花泥中浮起一枚浅黄色铭刻之羽，沾着雨后花香和一点红绸碎影。像一声没等到回应的“你回来了”。",
        "花田",
    ),
    "lixia": _boss("lixia", "蝉衣少年", "树下脱不下旧壳的少年魂", "立夏午后，老槐树上响起第一声蝉鸣，薄衣少年披着半透明的蝉蜕醒来。", "他曾约邻家姑娘立夏去河边捉第一只蝉，却病死在蝉鸣之前。后来每年立夏，他都以为自己只是睡过了头。", ("蝉鸣忽近忽远，像从很多年前的树影里传来。", "少年伸手去抓肩上的蝉蜕，却怎么也脱不下来。", "树叶筛下的光斑落在他脸上，像一个未曾长大的夏天。"), "少年跑向河边，半途碎成满树薄翼。", "槐树下落下一枚透明微黄的铭刻之羽，轻得像一枚空蝉壳。像少年迟到多年后，终于听见了第一声夏。", "老槐树"),
    "xiaoman": _boss("xiaoman", "未满酒娘", "倒酒等人的少女", "小满黄昏，酒肆门前的旧酒盏自己斟起半杯。少女按着酒壶，怎么也不肯倒满。", "她等赶路少年回来喝合卺酒，说等他进门再倒最后一线。少年死在外乡荒店，那杯酒便永远未满。", ("酒香很甜，甜得像一场未办成的喜宴。", "她望着门外，眼里盛着半杯将落未落的光。", "酒液轻晃，却始终差一滴才满。"), "她把半杯酒倒在地上，低声说，原来等人也会醉。", "酒盏旁浮起一枚带甜香的铭刻之羽。羽尖湿润，像一杯始终没有倒满的合卺酒。", "旧酒肆"),
    "mangzhong": _boss("mangzhong", "麦信郎", "麦田藏信的少年", "芒种风过，金黄麦浪里传来纸页翻动的声音。布衣少年抱着一束沉甸甸的麦穗。", "他把第一封情书藏进麦穗，想在收麦时送给教书姑娘。战乱烧毁村学，信被风雨磨成碎屑。", ("麦芒划过你的手背，像纸边轻轻割开旧事。", "少年把麦穗抱得很紧，仿佛里面藏着一生勇气。", "风吹过田野，无数碎纸在麦间低语。"), "他展开掌心，只剩一撮金黄麦壳，便把它们撒回田里。", "麦浪中飞出一枚金色铭刻之羽，羽根夹着极细的纸屑。像一封终于敢写、却再没人读的信。", "麦田"),
    "xiazhi": _boss("xiazhi", "长日晒衣女", "晒嫁衣的姑娘", "夏至白昼漫长，村口晒衣绳上挂起一件红嫁衣。少女抬头望着日光。", "她的未婚夫说夏至前必归，因为白昼最长，路也该最好走。边关大火吞没粮队，嫁衣晒到褪色。", ("日光白得刺眼，红嫁衣却像刚从血里洗出。", "她抚平衣角，每一下都像在抚一封迟来的讣告。", "你的影子被拉得很长，长到仿佛能走去边关。"), "她解下嫁衣抱在怀里，夕阳终于落下。", "晒衣绳上飘下一枚艳红的铭刻之羽，带着日晒后的暖意。像一件穿不上的嫁衣，仍替谁保留着体温。", "晒衣场"),
    "xiaoshu": _boss("xiaoshu", "热井藏信郎", "把信藏进井边的少年", "小暑热气蒸腾，荒井边的青石渗出墨痕。少年伏在井沿，寻找那封藏错地方的信。", "他怕雨湿了信，便把心事藏进井边石缝。取信时失足跌落，同窗姑娘一生都不知道这封信。", ("井口热气扑面，像有人把旧信贴在火上烘。", "少年指尖满是青苔和墨迹，眼神却亮得可怜。", "井底有纸张卷曲的声音，像一句话被热气烫弯。"), "他取出一片空白纸灰，忽然笑了，像信从未写过也好。", "井沿浮起一枚带墨痕的铭刻之羽，触手微烫。像一封藏得太深、终于烧空的少年心事。", "荒井"),
    "dashu": _boss("dashu", "焚荷红衣女", "荷塘烧旧约的新娘", "大暑正午，荷塘忽起红火。红衣少女立在火色荷叶间，攥着半张烧焦婚书。", "她被迫另嫁，误以为心上人负约，含泪烧掉婚书投了荷塘。多年后真相才被风传来。", ("红荷一朵朵燃起，却没有半点灰烬。", "她把婚书举向你，声音很轻：你也来晚了吗？", "热浪里有谁拍打祠堂门板，声声都迟了许多年。"), "她像终于听见了那晚没传到的敲门声，泪落进荷心。", "焦黑荷叶上留下一枚红边铭刻之羽，带着烟火和莲香。像一场误会烧到最后，只剩一句来不及解释。", "荷塘"),
    "liqiu": _boss("liqiu", "折簪秋娘", "秋风里拾断簪的少女", "立秋风起，长街尽头滚来半支断簪。素衣少女追着簪影而来，鬓边空空。", "卖剑少年送她木簪作聘，说秋收后换金簪。矿山塌方后，送回来的只有半支断簪。", ("秋风卷过，她鬓边发丝被吹得很乱。", "断簪在地上轻轻转动，像一直指向回不去的山路。", "她问你：若他真的不来，为什么还把簪子带在身上？"), "她把断簪插回发间，簪仍缺一半，她却不再追了。", "秋风中落下一枚木色铭刻之羽，羽骨细长如簪。像一份寒酸却真心的聘礼，断了也舍不得丢。", "长街"),
    "chushu": _boss("chushu", "病酒少年", "夏末醉倒的少年", "处暑暑气将退，酒楼旧席多出一只空坛。少年倚栏醉笑，眼尾却红得像刚哭过。", "他被假信骗走，以为唱曲姑娘心甘情愿嫁入高门。多年后才知她也在同夜被带往远乡。", ("酒气里混着残暑，熏得人眼眶发热。", "他笑得很响，可每次举杯都像在挡泪。", "楼下似有女子唱曲，唱到一半便被风吹散。"), "他放下空杯，轻声说：若是被拦住，那就不怪她了。", "酒坛里浮起一枚琥珀色铭刻之羽，带着苦酒香。像一个少年醉了一生，只为替她找一个不是背弃的理由。", "旧酒楼"),
    "bailu": _boss("bailu", "白露眠姬", "一夜未眠的少女", "白露清晨，草叶凝满细珠。披发少女坐在露水深处，眼下微青，像整夜都没有睡去。", "她等采药少年带秋草归来，却只等到被露水打湿的药篓。自此再不敢睡，怕一闭眼那人就真的不会回来。", ("露水沾上你的衣角，冷得像一夜未干的泪。", "她努力睁着眼，仿佛睡去就是一种背叛。", "药香清苦，像没来得及煎好的药。"), "她终于慢慢合上眼，草叶上的露珠滚落一地。", "露水中浮起一枚清白铭刻之羽，羽面微凉。像一个少女强撑整夜后，终于落下的第一滴泪。", "露草坡"),
    "qiufen": _boss("qiufen", "分镜书生", "持半面铜镜的少年", "秋分日，窗前铜镜裂成两片。书生捧着其中半面，站在明暗交界处。", "他与闺中少女隔墙借镜光写字，约秋分夜相见。少女被迫远嫁，只送出半片铜镜。", ("断镜映出你的脸，却总缺另一半。", "书生低头擦镜，动作轻得像怕惊动墙那边的人。", "墙上浮出旧日字影，刚成一句，便被秋风擦去。"), "他把半镜贴在墙上，什么也没有照见。", "镜片旁落下一枚银灰铭刻之羽，羽面有细细裂纹。像一段从未见面的相思，偏偏认真了一生。", "旧墙"),
    "hanlu": _boss("hanlu", "采露小僧", "为亡妻采露的少年僧", "寒露夜深，寺外秋草凝霜。年轻僧人提着小瓷瓶弯腰采露，眉眼并不平静。", "未婚妻久病，他听说寒露清晨第一滴露能缓咳血。归来时她已下葬，他剃发后仍夜夜采露。", ("瓷瓶轻响，里面盛着比月光还冷的露。", "他念经时总念错一个字，像旧名卡在喉间。", "秋草被他踏弯，又慢慢立起，仿佛替谁低头。"), "他将瓷瓶放在地上，瓶中寒露慢慢渗入泥土。", "草叶间浮起一枚冷白铭刻之羽，沾着寒露。像少年僧人一生没敢再喊出口的俗名。", "寒寺"),
    "shuangjiang": _boss("shuangjiang", "霜甲归郎", "披霜归来的少年兵", "霜降清晨，城门外马蹄声忽然响起。少年兵披着满身白霜归来。", "他从军时还未及冠，约青梅霜降前归来成亲。战场太远，归书丢在风雪里，红线结也没能送回。", ("霜花爬满他的甲叶，每一片都像未寄出的归书。", "他握着红线结，手指冻得发青，却不肯松开。", "城门很近，可他每走一步都像隔着一场战死的雪。"), "他把红线结放在霜地上，向城中行了一个很轻的军礼。", "霜地上留下一枚银白铭刻之羽，羽根缠着一线淡红。像一个少年用尽一生赶回来的婚约。", "霜城门"),
    "lidong": _boss("lidong", "封书雪女", "把信封进冰河的姑娘", "立冬水寒，河面结起第一层薄冰。白衣姑娘蹲在岸边，把一封信轻轻按进冰下。", "她写好回信，却不敢托人送出，只藏进河边石洞。冬水上涨，信卷入冰下，琴师等不到回信便远走。", ("冰面下有墨迹游动，像鱼，也像未送出的字。", "她的手指冻得通红，却仍把信压得很平。", "远处似有琴声一闪而过，随即被寒水吞没。"), "她看着信纸沉入水底，终于知道琴声不会回来了。", "冰缝里浮起一枚雪白铭刻之羽，羽面有淡淡墨痕。像一封写好了，却亲手封死的信。", "冰河"),
    "xiaoxue": _boss("xiaoxue", "初雪白头女", "第一场雪里等人的少女", "小雪初落，屋檐下站着一位少女。雪花落在她发间，转瞬成霜。", "她与少年约好第一场雪时在老梅树下相见。少年赶赴约定时被雪埋在半路，她等了一夜，满头皆白。", ("雪落无声，却像每一片都在替谁迟到。", "她低头摸着荷包，针脚细密，颜色仍新。", "梅枝未开，树下却已有一地白发似的雪。"), "她把荷包埋在梅树根下，身影随雪淡去。", "梅树下落下一枚雪色铭刻之羽，冰凉而柔软。像少女一夜白头后，仍舍不得丢掉的荷包。", "老梅树"),
    "daxue": _boss("daxue", "埋灯少年", "把灯埋进雪里的少年", "大雪封路，荒村外却有一点灯火从雪下透出。少年跪在雪地里，把灯埋得更深。", "他为晚归的姑娘守夜点灯。风雪太大，他用身体护灯，最后倒在雪里，可灯埋得太深，她没有看见。", ("雪下的灯光一明一暗，像快要断掉的呼吸。", "少年指尖全是冻伤，却仍固执地护着灯盏。", "风雪里似有人喊“小灯郎”，转眼又听不真切。"), "他把熄灭的灯抱进怀里，像终于不再怕风雪。", "雪坑中浮起一枚微暗的铭刻之羽，带着熄灯后的焦香。像一盏没能照到归人的小灯。", "荒村雪路"),
    "dongzhi": _boss("dongzhi", "藏阳小道姑", "守着一簇火的少女", "冬至夜长，破观中亮起一簇小火。小道姑跪坐火前，用袖子护着火苗。", "她曾收留冻伤少年，将暖阳符给他去北地寻亲。少年没能走出风雪，她却日日守火，怕他回来时屋里太冷。", ("火光很小，却把她的影子照得很长。", "她袖口被烧出黑边，仍不肯离火远一点。", "夜风穿过破观，铃铛响得像远行人的脚步。"), "她把最后一根柴放进火里，像终于承认那人不会再冷了。", "火盆旁落下一枚暖金色铭刻之羽，握在手里有微弱余温。像长夜尽处，一碗再也送不出的热粥。", "破观"),
    "xiaohan": _boss("xiaohan", "寒枝狐女", "衔枝筑巢的小狐仙", "小寒风紧，枯树上多出一座歪斜小巢。狐耳少女衔着寒枝站在树下。", "山脚小狐被少年救回旧屋，少年说伤好后可在屋后树上筑巢。后来旧屋空了，她仍年年衔枝回来。", ("她衔着枯枝，说话含混，却固执得可怜。", "旧屋窗洞黑着，像一双再也不会醒来的眼。", "寒风吹乱她的狐尾，她却只顾把小巢补得更紧。"), "她把最后一根枝条放进巢里，蜷成一团随风散去。", "枯巢里落下一枚浅棕铭刻之羽，带着木枝和雪气。像小狐仙年年筑好的巢，仍等着一句“我回来了”。", "旧屋"),
    "dahan": _boss("dahan", "收骨少年", "年尽时收拾旧骨的少年", "大寒岁尽，乱葬坡上风声低沉。少年背着竹篓走来，篓中只有无人认领的旧骨。", "他在义庄帮工，年年去乱葬坡收无名骨，只为找出青梅留下的半支发簪。他怕找不到，也怕真的找到。", ("竹篓轻响，里面的旧骨像在低声道谢。", "少年冻得嘴唇发白，却把每一枚骨都擦得很干净。", "他握着半支发簪，眼神里满是恐惧和希望。"), "他看着竹篓空出的一格，低声说：还没找到，也好。", "寒土上浮起一枚灰白铭刻之羽，羽根像细骨般清瘦。像少年一直不敢确认的那场重逢。", "乱葬坡"),
    "chuxi": _boss("chuxi", "守岁红烛郎", "守着年夜红烛的少年", "除夕夜，旧宅红烛一支支亮起。少年坐在门槛上守岁，身旁空着一只未归人的碗。", "他与远嫁少女约好年夜归家看灯，却等到鸡鸣也无人敲门。后来每年除夕，他都替她守着那盏不会熄的红烛。", ("爆竹声远得像隔着一生。", "红烛滴泪，烛花像小小的伤口。", "他把空碗摆正，像怕归人回来时看见冷清。"), "红烛终于燃尽，少年把空碗收回怀里。", "红烛旁留下一枚暖红铭刻之羽，像年夜里无人听见的一声“回来吃饭”。", "旧宅"),
    "chunjie": _boss("chunjie", "新桃门前女", "贴新桃符的少女", "正月初一，新桃符贴满旧门。少女踮脚抚平红纸，却迟迟不肯关门。", "她年年换新桃，只为等少年在新岁敲门。门漆换了数次，旧人却再也没来拜年。", ("红纸新得刺眼，门里却没有笑声。", "她把桃符贴歪又揭下，像怕错过敲门声。", "新雪落在门槛外，被她扫了一遍又一遍。"), "她轻轻合上门，桃符在风里响了一声。", "门前落下一枚桃红铭刻之羽，带着新纸和旧雪的味道。像一个新年里没等来的敲门声。", "旧门"),
    "yuanxiao": _boss("yuanxiao", "灯市寻郎女", "灯会里找人的姑娘", "元宵灯市人声如潮。少女提着半盏莲灯，在千万灯火中寻找一个约好的人。", "她与少年约在灯谜下相见，却被人潮冲散。后来满城灯火年年亮起，她再也没找到那张熟悉的脸。", ("花灯照得她眼睛很亮，亮得像快要哭出来。", "她每看见一人回头，都会往前走半步。", "灯谜纸条飘落，上面只剩一个未解的“归”字。"), "莲灯熄灭，她停在人潮尽头，不再回头。", "莲灯里飞出一枚明黄铭刻之羽。像满城灯火都亮了，却照不见的那个人。", "灯市"),
    "longtaitou": _boss("longtaitou", "梳龙辫少年", "河边替她梳发的少年", "二月二，河边柳影摇晃。少年握着木梳，身后水纹像一条刚抬头的小龙。", "他学会给姑娘梳龙辫，等她坐到河边。可姑娘被家人送走，他只把那把木梳梳旧了。", ("木梳齿间缠着一缕旧发。", "水里的龙影抬头又沉下，像欲言又止。", "少年把梳子洗了又洗，仍洗不掉等待。"), "他把木梳放进河里，任水纹带走。", "河面浮起一枚青黑铭刻之羽，像一把终于松手的木梳。", "河岸"),
    "huazhao": _boss("huazhao", "百花迟归娘", "花下等春信的少女", "花朝日，百花齐放，花下少女却拆不开一封空白春信。", "她等远行少年寄来花期，却只等到满园花谢。她总疑心信被花香藏住，年年花开都要找一遍。", ("花开得太热闹，越显得她身边寂静。", "她将每朵花都翻过，像找一枚印章。", "空白信纸沾满花粉，仍没有字。"), "她把空信埋在花根下，花香终于淡了。", "花瓣间落下一枚粉白铭刻之羽，像一封被春天弄丢的信。", "花园"),
    "shangsi": _boss("shangsi", "曲水遗簪女", "曲水边失簪的少女", "上巳曲水流觞，水面漂来一支玉簪。少女沿溪追来，裙角尽湿。", "她把心意藏在玉簪里，想借曲水送到少年面前。水流太急，簪子漂远，少年也离席远行。", ("溪水绕过你的脚踝，凉得像迟疑。", "她追着玉簪，不敢喊那人的名字。", "酒杯从水上漂过，无人停下。"), "她终于停步，看着玉簪沉入溪底。", "溪水中浮起一枚玉色铭刻之羽，像一支没送到手里的簪。", "曲水溪"),
    "duanwu": _boss("duanwu", "艾舟沉江郎", "系艾草香囊的少年", "端午江水翻绿，一只系着艾草的小舟从雾中漂来。少年站在船头，香囊早已湿透。", "他为心上人缝了艾草香囊，想赛舟归来送她。江潮翻船，香囊沉底，姑娘此后年年悬艾等舟。", ("艾草香苦，苦得像一口没咽下的告别。", "江面鼓声很远，像从水底传来。", "他摸着湿透的香囊，仍怕她嫌针脚歪。"), "小舟慢慢沉入江雾，艾草香留在水面。", "江雾里落下一枚青绿铭刻之羽，像一枚湿透却仍有香气的香囊。", "江湾"),
    "qixi": _boss("qixi", "星桥错约女", "银河桥下的织梦少女", "七夕夜，星河低垂。少女坐在断开的星桥边，手中织着一段永远接不上的梦。", "她与少年约在鹊桥下看星，却因一场误会错过。桥年年会成，她却总在错的桥头等。", ("星光落在她发间，像细小的针。", "她织出的梦一靠近桥心便断开。", "鹊羽纷纷落下，却没有一只肯带路。"), "她把未织完的梦放进星河，桥光随之暗下。", "星桥边落下一枚银蓝铭刻之羽，像一场只差一步的相逢。", "星桥"),
    "zhongyuan": _boss("zhongyuan", "河灯无归郎", "放河灯的少年魂", "中元夜，河面浮满灯盏。少年蹲在岸边，一盏盏放灯，却没有一盏照回家的路。", "他死在离乡的水路上，忘了归处，只记得有人在家门口等灯。每年中元，他放灯寻路，也替自己寻名。", ("河灯一盏盏远去，像无人认领的名字。", "他把灯推得很轻，怕惊醒水下亡人。", "灯影映出一张年轻却陌生的脸。"), "最后一盏河灯漂远，他站在岸边，像终于不再追。", "河灯旁浮起一枚暖黄铭刻之羽，像一条照不到尽头的归路。", "河岸"),
    "zhongqiu": _boss("zhongqiu", "月下缺环女", "月下戴残玉环的少女", "中秋月圆，少女坐在桂影下，腕上玉环缺了一角。月越圆，她越显得孤单。", "她与少年各执半只玉环，说月圆时合环成亲。少年死在归途，月年年圆，玉环却再也不圆。", ("桂香很淡，淡得像一句被忍住的哭声。", "她抬腕照月，缺口正好盛住一片月光。", "团圆宴的声音从远处传来，与她毫不相干。"), "她把残环放在桂树下，月光慢慢替它补了一瞬。", "桂影中落下一枚月白铭刻之羽，像一只永远缺了一角的玉环。", "桂树下"),
    "chongyang": _boss("chongyang", "茱萸望山郎", "登高望归的少年", "重阳风高，山顶插满茱萸。少年站在最高处，望着一条没有人来的山路。", "他与姑娘约好重阳登高避灾。姑娘被病困在山下，后来再没醒来，他却年年登高，替两人插满茱萸。", ("茱萸香辛，辛得人眼眶发热。", "他把多出的一枝插在身旁空处。", "山路蜿蜒向下，却没有脚步声。"), "他拔下身旁那枝茱萸，轻轻放进风里。", "山风中落下一枚赤褐铭刻之羽，像一枝始终留给她的茱萸。", "高山"),
    "hanyi": _boss("hanyi", "寄衣雪娘", "缝寒衣的姑娘", "寒衣节，针线篮自己翻开。姑娘低头缝着一件寒衣，袖口却永远差最后一针。", "她给远戍少年寄寒衣，衣到边关时人已埋在雪里。她不知死讯，只怪自己缝得太慢。", ("针尖刺破指腹，血珠像一点红线。", "寒衣很厚，却暖不到该暖的人。", "她反复量袖长，像怕那人长高了。"), "她把寒衣叠好，放进没有地址的包袱里。", "针线间浮起一枚灰蓝铭刻之羽，像一件终于缝完却寄不到的寒衣。", "针线房"),
    "xiayuan": _boss("xiayuan", "水官沉愿女", "把愿书沉进水里的少女", "下元夜，水面无风自漩。少女跪在岸边，将愿书一页页沉入水中。", "她求水官赦免心上人的罪，却不知那罪本就是替她顶下。愿书沉了很多年，她才知道错从来不在她。", ("水面吞下愿书，没有一点回声。", "她的袖口全湿，却仍写下一页又一页。", "水下似有人把愿书轻轻推回。"), "她停笔良久，把最后一页愿书撕成两半。", "水中浮起一枚墨蓝铭刻之羽，像一封再也不用替谁求赦的愿书。", "水岸"),
    "laba": _boss("laba", "粥香等归郎", "熬腊八粥的少年", "腊八清晨，旧灶上粥香滚起。少年守着一锅甜粥，不断往空碗里添热气。", "他为赶路姑娘熬腊八粥，想等她进门暖身。姑娘冻死在归路，他却怕粥凉，添柴添到天明。", ("粥香很甜，甜得让人心里发酸。", "他用勺背敲碗，像在催人回家。", "灶火映着他的脸，仍是很年轻的模样。"), "他把那碗粥端到门外，热气散进冷风里。", "灶边落下一枚米白铭刻之羽，像一碗再也没人喝到的腊八粥。", "旧灶"),
    "xiaonian": _boss("xiaonian", "灶前糖衣女", "灶前熬糖的少女", "小年夜，灶前糖香浓得化不开。少女搅着糖浆，案上却压着一纸退婚书。", "她想熬甜糖，请灶王替心上人说几句好话。糖还没冷，退婚书先到，她便年年把苦事熬成甜味。", ("糖丝拉得很长，像断不开的旧缘。", "她笑着尝糖，却被甜得红了眼。", "灶火噼啪，像有人撕碎红纸。"), "她把糖衣浇在退婚书上，纸字慢慢化开。", "糖香里浮起一枚蜜色铭刻之羽，像一句被熬到发苦的好话。", "灶前"),
}


class SeasonalBossService(CoreService):
    """按节令出现的岁时情劫首领。"""

    def open_recent_past_event_for_today(self, lookback_days: int = 45) -> dict[str, Any] | None:
        """为当前业务日补生成最近已过的岁时情劫。

        这个函数默认不自动调用，只适合临时在启动回调里手动放开。
        它不会覆盖已有首领，也不会在今天本来就是节气/节日时抢走原机制。
        """

        day = self._business_date()
        self._close_expired_events()
        event = self.db.fetch_one(
            "SELECT * FROM seasonal_boss_events WHERE business_day = ?",
            (day.isoformat(),),
        )
        if event:
            return dict(event)

        today_boss, _today_type, _today_weight = self._boss_for_date(day)
        if today_boss:
            return None

        past = self._recent_past_boss_for_date(day, lookback_days)
        if not past:
            return None

        source_day, boss_def, event_type, weight_type = past
        echo_type = f"岁时回响·{source_day.isoformat()}·{event_type}"
        return self._open_event(day, boss_def, echo_type, weight_type)

    def status(self, client_id: str) -> str:
        """查看今日岁时情劫。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        event = self._today_event(create=True, update=True)
        if not event:
            pending = self._latest_rewardable(client_id)
            next_info = self._next_boss_text()
            if pending:
                return hint("今日无岁时情劫，但你有首领奖励待领取。", "发送：首领奖励")
            return f"今日无岁时情劫。\n{next_info}"
        return self._format_status(event)

    def ranking(self, client_id: str) -> str:
        """查看今日或最近首领排行。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        event = self._today_event(create=False, update=True) or self._latest_event()
        if not event:
            return hint("暂无岁时情劫记录。", self._next_boss_text())
        rows = self._participants(event["event_id"])
        if not rows:
            return hint(f"{event['boss_name']} 暂无挑战记录。", "发送：挑战首领 参与今日岁时情劫。")
        lines = [f"☆岁时情劫排行·{event['boss_name']}☆"]
        for index, row in enumerate(rows[:10], start=1):
            lines.append(
                f"{index}. {self.format_player_name(row['client_id'])} "
                f"伤害{row['damage']} 贡献{self._contribution(row['damage'], event):.1%} "
                f"挑战{row['challenge_count']}/{SEASONAL_BOSS_MAX_CHALLENGES}次"
            )
        return "\n".join(lines)

    def challenge(self, client_id: str) -> str:
        """挑战今日岁时情劫。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        self.cleanup_battle_records()
        assert player is not None

        event = self._today_event(create=True, update=True)
        if not event:
            return hint("今日无岁时情劫。", self._next_boss_text())
        if event["status"] != "开启":
            return hint(f"{event['boss_name']} 已经{event['status']}，不能继续挑战。", "发送：首领奖励 查看是否可以领取奖励。")
        if player["status"] != "空闲":
            return self._busy_challenge_hint(player["status"])
        if int(player["hp"]) <= 0:
            return hint("血气不足，无法挑战首领。", "发送：休息，时间到后发送：结束休息")

        check = self._challenge_check(event["event_id"], client_id)
        if check:
            return check

        result = self._fight_boss(player, event)
        damage = min(int(result["damage"]), int(event["hp"]))
        killed = False
        with self.db.transaction() as conn:
            fresh = conn.execute(
                "SELECT * FROM seasonal_boss_events WHERE event_id = ? AND status = '开启'",
                (event["event_id"],),
            ).fetchone()
            if not fresh:
                return hint("今日岁时情劫已经结束。", "发送：首领奖励 查看是否可以领取奖励。")
            current = conn.execute(
                """
                SELECT challenge_count, last_challenge_at
                FROM seasonal_boss_participants
                WHERE event_id = ? AND client_id = ?
                """,
                (event["event_id"], client_id),
            ).fetchone()
            if current and int(current["challenge_count"]) >= SEASONAL_BOSS_MAX_CHALLENGES:
                return hint("今日挑战次数已用完。", "等下一次岁时情劫出现后再挑战。")
            if current:
                last = dt(current["last_challenge_at"])
                left = timedelta(minutes=SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES) - (now() - last) if last else timedelta()
                if left > timedelta():
                    seconds = max(1, int(left.total_seconds()))
                    return hint(f"岁时旧念尚未重新凝形，还需 {seconds // 60}分{seconds % 60}秒。", "稍后再发送：挑战首领")

            damage = min(damage, int(fresh["hp"]))
            left_hp = max(0, int(fresh["hp"]) - damage)
            killed = left_hp <= 0
            conn.execute(
                "UPDATE players SET hp = ?, mp = ? WHERE client_id = ?",
                (result["hp_left"], result["mp_left"], client_id),
            )
            conn.execute(
                """
                INSERT INTO seasonal_boss_participants
                (event_id, client_id, damage, challenge_count, last_challenge_at, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(event_id, client_id)
                DO UPDATE SET
                    damage = damage + excluded.damage,
                    challenge_count = challenge_count + 1,
                    last_challenge_at = excluded.last_challenge_at,
                    updated_at = excluded.updated_at
                """,
                (event["event_id"], client_id, damage, ts(), ts(), ts()),
            )
            if killed:
                conn.execute(
                    """
                    UPDATE seasonal_boss_events
                    SET hp = 0, status = '已击破', killed_at = ?, result = ?
                    WHERE event_id = ?
                    """,
                    (ts(), dump_json({"killer": client_id}), event["event_id"]),
                )
            else:
                conn.execute(
                    "UPDATE seasonal_boss_events SET hp = ? WHERE event_id = ?",
                    (left_hp, event["event_id"]),
                )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '挑战首领', ?, ?)",
                (client_id, f"event={event['event_id']}, boss={event['boss_name']}, damage={damage}", ts()),
            )

        atmosphere = random.choice(load_json(event["atmosphere"], [])) if event["atmosphere"] else event["scene"]
        return self._challenge_log_block(
            title=f"挑战岁时情劫：{event['boss_name']}",
            subtitle=atmosphere,
            boss_name=event["boss_name"],
            player=player,
            result=result,
            damage=damage,
            left_hp=left_hp,
            max_hp=int(event["max_hp"]),
            killed=killed,
            killed_text=f"{event['boss_name']} 已被送回岁时深处，发送：首领奖励",
            alive_text=f"再次挑战需等待 {SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES} 分钟。",
            hurt_text="你被旧念重伤，建议先休息。",
        )

    def reward(self, client_id: str) -> str:
        """领取最近一次可领取的首领奖励。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        assert player is not None
        self._today_event(create=False, update=True)
        event = self._latest_rewardable(client_id)
        if not event:
            active = self._today_event(create=False, update=False)
            if active:
                return hint("今日岁时情劫还没有结束。", "继续挑战，或等其被击破/次日 04:00 退去后再发送：首领奖励")
            return hint("没有可领取的首领奖励。", "发送：首领 查看今日是否有岁时情劫。")

        participant = self.db.fetch_one(
            "SELECT * FROM seasonal_boss_participants WHERE event_id = ? AND client_id = ?",
            (event["event_id"], client_id),
        )
        if not participant:
            return hint("你没有参与这次岁时情劫。", "下一次出现时发送：挑战首领")
        if int(participant["reward_claimed"]):
            return participant["reward_text"] or "奖励已经领取。"

        reward = self._roll_reward(event, participant, player)
        with self.db.transaction() as conn:
            fresh = conn.execute(
                "SELECT reward_claimed FROM seasonal_boss_participants WHERE event_id = ? AND client_id = ?",
                (event["event_id"], client_id),
            ).fetchone()
            if not fresh or int(fresh["reward_claimed"]):
                return "奖励已经领取。"
            old_level, new_level = self.add_exp_conn(conn, client_id, reward["exp"])
            conn.execute(
                "UPDATE players SET source_stones = source_stones + ? WHERE client_id = ?",
                (reward["stones"], client_id),
            )
            for item_id, quantity in reward["ring_items"]:
                self.add_ring_conn(conn, client_id, item_id, quantity)
            for gem_id, level, quantity in reward["gems"]:
                self.add_gem_conn(conn, client_id, gem_id, level, quantity)
            feather_lines = []
            for _ in range(reward["feathers"]):
                cursor = conn.execute(
                    """
                    INSERT INTO inscription_feathers
                    (client_id, source_key, source_name, title, flavor_text, obtained_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        event["boss_key"],
                        event["boss_name"],
                        f"{event['boss_name']}遗羽",
                        event["feather_text"],
                        ts(),
                    ),
                )
                feather_lines.append(f"获得铭刻之羽 #{int(cursor.lastrowid)}：{event['boss_name']}遗羽")
            weapon_text = ""
            if reward["weapon"]:
                drop = reward["weapon"]
                weapon_id = weapon_service.create_weapon_conn(
                    conn,
                    client_id,
                    drop["weapon_def_id"],
                    drop["quality"],
                    drop["max_level"],
                    equipped=False,
                )
                weapon_text = f"获得武器 #{weapon_id} {drop['name']}[{drop['quality']}] 上限{drop['max_level']}"

            lines = [
                f"岁时情劫奖励：{event['boss_name']}",
                f"贡献：{reward['contribution']:.1%}，排名：{reward['rank']}",
                f"源石+{money(reward['stones'])}，经验+{reward['exp']}",
            ]
            if new_level > old_level:
                lines.append(f"等级提升：{old_level} -> {new_level}")
            lines.extend(reward["item_texts"])
            lines.extend(feather_lines)
            if feather_lines:
                lines.append(event["feather_text"])
            if weapon_text:
                lines.append(weapon_text)
            text = "\n".join(lines)
            conn.execute(
                """
                UPDATE seasonal_boss_participants
                SET reward_claimed = 1, reward_text = ?, updated_at = ?
                WHERE event_id = ? AND client_id = ?
                """,
                (text, ts(), event["event_id"], client_id),
            )
        return text

    def _today_event(self, create: bool, update: bool) -> dict[str, Any] | None:
        """读取或生成当前业务日首领。"""

        day = self._business_date()
        if update:
            self._close_expired_events()
        event = self.db.fetch_one(
            "SELECT * FROM seasonal_boss_events WHERE business_day = ?",
            (day.isoformat(),),
        )
        if event:
            return dict(event)
        if not create:
            return None
        boss_def, event_type, weight_type = self._boss_for_date(day)
        if not boss_def:
            return None
        return self._open_event(day, boss_def, event_type, weight_type)

    def _open_event(self, day: date, boss_def: BossDef, event_type: str, weight_type: str) -> dict[str, Any]:
        """按当前服务器生态生成今日首领。"""

        snapshot = self._world_snapshot()
        level = max(3, min(MAX_LEVEL, snapshot["median_level"] + random.randint(-3, 5)))
        median_attack = max(8, snapshot["median_attack"])
        median_hp = max(120, snapshot["median_hp"])
        defense = max(1, int(median_attack * random.uniform(0.32, 0.52)))
        attack = max(1, int(median_hp / 22 + level * 1.5))
        one_challenge_damage = self._estimate_challenge_damage(median_attack, level, defense)
        expected_players = max(1, min(18, round(snapshot["active_count"] * 0.35)))
        expected_attempts = 3 if weight_type == "普通节气" else 4
        difficulty = random.uniform(0.92, 1.12)
        max_hp = max(360, int(one_challenge_damage * expected_players * expected_attempts * difficulty))
        opened = datetime.combine(day, time(hour=DAY_RESET_HOUR))
        closes = opened + timedelta(days=1)
        with self.db.transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO seasonal_boss_events (
                    business_day, boss_key, event_type, weight_type, boss_name, title,
                    scene, story, farewell, feather_text, atmosphere,
                    level, max_hp, hp, attack, defense, difficulty,
                    status, opened_at, closes_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '开启', ?, ?)
                """,
                (
                    day.isoformat(),
                    boss_def.key,
                    event_type,
                    weight_type,
                    boss_def.name,
                    boss_def.title,
                    boss_def.scene,
                    boss_def.story,
                    boss_def.farewell,
                    boss_def.feather_text,
                    dump_json(list(boss_def.atmosphere)),
                    level,
                    max_hp,
                    max_hp,
                    attack,
                    defense,
                    difficulty,
                    ts(opened),
                    ts(closes),
                ),
            )
            event_id = int(cursor.lastrowid)
        event = self.db.fetch_one("SELECT * FROM seasonal_boss_events WHERE event_id = ?", (event_id,))
        assert event is not None
        return dict(event)

    def _close_expired_events(self) -> None:
        """过了次日 04:00，未击破的首领会退去。"""

        self.db.execute(
            """
            UPDATE seasonal_boss_events
            SET status = '已退去', result = ?
            WHERE status = '开启' AND closes_at <= ?
            """,
            (dump_json({"reason": "timeout"}), ts()),
        )

    def _latest_event(self) -> dict[str, Any] | None:
        """读取最近一条首领记录。"""

        row = self.db.fetch_one("SELECT * FROM seasonal_boss_events ORDER BY opened_at DESC LIMIT 1")
        return dict(row) if row else None

    def _latest_rewardable(self, client_id: str) -> dict[str, Any] | None:
        """读取玩家最近可领取的首领。"""

        row = self.db.fetch_one(
            """
            SELECT e.*
            FROM seasonal_boss_events e
            JOIN seasonal_boss_participants p ON p.event_id = e.event_id
            WHERE p.client_id = ?
              AND p.reward_claimed = 0
              AND e.status IN ('已击破', '已退去')
            ORDER BY e.opened_at DESC
            LIMIT 1
            """,
            (client_id,),
        )
        return dict(row) if row else None

    def _challenge_check(self, event_id: int, client_id: str) -> str:
        """检查挑战次数和 30 分钟冷却。"""

        row = self.db.fetch_one(
            """
            SELECT challenge_count, last_challenge_at
            FROM seasonal_boss_participants
            WHERE event_id = ? AND client_id = ?
            """,
            (event_id, client_id),
        )
        if not row:
            return ""
        if int(row["challenge_count"]) >= SEASONAL_BOSS_MAX_CHALLENGES:
            return hint("今日挑战次数已用完。", "等下一次岁时情劫出现后再挑战。")
        last = dt(row["last_challenge_at"])
        if not last:
            return ""
        left = timedelta(minutes=SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES) - (now() - last)
        if left <= timedelta():
            return ""
        seconds = max(1, int(left.total_seconds()))
        return hint(f"岁时旧念尚未重新凝形，还需 {seconds // 60}分{seconds % 60}秒。", "稍后再发送：挑战首领")

    @staticmethod
    def _busy_challenge_hint(status: str) -> str:
        """玩家本体忙碌时，解释为什么不能挑战首领。"""

        if status == "探险中":
            return hint(
                "本体正在探险，不能挑战首领。",
                "行商化身仍可跑商；先发送：探险状态，30 分钟后发送：结束探险，再发送：挑战首领",
            )
        return hint(f"当前状态为 {status}，不能挑战首领。", "先结束当前状态，再发送：挑战首领")

    def _fight_boss(self, player: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        """结算一次挑战；这里只算数值和逐回合日志，不写数据库。"""

        client_id = player["client_id"]
        weapon_service.ensure_starter_weapon(client_id)
        weapon = weapon_service.equipped_weapon(client_id)
        skill = weapon_service.skill(weapon["skill_id"]) if weapon else None
        bonuses = self._merge_effects(self.equipment_bonuses(client_id), self._weapon_effects(weapon))
        player_attack = int(player["base_attack"]) + (int(weapon["attack"]) if weapon else 0)
        hp = int(player["hp"])
        mp = int(player["mp"])
        total_damage = 0
        skill_times = 0
        rounds = 10 + min(4, int(player["level"]) // 25)
        interval = self._skill_interval(skill, weapon, bonuses)
        skill_cost = self._skill_cost(skill, bonuses)
        boss_hp = int(event["hp"])
        actions: list[dict[str, Any]] = []

        for round_no in range(1, rounds + 1):
            raw = player_attack + random.randint(int(player["level"]), max(int(player["level"]) * 4, int(player["level"]) + 3))
            raw = int(raw * (1 + float(bonuses.get("hit_bonus", 0)) * 0.5))
            skill_used = False
            skill_name = ""
            if skill and interval and round_no % interval == 0 and mp >= skill_cost:
                raw = int(raw * self._skill_power(skill, bonuses))
                mp -= skill_cost
                skill_times += 1
                skill_used = True
                skill_name = str(skill["name"])
            damage = damage_after_defense(raw, int(event["defense"]), self._pierce_rate(bonuses))
            combo_damage = self._combo_damage(raw, int(event["defense"]), bonuses)
            round_damage = damage + combo_damage
            total_damage += round_damage
            boss_hp = max(0, boss_hp - round_damage)
            hp_before_steal = hp
            if bonuses.get("life_steal"):
                hp = min(int(player["max_hp"]), hp + int(round_damage * float(bonuses["life_steal"])))
            action = {
                "round": round_no,
                "raw": raw,
                "damage": round_damage,
                "base_damage": damage,
                "combo_damage": combo_damage,
                "life_steal": max(0, hp - hp_before_steal),
                "skill_used": skill_used,
                "skill_name": skill_name,
                "mp_cost": skill_cost if skill_used else 0,
                "boss_hp_left": boss_hp,
                "boss_hp_max": int(event["max_hp"]),
                "boss_attack": False,
                "boss_damage": 0,
                "player_hp_left": hp,
                "player_mp_left": mp,
                "dodged": False,
            }
            if boss_hp <= 0:
                actions.append(action)
                break
            if random.random() >= min(0.45, float(bonuses.get("dodge_bonus", 0))):
                hurt = damage_after_defense(
                    random.randint(max(1, int(event["attack"] * 0.75)), max(1, int(event["attack"] * 1.18))),
                    int(player["defense"]),
                )
                reduced_hurt = self._reduce_damage(hurt, bonuses, skill_used)
                hp -= reduced_hurt
                action["boss_attack"] = True
                action["boss_hurt_raw"] = hurt
                action["boss_damage"] = reduced_hurt
            else:
                action["dodged"] = True
            action["player_hp_left"] = max(0, hp)
            action["player_mp_left"] = 0 if hp <= 0 else max(0, mp)
            actions.append(action)
            if hp <= 0:
                break
        mp_left = 0 if hp <= 0 else max(0, mp)
        return {
            "damage": max(1, total_damage),
            "hp_left": max(0, hp),
            "mp_left": mp_left,
            "skill_times": skill_times,
            "actions": actions,
        }

    def _challenge_log_block(
        self,
        *,
        title: str,
        subtitle: str,
        boss_name: str,
        player: dict[str, Any],
        result: dict[str, Any],
        damage: int,
        left_hp: int,
        max_hp: int,
        killed: bool,
        killed_text: str,
        alive_text: str,
        hurt_text: str,
    ) -> str:
        """把首领挑战整理成包含逐次出手的代码块。"""

        lines = [
            title,
            subtitle,
            "",
            "一、战斗明细",
        ]
        actions = result.get("actions")
        if isinstance(actions, list) and actions:
            for action in actions:
                lines.extend(self._boss_action_lines(action, boss_name, player))
        else:
            lines.append("无逐次出手记录。")

        lines.extend(
            [
                "",
                "二、最终结算",
                f"本次造成伤害：{damage}",
                f"战斗后血气：{result['hp_left']}/{player['max_hp']}",
                f"战斗后精神：{result['mp_left']}/{player['max_mp']}",
                f"武器技能触发：{result['skill_times']} 次",
            ]
        )
        if int(result["hp_left"]) <= 0:
            lines.append(hurt_text)
        if killed:
            lines.append(killed_text)
        else:
            lines.append(f"剩余旧念：{left_hp}/{max_hp}")
            lines.append(alive_text)
        return "```javascript\r\n" + "\r\n".join(lines) + "\r\n```"

    @staticmethod
    def _boss_action_lines(action: dict[str, Any], boss_name: str, player: dict[str, Any]) -> list[str]:
        """整理一回合首领战日志。"""

        round_no = int(action.get("round", 0))
        damage = int(action.get("damage", 0))
        combo_damage = int(action.get("combo_damage", 0))
        life_steal = int(action.get("life_steal", 0))
        boss_hp_left = max(0, int(action.get("boss_hp_left", 0)))
        boss_hp_max = max(1, int(action.get("boss_hp_max", 1)))
        skill_name = str(action.get("skill_name") or "")
        if action.get("skill_used"):
            attack_text = f"技能「{skill_name}」"
            cost_text = f"，消耗精神 {int(action.get('mp_cost', 0))}"
        else:
            attack_text = "普通攻击"
            cost_text = ""
        combo_text = f"，连击追加 {combo_damage}" if combo_damage > 0 else ""
        steal_text = f"，吸血 +{life_steal}" if life_steal > 0 else ""
        lines = [
            f"第 {round_no} 回合",
            f"  我方出手：{attack_text}，造成 {damage} 伤害{combo_text}{steal_text}{cost_text}；{boss_name} 旧念 {boss_hp_left}/{boss_hp_max}",
        ]
        if boss_hp_left <= 0:
            lines.append(f"  首领出手：{boss_name} 已消散。")
            return lines

        hp_left = max(0, int(action.get("player_hp_left", 0)))
        mp_left = max(0, int(action.get("player_mp_left", 0)))
        if action.get("dodged"):
            lines.append(
                f"  首领出手：{boss_name} 攻击落空；"
                f"我方血气 {hp_left}/{player['max_hp']}，精神 {mp_left}/{player['max_mp']}"
            )
            return lines

        hurt = int(action.get("boss_damage", 0))
        raw_hurt = int(action.get("boss_hurt_raw", hurt))
        reduce_text = f"，减免 {max(0, raw_hurt - hurt)}" if raw_hurt > hurt else ""
        lines.append(
            f"  首领出手：{boss_name} 造成 {hurt} 伤害{reduce_text}；"
            f"我方血气 {hp_left}/{player['max_hp']}，精神 {mp_left}/{player['max_mp']}"
        )
        return lines

    def _roll_reward(self, event: dict[str, Any], participant: dict[str, Any], player: dict[str, Any]) -> dict[str, Any]:
        """按贡献、排名和节日权重生成奖励。"""

        rows = self._participants(event["event_id"])
        rank = next((index for index, row in enumerate(rows, start=1) if row["client_id"] == player["client_id"]), len(rows))
        contribution = self._contribution(int(participant["damage"]), event)
        killed_factor = 1.0 if event["status"] == "已击破" else 0.55
        weight = str(event["weight_type"])
        rank_factor = {1: 1.18, 2: 1.08, 3: 1.0}.get(rank, 0.92)
        stones = max(1, int((int(event["level"]) * 850 + int(event["max_hp"]) * 0.015) * killed_factor * (0.45 + contribution * 2.5) * rank_factor))
        exp = max(1, int(monster_exp(event["level"], 1.8, player["level"]) * killed_factor * (0.6 + contribution * 1.8)))
        feathers = self._feather_count(weight, contribution, rank)
        ring_items: list[tuple[str, int]] = []
        gems: list[tuple[str, int, int]] = []
        item_texts: list[str] = []

        recover = self._random_equipment_item("恢复类")
        if recover:
            ring_items.append((recover["equipment_item_id"], 1))
            item_texts.append(f"纳戒获得 {recover['name']} x1")
        gem = self._random_equipment_item("宝石")
        if gem and random.random() < 0.18 + contribution * 0.35:
            level = 1 + (1 if random.random() < min(0.25, contribution) else 0)
            gems.append((gem["equipment_item_id"], level, 1))
            item_texts.append(f"宝石获得 {gem['name']} {level}级 x1")
        book = self._random_equipment_item("技能书")
        if book and random.random() < 0.08 + contribution * 0.25:
            ring_items.append((book["equipment_item_id"], 1))
            item_texts.append(f"纳戒获得 {book['name']} x1")
        weapon = None
        if random.random() < 0.04 + contribution * 0.18:
            weapon = weapon_service.roll_weapon_drop(max(player["level"], event["level"]), "")
        return {
            "rank": rank,
            "contribution": contribution,
            "stones": stones,
            "exp": exp,
            "feathers": feathers,
            "ring_items": ring_items,
            "gems": gems,
            "weapon": weapon,
            "item_texts": item_texts,
        }

    @staticmethod
    def _feather_count(weight_type: str, contribution: float, rank: int) -> int:
        """计算铭刻之羽数量。"""

        if weight_type == "高权重传统节日":
            chance = 0.35
        elif weight_type == "普通传统节日":
            chance = 0.25
        else:
            chance = 0.20

        count = 1 if contribution >= 0.03 or random.random() < chance else 0
        if rank <= 3:
            count += 2 if weight_type == "高权重传统节日" else 1
            if rank == 1 and weight_type == "高权重传统节日":
                count += 1
        return count

    def _random_equipment_item(self, category: str) -> dict[str, Any] | None:
        """随机纳戒物品，不包含开孔器。"""

        rows = self.db.fetch_all(
            """
            SELECT * FROM equipment_item_defs
            WHERE category = ?
              AND equipment_item_id != 'kaikongqi'
            """,
            (category,),
        )
        return random.choice(rows) if rows else None

    def _participants(self, event_id: int) -> list[dict[str, Any]]:
        """读取首领贡献排行。"""

        return self.db.fetch_all(
            """
            SELECT * FROM seasonal_boss_participants
            WHERE event_id = ?
            ORDER BY damage DESC, updated_at ASC
            """,
            (event_id,),
        )

    def _contribution(self, damage: int, event: dict[str, Any]) -> float:
        """计算贡献占比。"""

        total = self.db.fetch_one(
            "SELECT COALESCE(SUM(damage), 0) AS total FROM seasonal_boss_participants WHERE event_id = ?",
            (event["event_id"],),
        )
        total_damage = int(total["total"] if total else 0)
        if total_damage <= 0:
            return 0.0
        return max(0.0, min(1.0, int(damage) / total_damage))

    def _world_snapshot(self) -> dict[str, int]:
        """读取近期活跃生态，用于动态难度。"""

        players = self.db.fetch_all("SELECT * FROM players")
        if not players:
            return {"active_count": 1, "median_level": 1, "median_attack": 12, "median_hp": 120}
        levels = sorted(max(1, int(row["level"])) for row in players)
        attacks = []
        hps = []
        for row in players:
            weapon = self.db.fetch_one(
                "SELECT attack FROM player_weapons WHERE owner_id = ? AND equipped = 1 LIMIT 1",
                (row["client_id"],),
            )
            attacks.append(max(1, int(row["base_attack"]) + (int(weapon["attack"]) if weapon else 0)))
            hps.append(max(1, int(row["max_hp"])))
        return {
            "active_count": max(1, len(players)),
            "median_level": int(median(levels)),
            "median_attack": int(median(attacks)),
            "median_hp": int(median(hps)),
        }

    @staticmethod
    def _estimate_challenge_damage(median_attack: int, level: int, boss_defense: int) -> int:
        """估算中位玩家单次挑战伤害。"""

        per_round = damage_after_defense(int(median_attack * 1.25 + level * 2.2), boss_defense)
        return max(25, per_round * 10)

    @staticmethod
    def _business_date() -> date:
        """取当前业务日日期。"""

        return (now() - timedelta(hours=DAY_RESET_HOUR)).date()

    @staticmethod
    def _boss_for_date(value: date) -> tuple[BossDef | None, str, str]:
        """按公历节气和农历节日选择今日首领。"""

        choices: list[tuple[int, str, str, BossDef]] = []
        term_key = _solar_term_key(value)
        if term_key:
            choices.append((1, "二十四节气", "普通节气", BOSS_DEFS[term_key]))

        try:
            lunar = LunarDate.fromSolarDate(value.year, value.month, value.day)
            festival_key = LUNAR_FESTIVAL_DATES.get((lunar.month, lunar.day))
            if festival_key:
                weight = "高权重传统节日" if festival_key in HIGH_WEIGHT_FESTIVALS else "普通传统节日"
                priority = 3 if festival_key in HIGH_WEIGHT_FESTIVALS else 2
                choices.append((priority, "传统节日", weight, BOSS_DEFS[festival_key]))
            tomorrow_lunar = LunarDate.fromSolarDate((value + timedelta(days=1)).year, (value + timedelta(days=1)).month, (value + timedelta(days=1)).day)
            if tomorrow_lunar.month == 1 and tomorrow_lunar.day == 1:
                choices.append((2, "传统节日", "普通传统节日", BOSS_DEFS["chuxi"]))
        except ValueError:
            pass

        if not choices:
            return None, "", ""
        _priority, event_type, weight_type, boss_def = sorted(choices, key=lambda item: item[0], reverse=True)[0]
        return boss_def, event_type, weight_type

    def _recent_past_boss_for_date(self, value: date, lookback_days: int) -> tuple[date, BossDef, str, str] | None:
        """从指定日期往前找最近一个已经过去的节气或传统节日首领。"""

        for offset in range(1, max(1, lookback_days) + 1):
            day = value - timedelta(days=offset)
            boss_def, event_type, weight_type = self._boss_for_date(day)
            if boss_def:
                return day, boss_def, event_type, weight_type
        return None

    def _next_boss_text(self) -> str:
        """展示下一次岁时情劫。"""

        start = self._business_date()
        for offset in range(1, 370):
            day = start + timedelta(days=offset)
            boss_def, event_type, _weight = self._boss_for_date(day)
            if boss_def:
                return f"下一次岁时情劫：{day.isoformat()} · {event_type} · {boss_def.name}，约 {offset} 天后。"
        return "暂未找到下一次岁时情劫。"

    def _format_status(self, event: dict[str, Any]) -> str:
        """格式化当前首领状态。"""

        closes = dt(event["closes_at"])
        left = max(0, int((closes - now()).total_seconds() // 60) + 1) if closes else 0
        extra = "\n今日为人间重节，旧愿尤深，铭刻之羽更易遗落。" if event["weight_type"] == "高权重传统节日" else ""
        source = self._echo_source_text(event)
        return (
            f"☆今日岁时情劫·{event['boss_name']}☆\n"
            f"{event['title']}，现于{BOSS_DEFS[event['boss_key']].location}。\n"
            f"{source}"
            f"{event['scene']}\n"
            f"等级:{event['level']} 血量:{event['hp']}/{event['max_hp']} 状态:{event['status']}\n"
            f"剩余约 {left} 分钟，挑战冷却 {SEASONAL_BOSS_CHALLENGE_COOLDOWN_MINUTES} 分钟，"
            f"每日最多 {SEASONAL_BOSS_MAX_CHALLENGES} 次。\n"
            f"{event['story']}{extra}"
        )

    @staticmethod
    def _echo_source_text(event: dict[str, Any]) -> str:
        """把岁时回响的来源补充到状态里。"""

        event_type = str(event["event_type"])
        if not event_type.startswith("岁时回响·"):
            return ""
        parts = event_type.split("·", 2)
        if len(parts) < 3:
            return "这是最近已过节令在今日留下的岁时回响。\n"
        return f"回响来源:{parts[1]} · {parts[2]}。\n"


service = SeasonalBossService(db)

__all__ = ["BOSS_DEFS", "SeasonalBossService", "service"]
