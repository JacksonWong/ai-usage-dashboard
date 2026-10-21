"""阿里云 OpenAPI ACS3-HMAC-SHA256 签名。

规范来源：
- https://help.aliyun.com/zh/sdk/product-overview/v3-request-structure-and-signature
- https://help.aliyun.com/zh/model-studio/roa-style-request-body-signature-mechanism
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from urllib.parse import quote

SIGNATURE_ALGORITHM = "ACS3-HMAC-SHA256"
EMPTY_PAYLOAD_SHA256 = hashlib.sha256(b"").hexdigest()
_UNRESERVED = "-_.~"


def percent_encode(value: object) -> str:
    """RFC 3986 编码：仅 A-Za-z0-9-._~ 不转义，空格转 %20。"""
    return quote(str(value), safe=_UNRESERVED, encoding="utf-8")


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hmac_sha256_hex(key: str, message: str) -> str:
    return hmac.new(key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def percent_encode_path(path: str) -> str:
    """按段编码路径，保留分隔符 "/"。"""
    return "/".join(percent_encode(segment) for segment in path.split("/"))


def canonical_query_string(query: dict[str, object]) -> str:
    """按参数名、参数值升序排列后拼接。"""
    pairs: list[tuple[str, str]] = []
    for name, value in query.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                pairs.append((name, str(item)))
        else:
            pairs.append((name, str(value)))
    pairs.sort(key=lambda item: (item[0], item[1]))
    return "&".join(f"{percent_encode(name)}={percent_encode(value)}" for name, value in pairs)


def canonical_headers(headers: dict[str, str]) -> tuple[str, str]:
    """返回 (CanonicalHeaders, SignedHeaders)。

    只有 x-acs- 前缀的 header 以及 host、content-type 参与签名。
    """
    normalized = {
        name.lower(): str(value).strip()
        for name, value in headers.items()
        if name.lower().startswith("x-acs-") or name.lower() in ("host", "content-type")
    }
    names = sorted(normalized)
    canonical = "".join(f"{name}:{normalized[name]}\n" for name in names)
    return canonical, ";".join(names)


@dataclass(frozen=True)
class SignedRequest:
    url: str
    method: str
    headers: dict[str, str]
    body: str


def sign_request(
    *,
    method: str,
    url: str,
    query: dict[str, object] | None = None,
    body: str = "",
    action: str,
    version: str,
    access_key_id: str,
    access_key_secret: str,
    security_token: str = "",
    extra_headers: dict[str, str] | None = None,
    now: _dt.datetime | None = None,
    nonce: str | None = None,
) -> SignedRequest:
    """生成带 Authorization 的请求。

    路径风格（Model Studio）传入 url 的真实 path；RPC 风格（BSS）传 path="/"。
    """
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    host = parts.netloc
    path = parts.path or "/"
    query = query or {}

    moment = now or _dt.datetime.now(_dt.timezone.utc)
    date_header = moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    headers = {
        "host": host,
        "x-acs-action": action,
        "x-acs-version": version,
        "x-acs-date": date_header,
        "x-acs-signature-nonce": nonce or secrets.token_hex(16),
        "content-type": "application/json",
    }
    if security_token:
        headers["x-acs-security-token"] = security_token
    if extra_headers:
        headers.update(extra_headers)

    canonical_head, signed_headers = canonical_headers(headers)
    payload_hash = _sha256_hex(body) if body else EMPTY_PAYLOAD_SHA256
    canonical_request = "\n".join(
        [
            method.upper(),
            percent_encode_path(path),
            canonical_query_string(query),
            canonical_head,
            signed_headers,
            payload_hash,
        ]
    )
    string_to_sign = f"{SIGNATURE_ALGORITHM}\n{_sha256_hex(canonical_request)}"
    signature = _hmac_sha256_hex(access_key_secret, string_to_sign)
    headers["Authorization"] = (
        f"{SIGNATURE_ALGORITHM} Credential={access_key_id},"
        f"SignedHeaders={signed_headers},Signature={signature}"
    )

    qs = canonical_query_string(query)
    full_url = f"{parts.scheme}://{host}{path}" + (f"?{qs}" if qs else "")
    return SignedRequest(url=full_url, method=method.upper(), headers=headers, body=body)
