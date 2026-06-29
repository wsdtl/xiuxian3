"""灵果凑十小游戏结算。

灵果凑十是两分半的轻量心算局。前端只负责上报得分材料；本文件按
每日难度、单局凭证、服务端经过时间重新裁定成绩与奖励。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .random_seed import daily_rng
from .service import medicine_embryo_reward

LINGGUO_SUM_TEN_KEY = "lingguo-sum-ten"
LINGGUO_SUM_TEN_TITLE = "灵果凑十"
LINGGUO_DURATION_SECONDS = 150
LINGGUO_SUM_TARGET = 10
LINGGUO_COLS = 8
LINGGUO_ROWS = 11
LINGGUO_SCORE_CAP = 260
LINGGUO_CLEARED_CELL_CAP = 320
LINGGUO_VALID_CLEAR_CAP = 120


@dataclass(frozen=True)
class LingguoDifficulty:
    """服务端定义的一局难度。

    这些字段一部分给前端生成棋盘，一部分给服务端验分和奖励使用。
    难度由开局日期派生，同一天全服统一，跨零点结算仍按开局日复算。
    """

    key: str
    label: str
    description: str
    forbidden_enabled: bool
    sprinkle_pairs: int
    forbidden_cell_rate: float
    reward_multiplier: float
    score_per_second_cap: float
    valid_clear_seconds: float
    max_cells_per_clear: int

    def public_config(self) -> dict[str, Any]:
        """返回前端生成本局棋盘需要的安全字段。"""

        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "forbidden_enabled": self.forbidden_enabled,
            "sprinkle_pairs": self.sprinkle_pairs,
            "forbidden_cell_rate": self.forbidden_cell_rate,
        }


LINGGUO_DIFFICULTIES: tuple[LingguoDifficulty, ...] = (
    LingguoDifficulty(
        key="qingtian",
        label="清甜局",
        description="盘面更容易看见凑十组合，适合稳稳摘果。",
        forbidden_enabled=False,
        sprinkle_pairs=20,
        forbidden_cell_rate=0.0,
        reward_multiplier=0.96,
        score_per_second_cap=1.6,
        valid_clear_seconds=1.55,
        max_cells_per_clear=10,
    ),
    LingguoDifficulty(
        key="ningxin",
        label="凝神局",
        description="组合少一点，节奏要更专注。",
        forbidden_enabled=False,
        sprinkle_pairs=14,
        forbidden_cell_rate=0.0,
        reward_multiplier=1.0,
        score_per_second_cap=1.45,
        valid_clear_seconds=1.75,
        max_cells_per_clear=10,
    ),
    LingguoDifficulty(
        key="suowei",
        label="锁味局",
        description="本局会出现禁用数字，框内混入它就不能摘果。",
        forbidden_enabled=True,
        sprinkle_pairs=10,
        forbidden_cell_rate=0.045,
        reward_multiplier=1.08,
        score_per_second_cap=1.32,
        valid_clear_seconds=1.95,
        max_cells_per_clear=10,
    ),
)


@dataclass(frozen=True)
class LingguoSumTenResult:
    """灵果凑十服务端认可的结算摘要。"""

    score: int
    cleared_cells: int
    valid_clears: int
    elapsed_seconds: int
    difficulty: LingguoDifficulty


def lingguo_sum_ten_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取灵果凑十启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        LINGGUO_SUM_TEN_KEY,
        LINGGUO_SUM_TEN_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": LINGGUO_DURATION_SECONDS,
            "score_cap": LINGGUO_SCORE_CAP,
            "sum_target": LINGGUO_SUM_TARGET,
            "cols": LINGGUO_COLS,
            "rows": LINGGUO_ROWS,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
            "difficulty_profiles": [item.public_config() for item in LINGGUO_DIFFICULTIES],
        },
    )


def start_lingguo_sum_ten(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，给灵果凑十签发一次单局凭证。"""

    if not isinstance(payload, dict):
        raise ValueError("灵果开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    round_info = service.start_round(LINGGUO_SUM_TEN_KEY, game_token)
    difficulty = _difficulty_for_day(str(round_info.get("issued_at") or ""))
    round_info.update(
        {
            "game_duration": LINGGUO_DURATION_SECONDS,
            "score_cap": LINGGUO_SCORE_CAP,
            "sum_target": LINGGUO_SUM_TARGET,
            "cols": LINGGUO_COLS,
            "rows": LINGGUO_ROWS,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
            "difficulty": difficulty.public_config(),
        }
    )
    return round_info


def finish_lingguo_sum_ten(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验灵果凑十成绩，签发低量洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("灵果结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        LINGGUO_SUM_TEN_KEY,
        game_token,
        session_id,
        round_token,
    )
    difficulty = _difficulty_for_day(str(round_row.get("issued_at") or ""))
    result = _sanitize_lingguo_sum_ten_payload(
        payload,
        difficulty=difficulty,
        server_elapsed_seconds=_server_elapsed_seconds(round_row),
    )
    rewards = _lingguo_sum_ten_rewards(result)
    issued = service.issue_code_for_round(
        LINGGUO_SUM_TEN_KEY,
        LINGGUO_SUM_TEN_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "cleared_cells": result.cleared_cells,
            "valid_clears": result.valid_clears,
            "elapsed_seconds": result.elapsed_seconds,
            "difficulty": result.difficulty.key,
        },
    )
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_cells = max(0, _safe_int(issued_meta.get("cleared_cells"))) if issued_meta else result.cleared_cells
    display_clears = max(0, _safe_int(issued_meta.get("valid_clears"))) if issued_meta else result.valid_clears
    display_elapsed = max(0, _safe_int(issued_meta.get("elapsed_seconds"))) if issued_meta else result.elapsed_seconds
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["cleared_cells"] = display_cells
    issued["valid_clears"] = display_clears
    issued["elapsed_seconds"] = display_elapsed
    issued["difficulty"] = result.difficulty.label
    issued["message"] = (
        f"灵果入匣：{display_score} 分，摘下 {display_cells} 枚灵果，"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _lingguo_sum_ten_rewards(result: LingguoSumTenResult) -> list[dict[str, Any]]:
    """把灵果凑十认可分转成洞天基础奖励快照。"""

    score = max(0, min(LINGGUO_SCORE_CAP, result.score))
    valid_clears = max(0, min(LINGGUO_VALID_CLEAR_CAP, result.valid_clears))
    multiplier = result.difficulty.reward_multiplier
    rewards: list[dict[str, Any]] = []

    currency = min(720, int((20 + score * 2.05 + valid_clears * 3) * multiplier))
    exp = min(58, int((4 + score // 5 + valid_clears // 4) * multiplier))
    rewards.append({"type": "currency", "quantity": max(18, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if score >= 24 or valid_clears >= 4:
        rewards.append(medicine_embryo_reward("yinmingcao" if score % 2 else "xueqidan"))
    if score >= 90 or valid_clears >= 14:
        rewards.append(medicine_embryo_reward("huichunlu" if score % 2 else "ningshenlu"))
    if score >= 150 and _chance_per_10000(min(720, 90 + score * 2 + valid_clears * 6)):
        rewards.append({"type": "wish_token", "quantity": 1})
    if score >= 225 and _chance_per_10000(min(90, 18 + valid_clears)):
        rewards.append({"type": "ring_item", "key": "xisuiye", "quantity": 1})
    return rewards


def _sanitize_lingguo_sum_ten_payload(
    payload: dict[str, Any],
    *,
    difficulty: LingguoDifficulty,
    server_elapsed_seconds: int | None = None,
) -> LingguoSumTenResult:
    """清洗灵果凑十前端成绩，并按时间密度重新裁定。"""

    reported_score = min(LINGGUO_SCORE_CAP, max(0, _safe_int(payload.get("score"))))
    cleared_cells = min(
        LINGGUO_CLEARED_CELL_CAP,
        max(0, _safe_int(payload.get("clearedCells") or payload.get("cleared_cells"))),
    )
    valid_clears = min(
        LINGGUO_VALID_CLEAR_CAP,
        max(0, _safe_int(payload.get("validClears") or payload.get("valid_clears"))),
    )
    elapsed_seconds = min(
        LINGGUO_DURATION_SECONDS,
        max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds"))),
    )
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), LINGGUO_DURATION_SECONDS)

    # 前端的分数只是一份材料。真正认可分必须同时被成局数、摘果数和
    # 服务端经过时间支撑，防止随手改请求体直接刷到封顶。
    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    valid_time_cap = min(
        LINGGUO_VALID_CLEAR_CAP,
        max(0, int(effective_seconds / difficulty.valid_clear_seconds) + 3),
    )
    valid_clears = min(valid_clears, valid_time_cap)
    cleared_cells = min(cleared_cells, valid_clears * difficulty.max_cells_per_clear)
    score_time_cap = min(
        LINGGUO_SCORE_CAP,
        int(effective_seconds * difficulty.score_per_second_cap) + difficulty.max_cells_per_clear,
    )
    accepted_score = min(reported_score, cleared_cells, score_time_cap)
    return LingguoSumTenResult(
        score=max(0, accepted_score),
        cleared_cells=max(0, cleared_cells),
        valid_clears=max(0, valid_clears),
        elapsed_seconds=elapsed_seconds,
        difficulty=difficulty,
    )


def _difficulty_for_day(issued_at: str) -> LingguoDifficulty:
    """用开局日期派生每日难度，全服同日一致，结算跨零点也不漂移。"""

    day = str(issued_at or "").strip()[:10]
    rng = daily_rng(LINGGUO_SUM_TEN_KEY, "difficulty", day)
    return LINGGUO_DIFFICULTIES[rng.randrange(len(LINGGUO_DIFFICULTIES))]


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(LINGGUO_DURATION_SECONDS, elapsed)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
