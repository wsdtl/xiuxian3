"""洞天福地组件服务。"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from typing import Any
from pathlib import Path
from datetime import timedelta
from urllib.parse import quote
from dataclasses import dataclass

from ..common import CoreService, business_day, dt, dump_json, load_json, money, now, ring_category_key, ring_item_display_name, ts
from ..constants import (
    DONGTIAN_CODE_RETENTION_DAYS,
    DONGTIAN_CODE_TTL_MINUTES,
    DONGTIAN_GAME_TOKEN_TTL_HOURS,
    DONGTIAN_MIN_REWARD_RATE,
    DONGTIAN_ROUND_MIN_SECONDS,
    DONGTIAN_ROUND_TTL_MINUTES,
    DONGTIAN_REWARD_DECAY,
    WISH_TOKEN_ITEM_ID,
)
from ..format_text import T
from ..markdown_utils import markdown_link
from ..public_url import public_url
from launch.paths import static_path
from ..sql import db

DONGTIAN_STATIC_DIR = static_path("dongtian")
DONGTIAN_PUBLIC_PATH = "/static/dongtian"
DONGTIAN_CODE_PREFIX = "DT"
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
DISALLOWED_RING_REWARDS = {"cuifengdan", "kaikongqi"}
DONGTIAN_MEDICINE_EMBRYO_TYPE = "medicine_embryo"
DONGTIAN_MEDICINE_EMBRYO_DECAY = 0.17
DONGTIAN_MEDICINE_EMBRYO_FREE_POINTS = 2
DONGTIAN_MEDICINE_EMBRYO_MIN_RATE = 0.24
DONGTIAN_MEDICINE_EMBRYO_DEFS: dict[str, dict[str, Any]] = {
    "dim_blood": {"name": "微光气血药胚", "medicine_id": "xueqidan", "points": 1},
    "dim_spirit": {"name": "微光神念药胚", "medicine_id": "yinmingcao", "points": 1},
    "dew_blood": {"name": "凝露气血药胚", "medicine_id": "huichunlu", "points": 2},
    "dew_spirit": {"name": "凝露神念药胚", "medicine_id": "ningshenlu", "points": 2},
    "mystic_blood": {"name": "玄息气血药胚", "medicine_id": "shenggudan", "points": 4},
    "mystic_spirit": {"name": "玄息神念药胚", "medicine_id": "yanghundan", "points": 4},
}
MEDICINE_TO_EMBRYO_KEY = {
    "xueqidan": "dim_blood",
    "yinmingcao": "dim_spirit",
    "huichunlu": "dew_blood",
    "ningshenlu": "dew_spirit",
    "shenggudan": "mystic_blood",
    "yanghundan": "mystic_spirit",
}


@dataclass(frozen=True)
class DongtianGame:
    """一个静态小游戏入口。"""

    key: str
    title: str
    index_path: Path
    public_path: str


class DongtianService(CoreService):
    """洞天福地入口、兑换码和短期记录。"""

    def games(self, client_id: str) -> str:
        """查看当前可玩的洞天小游戏。"""

        _, error = self.require_player(client_id)
        if error:
            return error

        games = self.discover_games()
        if not games:
            return T.hint(
                "洞天福地暂时没有开启的异世游乐场。",
                "把小游戏构建产物放到 static/dongtian/游戏目录/index.html 后，再发送：洞天福地。",
            )

        panel = T.panel()
        panel.section("洞天福地")
        panel.line("一缕神念可以游入异世，游玩后带回洞天兑换码。")
        for game in games:
            url = public_url(game.public_path)
            panel.line(markdown_link(game.title, url))
        panel.hr()
        panel.section("兑换")
        panel.line("小游戏结束后复制兑换码，发送：洞天兑换 兑换码")
        panel.line(f"兑换码 {DONGTIAN_CODE_TTL_MINUTES} 分钟有效，可以转赠；奖励按兑换人今日收益曲线结算。")
        return T.attach(panel.render(), T.buttons("洞天记录"))

    def records(self, client_id: str) -> str:
        """查看洞天今日收益系数和最近兑换记录。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        self.cleanup_expired_codes()

        claimed_count = self._today_claim_count(client_id)
        reward_rate = dongtian_reward_rate(claimed_count)
        medicine_points = self._today_medicine_points(client_id)
        embryo_rate = dongtian_medicine_embryo_rate(medicine_points)
        rows = self.db.fetch_all(
            """
            SELECT game_title, score, granted_json, claimed_at
            FROM dongtian_codes
            WHERE claimed_by = ?
            ORDER BY claimed_at DESC
            LIMIT 8
            """,
            (client_id,),
        )

        panel = T.panel()
        panel.section("洞天记录")
        panel.line(f"今日已兑换：**{claimed_count}** 次")
        panel.line(f"当前资源收益系数：**{_percent_text(reward_rate)}**｜今日药息点：**{medicine_points}**｜药胚稳定率：**{_percent_text(embryo_rate)}**")
        if rows:
            panel.hr()
            panel.section("最近兑换")
            for row in rows:
                granted_lines = _grant_lines(load_json(row["granted_json"], []))
                reward_text = "、".join(str(item) for item in granted_lines if str(item).strip())
                score_text = f"｜分数 {int(row['score'] or 0)}"
                panel.line(f"{row['claimed_at']}｜{row['game_title']}{score_text}｜{reward_text or '无奖励'}")
        else:
            panel.line("最近还没有兑换记录。")
        return T.attach(panel.render(), T.buttons("洞天福地"))

    def redeem(self, client_id: str, message: str) -> str:
        """兑换洞天小游戏结算码。"""

        _, error = self.require_player(client_id)
        if error:
            return error
        code = _normalize_code(message)
        if not code:
            return T.hint("缺少洞天兑换码。", "发送：洞天兑换 兑换码，例如：洞天兑换 DTXXXXXXXX")

        current = ts()
        with self.db.transaction() as conn:
            self._cleanup_expired_codes_conn(conn, current)
            row = conn.execute(
                """
                SELECT *
                FROM dongtian_codes
                WHERE code = ?
                LIMIT 1
                """,
                (code,),
            ).fetchone()
            if not row:
                return T.hint("没有找到这个洞天兑换码。", "请确认兑换码是否复制完整。<洞天福地>")
            if row["claimed_at"]:
                return T.hint("这个洞天兑换码已经被兑换过。", "每个兑换码只能使用一次。<洞天记录>")
            if str(row["expires_at"]) <= current:
                return T.hint("这个洞天兑换码已经过期。", "洞天兑换码只有 10 分钟有效，请重新游玩获取。<洞天福地>")

            rewards = load_json(row["reward_json"], [])
            if not isinstance(rewards, list):
                return T.hint("这个洞天兑换码奖励快照异常。", "请重新游玩获取新的兑换码。<洞天福地>")

            # 先用数据库条件抢占兑换码，再发奖。这样即使未来改成多 worker，
            # 也不会出现两个进程同时读到未领取后重复发奖的窗口。
            cursor = conn.execute(
                """
                UPDATE dongtian_codes
                SET claimed_by = ?, claimed_at = ?
                WHERE code = ? AND claimed_at IS NULL AND expires_at > ?
                """,
                (client_id, current, code, current),
            )
            if cursor.rowcount <= 0:
                return T.hint("这个洞天兑换码已经被兑换过。", "每个兑换码只能使用一次。<洞天记录>")

            claimed_count = max(0, self._today_claim_count_conn(conn, client_id) - 1)
            reward_rate = dongtian_reward_rate(claimed_count)
            medicine_points = self._today_medicine_points_conn(conn, client_id)
            embryo_rate = dongtian_medicine_embryo_rate(medicine_points)
            granted = self._grant_rewards_conn(conn, client_id, rewards, reward_rate, medicine_points)
            granted_lines = _grant_lines(granted)
            conn.execute(
                """
                UPDATE dongtian_codes
                SET reward_rate = ?, medicine_rate = ?, granted_json = ?
                WHERE code = ?
                """,
                (reward_rate, embryo_rate, dump_json(granted), code),
            )
            conn.execute(
                "INSERT INTO game_logs (client_id, action, detail, created_at) VALUES (?, '洞天兑换', ?, ?)",
                (client_id, f"game={row['game_key']}, code={code}", current),
            )

        panel = T.panel()
        panel.section("洞天福地")
        panel.line(f"{row['game_title']} 的异世回响落入修仙界。")
        panel.line(f"洞天收益系数：资源 {_percent_text(reward_rate)}｜药胚稳定 {_percent_text(embryo_rate)}")
        panel.hr()
        panel.section("获得")
        panel.lines(granted_lines or ["这枚兑换码没有可发放奖励。"])
        return T.attach(panel.render(), T.buttons("洞天记录", "纳戒", "修仙信息"))

    def issue_code(
        self,
        game_key: str,
        game_title: str,
        rewards: list[dict[str, Any]],
        *,
        score: int = 0,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """给具体小游戏结算接口调用的统一发码能力。

        每个小游戏负责校验自己的分数体系；这里只保存奖励快照并签发
        十分钟一次性兑换码。兑换时再按兑换人的当日洞天收益曲线折算。
        """

        clean_game_key = _safe_key(game_key)
        clean_title = str(game_title or clean_game_key or "洞天小游戏").strip()
        clean_rewards = self._clean_reward_snapshot(rewards)
        current = ts()
        expires_at = ts_from_now_minutes(DONGTIAN_CODE_TTL_MINUTES)
        with self.db.transaction() as conn:
            return self._insert_code_conn(
                conn,
                clean_game_key,
                clean_title,
                clean_rewards,
                max(0, int(score or 0)),
                meta or {},
                current,
                expires_at,
            )

    def issue_code_for_round(
        self,
        game_key: str,
        game_title: str,
        game_token: str,
        session_id: str,
        round_token: str,
        rewards: list[dict[str, Any]],
        *,
        score: int = 0,
        meta: dict[str, Any] | None = None,
        min_elapsed_seconds: int = DONGTIAN_ROUND_MIN_SECONDS,
    ) -> dict[str, Any]:
        """原子完成“消费单局凭证 + 签发兑换码”。

        小游戏结算不能先把单局标记为已消费、再另开一次事务写兑换码；
        否则服务在两步之间重启时，会出现“局已结算但玩家拿不到码”的
        半失败状态。这里把最终校验、发码和消费单局放进同一事务。
        """

        clean_game_key = _safe_key(game_key)
        clean_title = str(game_title or clean_game_key or "洞天小游戏").strip()
        clean_rewards = self._clean_reward_snapshot(rewards)
        current = ts()
        expires_at = ts_from_now_minutes(DONGTIAN_CODE_TTL_MINUTES)
        clean_session_id = _normalize_token(session_id)
        clean_round_token = _normalize_token(round_token)
        clean_game_token = _normalize_token(game_token)
        with self.db.transaction() as conn:
            self._cleanup_expired_session_conn(conn, current)
            row = self._round_row_for_settlement_conn(
                conn,
                clean_game_key,
                clean_game_token,
                clean_session_id,
                clean_round_token,
                current,
                min_elapsed_seconds=min_elapsed_seconds,
                allow_consumed=True,
            )
            if row["consumed_at"]:
                return self._issued_code_for_round_conn(conn, clean_session_id, clean_game_key)
            issued = self._insert_code_conn(
                conn,
                clean_game_key,
                clean_title,
                clean_rewards,
                max(0, int(score or 0)),
                meta or {},
                current,
                expires_at,
            )
            cursor = conn.execute(
                """
                UPDATE dongtian_rounds
                SET consumed_at = ?, issued_code = ?
                WHERE session_id = ?
                  AND game_key = ?
                  AND round_token_hash = ?
                  AND issued_code = ''
                  AND consumed_at IS NULL
                """,
                (current, str(issued["code"]), clean_session_id, clean_game_key, str(row["round_token_hash"])),
            )
            if cursor.rowcount <= 0:
                conn.execute("DELETE FROM dongtian_codes WHERE code = ? AND claimed_at IS NULL", (str(issued["code"]),))
                return self._issued_code_for_round_conn(conn, clean_session_id, clean_game_key)
            return issued

    def game_config(
        self,
        game_key: str,
        game_title: str,
        *,
        config: dict[str, Any] | None = None,
        reuse_token: str | None = None,
    ) -> dict[str, Any]:
        """签发静态小游戏启动配置。

        小游戏网页没有登录态，所以启动 token 是它后续开局、结算的第一层
        保险。服务端只保存 token 哈希；浏览器刷新时可带回原始 token 复用，
        避免通过反复刷新重新抽取本日小游戏难度。
        """

        clean_game_key = _safe_key(game_key)
        if not clean_game_key:
            raise ValueError("洞天小游戏标识异常。")
        clean_title = str(game_title or clean_game_key).strip()
        token = _normalize_token(reuse_token or "")
        current = ts()
        expires_at = ""
        reused = False
        with self.db.transaction() as conn:
            self._cleanup_expired_session_conn(conn, current)
            if token:
                expires_at = self._game_token_expires_conn(conn, clean_game_key, token, current)
                reused = bool(expires_at)
            if not reused:
                token = _new_token()
                expires_at = ts_from_now_hours(DONGTIAN_GAME_TOKEN_TTL_HOURS)
                conn.execute(
                    """
                    INSERT INTO dongtian_game_tokens
                    (token_hash, game_key, issued_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (self._token_hash("game", clean_game_key, token), clean_game_key, current, expires_at),
                )
        return {
            "game_key": clean_game_key,
            "game_title": clean_title,
            "game_token": token,
            "token_expires_at": expires_at,
            "reused_game_token": reused,
            "config": dict(config or {}),
        }

    def start_round(self, game_key: str, game_token: str) -> dict[str, Any]:
        """校验启动凭证并签发一次单局凭证。"""

        clean_game_key = _safe_key(game_key)
        token = _normalize_token(game_token)
        current = ts()
        session_id = _new_token(18)
        round_token = _new_token(24)
        expires_at = ts_from_now_minutes(DONGTIAN_ROUND_TTL_MINUTES)
        with self.db.transaction() as conn:
            self._cleanup_expired_session_conn(conn, current)
            game_token_hash = self._require_game_token_conn(conn, clean_game_key, token, current)
            self._clear_pending_rounds_conn(conn, clean_game_key, game_token_hash, current)
            conn.execute(
                """
                INSERT INTO dongtian_rounds
                (session_id, game_key, game_token_hash, round_token_hash, issued_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    clean_game_key,
                    game_token_hash,
                    self._token_hash("round", clean_game_key, f"{game_token_hash}:{round_token}"),
                    current,
                    expires_at,
                ),
            )
        return {
            "game_key": clean_game_key,
            "session_id": session_id,
            "round_token": round_token,
            "issued_at": current,
            "expires_at": expires_at,
        }

    def consume_round(
        self,
        game_key: str,
        game_token: str,
        session_id: str,
        round_token: str,
        *,
        min_elapsed_seconds: int = DONGTIAN_ROUND_MIN_SECONDS,
    ) -> dict[str, Any]:
        """消费单局凭证；同一局只能成功结算一次。"""

        clean_game_key = _safe_key(game_key)
        clean_session_id = _normalize_token(session_id)
        clean_round_token = _normalize_token(round_token)
        clean_game_token = _normalize_token(game_token)

        current = ts()
        with self.db.transaction() as conn:
            self._cleanup_expired_session_conn(conn, current)
            row = self._round_row_for_settlement_conn(
                conn,
                clean_game_key,
                clean_game_token,
                clean_session_id,
                clean_round_token,
                current,
                min_elapsed_seconds=min_elapsed_seconds,
            )
            cursor = conn.execute(
                """
                UPDATE dongtian_rounds
                SET consumed_at = ?
                WHERE session_id = ?
                  AND game_key = ?
                  AND round_token_hash = ?
                  AND consumed_at IS NULL
                """,
                (current, clean_session_id, clean_game_key, str(row["round_token_hash"])),
            )
            if cursor.rowcount <= 0:
                raise ValueError("这一局已经结算过，请重新开局。")
        return dict(row)

    def inspect_round(
        self,
        game_key: str,
        game_token: str,
        session_id: str,
        round_token: str,
        *,
        min_elapsed_seconds: int = DONGTIAN_ROUND_MIN_SECONDS,
    ) -> dict[str, Any]:
        """只校验单局凭证并返回单局记录，不消费。

        小游戏结算需要先知道服务端经过时间来裁定成绩；真正消费和发码
        由 `issue_code_for_round` 在同一事务完成。
        """

        clean_game_key = _safe_key(game_key)
        clean_session_id = _normalize_token(session_id)
        clean_round_token = _normalize_token(round_token)
        clean_game_token = _normalize_token(game_token)
        current = ts()
        with self.db.transaction() as conn:
            self._cleanup_expired_session_conn(conn, current)
            row = self._round_row_for_settlement_conn(
                conn,
                clean_game_key,
                clean_game_token,
                clean_session_id,
                clean_round_token,
                current,
                min_elapsed_seconds=min_elapsed_seconds,
                allow_consumed=True,
            )
            return dict(row)

    def discover_games(self) -> list[DongtianGame]:
        """遍历 static/dongtian 下的小游戏入口。"""

        if not DONGTIAN_STATIC_DIR.exists():
            return []
        result: list[DongtianGame] = []
        for index_path in sorted(DONGTIAN_STATIC_DIR.glob("*/index.html"), key=lambda item: item.parent.name):
            game_key = _safe_key(index_path.parent.name)
            if not game_key:
                continue
            title = _html_title(index_path) or game_key
            public_path = f"{DONGTIAN_PUBLIC_PATH}/{quote(index_path.parent.name)}/index.html"
            result.append(DongtianGame(game_key, title, index_path, public_path))
        return result

    def cleanup_expired_codes(self) -> None:
        """清理已经没有运营价值的洞天兑换码日志。"""

        with self.db.transaction() as conn:
            current = ts()
            self._cleanup_expired_codes_conn(conn, current)
            self._cleanup_expired_session_conn(conn, current)

    @staticmethod
    def _cleanup_expired_codes_conn(conn, current: str) -> None:
        """删除已兑换或已过期超过保留期的兑换码。"""

        conn.execute(
            """
            DELETE FROM dongtian_codes
            WHERE datetime(replace(COALESCE(claimed_at, expires_at), 'T', ' ')) < datetime(replace(?, 'T', ' '), ?)
            """,
            (current, f"-{DONGTIAN_CODE_RETENTION_DAYS} days"),
        )

    @staticmethod
    def _cleanup_expired_session_conn(conn, current: str) -> None:
        """清理短期启动凭证和单局凭证。"""

        conn.execute("DELETE FROM dongtian_game_tokens WHERE expires_at <= ?", (current,))
        conn.execute(
            """
            DELETE FROM dongtian_rounds
            WHERE (consumed_at IS NULL AND expires_at <= ?)
               OR (
                   consumed_at IS NOT NULL
                   AND datetime(replace(consumed_at, 'T', ' ')) < datetime(replace(?, 'T', ' '), ?)
               )
            """,
            (current, current, f"-{DONGTIAN_CODE_RETENTION_DAYS} days"),
        )

    def _require_game_token_conn(self, conn, game_key: str, token: str, current: str) -> str:
        """事务内校验启动凭证，返回 token 哈希。"""

        if not game_key or not token:
            raise ValueError("洞天启动凭证缺失，请重新进入小游戏。")
        token_hash = self._token_hash("game", game_key, token)
        row = conn.execute(
            """
            SELECT token_hash
            FROM dongtian_game_tokens
            WHERE token_hash = ? AND game_key = ? AND expires_at > ?
            LIMIT 1
            """,
            (token_hash, game_key, current),
        ).fetchone()
        if not row:
            raise ValueError("洞天启动凭证已失效，请重新进入小游戏。")
        return token_hash

    def _game_token_expires_conn(self, conn, game_key: str, token: str, current: str) -> str:
        """读取仍有效的启动凭证过期时间；无效时返回空字符串。"""

        if not game_key or not token:
            return ""
        token_hash = self._token_hash("game", game_key, token)
        row = conn.execute(
            """
            SELECT expires_at
            FROM dongtian_game_tokens
            WHERE token_hash = ? AND game_key = ? AND expires_at > ?
            LIMIT 1
            """,
            (token_hash, game_key, current),
        ).fetchone()
        return str(row["expires_at"]) if row else ""

    @staticmethod
    def _clear_pending_rounds_conn(conn, game_key: str, game_token_hash: str, current: str) -> None:
        """同一启动凭证同一时刻只保留一局未结算单局。

        小游戏接口没有玩家登录态，启动凭证就是浏览器侧的短期身份。
        开新局前清理这个身份名下仍未消费的旧局，可以防止脚本一次性囤
        多个未结算单局；已经签出兑换码的局会保留，方便结算回包丢失后重试。
        """

        if not game_key or not game_token_hash:
            return
        conn.execute(
            """
            DELETE FROM dongtian_rounds
            WHERE game_key = ?
              AND game_token_hash = ?
              AND consumed_at IS NULL
              AND issued_code = ''
              AND expires_at > ?
            """,
            (game_key, game_token_hash, current),
        )

    def _round_row_for_settlement_conn(
        self,
        conn,
        game_key: str,
        game_token: str,
        session_id: str,
        round_token: str,
        current: str,
        *,
        min_elapsed_seconds: int,
        allow_consumed: bool = False,
    ):
        """事务内校验单局凭证，并返回可结算的单局记录。"""

        if not session_id or not round_token:
            raise ValueError("本局凭证缺失，请重新开局。")
        game_token_hash = self._require_game_token_conn(conn, game_key, game_token, current)
        row = conn.execute(
            """
            SELECT *
            FROM dongtian_rounds
            WHERE session_id = ? AND game_key = ?
            LIMIT 1
            """,
            (session_id, game_key),
        ).fetchone()
        if not row:
            raise ValueError("本局凭证无效，请重新开局。")
        if not hmac.compare_digest(game_token_hash, str(row["game_token_hash"] or "")):
            raise ValueError("本局凭证校验失败，请重新开局。")
        expected_hash = self._token_hash("round", game_key, f"{game_token_hash}:{round_token}")
        if not hmac.compare_digest(expected_hash, str(row["round_token_hash"])):
            raise ValueError("本局凭证校验失败，请重新开局。")
        if row["consumed_at"]:
            if allow_consumed and str(row["issued_code"] or "").strip():
                return row
            raise ValueError("这一局已经结算过，请重新开局。")
        if str(row["expires_at"]) <= current:
            raise ValueError("本局凭证已过期，请重新开局。")

        issued_at = dt(str(row["issued_at"]))
        if not row["consumed_at"] and issued_at and max(0, int(min_elapsed_seconds)) > 0:
            elapsed = (now() - issued_at).total_seconds()
            if elapsed < int(min_elapsed_seconds):
                raise ValueError("本局结束过快，请正常游玩后再结算。")
        return row

    def _issued_code_for_round_conn(self, conn, session_id: str, game_key: str) -> dict[str, Any]:
        """读取已经由本局签出的兑换码，用于网页断线后的幂等重试。"""

        row = conn.execute(
            """
            SELECT issued_code
            FROM dongtian_rounds
            WHERE session_id = ? AND game_key = ?
            LIMIT 1
            """,
            (session_id, game_key),
        ).fetchone()
        code = str(row["issued_code"] if row else "").strip()
        if not code:
            raise ValueError("这一局已经结算过，请重新开局。")
        code_row = conn.execute(
            """
            SELECT *
            FROM dongtian_codes
            WHERE code = ? AND game_key = ?
            LIMIT 1
            """,
            (code, game_key),
        ).fetchone()
        if not code_row:
            raise ValueError("本局兑换码已失效，请重新开局。")
        rewards = load_json(code_row["reward_json"], [])
        if not isinstance(rewards, list):
            rewards = []
        meta = load_json(code_row["meta_json"], {})
        if not isinstance(meta, dict):
            meta = {}
        return {
            "code": code,
            "game_key": str(code_row["game_key"]),
            "game_title": str(code_row["game_title"]),
            "expires_at": str(code_row["expires_at"]),
            "rewards": rewards,
            "score": max(0, int(code_row["score"] or 0)),
            "meta": meta,
            "reissued": True,
        }

    def _insert_code_conn(
        self,
        conn,
        game_key: str,
        game_title: str,
        rewards: list[dict[str, Any]],
        score: int,
        meta: dict[str, Any],
        issued_at: str,
        expires_at: str,
    ) -> dict[str, Any]:
        """事务内写入兑换码，极低概率碰撞时自动重试。"""

        for _attempt in range(6):
            code = self._new_code()
            try:
                conn.execute(
                    """
                    INSERT INTO dongtian_codes
                    (code, game_key, game_title, score, reward_json, meta_json, issued_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        game_key,
                        game_title,
                        max(0, int(score or 0)),
                        dump_json(rewards),
                        dump_json(meta or {}),
                        issued_at,
                        expires_at,
                    ),
                )
                return {
                    "code": code,
                    "game_key": game_key,
                    "game_title": game_title,
                    "expires_at": expires_at,
                    "rewards": rewards,
                }
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("洞天兑换码生成失败，请重新结算。")

    @staticmethod
    def _token_hash(kind: str, game_key: str, token: str) -> str:
        """稳定哈希 token，数据库不保存原文。"""

        raw = f"{kind}:{game_key}:{token}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _grant_rewards_conn(
        self,
        conn,
        client_id: str,
        rewards: list[dict[str, Any]],
        reward_rate: float,
        medicine_points: int,
    ) -> list[dict[str, Any]]:
        """按兑换人当日曲线发放奖励快照。"""

        granted: list[dict[str, Any]] = []
        for reward in rewards:
            reward_type = str(reward.get("type") or reward.get("reward_type") or "").strip()
            key = str(reward.get("key") or reward.get("reward_key") or "").strip()
            quantity = max(0, int(reward.get("quantity") or 0))
            if quantity <= 0:
                continue
            if reward_type == "currency":
                amount = max(1, int(quantity * reward_rate))
                conn.execute("UPDATE players SET raw_stones = raw_stones + ? WHERE client_id = ?", (amount, client_id))
                granted.append({"type": "currency", "quantity": amount, "text": f"原石 +{money(amount)}"})
            elif reward_type == "exp":
                amount = max(1, int(quantity * reward_rate))
                old_level, new_level = self.add_exp_conn(conn, client_id, amount)
                level_text = f"，等级 {old_level}->{new_level}" if new_level != old_level else ""
                granted.append({"type": "exp", "quantity": amount, "text": f"经验 +{amount}{level_text}"})
            elif reward_type == "ring_item":
                if key in DISALLOWED_RING_REWARDS:
                    continue
                item = self.ring_item_def(key)
                if not item:
                    continue
                category_key = ring_category_key(item.get("category_key") or item.get("category"))
                if category_key == "recovery":
                    continue
                else:
                    amount = max(1, int(quantity * reward_rate))
                    self.add_ring_conn(conn, client_id, key, amount)
                    granted.append({"type": "ring_item", "key": key, "quantity": amount, "text": f"纳戒获得 {ring_item_display_name(item, key)} x{amount}"})
            elif reward_type == DONGTIAN_MEDICINE_EMBRYO_TYPE:
                for _ in range(quantity):
                    embryo_rate = dongtian_medicine_embryo_rate(medicine_points)
                    result = self._stabilize_medicine_embryo_conn(conn, client_id, key, embryo_rate)
                    medicine_points += result.get("points", 0) if result.get("success") else 0
                    granted.append(result)
            elif reward_type == "wish_token":
                amount = max(1, int(quantity * reward_rate))
                self.add_ring_conn(conn, client_id, WISH_TOKEN_ITEM_ID, amount)
                item = self.ring_item_def(WISH_TOKEN_ITEM_ID)
                granted.append({"type": "wish_token", "key": WISH_TOKEN_ITEM_ID, "quantity": amount, "text": f"纳戒获得 {ring_item_display_name(item, WISH_TOKEN_ITEM_ID)} x{amount}"})
        return granted

    def reward_preview(self, rewards: list[dict[str, Any]]) -> list[str]:
        """给小游戏页面展示基础奖励预览。"""

        lines: list[str] = []
        for reward in rewards:
            reward_type = str(reward.get("type") or "").strip()
            key = str(reward.get("key") or "").strip()
            quantity = max(0, int(reward.get("quantity") or 0))
            if quantity <= 0:
                continue
            if reward_type == "currency":
                lines.append(f"基础原石 +{money(quantity)}")
            elif reward_type == "exp":
                lines.append(f"基础经验 +{quantity}")
            elif reward_type == "wish_token":
                item = self.ring_item_def(WISH_TOKEN_ITEM_ID)
                lines.append(f"{ring_item_display_name(item, WISH_TOKEN_ITEM_ID)} x{quantity}")
            elif reward_type == DONGTIAN_MEDICINE_EMBRYO_TYPE:
                embryo = DONGTIAN_MEDICINE_EMBRYO_DEFS.get(key)
                if embryo:
                    lines.append(f"{embryo['name']} x{quantity}")
            elif reward_type == "ring_item":
                item = self.ring_item_def(key)
                if item:
                    lines.append(f"{ring_item_display_name(item, key)} x{quantity}")
        return lines[:6]

    def _clean_reward_snapshot(self, rewards: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """保存奖励快照前做一次白名单清洗。"""

        clean: list[dict[str, Any]] = []
        for reward in rewards:
            if not isinstance(reward, dict):
                continue
            reward_type = str(reward.get("type") or reward.get("reward_type") or "").strip()
            key = str(reward.get("key") or reward.get("reward_key") or "").strip()
            quantity = max(0, int(reward.get("quantity") or 0))
            if quantity <= 0:
                continue
            if reward_type in {"currency", "exp", "wish_token"}:
                clean.append({"type": reward_type, "key": key, "quantity": quantity})
            elif reward_type == DONGTIAN_MEDICINE_EMBRYO_TYPE and key in DONGTIAN_MEDICINE_EMBRYO_DEFS:
                clean.append({"type": DONGTIAN_MEDICINE_EMBRYO_TYPE, "key": key, "quantity": quantity})
            elif reward_type == "ring_item" and key and key not in DISALLOWED_RING_REWARDS and self.ring_item_def(key):
                item = self.ring_item_def(key)
                category_key = ring_category_key(item.get("category_key") or item.get("category")) if item else ""
                if category_key != "recovery":
                    clean.append({"type": reward_type, "key": key, "quantity": quantity})
        return clean

    def _stabilize_medicine_embryo_conn(self, conn, client_id: str, embryo_key: str, embryo_rate: float) -> dict[str, Any]:
        """让洞天药胚在兑换人手里成药；失败只散形，不再计入今日药息点。"""

        embryo = DONGTIAN_MEDICINE_EMBRYO_DEFS.get(embryo_key)
        if not embryo:
            return {"type": "medicine_embryo", "key": embryo_key, "success": False, "text": "药胚散形：未知药胚未能成丹"}
        rate = max(0.0, min(1.0, float(embryo_rate)))
        if secrets.randbelow(10_000) >= int(rate * 10_000):
            return {
                "type": "medicine_embryo",
                "key": embryo_key,
                "success": False,
                "points": 0,
                "text": f"药胚散形：{embryo['name']}未能成丹",
            }

        medicine_id = str(embryo["medicine_id"])
        item = self.ring_item_def(medicine_id)
        if not item:
            return {
                "type": "medicine_embryo",
                "key": embryo_key,
                "success": False,
                "points": 0,
                "text": f"药胚散形：{embryo['name']}未能成丹",
            }
        self.add_ring_conn(conn, client_id, medicine_id, 1)
        points = int(embryo["points"])
        return {
            "type": "medicine_embryo",
            "key": embryo_key,
            "success": True,
            "medicine_id": medicine_id,
            "quantity": 1,
            "points": points,
            "text": f"药胚成形：{ring_item_display_name(item, medicine_id)} x1",
        }

    def _today_claim_count(self, client_id: str) -> int:
        """读取玩家今天已兑换次数。"""

        with self.db.transaction() as conn:
            return self._today_claim_count_conn(conn, client_id)

    @staticmethod
    def _today_claim_count_conn(conn, client_id: str) -> int:
        """事务内读取玩家今天已兑换次数。"""

        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM dongtian_codes
            WHERE claimed_by = ?
              AND claimed_at IS NOT NULL
              AND date(datetime(replace(claimed_at, 'T', ' '), '-4 hours')) = ?
            """,
            (client_id, business_day()),
        ).fetchone()
        return int(row["count"] or 0) if row else 0

    def _today_medicine_points(self, client_id: str) -> int:
        """读取玩家今天从洞天药胚成功稳定出的药息点。"""

        with self.db.transaction() as conn:
            return self._today_medicine_points_conn(conn, client_id)

    @staticmethod
    def _today_medicine_points_conn(conn, client_id: str) -> int:
        """事务内读取洞天药息点；只认结构化发放摘要，旧文本自然不参与。"""

        rows = conn.execute(
            """
            SELECT granted_json
            FROM dongtian_codes
            WHERE claimed_by = ?
              AND claimed_at IS NOT NULL
              AND date(datetime(replace(claimed_at, 'T', ' '), '-4 hours')) = ?
            """,
            (client_id, business_day()),
        ).fetchall()
        total = 0
        for row in rows:
            for item in _granted_entries(load_json(row["granted_json"], [])):
                if item.get("type") == DONGTIAN_MEDICINE_EMBRYO_TYPE and item.get("success"):
                    total += max(0, int(item.get("points") or 0))
        return total

    @staticmethod
    def _new_code() -> str:
        """生成玩家可复制的短兑换码。"""

        return f"{DONGTIAN_CODE_PREFIX}{secrets.token_urlsafe(9).replace('-', '').replace('_', '').upper()[:12]}"


def dongtian_reward_rate(claimed_count: int) -> float:
    """按今日已兑换次数计算资源收益系数。"""

    pressure = max(0, int(claimed_count))
    return max(DONGTIAN_MIN_REWARD_RATE, 1 / (1 + DONGTIAN_REWARD_DECAY * pressure))


def dongtian_medicine_embryo_rate(medicine_points: int) -> float:
    """按今日已成药药息点计算药胚稳定率。"""

    points = max(0, int(medicine_points))
    if points <= DONGTIAN_MEDICINE_EMBRYO_FREE_POINTS:
        return 1.0
    pressure = points - DONGTIAN_MEDICINE_EMBRYO_FREE_POINTS
    return max(DONGTIAN_MEDICINE_EMBRYO_MIN_RATE, 1 / (1 + DONGTIAN_MEDICINE_EMBRYO_DECAY * pressure))


def medicine_embryo_reward(medicine_id: str, quantity: int = 1) -> dict[str, Any]:
    """小游戏把恢复药写成药胚快照，真正成药留到洞天兑换阶段。"""

    embryo_key = MEDICINE_TO_EMBRYO_KEY.get(str(medicine_id).strip())
    if not embryo_key:
        raise ValueError(f"未知洞天药胚来源：{medicine_id}")
    return {"type": DONGTIAN_MEDICINE_EMBRYO_TYPE, "key": embryo_key, "quantity": max(1, int(quantity))}


def _granted_entries(value: Any) -> list[dict[str, Any]]:
    """读取结构化发放摘要，供药息点统计使用。"""

    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _grant_lines(value: Any) -> list[str]:
    """把结构化发放摘要转回玩家可读文本。"""

    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            lines.append(text)
    return lines


def ts_from_now_minutes(minutes: int) -> str:
    """生成当前时间若干分钟后的时间戳。"""

    return ts(now() + timedelta(minutes=max(1, int(minutes))))


def ts_from_now_hours(hours: int) -> str:
    """生成当前时间若干小时后的时间戳。"""

    return ts(now() + timedelta(hours=max(1, int(hours))))


def _new_token(size: int = 32) -> str:
    """生成 URL 安全 token。"""

    return secrets.token_urlsafe(max(12, int(size)))


def _html_title(path: Path) -> str:
    """读取 HTML 标题；失败时返回空，入口仍可用目录名展示。"""

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    match = TITLE_RE.search(text)
    if not match:
        return ""
    raw = TAG_RE.sub("", match.group(1))
    return " ".join(raw.split()).strip()


def _safe_key(value: str) -> str:
    """小游戏目录和接口键只保留稳定安全字符。"""

    return re.sub(r"[^A-Za-z0-9_-]+", "", str(value or "").strip())[:64]


def _normalize_code(value: str) -> str:
    """规范化玩家输入的兑换码。"""

    return re.sub(r"\s+", "", str(value or "").strip()).upper()


def _normalize_token(value: str) -> str:
    """规范化接口 token；token 只给接口用，不做大小写转换。"""

    return re.sub(r"\s+", "", str(value or "").strip())[:512]


def _percent_text(value: float) -> str:
    """展示百分比。"""

    return f"{max(0.0, float(value)) * 100:.1f}%".replace(".0%", "%")


service = DongtianService(db)
