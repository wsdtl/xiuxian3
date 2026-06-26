"""修仙富文本格式工具。

业务函数只负责选择要返回的文字类型；这里集中处理提示、按钮和正文卡排版。
"""

from __future__ import annotations

from .markdown_utils import split_button_tags


SECTION_ICON_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("世界皮肤",), "🎭"),
    (("指南", "修仙帮助", "修仙百科", "百科"), "📜"),
    (("历史", "风云", "史榜", "名局", "奇闻", "早报", "人物志", "日记", "记录", "日志"), "📜"),
    (("状态", "今日加成", "体质", "修仙信息"), "🌱"),
    (("宗门", "大会", "成员", "影响力", "贡献"), "🏯"),
    (("地图", "位置", "城池", "商路", "地标", "导航", "秘境"), "🗺️"),
    (("银行", "商场", "跑商", "市价", "贸易", "二手市场", "出售", "收益", "曲线"), "💰"),
    (("背包", "纳戒", "保险箱", "物品", "资产", "凭证", "奖品"), "📦"),
    (("武器", "装备", "孔位", "宝石", "铭刻"), "⚔️"),
    (("探险", "战力", "战斗", "对战", "切磋", "决斗", "首领", "虫洞"), "⚔️"),
    (("祈愿", "奖池", "奖励", "收获", "藏宝图"), "✨"),
    (("用户组", "后台", "使用流程", "边界"), "🧩"),
)
SECTION_ICON_PREFIXES = tuple(dict.fromkeys(icon for _keywords, icon in SECTION_ICON_RULES))


def section_title(title: object) -> str:
    """给正文卡栏目补一个轻量语义图标。

    图标只服务展示层，不进入命令、数据库字段或业务判断。这里按关键词
    做集中映射，避免各组件各写一套小装饰，后续新增栏目也能自然收敛。
    """

    value = str(title).strip()
    if not value or value.startswith(SECTION_ICON_PREFIXES):
        return value
    icon = _section_icon(value)
    return f"{icon} {value}" if icon else value


def _section_icon(title: str) -> str:
    """按栏目关键词选择图标；越具体、越高频的规则放越前。"""

    for keywords, icon in SECTION_ICON_RULES:
        if any(keyword in title for keyword in keywords):
            return icon
    return ""


class MdPanel:
    """引用块正文卡，适合资料和详情展示。"""

    def __init__(self) -> None:
        self._lines: list[str] = []

    def section(self, title: str) -> "MdPanel":
        """添加栏目标题。"""

        return self.line(f"**{section_title(title)}**")

    def line(self, text: object = "") -> "MdPanel":
        """添加一行正文；渲染时自动补引用符号。"""

        value = str(text).strip()
        if "\n" not in value:
            self._lines.append(value)
            return self

        for line in value.splitlines():
            self._lines.append(line.strip())
        return self

    def blank(self) -> "MdPanel":
        """添加正文卡内空行。"""

        self._lines.append("")
        return self

    def hr(self) -> "MdPanel":
        """添加正文卡内段落间隔。

        当前 markdown 客户端会把引用块里的 --- 误判成标题下划线，
        导致上一行被放大加粗；这里用空行分隔最稳。
        """

        if self._lines and self._lines[-1] != "":
            self.blank()
        return self

    def lines(self, lines: list[str]) -> "MdPanel":
        """批量添加行。"""

        for line in lines:
            self.line(line)
        return self

    def render(self) -> str:
        """渲染成 markdown 引用块。"""

        return "\n".join(">" if line == "" else f"> {line}" for line in self._lines).strip()


class T:
    """修仙文本格式工具。"""

    @staticmethod
    def tip(text: object) -> str:
        """提示文本，统一使用斜体。

        这是提示文本的底层格式函数；`T.hint()` 会调用它来组合
        “提示 + 建议 + 手工按钮”。
        """

        value = str(text).strip()
        return f"*{value}*" if value else ""

    @staticmethod
    def success(text: object) -> str:
        """成功文本保持普通文本。"""

        return str(text).strip()

    @staticmethod
    def hint(text: object, suggestion: object = "", buttons: tuple[str, ...] = ()) -> str:
        """生成失败、条件不足、冷却等完整提示。

        按钮只来自已经手写的尖括号标记或显式传入的 buttons，不做命令推断。
        """

        reason, reason_buttons = split_button_tags(str(text))
        advice, advice_buttons = split_button_tags(str(suggestion))
        all_buttons = [*reason_buttons, *advice_buttons, *[item for item in buttons if str(item).strip()]]

        parts: list[str] = []
        if reason.strip():
            parts.append(T.tip(reason))
        if advice.strip():
            parts.append(advice.strip())
        if all_buttons:
            if parts:
                parts.append("")
            parts.append(T.buttons(*all_buttons))
        return "\n".join(parts).strip()

    @staticmethod
    def attach(text: object, suggestion: object = "", buttons: tuple[str, ...] = ()) -> str:
        """把补充说明接到正文末尾，并保留手写按钮。

        这是普通正文拼接，不会把第一行改成提示格式。
        """

        content, content_buttons = split_button_tags(str(text))
        advice, advice_buttons = split_button_tags(str(suggestion))
        all_buttons = [*content_buttons, *advice_buttons, *[item for item in buttons if str(item).strip()]]

        parts: list[str] = []
        if content.strip():
            parts.append(content.strip())
        if advice.strip() and advice.strip() not in content:
            parts.append(advice.strip())
        if all_buttons:
            if parts:
                parts.append("")
            parts.append(T.buttons(*all_buttons))
        return "\n".join(parts).strip()

    @staticmethod
    def buttons(*commands: str) -> str:
        """生成手写按钮串。"""

        return "".join(f"<{str(command).strip()}>" for command in commands if str(command).strip())

    @staticmethod
    def panel() -> MdPanel:
        """创建正文卡。"""

        return MdPanel()
