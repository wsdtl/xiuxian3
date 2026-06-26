"""修仙 Markdown 知识源边界。"""

from __future__ import annotations

from pathlib import Path


# Markdown 是玩家帮助、百科和开发约束共用的“规则入口”。
# 这里集中排除封版记录、实施步骤、绘图参考这类维护材料，避免它们被
# 帮助站或百科当成当前玩法事实。新增排除项时只改这里，别在各组件散写。
EXCLUDED_MARKDOWN_NAME_MARKERS = ("封版记录", "实施方案", "地图绘制资料")


def stable_markdown_paths(root: Path) -> list[Path]:
    """递归收集稳定 Markdown，并按相对路径排序。"""

    base = Path(root)
    return sorted(
        (path for path in base.rglob("*.md") if is_stable_markdown(path)),
        key=lambda item: item.relative_to(base).as_posix(),
    )


def is_stable_markdown(path: Path) -> bool:
    """判断 Markdown 是否允许进入帮助站和百科知识源。"""

    name = path.name
    return not any(marker in name for marker in EXCLUDED_MARKDOWN_NAME_MARKERS)
