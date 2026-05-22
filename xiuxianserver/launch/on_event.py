from typing import Callable, List


class OnEvent:
    """启动和关闭回调注册器。"""

    connect_list: List[Callable] = []
    disconnect_list: List[Callable] = []

    @staticmethod
    def connect() -> Callable:
        """注册服务启动回调。"""

        def wrapper(func: Callable):
            OnEvent.connect_list.append(func)
            return func

        return wrapper

    @staticmethod
    def disconnect() -> Callable:
        """注册服务关闭回调。"""

        def wrapper(func: Callable):
            OnEvent.disconnect_list.append(func)
            return func

        return wrapper
