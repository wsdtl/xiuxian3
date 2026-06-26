"""QQ OpenAPI 客户端。

本文件只封装主动调用 QQ 开放接口的细节，包括获取 app access token
和发送消息。驱动器的 webhook 接收、事件排队和命令派发不放在这里。
"""

from base64 import b64encode
import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict

from launch.config import config
from launch.log import C, logger


QQ_TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
QQ_OPEN_API_BASE = "https://sandbox.api.sgroup.qq.com"


class QqOpenApiClient:
    """QQ 驱动器内部使用的开放接口客户端。

    这个类只负责主动调用 QQ OpenAPI：获取 app access token、发送 C2C
    消息、发送群消息。事件接收、命令匹配和业务调度都在 handler.py，
    不在这里混入。
    """

    def __init__(self) -> None:
        self.api_base = QQ_OPEN_API_BASE.rstrip("/")
        self.app_id = config.get("QQ_BOT_APP_ID", "").strip()
        self.client_secret = config.get("QQ_BOT_SECRET", "").strip()
        self._access_token = ""
        self._access_token_expires_at = 0.0

    def send_c2c_message(
        self,
        openid: str,
        content: str,
        message_id: str,
        event_id: str = "",
    ) -> dict:
        """回复 C2C 私聊消息。"""

        return self.send_c2c_payload(
            openid,
            {
                "content": content,
                "msg_type": 0,
            },
            message_id,
            event_id,
        )

    def send_c2c_payload(
        self,
        openid: str,
        payload: dict,
        message_id: str,
        event_id: str = "",
    ) -> dict:
        """按 QQ OpenAPI 消息载荷回复 C2C 私聊消息。"""

        return self._post_openapi(
            f"/v2/users/{openid}/messages",
            self._reply_payload(payload, message_id, event_id),
        )

    def ack_interaction(self, interaction_id: str, code: int = 0) -> dict:
        """确认 QQ 按钮回调，避免客户端点击后一直等待。"""

        value = str(interaction_id or "").strip()
        if not value:
            return {}
        return self._put_openapi(
            f"/interactions/{value}",
            {"code": int(code)},
            log_title="QQ 按钮回调已确认",
        )

    def upload_c2c_image(self, openid: str, image_bytes: bytes) -> str:
        """上传 C2C 私聊图片，返回发消息接口可使用的 file_info。"""

        return self._upload_image_file_info(f"/v2/users/{openid}/files", image_bytes)

    def send_group_message(
        self,
        group_openid: str,
        content: str,
        message_id: str,
        event_id: str = "",
    ) -> dict:
        """回复群消息。

        群消息接口需要 group_openid 作为目标；event_id 可用于开放平台
        的事件关联，传入为空时只按 message_id 回复。
        """

        return self.send_group_payload(
            group_openid,
            {
                "content": content,
                "msg_type": 0,
            },
            message_id,
            event_id,
        )

    def send_group_payload(
        self,
        group_openid: str,
        payload: dict,
        message_id: str,
        event_id: str = "",
    ) -> dict:
        """按 QQ OpenAPI 消息载荷回复群消息。"""

        return self._post_openapi(
            f"/v2/groups/{group_openid}/messages",
            self._reply_payload(payload, message_id, event_id),
        )

    def upload_group_image(self, group_openid: str, image_bytes: bytes) -> str:
        """上传群聊图片，返回发消息接口可使用的 file_info。"""

        return self._upload_image_file_info(f"/v2/groups/{group_openid}/files", image_bytes)

    @staticmethod
    def _reply_payload(payload: dict, message_id: str, event_id: str = "") -> Dict[str, Any]:
        """补齐回复消息必须携带的 msg_id 和可选 event_id。"""

        result: Dict[str, Any] = dict(payload)
        if message_id:
            result["msg_id"] = message_id
        if event_id:
            result["event_id"] = event_id
        return result

    def _upload_image_file_info(self, path: str, image_bytes: bytes) -> str:
        """把本地图片二进制上传成 QQ 富媒体 file_info。"""

        if not image_bytes:
            raise ValueError("QQ 图片内容为空")

        result = self._post_openapi(
            path,
            {
                "file_type": 1,
                "file_data": b64encode(image_bytes).decode("ascii"),
                "srv_send_msg": False,
            },
            log_title="QQ 图片上传成功",
        )
        file_info = str(result.get("file_info") or "").strip()
        if not file_info:
            raise RuntimeError(f"QQ 图片上传未返回 file_info：{json.dumps(result, ensure_ascii=False)}")
        return file_info

    def _post_openapi(self, path: str, payload: dict, log_title: str = "QQ 发消息成功") -> dict:
        """调用 QQ OpenAPI，遇到 token 失效时刷新后重试一次。"""

        return self._request_openapi("POST", path, payload, log_title)

    def _put_openapi(self, path: str, payload: dict, log_title: str) -> dict:
        """调用 QQ OpenAPI PUT 接口，遇到 token 失效时刷新后重试一次。"""

        return self._request_openapi("PUT", path, payload, log_title)

    def _request_openapi(self, method: str, path: str, payload: dict, log_title: str) -> dict:
        """调用 QQ OpenAPI，遇到 token 失效时刷新后重试一次。"""

        try:
            return self._request_openapi_once(method, path, payload, log_title)
        except QqOpenApiError as exc:
            if exc.status_code != 401:
                raise
            self._access_token = ""
            self._access_token_expires_at = 0.0
            return self._request_openapi_once(method, path, payload, log_title)

    def _request_openapi_once(self, method: str, path: str, payload: dict, log_title: str) -> dict:
        """执行一次 OpenAPI 请求，不做业务层重试。"""

        token = self.get_access_token()
        request = urllib.request.Request(
            self.api_base + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"QQBot {token}",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise QqOpenApiError(exc.code, detail) from exc

        result = json.loads(raw) if raw else {}
        if isinstance(result, dict) and int(result.get("code") or 0) != 0:
            raise RuntimeError(f"QQ OpenAPI 返回异常：{json.dumps(result, ensure_ascii=False)}")

        logger.opt(colors=True).debug(
            C.join(
                C.ok(log_title),
                *self._openapi_result_log_parts(path, payload, result),
            )
        )
        return result

    def get_access_token(self) -> str:
        """获取并缓存 QQ app access token。"""

        if self._access_token and time.time() < self._access_token_expires_at - 60:
            return self._access_token

        if not self.app_id or not self.client_secret:
            raise RuntimeError("QQ_BOT_APP_ID 或 QQ_BOT_SECRET 未配置")

        payload = {
            "appId": self.app_id,
            "clientSecret": self.client_secret,
        }
        request = urllib.request.Request(
            QQ_TOKEN_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"获取 QQ access_token 失败：{exc.code} {detail}") from exc

        data = json.loads(raw)
        token = str(data.get("access_token") or "").strip()
        expires_in = int(data.get("expires_in") or 0)
        if not token:
            raise RuntimeError(f"获取 QQ access_token 返回异常：{raw}")

        self._access_token = token
        self._access_token_expires_at = time.time() + expires_in
        return token

    @staticmethod
    def _openapi_result_log_parts(path: str, payload: dict, result: object) -> list[str]:
        """生成 OpenAPI 成功日志摘要，避免把返回整包刷进日志。"""

        result_data = result if isinstance(result, dict) else {}
        if str(path).rstrip("/").endswith("/files"):
            return [
                *QqOpenApiClient._path_log_parts(path),
                C.kv("file_type", payload.get("file_type") or "-"),
                C.kv("file", QqOpenApiClient._short_id(result_data.get("file_uuid"))),
                C.kv("ttl", result_data.get("ttl", "-")),
            ]

        return [
            *QqOpenApiClient._path_log_parts(path),
            C.kv("msg_type", payload.get("msg_type") or "-"),
            C.kv("msg", QqOpenApiClient._short_id(payload.get("msg_id"))),
            C.kv(
                "result",
                QqOpenApiClient._short_id(
                    result_data.get("id")
                    or result_data.get("message_id")
                    or result_data.get("msg_id")
                ),
            ),
        ]

    @staticmethod
    def _path_log_parts(path: str) -> list[str]:
        """从 OpenAPI path 中提取发送目标类型和目标 ID。"""

        parts = [part for part in str(path).strip("/").split("/") if part]
        if len(parts) >= 4 and parts[-1] in {"messages", "files"}:
            target_type = "私聊" if parts[-3] == "users" else "群聊"
            return [
                C.kv("target", target_type),
                C.kv("openid", QqOpenApiClient._short_id(parts[-2])),
            ]
        return [C.kv("path", path)]

    @staticmethod
    def _short_id(value: object, head: int = 8, tail: int = 6) -> str:
        """缩短开放平台长 ID，保留首尾方便排查。"""

        text = str(value or "").strip()
        if not text:
            return "-"
        if len(text) <= head + tail + 3:
            return text
        return f"{text[:head]}...{text[-tail:]}"


class QqOpenApiError(RuntimeError):
    """QQ OpenAPI HTTP 层异常。"""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"QQ 发消息失败：{status_code} {detail}")


client = QqOpenApiClient()
