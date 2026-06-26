"""修仙帮助站地图页面。"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from fastapi_cache.decorator import cache

from ..sql import db
from .map_builder import build_map_data


# 交互地图的视觉底板只由静态 HTML/CSS/JS 维护；地点、宗门、虫洞、
# 藏宝图等动态信息统一从 `/xiuxian/map/data` 读取数据库，不再把
# 绘图提示词或画师参考放进 Markdown 知识源。
MAP_HTML = Path(__file__).resolve().parents[2] / "static" / "map" / "world-map.html"
router = APIRouter()


@router.get("/xiuxian/map", response_class=HTMLResponse)
async def map_index() -> HTMLResponse:
    """交互地图页面。"""

    if not MAP_HTML.exists():
        raise HTTPException(status_code=404, detail="map page not found")
    return HTMLResponse(MAP_HTML.read_text(encoding="utf-8"))


@router.get("/xiuxian/map/data")
@cache(expire=60, namespace="help:map")
async def map_data(player_id: str = "") -> dict:
    """地图动态数据；页面每 60 秒刷新一次。"""

    return build_map_data(db, player_id=player_id)
