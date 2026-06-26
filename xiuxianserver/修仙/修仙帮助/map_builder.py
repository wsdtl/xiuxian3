"""修仙帮助站地图数据组装。"""

from __future__ import annotations

from typing import Any

from ..common import now
from ..constants import WORLD_COORD_MAX, WORLD_COORD_MIN
from ..sql import db


# 地图坐标范围是 -100..100。前端按 1 坐标 = 24px 渲染，
# 用缩放和平移查看细节，避免相距十几个坐标的宗门在最大缩放下仍挤在一起。
MAP_COORD_PIXELS = 24


def build_map_data(database: Any = db, player_id: str = "") -> dict[str, Any]:
    """组装公开地图需要的动态数据。"""

    player = _player(database, player_id)
    active_events = [*_wormhole_events(database), *_treasure_events(database)]
    return {
        "updatedAt": now().strftime("%Y-%m-%d %H:%M:%S"),
        "bounds": {
            "min": WORLD_COORD_MIN,
            "max": WORLD_COORD_MAX,
            "unitPixels": MAP_COORD_PIXELS,
        },
        "cities": _cities(database),
        "realms": _realms(database),
        "buyers": _buyers(database),
        "recycles": _recycles(database),
        "sects": _sects(database),
        "events": active_events,
        "player": player,
    }


def _cities(database: Any) -> list[dict[str, Any]]:
    rows = database.fetch_all(
        """
        SELECT t.location_id, t.name, t.x, t.y, t.specialties,
               COALESCE(w.terrain, '') AS terrain,
               COALESCE(w.desc, '') AS desc,
               COALESCE(c.city_level, 1) AS city_level,
               COALESCE(c.build_exp, 0) AS build_exp,
               COALESCE(c.relic_energy, 0) AS relic_energy
        FROM trade_locations AS t
        LEFT JOIN world_locations AS w ON w.location_id = t.location_id
        LEFT JOIN city_world_states AS c ON c.location_id = t.location_id
        ORDER BY t.name
        """
    )
    return [
        {
            "type": "city",
            "id": str(row["location_id"]),
            "name": str(row["name"]),
            "x": int(row["x"]),
            "y": int(row["y"]),
            "level": int(row["city_level"] or 1),
            "build": int(row["build_exp"] or 0),
            "relic": int(row["relic_energy"] or 0),
            "continent": _continent_name(int(row["x"]), int(row["y"])),
            "region": str(row["terrain"] or "未明地貌"),
            "specialties": str(row["specialties"] or ""),
            "desc": str(row["desc"] or ""),
        }
        for row in rows
    ]


def _realms(database: Any) -> list[dict[str, Any]]:
    rows = database.fetch_all(
        """
        SELECT e.location_id, e.name, e.x, e.y, e.desc,
               COALESCE(w.terrain, '') AS terrain
        FROM exploration_locations AS e
        LEFT JOIN world_locations AS w ON w.location_id = e.location_id
        WHERE e.location_id NOT IN (SELECT location_id FROM trade_locations)
        ORDER BY e.name
        """
    )
    return [
        {
            "type": "realm",
            "id": str(row["location_id"]),
            "name": str(row["name"]),
            "x": int(row["x"]),
            "y": int(row["y"]),
            "desc": str(row["desc"] or "动态映身秘境"),
            "terrain": str(row["terrain"] or "秘境"),
        }
        for row in rows
    ]


def _buyers(database: Any) -> list[dict[str, Any]]:
    rows = database.fetch_all(
        """
        SELECT b.location_id, b.buyer_name, b.price_factor, b.x, b.y,
               COALESCE(w.terrain, '') AS terrain
        FROM special_buyers AS b
        LEFT JOIN world_locations AS w ON w.location_id = b.location_id
        ORDER BY b.buyer_name
        """
    )
    return [
        {
            "type": "buyer",
            "id": str(row["location_id"]),
            "name": str(row["buyer_name"]),
            "x": int(row["x"]),
            "y": int(row["y"]),
            "desc": f"战利品收购｜倍率 {float(row['price_factor'] or 1):.2f}",
            "terrain": str(row["terrain"] or ""),
        }
        for row in rows
    ]


def _recycles(database: Any) -> list[dict[str, Any]]:
    rows = database.fetch_all(
        """
        SELECT r.location_id, r.name, r.recycle_type, r.price_factor, r.x, r.y, r.desc,
               COALESCE(w.terrain, '') AS terrain
        FROM recycle_locations AS r
        LEFT JOIN world_locations AS w ON w.location_id = r.location_id
        ORDER BY r.recycle_type, r.name
        """
    )
    return [
        {
            "type": "recycle",
            "id": str(row["location_id"]),
            "name": str(row["name"]),
            "x": int(row["x"]),
            "y": int(row["y"]),
            "desc": str(row["desc"] or f"{row['recycle_type']} 回收"),
            "recycleType": str(row["recycle_type"] or ""),
            "priceFactor": float(row["price_factor"] or 1),
            "terrain": str(row["terrain"] or ""),
        }
        for row in rows
    ]


def _sects(database: Any) -> list[dict[str, Any]]:
    rows = database.fetch_all(
        """
        SELECT s.sect_id, s.name, s.location_x, s.location_y, s.master_client_id,
               COALESCE(st.level, 1) AS level,
               COALESCE(st.exp, 0) AS exp,
               COUNT(m.client_id) AS member_count
        FROM sects AS s
        LEFT JOIN sect_stats AS st ON st.sect_id = s.sect_id
        LEFT JOIN sect_members AS m ON m.sect_id = s.sect_id
        GROUP BY s.sect_id
        ORDER BY s.sect_id
        """
    )
    return [
        {
            "type": "sect",
            "id": f"sect_{int(row['sect_id'])}",
            "name": str(row["name"]),
            "x": int(row["location_x"]),
            "y": int(row["location_y"]),
            "level": int(row["level"] or 1),
            "exp": int(row["exp"] or 0),
            "members": int(row["member_count"] or 0),
            "master": _player_name(database, str(row["master_client_id"] or "")),
        }
        for row in rows
    ]


def _wormhole_events(database: Any) -> list[dict[str, Any]]:
    rows = database.fetch_all(
        """
        SELECT wormhole_id, boss_name, boss_kind, location_name, x, y, hp, max_hp, difficulty, closes_at
        FROM wormholes
        WHERE status = '开启'
        ORDER BY opened_at DESC
        """
    )
    return [
        {
            "type": "event",
            "id": f"wormhole_{int(row['wormhole_id'])}",
            "name": f"虫洞·{row['boss_name']}",
            "eventKind": "异界虫洞",
            "x": int(row["x"]),
            "y": int(row["y"]),
            "desc": f"{row['location_name']}｜{row['boss_kind']}｜血气 {int(row['hp'])}/{int(row['max_hp'])}｜难度 {float(row['difficulty']):.2f}",
            "closesAt": str(row["closes_at"] or ""),
        }
        for row in rows
    ]


def _treasure_events(database: Any) -> list[dict[str, Any]]:
    rows = database.fetch_all(
        """
        SELECT map_id, city_name, status, x, y, current_price, bid_count, weapon_name, weapon_max_level, expires_at
        FROM treasure_maps
        WHERE status IN ('拍卖中', '可拾取', '宗主待领', '已成交')
        ORDER BY generated_at DESC
        """
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        x = row["x"]
        y = row["y"]
        if x is None or y is None:
            point = _city_point(database, str(row["city_name"] or ""))
            x = point.get("x", 0)
            y = point.get("y", 0)
        result.append(
            {
                "type": "event",
                "id": f"treasure_{int(row['map_id'])}",
                "name": f"藏宝图·{row['city_name']}",
                "eventKind": "藏宝图",
                "x": int(x),
                "y": int(y),
                "desc": f"{row['status']}｜{row['weapon_name']} 上限{int(row['weapon_max_level'] or 0)}｜当前价 {int(row['current_price'] or 0)}｜出价 {int(row['bid_count'] or 0)}",
                "closesAt": str(row["expires_at"] or ""),
            }
        )
    return result


def _player(database: Any, player_id: str) -> dict[str, Any] | None:
    clean_id = str(player_id or "").strip()
    if not clean_id:
        return None
    row = database.fetch_one(
        """
        SELECT client_id, display_name, location_name, location_id, x, y, level, status
        FROM players
        WHERE client_id = ?
        """,
        (clean_id,),
    )
    if not row:
        return None
    return {
        "type": "player",
        "id": f"player_{row['client_id']}",
        "name": str(row["display_name"] or "当前位置"),
        "x": int(row["x"]),
        "y": int(row["y"]),
        "level": int(row["level"] or 1),
        "status": str(row["status"] or ""),
        "location": str(row["location_name"] or ""),
        "locationId": str(row["location_id"] or ""),
    }


def _city_point(database: Any, city_name: str) -> dict[str, int]:
    row = database.fetch_one(
        "SELECT x, y FROM trade_locations WHERE name = ?",
        (str(city_name or "").strip(),),
    )
    if not row:
        return {"x": 0, "y": 0}
    return {"x": int(row["x"]), "y": int(row["y"])}


def _player_name(database: Any, player_id: str) -> str:
    if not player_id:
        return ""
    row = database.fetch_one("SELECT display_name FROM players WHERE client_id = ?", (player_id,))
    return str(row["display_name"] or player_id) if row else player_id


def _continent_name(x: int, y: int) -> str:
    """四洲只是地图底图地基，按坐标粗分展示，不参与业务规则。"""

    if y >= 42:
        return "北俱芦洲"
    if y <= -34:
        return "南赡部洲"
    if x >= 20:
        return "东胜神洲"
    if x <= -20:
        return "西牛贺洲"
    return "南赡部洲"
