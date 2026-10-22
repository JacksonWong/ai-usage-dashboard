from __future__ import annotations

import datetime as dt
import os

import pytest

from custom_components.llm_balance.core.signing import (
    canonical_headers,
    canonical_query_string,
    percent_encode,
    percent_encode_path,
    sign_request,
)

NOW = dt.datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
NONCE = "3e3b2a9f0c7d4f8e9a1b2c3d4e5f6a7b"
AK = "LTAI5tExampleAccessKeyId"
SK = "exampleAccessKeySecret"


def test_percent_encode_follows_rfc3986():
    assert percent_encode("abcXYZ019") == "abcXYZ019"
    assert percent_encode("-_.~") == "-_.~"
    assert percent_encode("a b") == "a%20b"
    assert percent_encode("a*b") == "a%2Ab"
    assert percent_encode("a+b") == "a%2Bb"
    assert percent_encode("a/b") == "a%2Fb"
    assert percent_encode("中") == "%E4%B8%AD"


def test_percent_encode_path_keeps_separator():
    assert percent_encode_path("/modelstudio/billing/overview") == (
        "/modelstudio/billing/overview"
    )
    assert percent_encode_path("/a b/c") == "/a%20b/c"


def test_canonical_query_string_sorts_and_encodes():
    query = {"billMonth": "2026-08", "groupBy": '[{"code":"MAAS_TYPE"}]', "topNum": 20}
    encoded = canonical_query_string(query)
    assert encoded == (
        "billMonth=2026-08"
        "&groupBy=%5B%7B%22code%22%3A%22MAAS_TYPE%22%7D%5D"
        "&topNum=20"
    )


def test_canonical_query_string_skips_none():
    assert canonical_query_string({"a": "1", "b": None}) == "a=1"


def test_canonical_headers_filters_and_sorts():
    headers = {
        "host": "modelstudio.cn-beijing.aliyuncs.com",
        "x-acs-action": "GetBillingOverview",
        "x-acs-date": "2026-01-01T12:00:00Z",
        "content-type": "application/json",
        "user-agent": "should-not-be-signed",
        "Accept": "*/*",
    }
    canonical, signed = canonical_headers(headers)
    assert signed == (
        "content-type;host;x-acs-action;x-acs-date"
    )
    assert canonical == (
        "content-type:application/json\n"
        "host:modelstudio.cn-beijing.aliyuncs.com\n"
        "x-acs-action:GetBillingOverview\n"
        "x-acs-date:2026-01-01T12:00:00Z\n"
    )


def test_sign_request_is_deterministic():
    kwargs = dict(
        method="GET",
        url="https://modelstudio.cn-beijing.aliyuncs.com/modelstudio/billing/overview",
        query={"billMonth": "2026-08", "groupBy": '[{"code":"MAAS_TYPE"}]'},
        action="GetBillingOverview",
        version="2026-02-10",
        access_key_id=AK,
        access_key_secret=SK,
        now=NOW,
        nonce=NONCE,
    )
    first = sign_request(**kwargs)
    second = sign_request(**kwargs)
    assert first.headers["Authorization"] == second.headers["Authorization"]
    assert first.headers["Authorization"].startswith(
        "ACS3-HMAC-SHA256 Credential=LTAI5tExampleAccessKeyId,SignedHeaders="
    )
    assert "Signature=" in first.headers["Authorization"]
    assert "host" in first.headers["Authorization"]
    assert first.url.endswith(
        "billMonth=2026-08&groupBy=%5B%7B%22code%22%3A%22MAAS_TYPE%22%7D%5D"
    )


def test_sign_request_includes_security_token_when_present():
    signed = sign_request(
        method="GET",
        url="https://modelstudio.cn-beijing.aliyuncs.com/tokenplan/subscription/stats",
        action="GetSubscriptionStats",
        version="2026-02-10",
        access_key_id=AK,
        access_key_secret=SK,
        security_token="sts-token",
        now=NOW,
        nonce=NONCE,
    )
    assert signed.headers["x-acs-security-token"] == "sts-token"
    assert "x-acs-security-token" in signed.headers["Authorization"]


@pytest.mark.skipif(
    os.environ.get("AIDASH_NETWORK_TESTS") != "1",
    reason="需要外网；设置 AIDASH_NETWORK_TESTS=1 开启",
)
@pytest.mark.parametrize(
    "url,action,version,path",
    [
        (
            "https://modelstudio.cn-beijing.aliyuncs.com/tokenplan/subscription/stats",
            "GetSubscriptionStats",
            "2026-02-10",
            "/tokenplan/subscription/stats",
        ),
        (
            "https://modelstudio.cn-beijing.aliyuncs.com/modelstudio/billing/overview",
            "GetBillingOverview",
            "2026-02-10",
            "/modelstudio/billing/overview",
        ),
        (
            "https://business.aliyuncs.com/",
            "QueryAccountBalance",
            "2017-12-14",
            "/",
        ),
    ],
)
def test_gateway_accepts_signature_shape(url, action, version, path):
    """签名格式正确时，网关应报 AccessKey 无效而不是缺少参数。"""
    import httpx

    signed = sign_request(
        method="GET",
        url=url,
        query={"Action": action, "Version": version} if path == "/" else {},
        action=action,
        version=version,
        access_key_id="TESTACCESSKEYID01",
        access_key_secret="testsecret",
    )
    headers = {k: v for k, v in signed.headers.items() if k != "host"}
    response = httpx.get(signed.url, headers=headers, timeout=20)
    body = response.text
    assert "MissingAccessKeyId" not in body
    assert "MissingSignatureNonce" not in body
    assert "IncompleteSignature" not in body
    assert "InvalidAccessKeyId" in body
