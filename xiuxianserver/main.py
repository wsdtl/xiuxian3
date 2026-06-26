import uvicorn
from fastapi import FastAPI

from launch import config, lifespan, LOGGING_CONFIG, FastAPIAllowed, FastAPIIncludeRouter


def create_app():
    """创建 FastAPI 应用。

    uvicorn 使用 factory 模式调用这个函数，避免 reload 父进程提前创建 app。
    HTTP 路由也在这里注册，这样 /docs 生成时能看到完整接口。
    """

    app = FastAPI(
        title=config.project.name,
        debug=config.project.debug,
        lifespan=lifespan,
    )

    FastAPIAllowed(app)
    FastAPIIncludeRouter(app)

    return app


def uvicorn_ssl_kwargs() -> dict:
    """配置证书路径后返回 uvicorn SSL 参数。"""

    if not config.server.ssl_certfile or not config.server.ssl_keyfile:
        return {}

    return {
        "ssl_certfile": str(config.server.ssl_certfile),
        "ssl_keyfile": str(config.server.ssl_keyfile),
    }


if __name__ == "__main__":
    uvicorn.run(
        app="main:create_app",
        factory=True,
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
        log_config=LOGGING_CONFIG,
        **uvicorn_ssl_kwargs(),
    )
