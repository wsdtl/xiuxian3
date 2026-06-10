"""修仙数据库备份包。

这个包没有 HTTP 路由，只负责在服务关闭时备份修仙数据库。
APP_ROUTER_GROUPS 会导入中文子包，因此这里可以直接注册 OnEvent 回调。
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from launch import C, OnEvent, logger

from ..sql import XiuxianDB, db


MAX_BACKUPS = 10


def backup_database(database: XiuxianDB) -> Path:
    """把当前 sqlite 库备份到本包目录，并只保留最近 10 份。"""

    db_path = Path(database.db_path)
    backup_dir = Path(__file__).resolve().parent

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{db_path.stem}_{timestamp}{db_path.suffix}"

    with database.lock:
        database.init()
        assert database.conn is not None
        database.conn.commit()

        # sqlite3 的上下文管理器只提交事务，不会自动关闭连接。
        # Windows 下备份文件被占用时尤其明显，所以这里显式 close。
        backup_conn = sqlite3.connect(backup_path)
        try:
            database.conn.backup(backup_conn)
            backup_conn.commit()
        finally:
            backup_conn.close()

    _cleanup_old_backups(backup_dir, db_path.stem, db_path.suffix)
    return backup_path


@OnEvent.disconnect(priority=100)
async def backup_db() -> None:
    """服务关闭时备份修仙数据库。"""

    try:
        backup_path = backup_database(db)
        logger.opt(colors=True).info(
            C.join(
                C.warn("执行 修仙数据库 备份"),
                C.kv("path", backup_path),
            )
        )
    except Exception as exc:
        logger.opt(colors=True).error(
            C.join(
                C.fail("执行 修仙数据库 备份失败"),
                C.kv("error", exc),
            )
        )


def _cleanup_old_backups(backup_dir: Path, stem: str, suffix: str) -> None:
    """删除过旧备份，避免每次停服都无限堆文件。"""

    backups = sorted(
        backup_dir.glob(f"{stem}_*{suffix}"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in backups[MAX_BACKUPS:]:
        path.unlink(missing_ok=True)
