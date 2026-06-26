"""用户组服务。

用户组只解决“多个通信入口映射到同一个修仙角色”的问题：
已有角色确认用户组后台登录，新入口使用一次性绑定码加入同一用户组。
它不会合并两个已有角色，也不会搬运背包、纳戒、银行、武器等业务资产。
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from ..format_text import T
from ..identity import (
    bind_client_to_player,
    client_id_has_player,
    ensure_player_identity,
    identities_for_player,
    player_exists,
    resolve_player_id,
)
from ..markdown_utils import markdown_link
from ..public_url import public_url
from ..sql import db


LOGIN_TTL_MINUTES = 15
BIND_CODE_TTL_MINUTES = 10
TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
USER_GROUP_ADMIN_PATH = "/xiuxian/user-groups"


class UserGroupService:
    """用户组绑定和用户组后台登录业务。"""

    def __init__(self, database: Any | None = None) -> None:
        self.db = database if database is not None else db

    def resolve_player_id(self, client_id: str) -> str:
        """把当前入口 ID 解析成用户组主角色 ID。"""

        return resolve_player_id(client_id, self.db)

    def overview(self) -> str:
        """返回用户组后台入口和绑定流程提示。"""

        panel = T.panel()
        panel.section("用户组后台")
        panel.line(f"网页登录：{user_group_admin_link()}")
        panel.line("用途：把 QQ、WS 或其它入口绑定到同一个修仙角色。")
        panel.blank()
        panel.section("使用流程")
        panel.line("1. 用已有角色打开网页，生成登录码。")
        panel.line("2. 在已有角色入口发送：用户组后台登录 登录码")
        panel.line("3. 网页登录成功后生成一次性绑定码。")
        panel.line("4. 用新入口发送：绑定用户组 绑定码")
        panel.blank()
        panel.section("边界")
        panel.line("只绑定入口身份，不合并两个已有角色，也不搬运背包、纳戒、银行、武器等资产。")
        return panel.render()

    def confirm_admin_login(self, player_id: str, message: str) -> str:
        """由已有角色账号确认浏览器后台生成的用户组登录挑战。"""

        challenge_id = message.strip().upper()
        if not challenge_id:
            return T.hint("缺少用户组后台登录码。", f"打开{user_group_admin_link()}生成登录码。\n然后发送：用户组后台登录 登录码")

        if not player_exists(player_id, self.db):
            return T.hint("当前账号还没有创建用户，不能登录用户组后台。", f"请先用已有角色账号打开{user_group_admin_link()}。")

        now_text = _ts()
        row = self.db.fetch_one(
            """
            SELECT challenge_id, session_id, confirmed_at, expires_at
            FROM user_group_login_challenges
            WHERE challenge_id = ?
            LIMIT 1
            """,
            (challenge_id,),
        )
        if not row:
            return T.hint("用户组后台登录码不存在或已失效。", f"请回到{user_group_admin_link()}重新生成登录码。")
        if row.get("confirmed_at"):
            return T.hint("这个用户组后台登录码已经确认过。", f"请回到{user_group_admin_link()}查看登录状态。")
        if str(row["expires_at"]) <= now_text:
            return T.hint("用户组后台登录码已过期。", f"请回到{user_group_admin_link()}重新生成登录码。")

        ensure_player_identity(player_id, self.db)
        self.db.execute(
            """
            UPDATE user_group_login_challenges
            SET player_id = ?, confirmed_at = ?
            WHERE challenge_id = ?
            """,
            (player_id, now_text, challenge_id),
        )
        self.db.execute(
            """
            INSERT OR REPLACE INTO user_group_sessions (session_id, player_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(row["session_id"]),
                player_id,
                _ts(datetime.now() + timedelta(minutes=LOGIN_TTL_MINUTES)),
                now_text,
            ),
        )
        return f"用户组后台登录已确认。\n回到{user_group_admin_link()}即可继续生成绑定码。"

    def create_login_challenge(self) -> dict[str, Any]:
        """创建一次用户组后台登录挑战，浏览器用 session_id 轮询登录状态。"""

        self.cleanup_expired()
        challenge_id = _token(8)
        session_id = secrets.token_urlsafe(24)
        now = datetime.now()
        self.db.execute(
            """
            INSERT INTO user_group_login_challenges (challenge_id, session_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                challenge_id,
                session_id,
                _ts(now + timedelta(minutes=LOGIN_TTL_MINUTES)),
                _ts(now),
            ),
        )
        return {
            "challenge_id": challenge_id,
            "session_id": session_id,
            "expires_in_seconds": LOGIN_TTL_MINUTES * 60,
        }

    def login_status(self, session_id: str) -> dict[str, Any]:
        """返回浏览器 session 的确认状态。"""

        session = self.session(session_id)
        if session:
            return {"confirmed": True, "player_id": session["player_id"]}
        return {"confirmed": False}

    def session(self, session_id: str) -> dict[str, Any] | None:
        """读取仍在有效期内的后台 session。"""

        value = str(session_id or "").strip()
        if not value:
            return None

        now_text = _ts()
        row = self.db.fetch_one(
            """
            SELECT session_id, player_id, expires_at
            FROM user_group_sessions
            WHERE session_id = ?
            LIMIT 1
            """,
            (value,),
        )
        if not row or str(row["expires_at"]) <= now_text:
            return None
        return row

    def create_bind_code(self, session_id: str) -> dict[str, Any]:
        """为已登录用户组创建一次性绑定码。"""

        session = self.session(session_id)
        if not session:
            raise PermissionError("用户组后台登录已过期，请重新登录。")

        player_id = str(session["player_id"])
        ensure_player_identity(player_id, self.db)
        code = _token(8)
        now = datetime.now()
        self.db.execute(
            """
            INSERT INTO user_group_bind_codes (code, player_id, expires_at, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                code,
                player_id,
                _ts(now + timedelta(minutes=BIND_CODE_TTL_MINUTES)),
                _ts(now),
            ),
        )
        return {
            "code": code,
            "player_id": player_id,
            "expires_in_seconds": BIND_CODE_TTL_MINUTES * 60,
        }

    def identities(self, session_id: str) -> list[dict[str, Any]]:
        """列出当前后台 session 对应用户组的入口身份。"""

        session = self.session(session_id)
        if not session:
            raise PermissionError("用户组后台登录已过期，请重新登录。")
        return identities_for_player(str(session["player_id"]), self.db)

    def bind_user_group(self, client_id: str, message: str) -> str:
        """把一个还没有角色的新入口绑定到绑定码对应的用户组。"""

        code = message.strip().upper()
        if not code:
            return T.hint("缺少绑定码。", f"请先在{user_group_admin_link()}生成绑定码。\n然后发送：绑定用户组 绑定码")

        normalized_client = str(client_id or "").strip()
        if not normalized_client:
            return T.hint("当前入口缺少 client_id，不能绑定。", "请换一个可识别用户身份的入口。")

        if client_id_has_player(normalized_client, self.db):
            return T.hint("当前账号已经创建过修仙用户，暂时不能绑定到其他用户组。", "已有角色合并需要单独处理。")

        current_player_id = resolve_player_id(normalized_client, self.db)
        if current_player_id != normalized_client:
            return T.hint("当前账号已经绑定过用户组。", "无需重复绑定。")

        now_text = _ts()
        row = self.db.fetch_one(
            """
            SELECT code, player_id, used_at, expires_at
            FROM user_group_bind_codes
            WHERE code = ?
            LIMIT 1
            """,
            (code,),
        )
        if not row:
            return T.hint("绑定码不存在。", f"请确认{user_group_admin_link()}生成的绑定码是否输入正确。")
        if row.get("used_at"):
            return T.hint("绑定码已经使用过。", f"请在{user_group_admin_link()}重新生成一次性绑定码。")
        if str(row["expires_at"]) <= now_text:
            return T.hint("绑定码已过期。", f"请在{user_group_admin_link()}重新生成绑定码。")

        player_id = str(row["player_id"])
        bind_client_to_player(normalized_client, player_id, self.db)
        self.db.execute(
            """
            UPDATE user_group_bind_codes
            SET used_by_client_id = ?, used_at = ?
            WHERE code = ?
            """,
            (normalized_client, now_text, code),
        )
        return "用户组绑定成功。\n之后这个入口会使用同一个修仙角色。"

    def cleanup_expired(self) -> None:
        """清理短期登录挑战、后台 session 和已失效绑定码。"""

        now_text = _ts()
        self.db.execute(
            "DELETE FROM user_group_login_challenges WHERE confirmed_at IS NULL AND expires_at <= ?",
            (now_text,),
        )
        self.db.execute("DELETE FROM user_group_sessions WHERE expires_at <= ?", (now_text,))
        self.db.execute(
            "DELETE FROM user_group_bind_codes WHERE used_at IS NOT NULL OR expires_at <= ?",
            (now_text,),
        )


def _token(length: int) -> str:
    """生成不含易混淆字符的短码。"""

    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(length))


def user_group_admin_url() -> str:
    """返回当前环境下的用户组后台公开地址。"""

    return public_url(USER_GROUP_ADMIN_PATH)


def user_group_admin_link(label: str = "用户组后台") -> str:
    """返回用户组后台 Markdown 改名链接，消息里不裸露真实地址。"""

    return markdown_link(label, user_group_admin_url())


def _ts(value: datetime | None = None) -> str:
    """生成数据库使用的秒级 ISO 时间。"""

    return (value or datetime.now()).replace(microsecond=0).isoformat()


service = UserGroupService(db)


__all__ = ["UserGroupService", "service", "user_group_admin_link", "user_group_admin_url"]
