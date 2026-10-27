from __future__ import annotations

import asyncio
from typing import Any

import httpx

ALLOWED_HOST_PATTERNS = (
    "modelstudio.",  # modelstudio.<region>.aliyuncs.com
    "business.",  # business[.<region>].aliyuncs.com
)
ALLOWED_HOSTS = {
    "www.minimax.cn",
    "api.minimax.chat",
    "api.deepseek.com",
}


class ApiError(RuntimeError):
    """外部接口调用失败。"""

    def __init__(self, message: str, *, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def _assert_allowed(url: str) -> None:
    host = httpx.URL(url).host
    if host in ALLOWED_HOSTS:
        return
    if host.endswith(".aliyuncs.com") and host.startswith(ALLOWED_HOST_PATTERNS):
        return
    raise ApiError(f"拒绝访问非白名单域名：{host}")


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip()
        return text[:300] or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        denied = payload.get("AccessDeniedDetail")
        if isinstance(denied, dict) and denied.get("AuthAction"):
            return f"无权限：缺少 {denied['AuthAction']} 授权（NoPermission）"
        for key in ("Message", "message", "status_msg", "Message_", "Code", "code"):
            value = payload.get(key)
            if value:
                code = payload.get("Code") or payload.get("code")
                return f"{value}" + (f"（{code}）" if code and code != value else "")
        base_resp = payload.get("base_resp")
        if isinstance(base_resp, dict) and base_resp.get("status_msg"):
            return str(base_resp["status_msg"])
        error = payload.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
    return str(payload)[:300]


async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    content: bytes | None = None,
    params: dict[str, Any] | None = None,
    retries: int = 2,
) -> dict[str, Any]:
    _assert_allowed(url)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await client.request(
                method, url, headers=headers, content=content, params=params
            )
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            raise ApiError(f"网络请求失败：{exc}") from exc

        if response.status_code >= 400:
            message = _error_message(response)
            if response.status_code >= 500 and attempt < retries:
                await asyncio.sleep(0.4 * (attempt + 1))
                continue
            raise ApiError(
                f"HTTP {response.status_code}：{message}",
                status=response.status_code,
                payload=_safe_json(response),
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError("响应不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise ApiError("响应 JSON 结构异常")
        return payload
    raise ApiError(f"网络请求失败：{last_error}")


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:500]
