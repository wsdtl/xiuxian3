"""
项目配置。

只读取项目根目录的 .env，并实例化出全局 config。

其他模块统一这样使用：

    from launch.config import config

或：

    from launch import config

项目只有一个配置入口，也只有一个配置对象。
"""

import ast
from pathlib import Path
from typing import Iterable, List
from dataclasses import dataclass

# 项目根目录。
BASE_DIR = Path(__file__).resolve().parent.parent


# 唯一配置入口：项目根目录下的 .env 文件。
ENV_FILE = BASE_DIR / ".env"


# 项目基础配置在 .env 里的键名。
PROJECT_ENV_KEYS = {"APP_NAME", "APP_DEBUG", "APP_TIMEZONE"}


# 日志配置在 .env 里的键名。默认值在 load_config() 中维护。
LOG_ENV_KEYS = {
    "LOG_LEVEL",
    "LOG_COLOR",
    "LOG_DIR",
    "LOG_FILE",
    "LOG_ROTATION",
    "LOG_RETENTION",
    "LOG_COMPRESSION",
}


# 模块 / 路由加载配置在 .env 里的键名。
ROUTER_ENV_KEYS = {
    "APP_MODULE_GROUPS",
    "APP_MODULES",
    "APP_ROUTER_FOLDERS",
    "APP_ROUTER_GROUPS",
    "APP_ROUTER_CHILD_FOLDERS",
}


# 项目已经认识的配置键名；其他 .env 项会进入 config.custom。
SYSTEM_ENV_KEYS = PROJECT_ENV_KEYS | LOG_ENV_KEYS | ROUTER_ENV_KEYS


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """
    读取 .env，返回字符串字典。

    支持写法：

        APP_NAME=xiuxianserver
        APP_MODULES=["src.ws"]
        zdy1=hello

    空行、# 注释、无等号的行会被忽略。
    """

    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在：{path}\n" "请复制项目根目录的 .env.example 为 .env 后再启动项目。")

    values: dict[str, str] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key:
            values[key] = value

    return values


class Env:
    """
    .env 字符串字典的读取工具。

    只负责把字符串转成常用类型，不负责业务含义。
    """

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def get(self, name: str, default: str = "") -> str:
        """读取一个字符串配置。"""

        return self.values.get(name, default).strip()

    def get_bool(self, name: str, default: bool = False) -> bool:
        """
        读取布尔配置。

        推荐写法：

            APP_DEBUG=true
            APP_DEBUG=false

        也支持 1/0、yes/no、on/off。
        """

        raw = self.get(name)
        if not raw:
            return default

        value = raw.lower()
        if value in {"true", "1", "yes", "on"}:
            return True
        if value in {"false", "0", "no", "off"}:
            return False

        raise ValueError(f"{name} 的值只能是 true/false、1/0、yes/no、on/off，当前值是：{raw}")

    def get_list(self, name: str, default: Iterable[str] = ()) -> List[str]:
        """
        读取列表配置。

        .env 中必须写成列表：

            APP_MODULES=["src.ws"]
        """

        raw = self.get(name)
        if not raw:
            return list(default)

        try:
            value = ast.literal_eval(raw)
        except (SyntaxError, ValueError) as exc:
            raise ValueError(f"{name} 必须写成列表，例如：{name}=['src.ws']") from exc

        if not isinstance(value, list):
            raise ValueError(f"{name} 必须是列表，例如：{name}=['src.ws']")

        for item in value:
            if not isinstance(item, str):
                raise ValueError(f"{name} 里的每一项都必须是字符串，当前项是：{item!r}")

        return [item.strip() for item in value if item.strip()]

    def get_path(self, name: str, default: Path | str) -> Path:
        """
        读取路径配置。

        相对路径会转成相对于项目根目录的绝对路径。
        """

        path = Path(self.get(name, str(default)))
        if path.is_absolute():
            return path
        return BASE_DIR / path


@dataclass(frozen=True)
class ProjectConfig:
    """项目基础配置。"""

    name: str
    debug: bool
    timezone: str


@dataclass(frozen=True)
class LogConfig:
    """日志相关配置。"""

    level: str
    color: str
    dir: Path
    file: Path
    rotation: str
    retention: str
    compression: str


@dataclass(frozen=True)
class RouterConfig:
    """
    模块和路由加载配置。

    .env 中必须写成列表：

        APP_MODULES=["src.ws"]
        APP_ROUTER_GROUPS=[]
    """

    module_groups: List[str]
    modules: List[str]
    router_folders: List[str]
    router_groups: List[str]
    router_child_folders: List[str]


@dataclass(frozen=True)
class AppConfig:
    """
    项目总配置。

    常用读取：

        from launch import config

        print(config.project.name)
        print(config.project.debug)
        print(config.project.timezone)
        print(config.log.level)
        print(config.router.modules)

    自定义参数：

        zdy1=hello
        print(config.zdy1)

    非 Python 属性名用 get：

        MY-TOKEN=123
        token = config.get("MY-TOKEN", "")
    """

    base_dir: Path
    env_file: Path
    raw: dict[str, str]
    project: ProjectConfig
    log: LogConfig
    router: RouterConfig
    custom: dict[str, str]

    def get(self, name: str, default: str = "") -> str:
        """
        安全读取自定义配置。

        适合读取不方便点语法的名字：

            config.get("MY-TOKEN")
            config.get("abc.def")
            config.get("1name")
        """

        return self.custom.get(name, default)

    def __getattr__(self, name: str) -> str:
        """
        让自定义配置可以用 config.xxx 直接读取。

        例如：

            zdy1=hello
            print(config.zdy1)
        """

        if name in self.custom:
            return self.custom[name]

        raise AttributeError(f"配置项不存在：config.{name}")


def load_config() -> AppConfig:
    """读取 .env，并实例化项目配置。"""

    raw = read_env_file()
    env = Env(raw)

    # 项目基础配置。
    project = ProjectConfig(
        name=env.get("APP_NAME", "xiuxianserver"),
        debug=env.get_bool("APP_DEBUG", False),
        timezone=env.get("APP_TIMEZONE", "Asia/Shanghai"),
    )

    # 日志配置默认写在这里，需要变化时再放到 .env 覆盖。
    log_dir = env.get_path("LOG_DIR", BASE_DIR / "launch" / "log")

    log = LogConfig(
        level=env.get("LOG_LEVEL", "INFO").upper(),
        color=env.get("LOG_COLOR", "auto").lower(),
        dir=log_dir,
        file=env.get_path("LOG_FILE", log_dir / "runserver.log"),
        rotation=env.get("LOG_ROTATION", "12:00"),
        retention=env.get("LOG_RETENTION", "14 days"),
        compression=env.get("LOG_COMPRESSION", "zip"),
    )

    # Router 配置默认写在这里，.env 覆盖时必须写成列表。
    router = RouterConfig(
        module_groups=env.get_list("APP_MODULE_GROUPS", []),
        modules=env.get_list("APP_MODULES", []),
        router_folders=env.get_list("APP_ROUTER_FOLDERS", []),
        router_groups=env.get_list("APP_ROUTER_GROUPS", []),
        router_child_folders=env.get_list("APP_ROUTER_CHILD_FOLDERS", []),
    )

    # 未被系统识别的键都作为自定义配置。
    custom = {key: value for key, value in raw.items() if key not in SYSTEM_ENV_KEYS}

    return AppConfig(
        base_dir=BASE_DIR,
        env_file=ENV_FILE,
        raw=raw,
        project=project,
        log=log,
        router=router,
        custom=custom,
    )


# 已经实例化好的项目配置对象，供其他模块直接读取。
config = load_config()
