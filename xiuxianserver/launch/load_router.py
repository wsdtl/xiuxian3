import os
from fastapi import APIRouter
from abc import abstractmethod
from importlib import import_module
from typing import Callable, List, Tuple

from .log import C, logger
from .config import config


class Routers:
    """保存待导入模块和待注册路由模块。"""

    router_list: List[str] = []
    module_list: List[str] = []

    @staticmethod
    def clear() -> None:
        """
        清空上一次收集到的模块和路由。

        create_app() 在测试或热重载场景下可能被多次调用。
        每次重新收集前先清空，避免把旧结果带到新的 app 里。
        """

        Routers.router_list = []
        Routers.module_list = []

    @staticmethod
    def run() -> None:
        """按原顺序去重。"""

        Routers.router_list = list(dict.fromkeys(Routers.router_list))
        Routers.module_list = list(dict.fromkeys(Routers.module_list))

    class Router:

        @abstractmethod
        def router(self) -> "APIRouter":
            """带 HTTP 路由的模块需要在 __init__.py 暴露 router。"""
            ...


class LoadRouter:
    """根据 RouterConfig 收集模块路径。"""

    @staticmethod
    def module_to_path(folder: str) -> str:
        """把 Python 模块路径转成本地目录路径。"""

        if "." in folder:
            folder = os.path.join(*folder.split("."))

        return folder

    @staticmethod
    def load_router_folders(folder: str) -> None:
        """收集某个目录下所有带 router 的子模块。

        例：folder="src" 时，会收集 src.xxx、src.yyy。
        """

        folders = [f for f in os.listdir(LoadRouter.module_to_path(folder)) if os.path.isdir(os.path.join(LoadRouter.module_to_path(folder), f))]

        for module in folders:
            if "__init__.py" in os.listdir(os.path.join(LoadRouter.module_to_path(folder), module)):
                Routers.router_list.append(f"{folder}.{module}")
                Routers.module_list.append(f"{folder}.{module}")

    @staticmethod
    def load_router_folder(folder: str) -> None:
        """收集一个自身带 router 的模块。"""

        if "__init__.py" in os.listdir(LoadRouter.module_to_path(folder)):
            Routers.router_list.append(folder)
            Routers.module_list.append(folder)

    @staticmethod
    def load_router_group(folder: str) -> None:
        """收集一个路由组。

        组本身带 router，组内子目录只作为普通模块导入。
        """

        LoadRouter.load_router_folder(folder)
        folders = [f for f in os.listdir(LoadRouter.module_to_path(folder)) if os.path.isdir(os.path.join(LoadRouter.module_to_path(folder), f))]
        for module in folders:
            if "__init__.py" in os.listdir(os.path.join(LoadRouter.module_to_path(folder), module)):
                Routers.module_list.append(f"{folder}.{module}")

    @staticmethod
    def load_module(folder: str) -> None:
        """收集一个普通模块，不要求它提供 router。"""

        Routers.module_list.append(folder)

    @staticmethod
    def load_module_group(folder: str) -> None:
        """收集某个目录下所有普通子模块。

        例：folder="auto" 时，会收集 auto.cfg 这类子模块。
        """

        folders = [f for f in os.listdir(LoadRouter.module_to_path(folder)) if os.path.isdir(os.path.join(LoadRouter.module_to_path(folder), f))]
        for module in folders:
            if "__init__.py" in os.listdir(os.path.join(LoadRouter.module_to_path(folder), module)):
                Routers.module_list.append(f"{folder}.{module}")


def FastAPILoadRouter() -> None:
    """按配置收集业务模块和路由模块。"""

    Routers.clear()

    load_plan: Tuple[Tuple[Callable[[str], None], List[str]], ...] = (
        (LoadRouter.load_module_group, config.router.module_groups),
        (LoadRouter.load_router_folder, config.router.router_folders),
        (LoadRouter.load_module, config.router.modules),
        (LoadRouter.load_router_group, config.router.router_groups),
        (LoadRouter.load_router_folders, config.router.router_child_folders),
    )

    for loader, modules in load_plan:
        for module in modules:
            loader(module)


def module_tag(module_name: str) -> str:
    """根据模块名生成 /docs 分类名。

    例如：

        src.室温监控 -> 室温监控
        src.user.api -> api

    以后想显示更完整的分类名，可以只改这里。
    """

    return module_name.rsplit(".", 1)[-1]


def FastAPIIncludeRouter(app) -> None:
    """导入业务模块，并把 HTTP router 注册到 FastAPI。

    必须在 create_app() 阶段执行，否则 /docs 生成 OpenAPI 时可能看不到路由。
    - 普通模块只导入，用来触发 OnEvent / Scheduler 等装饰器注册。
    - 带 router 的模块会 app.include_router(...)。
    - router 会自动补 tags=[模块名]，用于 /docs 分类。
    """

    if getattr(app.state, "business_router_loaded", False):
        return

    FastAPILoadRouter()
    Routers.run()

    for module_name in Routers.module_list:
        try:
            module: Routers.Router = import_module(module_name)
        except Exception as exc:
            logger.opt(colors=True, exception=exc).error(
                C.join(
                    C.fail("Loaded module error"),
                    C.kv("module", module_name),
                )
            )
            raise

        if module_name in Routers.router_list and hasattr(module, "router"):
            tag = module_tag(module_name)
            app.include_router(module.router, tags=[tag])
            logger.opt(colors=True).success(
                C.join(
                    C.ok("Loaded module include router"),
                    C.kv("module", module_name),
                    C.kv("tag", tag),
                )
            )
        else:
            logger.opt(colors=True).success(
                C.join(
                    C.ok("Loaded module not include router"),
                    C.kv("module", module_name),
                )
            )

    app.state.business_router_loaded = True
