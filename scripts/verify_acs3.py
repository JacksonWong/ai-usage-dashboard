#!/usr/bin/env python3
"""用真实 AccessKey 验证 ACS3-HMAC-SHA256 签名是否被阿里云网关接受。

用法：
    export ALIBABA_CLOUD_ACCESS_KEY_ID=...
    export ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
    python scripts/verify_acs3.py

也可以只验签（不调真实接口，用假 AK 看网关是否报 AccessKey 无效）：
    python scripts/verify_acs3.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.signing import sign_request  # noqa: E402

CASES = [
    {
        "name": "百炼 · 订阅 Token Plan 额度统计",
        "url": "https://modelstudio.cn-beijing.aliyuncs.com/tokenplan/subscription/stats",
        "action": "GetSubscriptionStats",
        "version": "2026-02-10",
        "query": {},
    },
    {
        "name": "百炼 · 按量付费账单概览",
        "url": "https://modelstudio.cn-beijing.aliyuncs.com/modelstudio/billing/overview",
        "action": "GetBillingOverview",
        "version": "2026-02-10",
        "query": {
            "billMonth": "2026-08",
            "groupBy": json.dumps([{"code": "MAAS_TYPE"}], ensure_ascii=False),
            "topNum": 20,
            "zeroFilter": "true",
            "locale": "zh-CN",
        },
    },
    {
        "name": "阿里云 · 账户可用额度",
        "url": "https://business.aliyuncs.com/",
        "action": "QueryAccountBalance",
        "version": "2017-12-14",
        "query": {"Action": "QueryAccountBalance", "Version": "2017-12-14", "Format": "json"},
    },
]


def run_case(
    case: dict, access_key_id: str, access_key_secret: str, dry_run: bool
) -> tuple[bool, str]:
    signed = sign_request(
        method="GET",
        url=case["url"],
        query=case["query"],
        action=case["action"],
        version=case["version"],
        access_key_id=access_key_id,
        access_key_secret=access_key_secret,
    )
    headers = {k: v for k, v in signed.headers.items() if k != "host"}
    try:
        response = httpx.get(signed.url, headers=headers, timeout=20)
    except httpx.HTTPError as exc:
        return False, f"请求失败：{exc}"

    body = response.text
    if response.status_code == 200:
        return True, body[:400]

    for marker in (
        "MissingAccessKeyId",
        "MissingSignatureNonce",
        "IncompleteSignature",
        "SignatureDoesNotMatch",
    ):
        if marker in body:
            return False, f"签名格式不被接受：{marker}\n{body[:300]}"

    if "InvalidAccessKeyId" in body:
        if dry_run:
            return True, "签名格式正确（网关已解析签名，仅 AccessKey 无效）"
        return False, f"AccessKey 无效：{body[:240]}"

    return False, f"HTTP {response.status_code}\n{body[:300]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 ACS3-HMAC-SHA256 签名")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="使用假 AccessKey，只验证网关是否接受签名格式",
    )
    args = parser.parse_args()

    if args.dry_run:
        access_key_id = "TESTACCESSKEYID01"
        access_key_secret = "testsecret"
        print("== 干跑模式：使用假 AccessKey，网关应报 InvalidAccessKeyId ==")
    else:
        access_key_id = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
        access_key_secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
        if not access_key_id or not access_key_secret:
            print(
                "请先设置环境变量 ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET，"
                "或使用 --dry-run。",
                file=sys.stderr,
            )
            return 2

    failures = 0
    for case in CASES:
        ok, detail = run_case(case, access_key_id, access_key_secret, args.dry_run)
        mark = "通过" if ok else "失败"
        print(f"[{mark}] {case['name']}")
        print(f"       {detail}")
        if not ok:
            failures += 1

    if failures:
        print(f"\n{failures} 个用例未通过")
        return 1
    print("\n全部用例通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
