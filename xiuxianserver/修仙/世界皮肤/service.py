"""世界皮肤组件服务。"""

from __future__ import annotations

import sqlite3
from typing import Any

from ..common import CoreService
from ..format_text import T
from ..sql import db
from ..world_skin import (
    current_skin_id,
    list_skin_packages,
    load_skin_package,
    validate_skin_package,
    apply_world_skin_package,
)


class WorldSkinService(CoreService):
    """世界皮肤包查看和主人切换。"""

    def info(self, client_id: str, *, is_master: bool = False) -> str:
        """查看当前世界皮肤和可用包。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        active_id = current_skin_id(self.db)
        packages = list_skin_packages()
        panel = T.panel()
        panel.section("世界皮肤")
        panel.line(f"当前：**{active_id}**")
        panel.hr()
        panel.line("可用包：")
        for package in packages:
            marker = "当前" if package.skin_id == active_id else "可切换"
            panel.line(f"{package.skin_id}｜{package.display_name}｜{package.version}｜{marker}")
        if is_master:
            panel.hr()
            panel.line("主人命令：世界皮肤切换 包名")
            panel.line("切换会先自动校验，失败不写库，异常会回滚。")
        return panel.render()

    def switch(self, client_id: str, message: str, *, is_master: bool = False) -> str:
        """校验并切换世界皮肤。"""

        player, error = self.require_player(client_id)
        if error:
            return error
        if not is_master:
            return T.hint("只有主人可以切换世界皮肤。", "普通玩家可以发送：世界皮肤 查看当前包。<世界皮肤>")
        skin_id = message.strip()
        if not skin_id:
            return T.hint("缺少皮肤包名。", "发送：世界皮肤 查看可用包，再发送：世界皮肤切换 包名。<世界皮肤>")
        try:
            package = load_skin_package(skin_id)
        except ValueError as exc:
            return T.hint(str(exc), "发送：世界皮肤 查看可用包。<世界皮肤>")

        errors = validate_skin_package(package, self.db)
        if errors:
            return self._validation_failed_text(package, errors)

        switched_by = str(player.get("display_name") or client_id)
        try:
            with self.db.transaction() as conn:
                counts = apply_world_skin_package(conn, package, switched_by=switched_by)
                integrity = conn.execute("PRAGMA integrity_check").fetchone()
                integrity_text = str(integrity[0] if integrity else "")
                if integrity_text.lower() != "ok":
                    raise RuntimeError(f"数据库完整性检查失败：{integrity_text}")
        except (sqlite3.Error, RuntimeError, ValueError) as exc:
            return T.hint(f"世界皮肤切换失败：{exc}", "本次事务已回滚，当前世界不会留下半切换状态。<世界皮肤>")

        panel = T.panel()
        panel.section("世界皮肤切换完成")
        panel.line(f"当前：**{package.skin_id}**｜{package.display_name}")
        panel.line(f"版本：{package.version}｜作者：{package.author or '未注明'}")
        panel.hr()
        panel.line(
            "写入："
            f"地点 {counts['locations']}，"
            f"物品 {counts['items']}，"
            f"纳戒 {counts['ring_items']}，"
            f"武器 {counts['weapons']}，"
            f"技能 {counts['skills']}，"
            f"生物 {counts['monsters']}，"
            f"体质 {counts['physiques']}，"
            f"系统 {counts['system']}，"
            f"事件 {counts['events']}。"
        )
        panel.line("完整性检查：ok")
        return panel.render() + "<世界皮肤>"

    @staticmethod
    def _validation_failed_text(package: Any, errors: list[str]) -> str:
        panel = T.panel()
        panel.section("世界皮肤校验失败")
        panel.line(f"包名：**{package.skin_id}**｜{package.display_name}")
        for item in errors[:12]:
            panel.line(f"- {item}")
        if len(errors) > 12:
            panel.line(f"还有 {len(errors) - 12} 项未显示。")
        panel.hr()
        panel.line("切换已停止，数据库没有写入。")
        return panel.render() + "<世界皮肤>"


service = WorldSkinService(db)

__all__ = ["WorldSkinService", "service"]
