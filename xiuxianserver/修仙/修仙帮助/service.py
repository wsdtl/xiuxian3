"""修仙帮助组件服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..common import CoreService, currency_name
from ..format_text import T
from ..markdown_utils import inline_command_link, markdown_link
from ..public_url import public_url
from ..sql import db

HELP_IMAGE = Path(__file__).with_name("help.jpg")


GUIDE_COMMANDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "成长": (
        "修行成长",
        (
            "创建用户 名称",
            "改名 新名称",
            "修仙信息",
            "状态",
            "修仙日记",
            "签到",
            "新手礼包",
            "自动用药",
            "休息",
            "结束休息",
            "战斗日志",
        ),
    ),
    "账户": (
        "账户银行",
        (
            "货币",
            "银行",
            "银行结息",
            "升级银行",
            "银行升级",
            "存入货币 数量",
            "货币存入 数量",
            "取出货币 数量",
            "货币取出 数量",
            "用户组",
            "用户组后台",
            "用户组后台登录 登录码",
            "绑定用户组 绑定码",
        ),
    ),
    "行囊": (
        "行囊物品",
        (
            "背包",
            "使用 物品名 数量",
            "纳戒",
            "保险箱",
            "存入保险箱 物品名 数量",
            "取出保险箱 物品名 数量",
            "查看修仙物品 物品名",
        ),
    ),
    "奖励": (
        "奖励机缘",
        (
            "祈愿",
            "十连祈愿",
            "祈愿奖池",
            "我的凭证",
            "祈愿记录",
            "开启缘契",
            "查看所有缘契",
            "洞天福地",
            "洞天兑换 兑换码",
            "洞天记录",
        ),
    ),
    "武器": (
        "武器流派",
        (
            "武器",
            "查看武器 编号",
            "武器传奇 编号",
            "切换武器 编号",
            "升级武器 编号",
            "附魔武器 武器编号 技能书名",
            "武器升限 武器编号",
        ),
    ),
    "装备": (
        "装备宝石",
        (
            "装备",
            "装备升级 装备位",
            "孔位",
            "开孔 装备位",
            "镶嵌 装备位 孔位 宝石名",
            "拆卸 装备位 孔位",
            "宝石",
            "宝石升级 宝石名",
            "体质重塑",
        ),
    ),
    "铭刻": (
        "铭刻留名",
        (
            "铭刻",
            "铭刻之羽",
            "铭刻装备",
            "铭刻武器",
            "铭刻附魔",
            "铭刻技能",
        ),
    ),
    "探险": (
        "地图探险",
        (
            "地图",
            "位置",
            "探险列表",
            "导航 地点名",
            "去 地点名",
            "来 地点名",
            "探险 地点名",
            "探险状态",
            "结束探险",
            "探险记录",
        ),
    ),
    "战斗": (
        "玩家对战",
        (
            "战斗日志",
            "切磋 玩家名",
            "接受切磋 玩家名",
            "拒绝切磋 玩家名",
            "决斗 玩家名 数量",
            "接受决斗 玩家名",
            "拒绝决斗 玩家名",
            "决斗记录",
            "抢劫 玩家名",
        ),
    ),
    "首领": (
        "首领虫洞",
        (
            "首领",
            "首领状态",
            "挑战首领",
            "首领排行",
            "首领奖励",
            "虫洞",
            "虫洞状态",
            "挑战虫洞",
            "虫洞排行",
            "虫洞奖励",
        ),
    ),
    "交易": (
        "商路藏宝",
        (
            "商场推荐",
            "商场行情",
            "商场购买 商品名 数量",
            "商场出售 商品名 数量",
            "跑商记录",
            "跑商限制",
            "跑商奖励",
            "藏宝图",
            "藏宝图出价 数量",
            "领取藏宝图",
        ),
    ),
    "出售": (
        "出售二手",
        (
            "出售 物品名 数量",
            "自动出售",
            "出售全部 武器",
            "出售全部 宝石",
            "出售全部 技能书",
            "二手市场",
            "二手市场上架 物品名 数量 价格",
            "二手市场下架",
            "二手市场购买 编号",
        ),
    ),
    "宗门": (
        "宗门山门",
        (
            "宗门",
            "宗门成员",
            "建立宗门 x y 宗门名",
            "加入宗门 宗门名",
            "退出宗门",
            "确认退出宗门",
            "取消退出宗门",
            "宗门大会",
            "领取宗门大会奖励",
        ),
    ),
    "世界": (
        "世界文卷",
        (
            "风云榜",
            "修仙早报",
            "修仙界历史",
            "人物史榜",
            "宗门史榜",
            "城池史榜",
            "战斗名局",
            "商路奇闻",
            "异界虫洞录",
            "人物志 玩家名",
            "修仙百科",
            "修仙百科 问题",
            "世界皮肤",
            "修仙帮助",
        ),
    ),
    "消息": (
        "公开消息流",
        (
            "消息流水",
        ),
    ),
}
GUIDE_ALIASES = {
    "主": "",
    "主页": "",
    "总览": "",
    "成长": "成长",
    "玩家": "成长",
    "修炼": "成长",
    "账户": "账户",
    "账号": "账户",
    "银行": "账户",
    "用户组": "账户",
    "行囊": "行囊",
    "物品": "行囊",
    "纳戒": "行囊",
    "奖励": "奖励",
    "祈愿": "奖励",
    "缘契": "奖励",
    "洞天": "奖励",
    "装备": "装备",
    "武器": "武器",
    "宝石": "装备",
    "铭刻": "铭刻",
    "地图": "探险",
    "位置": "探险",
    "探险": "探险",
    "战斗": "战斗",
    "对战": "战斗",
    "首领": "首领",
    "虫洞": "首领",
    "交易": "交易",
    "商场": "交易",
    "跑商": "交易",
    "藏宝图": "交易",
    "出售": "出售",
    "二手": "出售",
    "市场": "出售",
    "宗门": "宗门",
    "山门": "宗门",
    "大会": "宗门",
    "世界": "世界",
    "历史": "世界",
    "百科": "世界",
    "帮助": "世界",
    "消息": "消息",
    "消息流": "消息",
    "消息流水": "消息",
    "消息记录": "消息",
}

DAILY_GUIDE_GROUPS: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "修行",
        (
            ("签到", "签到"),
            ("状态", "状态"),
            ("信息", "修仙信息"),
            ("休息", "休息"),
            ("结束休息", "结束休息"),
        ),
    ),
    (
        "探险",
        (
            ("地图", "地图"),
            ("列表", "探险列表"),
            ("探险", "探险"),
            ("状态", "探险状态"),
            ("结算", "结束探险"),
        ),
    ),
    (
        "整理",
        (
            ("背包", "背包"),
            ("纳戒", "纳戒"),
            ("保险箱", "保险箱"),
            ("自动出售", "自动出售"),
            ("卖宝石", "出售全部 宝石"),
            ("卖技能书", "出售全部 技能书"),
        ),
    ),
    (
        "成长",
        (
            ("武器", "武器"),
            ("装备", "装备"),
            ("宝石", "宝石"),
            ("孔位", "孔位"),
            ("升限", "武器升限"),
            ("体质", "体质重塑"),
        ),
    ),
    (
        "挑战",
        (
            ("首领", "首领"),
            ("挑战首领", "挑战首领"),
            ("首领奖励", "首领奖励"),
            ("虫洞", "虫洞"),
            ("挑战虫洞", "挑战虫洞"),
            ("虫洞奖励", "虫洞奖励"),
        ),
    ),
    (
        "交易",
        (
            ("商路", "商场推荐"),
            ("跑商奖励", "跑商奖励"),
            ("藏宝图", "藏宝图"),
            ("二手市场", "二手市场"),
        ),
    ),
    (
        "宗门",
        (
            ("宗门", "宗门"),
            ("成员", "宗门成员"),
            ("大会", "宗门大会"),
            ("领奖", "领取宗门大会奖励"),
        ),
    ),
    (
        "机缘",
        (
            ("祈愿", "祈愿"),
            ("十连", "十连祈愿"),
            ("凭证", "我的凭证"),
            ("缘契", "开启缘契"),
            ("洞天", "洞天福地"),
        ),
    ),
)


class HelpService(CoreService):
    """修仙帮助图片、网页入口和固定导航。"""

    def web_help(self) -> str:
        """返回当前阶段的帮助入口提示。"""

        help_url = public_url("/xiuxian/help")
        map_url = public_url("/xiuxian/map")
        return (
            f"{markdown_link('修仙帮助网页', help_url)}\n"
            f"{markdown_link('修仙界地图', map_url)}\n\n"
            "发送：修仙帮助 查看指令速查图，发送：引导 查看日常入口，发送：指南 查看关键入口。"
        )

    def map_help(self, player_id: str = "") -> str:
        """返回交互地图入口；带玩家 ID 时页面可展示当前位置。"""

        suffix = f"?player_id={quote(str(player_id), safe='')}" if player_id else ""
        map_url = public_url(f"/xiuxian/map{suffix}")
        return (
            f"{markdown_link('修仙界地图', map_url)}\n\n"
            "地图展示城池、秘境、特殊收购点、回收建筑、宗门山门和活跃事件；页面会每 60 秒刷新一次。"
        )

    def command_guide(self, section: str = "") -> str:
        """返回分方向的关键组件跳转按钮。"""

        key = self._guide_key(section)
        if not key:
            return self._guide_index()
        sections = self._guide_sections()
        if key not in sections:
            return T.hint(
                f"没有这个指南方向：{section.strip()}。",
                "可用方向：成长、账户、行囊、奖励、武器、装备、铭刻、探险、战斗、首领、交易、出售、宗门、世界、消息。",
                buttons=self._guide_section_buttons(),
            )
        return self._guide_section(key)

    def daily_guide(self) -> str:
        """返回无框命令链接组成的日常入口引导。"""

        panel = T.panel()
        panel.section("引导")
        panel.line("按当前想做的事点入口；这些是轻量引导，不是每日必做。")
        for title, commands in DAILY_GUIDE_GROUPS:
            links = "｜".join(inline_command_link(label, command) for label, command in commands)
            panel.line(f"{title}：{links}")
        return panel.render()

    def _guide_index(self) -> str:
        """返回指南方向首页。"""

        sections = self._guide_sections()
        panel = T.panel()
        panel.section("指南")
        panel.line("关键业务已经按方向拆分，先选方向，再进入具体按钮。")
        for key, (title, desc, _commands) in sections.items():
            panel.line(f"{title}：{desc} 发送：指南 {key}")
        return T.attach(panel.render(), T.buttons(*self._guide_section_buttons()))

    def _guide_section(self, key: str) -> str:
        """返回单个方向的按钮页。"""

        title, desc, commands = self._guide_sections()[key]
        panel = T.panel()
        panel.section(f"指南·{title}")
        panel.line(desc)
        panel.line("只放固定命令按钮；需要补参数的命令请看帮助网页或对应功能返回文本。")
        if key == "战斗":
            panel.line("切磋、决斗、抢劫和人物志都可以直接@对方；绑定用户组后会自动指向对方主角色。")
        return T.attach(panel.render(), T.buttons(*commands, "指南"))

    @staticmethod
    def _guide_key(section: str) -> str:
        """解析指南方向别名。"""

        value = str(section or "").strip()
        if not value:
            return ""
        return GUIDE_ALIASES.get(value, value)

    def _guide_section_buttons(self) -> tuple[str, ...]:
        """主指南方向按钮。"""

        return tuple(f"指南 {key}:{title}" for key, (title, _desc, _commands) in self._guide_sections().items())

    @staticmethod
    def _guide_sections() -> dict[str, tuple[str, str, tuple[str, ...]]]:
        """动态生成指南文案，避免世界皮肤切换后货币名仍停在旧值。"""

        return {
            "成长": (
                GUIDE_COMMANDS["成长"][0],
                "建档、改名、角色状态、日常收益、休息恢复和战斗日志。",
                GUIDE_COMMANDS["成长"][1],
            ),
            "账户": (
                GUIDE_COMMANDS["账户"][0],
                f"{currency_name()}银行、存取、结息、用户组和后台绑定。",
                GUIDE_COMMANDS["账户"][1],
            ),
            "行囊": (
                GUIDE_COMMANDS["行囊"][0],
                "背包、纳戒、保险箱和修仙物品查询。",
                GUIDE_COMMANDS["行囊"][1],
            ),
            "奖励": (
                GUIDE_COMMANDS["奖励"][0],
                "祈愿、凭证、缘契体验、洞天福地、兑换码和小游戏记录。",
                GUIDE_COMMANDS["奖励"][1],
            ),
            "武器": (
                GUIDE_COMMANDS["武器"][0],
                "武器详情、切换、升级、附魔、升限和传奇记录。",
                GUIDE_COMMANDS["武器"][1],
            ),
            "装备": (
                GUIDE_COMMANDS["装备"][0],
                "装备升级、开孔、镶嵌、拆卸、宝石和体质重塑。",
                GUIDE_COMMANDS["装备"][1],
            ),
            "铭刻": (
                GUIDE_COMMANDS["铭刻"][0],
                "铭刻之羽、装备铭刻、武器铭刻、附魔铭刻和技能铭刻。",
                GUIDE_COMMANDS["铭刻"][1],
            ),
            "探险": (
                GUIDE_COMMANDS["探险"][0],
                "地图、位置、导航、探险地点和探险结算。",
                GUIDE_COMMANDS["探险"][1],
            ),
            "战斗": (
                GUIDE_COMMANDS["战斗"][0],
                "切磋、决斗、抢劫和玩家战斗记录。",
                GUIDE_COMMANDS["战斗"][1],
            ),
            "首领": (
                GUIDE_COMMANDS["首领"][0],
                "岁时情劫、首领排行、首领奖励、异界虫洞和虫洞奖励。",
                GUIDE_COMMANDS["首领"][1],
            ),
            "交易": (
                GUIDE_COMMANDS["交易"][0],
                "商路推荐、行情、买卖、跑商收益和藏宝图。",
                GUIDE_COMMANDS["交易"][1],
            ),
            "出售": (
                GUIDE_COMMANDS["出售"][0],
                "背包清理、纳戒资产回收、二手市场上架和购买。",
                GUIDE_COMMANDS["出售"][1],
            ),
            "宗门": (
                GUIDE_COMMANDS["宗门"][0],
                "宗门信息、成员、建宗、入宗、退宗和宗门大会。",
                GUIDE_COMMANDS["宗门"][1],
            ),
            "世界": (
                GUIDE_COMMANDS["世界"][0],
                "世界历史、史榜、百科、世界皮肤和帮助入口。",
                GUIDE_COMMANDS["世界"][1],
            ),
            "消息": (
                GUIDE_COMMANDS["消息"][0],
                "查看驱动器收发消息的公开聊天框式短期流水。消息记录是同义入口，不单独放按钮。",
                GUIDE_COMMANDS["消息"][1],
            ),
        }


service = HelpService(db)
