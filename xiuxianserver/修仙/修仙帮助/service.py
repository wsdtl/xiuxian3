"""修仙帮助组件服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..common import CoreService, currency_name
from ..format_text import T
from ..markdown_utils import markdown_link
from ..public_url import public_url
from ..sql import db

HELP_IMAGE = Path(__file__).with_name("help.jpg")


GUIDE_COMMANDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "成长": (
        "修行成长",
        (
            "修仙信息",
            "状态",
            "修仙日记",
            "签到",
            "新手礼包",
            "休息",
            "结束休息",
            "自动用药",
            "银行",
            "银行结息",
            "升级银行",
            "用户组",
        ),
    ),
    "行囊": (
        "行囊装备",
        (
            "背包",
            "纳戒",
            "保险箱",
            "武器",
            "装备",
            "孔位",
            "宝石",
            "体质重塑",
            "武器升限",
            "祈愿",
            "十连祈愿",
            "祈愿奖池",
            "我的凭证",
            "铭刻",
        ),
    ),
    "战斗": (
        "探险战斗",
        (
            "地图",
            "探险列表",
            "探险状态",
            "结束探险",
            "战斗日志",
            "首领",
            "首领状态",
            "挑战首领",
            "首领奖励",
            "虫洞",
            "虫洞状态",
            "挑战虫洞",
            "虫洞奖励",
            "决斗记录",
        ),
    ),
    "交易": (
        "交易流通",
        (
            "商场推荐",
            "跑商记录",
            "跑商限制",
            "跑商奖励",
            "自动出售",
            "出售全部 武器",
            "出售全部 宝石",
            "出售全部 技能书",
            "藏宝图",
            "领取藏宝图",
            "二手市场",
        ),
    ),
    "世界": (
        "宗门世界",
        (
            "地图",
            "宗门",
            "宗门成员",
            "宗门大会",
            "领取宗门大会奖励",
            "风云榜",
            "修仙早报",
            "修仙界历史",
            "人物史榜",
            "战斗名局",
            "修仙百科",
            "世界皮肤",
            "帮助",
            "修仙帮助",
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
    "行囊": "行囊",
    "装备": "行囊",
    "物品": "行囊",
    "纳戒": "行囊",
    "战斗": "战斗",
    "探险": "战斗",
    "首领": "战斗",
    "虫洞": "战斗",
    "交易": "交易",
    "商场": "交易",
    "跑商": "交易",
    "出售": "交易",
    "世界": "世界",
    "宗门": "世界",
    "地图": "世界",
    "历史": "世界",
}


class HelpService(CoreService):
    """修仙帮助图片、网页入口和固定导航。"""

    def web_help(self) -> str:
        """返回当前阶段的帮助入口提示。"""

        help_url = public_url("/xiuxian/help")
        map_url = public_url("/xiuxian/map")
        return (
            f"{markdown_link('修仙帮助网页', help_url)}\n"
            f"{markdown_link('修仙界地图', map_url)}\n\n"
            "发送：修仙帮助 查看指令速查图，发送：指南 查看关键入口。"
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
                "可用方向：成长、行囊、战斗、交易、世界。",
                buttons=self._guide_section_buttons(),
            )
        return self._guide_section(key)

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
                f"角色状态、每日收益、休息恢复和{currency_name()}管理。",
                GUIDE_COMMANDS["成长"][1],
            ),
            "行囊": (
                GUIDE_COMMANDS["行囊"][0],
                "背包、纳戒、保险箱、武器、装备、宝石和特殊消耗品。",
                GUIDE_COMMANDS["行囊"][1],
            ),
            "战斗": (
                GUIDE_COMMANDS["战斗"][0],
                "探险、休整、首领、虫洞和玩家对战。",
                GUIDE_COMMANDS["战斗"][1],
            ),
            "交易": (
                GUIDE_COMMANDS["交易"][0],
                "跑商、出售、藏宝图、二手市场和背包清理。",
                GUIDE_COMMANDS["交易"][1],
            ),
            "世界": (
                GUIDE_COMMANDS["世界"][0],
                "地图、宗门、世界记录、百科和帮助文档。",
                GUIDE_COMMANDS["世界"][1],
            ),
        }


service = HelpService(db)
