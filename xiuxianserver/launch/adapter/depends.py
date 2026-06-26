from __future__ import annotations

import inspect
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Tuple


_current_message_context: ContextVar[dict[str, Any]] = ContextVar(
    "adapter_current_message_context",
    default={},
)


@dataclass(frozen=True)
class Depends:
    """声明一个命令参数由依赖函数计算得到。"""

    dependency: Callable
    use_cache: bool = True


class DependencyContext:
    """单条消息内的依赖解析上下文。"""

    def __init__(self, values: Mapping[str, Any]) -> None:
        self.values = dict(values)
        self.cache: Dict[Callable, Any] = {}


async def call_with_dependencies(func: Callable, context: Mapping[str, Any]) -> Any:
    """按函数签名解析参数，支持普通上下文字段和 Depends。"""

    dependency_context = DependencyContext(context)
    token = _current_message_context.set(dict(context))
    try:
        kwargs = await resolve_kwargs(func, dependency_context)
        result = func(**kwargs)
        if inspect.isawaitable(result):
            return await result
        return result
    finally:
        _current_message_context.reset(token)


def current_context_value(name: str, default: Any = None) -> Any:
    """读取当前消息上下文中的字段。"""

    return _current_message_context.get().get(name, default)


async def resolve_kwargs(func: Callable, dependency_context: DependencyContext) -> dict[str, Any]:
    signature = inspect.signature(func)
    kwargs: dict[str, Any] = {}

    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            kwargs.update(dependency_context.values)
            continue

        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue

        default = parameter.default
        if isinstance(default, Depends):
            kwargs[name] = await resolve_dependency(default, dependency_context)
            continue

        if name in dependency_context.values:
            kwargs[name] = dependency_context.values[name]
            continue

        if default is inspect.Parameter.empty:
            raise TypeError(f"缺少命令参数：{name}")

    return kwargs


async def resolve_dependency(
    depends: Depends,
    dependency_context: DependencyContext,
    stack: Tuple[Callable, ...] = (),
) -> Any:
    dependency = depends.dependency
    if dependency in stack:
        raise RuntimeError(f"循环依赖：{dependency!r}")
    if depends.use_cache and dependency in dependency_context.cache:
        return dependency_context.cache[dependency]

    kwargs = await resolve_dependency_kwargs(
        dependency,
        dependency_context,
        stack + (dependency,),
    )
    result = dependency(**kwargs)
    if inspect.isawaitable(result):
        result = await result

    if depends.use_cache:
        dependency_context.cache[dependency] = result
    return result


async def resolve_dependency_kwargs(
    dependency: Callable,
    dependency_context: DependencyContext,
    stack: Tuple[Callable, ...] = (),
) -> dict[str, Any]:
    signature = inspect.signature(dependency)
    kwargs: dict[str, Any] = {}

    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            kwargs.update(dependency_context.values)
            continue

        if parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue

        default = parameter.default
        if isinstance(default, Depends):
            kwargs[name] = await resolve_dependency(default, dependency_context, stack)
            continue

        if name in dependency_context.values:
            kwargs[name] = dependency_context.values[name]
            continue

        if default is inspect.Parameter.empty:
            raise TypeError(f"缺少依赖参数：{dependency.__name__}.{name}")

    return kwargs
