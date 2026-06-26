"""修仙运行态缓存总线。

这个模块只做两件事：
1. 给各个缓存模块提供统一注册和清理入口。
2. 提供稳定的数据库缓存键，避免同进程测试多个数据库时串缓存。

约束：
- 这里不缓存业务数据本身，不读写数据库。
- 玩家状态、背包、纳戒、交易热度等实时玩法数据不能挂到这里。
- 定义表、身份映射这类缓存必须在对应写入点显式清理。
"""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Callable


CacheClearer = Callable[[], None]

_LOCK = RLock()
_CLEARERS: dict[str, CacheClearer] = {}


def register_runtime_cache(name: str, clearer: CacheClearer) -> None:
    """注册一个运行态缓存清理函数。

    使用稳定名称注册，后注册同名缓存会覆盖旧函数；这让热重载或测试重复
    import 时不会把同一个清理函数累积多份。
    """

    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("缓存名称不能为空")
    with _LOCK:
        _CLEARERS[clean_name] = clearer


def clear_runtime_caches(*, reason: str = "") -> None:
    """清理所有已注册运行态缓存。

    `reason` 只用于调用方表达语义，当前不写日志，避免缓存层依赖 launch 日志
    系统而形成反向依赖。清理函数本身都应该是幂等、快速、无数据库写入的。
    """

    _ = reason
    with _LOCK:
        clearers = tuple(_CLEARERS.values())
    for clearer in clearers:
        clearer()


def database_cache_key(database: Any) -> str:
    """生成数据库相关缓存键。

    正式运行时 `database` 是 `XiuxianDatabase`，带有 `db_path`；测试或工具里也
    可能传入轻量对象。优先使用绝对数据库路径，缺失时退回对象 id，避免不同
    数据库实例共享定义表缓存。
    """

    db_path = getattr(database, "db_path", None)
    if db_path is not None:
        try:
            return str(Path(db_path).resolve()).lower()
        except OSError:
            return str(db_path).lower()
    return f"object:{id(database)}"
