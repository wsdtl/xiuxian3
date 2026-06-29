"""合丹炉小游戏结算。

合丹炉是 150 秒的短局 2048 玩法。前端只负责把炼丹过程摘要上报；
服务端按启动凭证、单局凭证、经过时间、本局随机炉火和分数密度重新裁定成绩。
"""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Any

from ..common import dt, now
from ..constants import DONGTIAN_ROUND_MIN_SECONDS, DONGTIAN_ROUND_TTL_MINUTES
from .lingxi_fishing import DongtianIssuer
from .random_seed import round_rng
from .service import medicine_embryo_reward

HEDAN_FURNACE_KEY = "hedan-furnace"
HEDAN_FURNACE_TITLE = "合丹炉"
HEDAN_DURATION_SECONDS = 150
HEDAN_BOARD_SIZE = 4
HEDAN_SCORE_CAP = 4200
HEDAN_MAX_TILE_CAP = 4096
HEDAN_MOVE_CAP = 240
HEDAN_MERGE_CAP = 220


@dataclass(frozen=True)
class HedanDifficulty:
    """服务端定义的一局炉火。

    炉火由单局凭证派生，每次开炉都会换一炉火。前端可以按这些
    安全字段生成手感，但不能把炉火当成结算依据提交回来。
    """

    key: str
    label: str
    description: str
    start_tiles: int
    four_rate: float
    reward_multiplier: float
    score_per_second_cap: float
    move_seconds: float
    merge_seconds: float

    def public_config(self) -> dict[str, Any]:
        """返回前端生成本局棋盘需要的安全字段。"""

        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "start_tiles": self.start_tiles,
            "four_rate": self.four_rate,
        }


HEDAN_DIFFICULTIES: tuple[HedanDifficulty, ...] = (
    HedanDifficulty(
        key="wenhuo",
        label="文火炉",
        description="炉火绵软，丹胚更容易慢慢合拢。",
        start_tiles=3,
        four_rate=0.07,
        reward_multiplier=0.96,
        score_per_second_cap=22.0,
        move_seconds=0.62,
        merge_seconds=0.72,
    ),
    HedanDifficulty(
        key="zhenhuo",
        label="真火炉",
        description="炉火平稳，讲究手感和取舍。",
        start_tiles=2,
        four_rate=0.10,
        reward_multiplier=1.0,
        score_per_second_cap=20.0,
        move_seconds=0.70,
        merge_seconds=0.82,
    ),
    HedanDifficulty(
        key="jiehuo",
        label="劫火炉",
        description="火势更躁，容易出高阶丹胚，也更容易堵炉。",
        start_tiles=2,
        four_rate=0.16,
        reward_multiplier=1.08,
        score_per_second_cap=18.0,
        move_seconds=0.80,
        merge_seconds=0.94,
    ),
)


@dataclass(frozen=True)
class HedanFurnaceResult:
    """合丹炉服务端认可的结算摘要。"""

    score: int
    max_tile: int
    merge_count: int
    move_count: int
    elapsed_seconds: int
    difficulty: HedanDifficulty


def hedan_furnace_config(service: DongtianIssuer, reuse_token: str | None = None) -> dict[str, Any]:
    """读取合丹炉启动配置，并签发 24 小时启动凭证。"""

    return service.game_config(
        HEDAN_FURNACE_KEY,
        HEDAN_FURNACE_TITLE,
        reuse_token=reuse_token,
        config={
            "game_duration": HEDAN_DURATION_SECONDS,
            "board_size": HEDAN_BOARD_SIZE,
            "score_cap": HEDAN_SCORE_CAP,
            "max_tile_cap": HEDAN_MAX_TILE_CAP,
            "round_ttl_minutes": DONGTIAN_ROUND_TTL_MINUTES,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
            "difficulty_profiles": [item.public_config() for item in HEDAN_DIFFICULTIES],
        },
    )


def start_hedan_furnace(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验启动凭证，给合丹炉签发一次单局凭证和本局炉火。"""

    if not isinstance(payload, dict):
        raise ValueError("合丹炉开局数据异常，请重新进入小游戏。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    round_info = service.start_round(HEDAN_FURNACE_KEY, game_token)
    difficulty = _difficulty_for_round(
        game_token,
        str(round_info.get("session_id") or ""),
        str(round_info.get("round_token") or ""),
    )
    round_info.update(
        {
            "game_duration": HEDAN_DURATION_SECONDS,
            "board_size": HEDAN_BOARD_SIZE,
            "score_cap": HEDAN_SCORE_CAP,
            "max_tile_cap": HEDAN_MAX_TILE_CAP,
            "round_min_seconds": DONGTIAN_ROUND_MIN_SECONDS,
            "difficulty": difficulty.public_config(),
        }
    )
    return round_info


def finish_hedan_furnace(service: DongtianIssuer, payload: dict[str, Any]) -> dict[str, Any]:
    """校验合丹炉成绩，签发低量洞天兑换码。"""

    if not isinstance(payload, dict):
        raise ValueError("合丹炉结算数据异常，请重新开局。")
    game_token = str(payload.get("gameToken") or payload.get("game_token") or "").strip()
    session_id = str(payload.get("sessionId") or payload.get("session_id") or "").strip()
    round_token = str(payload.get("roundToken") or payload.get("round_token") or "").strip()
    difficulty = _difficulty_for_round(game_token, session_id, round_token)
    round_row = service.inspect_round(
        HEDAN_FURNACE_KEY,
        game_token,
        session_id,
        round_token,
    )
    result = _sanitize_hedan_furnace_payload(
        payload,
        difficulty=difficulty,
        server_elapsed_seconds=_server_elapsed_seconds(round_row),
    )
    rewards = _hedan_furnace_rewards(result)
    issued = service.issue_code_for_round(
        HEDAN_FURNACE_KEY,
        HEDAN_FURNACE_TITLE,
        game_token,
        session_id,
        round_token,
        rewards,
        score=result.score,
        meta={
            "max_tile": result.max_tile,
            "merge_count": result.merge_count,
            "move_count": result.move_count,
            "elapsed_seconds": result.elapsed_seconds,
            "difficulty": result.difficulty.key,
        },
    )
    display_score = max(0, int(issued.get("score", result.score))) if issued.get("reissued") else result.score
    issued_meta = issued.get("meta") if issued.get("reissued") and isinstance(issued.get("meta"), dict) else {}
    display_tile = _normalize_tile(issued_meta.get("max_tile")) if issued_meta else result.max_tile
    display_merges = max(0, _safe_int(issued_meta.get("merge_count"))) if issued_meta else result.merge_count
    display_moves = max(0, _safe_int(issued_meta.get("move_count"))) if issued_meta else result.move_count
    display_elapsed = max(0, _safe_int(issued_meta.get("elapsed_seconds"))) if issued_meta else result.elapsed_seconds
    issued["reward_preview"] = service.reward_preview(issued["rewards"])
    issued["accepted_score"] = display_score
    issued["max_tile"] = display_tile
    issued["merge_count"] = display_merges
    issued["move_count"] = display_moves
    issued["elapsed_seconds"] = display_elapsed
    issued["difficulty"] = result.difficulty.label
    issued["message"] = (
        f"丹炉收火：{display_score} 分，最高丹胚 {display_tile}，"
        "回到机器人发送洞天兑换即可领取。"
    )
    return issued


def _hedan_furnace_rewards(result: HedanFurnaceResult) -> list[dict[str, Any]]:
    """把合丹炉认可分转成洞天基础奖励快照。"""

    score = max(0, min(HEDAN_SCORE_CAP, result.score))
    max_tile = max(2, min(HEDAN_MAX_TILE_CAP, result.max_tile))
    merge_count = max(0, min(HEDAN_MERGE_CAP, result.merge_count))
    multiplier = result.difficulty.reward_multiplier
    tier = max(1, int(math.log2(max_tile)))
    rewards: list[dict[str, Any]] = []

    currency = min(740, int((24 + score * 0.15 + merge_count * 2.2 + tier * 9) * multiplier))
    exp = min(60, int((4 + score // 120 + merge_count // 10 + tier // 2) * multiplier))
    rewards.append({"type": "currency", "quantity": max(20, currency)})
    rewards.append({"type": "exp", "quantity": max(4, exp)})

    if score >= 180 or max_tile >= 64:
        rewards.append(medicine_embryo_reward("xueqidan" if score % 2 == 0 else "yinmingcao"))
    if score >= 1100 or max_tile >= 256:
        rewards.append(medicine_embryo_reward("huichunlu" if score % 2 else "ningshenlu"))
    if (score >= 2300 or max_tile >= 512) and _chance_per_10000(min(520, 110 + tier * 18 + merge_count // 2)):
        rewards.append(medicine_embryo_reward("shenggudan" if score % 2 else "yanghundan"))
    if score >= 1900 and _chance_per_10000(min(820, 100 + score // 6 + tier * 28)):
        rewards.append({"type": "wish_token", "quantity": 1})
    if score >= 3600 and _chance_per_10000(min(110, 22 + tier * 4 + merge_count // 8)):
        rewards.append({"type": "ring_item", "key": "xisuiye", "quantity": 1})
    return rewards


def _sanitize_hedan_furnace_payload(
    payload: dict[str, Any],
    *,
    difficulty: HedanDifficulty,
    server_elapsed_seconds: int | None = None,
) -> HedanFurnaceResult:
    """清洗合丹炉前端成绩，并按时间、手数和合丹密度重新裁定。"""

    reported_score = min(HEDAN_SCORE_CAP, max(0, _safe_int(payload.get("score"))))
    max_tile = _normalize_tile(payload.get("maxTile") or payload.get("max_tile"))
    merge_count = min(HEDAN_MERGE_CAP, max(0, _safe_int(payload.get("mergeCount") or payload.get("merge_count"))))
    move_count = min(HEDAN_MOVE_CAP, max(0, _safe_int(payload.get("moveCount") or payload.get("move_count"))))
    elapsed_seconds = min(
        HEDAN_DURATION_SECONDS,
        max(0, _safe_int(payload.get("elapsedSeconds") or payload.get("elapsed_seconds"))),
    )
    if server_elapsed_seconds is not None:
        elapsed_seconds = min(elapsed_seconds, max(0, int(server_elapsed_seconds)), HEDAN_DURATION_SECONDS)

    effective_seconds = max(DONGTIAN_ROUND_MIN_SECONDS, elapsed_seconds)
    move_time_cap = min(HEDAN_MOVE_CAP, int(effective_seconds / difficulty.move_seconds) + 4)
    merge_time_cap = min(HEDAN_MERGE_CAP, int(effective_seconds / difficulty.merge_seconds) + 3)
    move_count = min(move_count, move_time_cap)
    merge_count = min(merge_count, merge_time_cap, max(0, move_count * 2))

    # 2048 的分数天然由合并块产生；这里不尝试还原棋盘，只把分数压回到
    # 最高丹胚、合并次数、有效手数和服务端经过时间都能支撑的范围。
    tile_score_cap = max_tile * 3 + int(math.log2(max_tile)) * 160
    action_score_cap = merge_count * 34 + move_count * 8
    time_score_cap = int(effective_seconds * difficulty.score_per_second_cap) + max_tile
    accepted_score = min(reported_score, tile_score_cap, action_score_cap, time_score_cap, HEDAN_SCORE_CAP)
    return HedanFurnaceResult(
        score=max(0, accepted_score),
        max_tile=max_tile,
        merge_count=max(0, merge_count),
        move_count=max(0, move_count),
        elapsed_seconds=elapsed_seconds,
        difficulty=difficulty,
    )


def _difficulty_for_round(game_token: str, session_id: str, round_token: str) -> HedanDifficulty:
    """用单局凭证派生炉火，每次开炉随机，但结算阶段可复算。"""

    rng = round_rng(HEDAN_FURNACE_KEY, game_token, session_id, round_token, "difficulty")
    return HEDAN_DIFFICULTIES[rng.randrange(len(HEDAN_DIFFICULTIES))]


def _server_elapsed_seconds(round_row: dict[str, Any]) -> int:
    """按服务端单局凭证计算已游玩秒数。"""

    issued_at = dt(str(round_row.get("issued_at") or ""))
    if issued_at is None:
        return 0
    elapsed = int(max(0, (now() - issued_at).total_seconds()))
    return min(HEDAN_DURATION_SECONDS, elapsed)


def _normalize_tile(value: Any) -> int:
    """把前端上报的最高块压成合法 2 的幂。"""

    raw = max(2, min(HEDAN_MAX_TILE_CAP, _safe_int(value)))
    power = 2
    while power * 2 <= raw and power * 2 <= HEDAN_MAX_TILE_CAP:
        power *= 2
    return power


def _safe_int(value: Any) -> int:
    """宽松读取前端数字。"""

    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _chance_per_10000(chance: int) -> bool:
    """万分比随机。"""

    return secrets.randbelow(10_000) < max(0, min(10_000, int(chance)))
