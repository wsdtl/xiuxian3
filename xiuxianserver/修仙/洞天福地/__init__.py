"""洞天福地组件 命令。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from launch.adapter import Depends, MessageHandler, manager

from ..identity import current_player_id
from ..reply import send_reply
from .bianling_color import bianling_color_config, finish_bianling_color, start_bianling_color
from .hedan_furnace import finish_hedan_furnace, hedan_furnace_config, start_hedan_furnace
from .lingguo_sum_ten import finish_lingguo_sum_ten, lingguo_sum_ten_config, start_lingguo_sum_ten
from .lingpai_memory import finish_lingpai_memory, lingpai_memory_config, start_lingpai_memory
from .lingquan_ten_drop import finish_lingquan_ten_drop, lingquan_ten_drop_config, start_lingquan_ten_drop
from .lingxi_fishing import finish_lingxi_fishing, lingxi_fishing_config, start_lingxi_fishing
from .service import service
from .zhuiyuan_hundred_floor import (
    finish_zhuiyuan_hundred_floor,
    start_zhuiyuan_hundred_floor,
    zhuiyuan_hundred_floor_config,
)


router = APIRouter(prefix="/xiuxian/dongtian")
GAME_TOKEN_COOKIE_PREFIX = "xiuxian_dongtian_token_"
GAME_TOKEN_COOKIE_MAX_AGE = 24 * 60 * 60


@router.get("/lingxi-fishing/config")
async def api_lingxi_fishing_config(request: Request, response: Response) -> dict:
    """灵溪垂钓启动配置。"""

    try:
        return _config_with_cookie(
            request,
            response,
            "lingxi-fishing",
            lingxi_fishing_config(service, _game_token_cookie(request, "lingxi-fishing")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingxi-fishing/start")
async def api_lingxi_fishing_start(request: Request) -> dict:
    """灵溪垂钓开局，返回一次性单局凭证。"""

    payload = await _json_payload(request, "灵溪开局数据不是有效 JSON。")
    try:
        return start_lingxi_fishing(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingxi-fishing/finish")
async def api_lingxi_fishing_finish(request: Request) -> dict:
    """灵溪垂钓静态小游戏结算。

    小游戏网页没有机器人身份，只能换取一次性兑换码；玩家身份、收益
    曲线和实际发奖都在 `洞天兑换` 命令中处理。
    """

    payload = await _json_payload(request, "灵溪结算数据不是有效 JSON。")
    try:
        return finish_lingxi_fishing(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/lingpai-memory/config")
async def api_lingpai_memory_config(request: Request, response: Response) -> dict:
    """灵牌记忆启动配置。"""

    try:
        return _config_with_cookie(
            request,
            response,
            "lingpai-memory",
            lingpai_memory_config(service, _game_token_cookie(request, "lingpai-memory")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingpai-memory/start")
async def api_lingpai_memory_start(request: Request) -> dict:
    """灵牌记忆开局，返回服务端牌序和单局凭证。"""

    payload = await _json_payload(request, "灵牌记忆开局数据不是有效 JSON。")
    try:
        return start_lingpai_memory(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingpai-memory/finish")
async def api_lingpai_memory_finish(request: Request) -> dict:
    """灵牌记忆结算。

    牌序由服务端按单局凭证派生；前端提交的配对数和翻牌数
    只是材料，服务端会按时间密度重新裁定并签发一次性洞天兑换码。
    """

    payload = await _json_payload(request, "灵牌记忆结算数据不是有效 JSON。")
    try:
        return finish_lingpai_memory(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/lingquan-ten-drop/config")
async def api_lingquan_ten_drop_config(request: Request, response: Response) -> dict:
    """灵泉十滴启动配置。"""

    try:
        return _config_with_cookie(
            request,
            response,
            "lingquan-ten-drop",
            lingquan_ten_drop_config(service, _game_token_cookie(request, "lingquan-ten-drop")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingquan-ten-drop/start")
async def api_lingquan_ten_drop_start(request: Request) -> dict:
    """灵泉十滴开局，返回一次性单局凭证。"""

    payload = await _json_payload(request, "灵泉开局数据不是有效 JSON。")
    try:
        return start_lingquan_ten_drop(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingquan-ten-drop/finish")
async def api_lingquan_ten_drop_finish(request: Request) -> dict:
    """灵泉十滴结算。

    前端提交的关卡、爆裂和连锁只是材料；服务端会按五分钟上限和
    综合计分重新裁定，最终仍只签发一次性洞天兑换码。
    """

    payload = await _json_payload(request, "灵泉结算数据不是有效 JSON。")
    try:
        return finish_lingquan_ten_drop(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/lingguo-sum-ten/config")
async def api_lingguo_sum_ten_config(request: Request, response: Response) -> dict:
    """灵果凑十启动配置。"""

    try:
        return _config_with_cookie(
            request,
            response,
            "lingguo-sum-ten",
            lingguo_sum_ten_config(service, _game_token_cookie(request, "lingguo-sum-ten")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingguo-sum-ten/start")
async def api_lingguo_sum_ten_start(request: Request) -> dict:
    """灵果凑十开局，返回今日难度和单局凭证。"""

    payload = await _json_payload(request, "灵果开局数据不是有效 JSON。")
    try:
        return start_lingguo_sum_ten(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lingguo-sum-ten/finish")
async def api_lingguo_sum_ten_finish(request: Request) -> dict:
    """灵果凑十结算。

    只认可分数、摘果数、成局数、经过时间和单局凭证；今日难度由
    服务端按开局日期复算，跨零点结算也不会漂移。
    """

    payload = await _json_payload(request, "灵果结算数据不是有效 JSON。")
    try:
        return finish_lingguo_sum_ten(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/bianling-color/config")
async def api_bianling_color_config(request: Request, response: Response) -> dict:
    """辨灵试色启动配置。"""

    try:
        return _config_with_cookie(
            request,
            response,
            "bianling-color",
            bianling_color_config(service, _game_token_cookie(request, "bianling-color")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bianling-color/start")
async def api_bianling_color_start(request: Request) -> dict:
    """辨灵试色开局，返回服务端色阶和单局凭证。"""

    payload = await _json_payload(request, "辨灵试色开局数据不是有效 JSON。")
    try:
        return start_bianling_color(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bianling-color/finish")
async def api_bianling_color_finish(request: Request) -> dict:
    """辨灵试色结算。

    色阶由服务端按单局凭证派生；前端提交的通关层数和误触
    只是材料，服务端会按时间密度重新裁定并签发一次性洞天兑换码。
    """

    payload = await _json_payload(request, "辨灵试色结算数据不是有效 JSON。")
    try:
        return finish_bianling_color(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/hedan-furnace/config")
async def api_hedan_furnace_config(request: Request, response: Response) -> dict:
    """合丹炉启动配置。"""

    try:
        return _config_with_cookie(
            request,
            response,
            "hedan-furnace",
            hedan_furnace_config(service, _game_token_cookie(request, "hedan-furnace")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/hedan-furnace/start")
async def api_hedan_furnace_start(request: Request) -> dict:
    """合丹炉开局，返回服务端随机炉火和单局凭证。"""

    payload = await _json_payload(request, "合丹炉开局数据不是有效 JSON。")
    try:
        return start_hedan_furnace(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/hedan-furnace/finish")
async def api_hedan_furnace_finish(request: Request) -> dict:
    """合丹炉结算。

    只认可分数、最高丹胚、合丹次数、有效手数、经过时间和单局凭证；
    本局炉火由服务端按单局凭证复算，每次开炉都会重抽。
    """

    payload = await _json_payload(request, "合丹炉结算数据不是有效 JSON。")
    try:
        return finish_hedan_furnace(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/zhuiyuan-hundred-floor/config")
async def api_zhuiyuan_hundred_floor_config(request: Request, response: Response) -> dict:
    """坠渊百层启动配置。"""

    try:
        return _config_with_cookie(
            request,
            response,
            "zhuiyuan-hundred-floor",
            zhuiyuan_hundred_floor_config(service, _game_token_cookie(request, "zhuiyuan-hundred-floor")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/zhuiyuan-hundred-floor/start")
async def api_zhuiyuan_hundred_floor_start(request: Request) -> dict:
    """坠渊百层开局，返回一次性单局凭证。"""

    payload = await _json_payload(request, "坠渊百层开局数据不是有效 JSON。")
    try:
        return start_zhuiyuan_hundred_floor(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/zhuiyuan-hundred-floor/finish")
async def api_zhuiyuan_hundred_floor_finish(request: Request) -> dict:
    """坠渊百层结算。

    前端提交的层数和经过时间只是材料；服务端会按单局凭证、九十息
    上限和层数密度重新裁定，最终只签发一次性洞天兑换码。
    """

    payload = await _json_payload(request, "坠渊百层结算数据不是有效 JSON。")
    try:
        return finish_zhuiyuan_hundred_floor(service, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _json_payload(request: Request, error_text: str) -> dict:
    """读取小游戏接口 JSON。"""

    try:
        payload = await request.json()
    except Exception as exc:  # pragma: no cover - FastAPI 只在坏请求时进入
        raise HTTPException(status_code=400, detail=error_text) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=error_text)
    return payload


def _config_with_cookie(request: Request, response: Response, game_key: str, payload: dict) -> dict:
    """把 24 小时启动 token 写入 HttpOnly cookie，刷新页面时复用同一局外身份。

    洞天小游戏没有登录态；这个 cookie 不是玩家身份，只是浏览器和某个
    小游戏之间的短期启动凭证。玩法随机是否绑定每日或单局，由具体小
    游戏结算文件决定，不能默认绑定到启动凭证。
    """

    token = str(payload.get("game_token") or "").strip()
    if token and token != _game_token_cookie(request, game_key):
        response.set_cookie(
            _game_token_cookie_name(game_key),
            token,
            max_age=GAME_TOKEN_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            path=f"/xiuxian/dongtian/{game_key}",
        )
    return payload


def _game_token_cookie(request: Request, game_key: str) -> str:
    """读取当前小游戏的启动 token cookie。"""

    return str(request.cookies.get(_game_token_cookie_name(game_key)) or "").strip()


def _game_token_cookie_name(game_key: str) -> str:
    """生成稳定 cookie 名；只用在洞天 HTTP 接口层。"""

    safe_key = "".join(ch if ch.isalnum() else "_" for ch in str(game_key or "").strip())
    return f"{GAME_TOKEN_COOKIE_PREFIX}{safe_key}"


@MessageHandler.handler(cmd="洞天福地", priority=100, block=True)
async def ws_dongtian_games(player_id: str = Depends(current_player_id)) -> None:
    """查看洞天福地小游戏入口。"""

    await send_reply(player_id, service.games(player_id), manager, service)


@MessageHandler.handler(cmd="洞天兑换", priority=100, block=True)
async def ws_dongtian_redeem(message: str, player_id: str = Depends(current_player_id)) -> None:
    """兑换洞天福地兑换码。"""

    await send_reply(player_id, service.redeem(player_id, message), manager, service)


@MessageHandler.handler(cmd="洞天记录", priority=100, block=True)
async def ws_dongtian_records(player_id: str = Depends(current_player_id)) -> None:
    """查看洞天福地兑换记录。"""

    await send_reply(player_id, service.records(player_id), manager, service)
