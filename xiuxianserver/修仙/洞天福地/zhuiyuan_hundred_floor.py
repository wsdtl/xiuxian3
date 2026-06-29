"""坠渊百层小游戏结算。

坠渊百层是 90 秒动作生存局。前端负责游戏手感和过程展示，服务端只
认可单局凭证、服务端经过时间和合理层数密度支撑的成绩，避免静态页
直接上报离谱层数后抬高洞天兑换收益。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .service import medicine_embryo_reward

ZHUIYUAN_HUNDRED_FLOOR_KEY = "zhuiyuan-hundred-floor"
ZHUIYUAN_HUNDRED_FLOOR_TITLE = "坠渊百层"
ZHUIYUAN_DURATION_SECONDS = 90
ZHUIYUAN_LAYER_CAP = 180
ZHUIYUAN_SCORE_CAP = 3600
ZHUIYUAN_END_REASONS = {"ceiling", "fall", "spike", "timeout", "manual"}


@dataclass(frozen=True)
class ZhuiyuanHundredFloorResult:
    """坠渊百层服务端认可的结算摘要。"""

    layers: int
    score: int
    elapsed_seconds: int
    death_reason: str
    frame_count: int


def zhuiyuan_hundred_floor_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取坠渊百层启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        ZHUIYUAN_HUNDRED_FLOOR_KEY,
        ZHUIYUAN_HUNDRED_FLOOR_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": ZHUIYUAN_DURATION_SECONDS,
            "layer_cap": ZHUIYUAN_LAYER_CAP,
            "score_cap": ZHUIYUAN_SCORE_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        },
    )


def start_zhuiyuan_hundred_floor(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，给坠渊百层签发一次单局凭证。"""

    if not isinstance(payload, dict):
        raise ValueError("坠渊开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    round_info = service.start_round(ZHUIYUAN_HUNDRED_FLOOR_KEY, game_token)
    round_info.update(
        {
            "game_duration": ZHUIYUAN_DURATION_SECONDS,
            "layer_cap": ZHUIYUAN_LAYER_CAP,
            "score_cap": ZHUIYUAN_SCORE_CAP,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
        }
    )
    return round_info


def finish_zhuiyuan_hundred_floor(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验坠渊百层成绩，签发高期待洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("坠渊结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    round_row = service.inspect_round(
        ZHUIYUAN_HUNDRED_FLOOR_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_zhuiyuan_payload(payload, server_elapsed_seconds=_server_elapsed_seconds(round_row))
    rewards = _zhuiyuan_rewards(result)
    issued = service.issue_code_for_round(
        ZHUIYUAN_HUNDRED_FLOOR_KEY,
        ZHUIYUAN_HUNDRED_FLOOR_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "layers": result.layers,
            "elapsed_seconds": result.elapsed_seconds,
            "death_reason": result.death_reason,
            "frame_count": result.frame_count,
        },
    )
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_layers = max(0, _safe_int(issued_meta.get("layers"))) if issued_meta else result.layers
    display_elapsed = max(0, _safe_int(issued_meta.get("elapsed_seconds"))) if issued_meta else result.elapsed_seconds
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["accepted_layers"] = display_layers
    issued["elapsed_seconds"] = display_elapsed
    issued["message"] = (
        f"坠渊止步：认可 {display_layers} 层，{display_score} 分。"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _zhuiyuan_rewards(result: ZhuiyuanHundredFloorResult) -> list[dict[str, Any]]:
    """把认可层数转成洞天基础奖励快照。"""

    layers = max(0, min(ZHUIYUAN_LAYER_CAP, result.layers))
    rewards: list[dict[str, Any]] = []
    currency = min(980, 36 + layers * 6)
    exp = min(78, 6 + layers // 2)
    rewards.append({"type": "currency", "quantity": max(18, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if layers >= 5:
        rewards.append(medicine_embryo_reward("yinmingcao"))
    if layers >= 15:
        rewards.append(medicine_embryo_reward("xueqidan"))
    if layers >= 35:
        rewards.append(medicine_embryo_reward("yinmingcao" if layers % 2 else "xueqidan"))
    if layers >= 75:
        rewards.append(medicine_embryo_reward("huichunlu" if layers % 2 else "ningshenlu"))
    if layers >= 60 and _chance_per_10000(min(1200, 180 + layers * 7)):
        rewards.append(medicine_embryo_reward("huichunlu" if layers % 3 else "ningshenlu"))
    if layers >= 45 and _chance_per_10000(min(1600, 160 + layers * 10)):
        rewards.append({"type": "wish_token", "quantity": 1})
    if layers >= 120 and _chance_per_10000(min(420, 60 + (layers - 120) * 6)):
        rewards.append(medicine_embryo_reward("shenggudan" if layers % 2 else "yanghundan"))
    return rewards


def _sanitize_zhuiyuan_payload(
    payload: dict[str, Any],
    *,
    server_elapsed_seconds: int | None = None,
) -> ZhuiyuanHundredFloorResult:
    """清洗坠渊百层前端成绩，并按服务端时间重新裁定层数。"""

    reported_layers = max(0, _safe_int(payload.get("layers") or payload.get("score")))
    reported_elapsed = max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds")))
    elapsed_seconds = min(ZHUIYUAN_DURATION_SECONDS, reported_elapsed)
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), ZHUIYUAN_DURATION_SECONDS)
    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)

    # 原玩法约 60fps、每 30 帧加一层；90 秒理论 180 层。这里给少量
    # 前置余量，主要拦截明显伪造的超高层数，不误伤高水平玩家。
    time_layer_cap = min(ZHUIYUAN_LAYER_CAP, int(effective_seconds * 2.1) + 8)
    frame_count = max(0, _safe_int(payload.get("frameCount") or payload.get("frame_count")))

    layers = min(reported_layers, time_layer_cap, ZHUIYUAN_LAYER_CAP)
    death_reason = str(payload.get("deathReason") or payload.get("death_reason") or "manual").strip().lower()
    if death_reason not in ZHUIYUAN_END_REASONS:
        death_reason = "manual"
    score = min(ZHUIYUAN_SCORE_CAP, layers * 20)
    return ZhuiyuanHundredFloorResult(
        layers=max(0, layers),
        score=max(0, score),
        elapsed_seconds=max(0, elapsed_seconds),
        death_reason=death_reason,
        frame_count=frame_count,
    )


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(ZHUIYUAN_DURATION_SECONDS, elapsed)


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
