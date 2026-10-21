from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta
from typing import Any

import httpx

from ..db import Account
from ..format import format_money, format_number, format_percent, format_timestamp, now_iso, to_float
from ..http_client import ApiError, request_json
from ..signing import sign_request
from ..snapshot import (
    BreakdownItem,
    Donut,
    DonutItem,
    Metric,
    SeriesPoint,
    Snapshot,
    Stacked,
    StackedPart,
    StackedPoint,
)
from .base import Provider

MODEL_STUDIO_VERSION = "2026-02-10"
BSS_VERSION = "2017-12-14"

PAYG_DIMENSIONS = {
    "BASE_MODEL": "模型",
    "API_KEY_ID": "API Key",
}

FEE_TYPE_LABELS = {
    "billing": "账单费用",
    "subscription": "订阅购买费用",
}
MAAS_TYPE_LABELS = {
    "inference": "模型调用",
    "training": "模型训练",
    "model_units": "模型单元",
    "capacity_reserved": "容量预留",
}
SEAT_TYPE_LABELS = {"standard": "标准席位", "pro": "高级席位", "max": "尊享席位"}


class AliyunProvider(Provider):
    platform = "aliyun"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        account: Account,
        settings: dict[str, Any],
    ) -> Snapshot:
        if account.mode == "token_plan":
            return await self._fetch_token_plan(client, account, settings)
        return await self._fetch_payg(client, account, settings)

    # ------------------------------------------------------------------ 公共

    def _credentials(self, account: Account) -> tuple[str, str, str, str]:
        creds = account.credentials
        ak = creds.get("access_key_id", "").strip()
        sk = creds.get("access_key_secret", "").strip()
        token = creds.get("security_token", "").strip()
        region = creds.get("region_id", "").strip() or "cn-beijing"
        return ak, sk, token, region

    async def _call(
        self,
        client: httpx.AsyncClient,
        account: Account,
        *,
        host: str,
        path: str,
        action: str,
        version: str,
        query: dict[str, Any] | None = None,
        method: str = "GET",
        body: str = "",
    ) -> dict[str, Any]:
        ak, sk, token, _ = self._credentials(account)
        if not ak or not sk:
            raise ApiError("未配置 AccessKey ID / AccessKey Secret")
        url = f"https://{host}{path}"
        signed = sign_request(
            method=method,
            url=url,
            query=query or {},
            body=body,
            action=action,
            version=version,
            access_key_id=ak,
            access_key_secret=sk,
            security_token=token,
        )
        headers = {k: v for k, v in signed.headers.items() if k != "host"}
        return await request_json(
            client,
            signed.method,
            signed.url,
            headers=headers,
            content=signed.body.encode("utf-8") if signed.body else None,
        )

    def _bill_month(self, account: Account, settings: dict[str, Any]) -> str:
        month = account.options.get("bill_month") or settings.get("bill_month") or ""
        if isinstance(month, str) and len(month) == 7 and month[4] == "-":
            return month
        return date.today().strftime("%Y-%m")

    def _locale(self, account: Account, settings: dict[str, Any]) -> str:
        return account.options.get("locale") or settings.get("locale") or "zh-CN"

    # ------------------------------------------------------------- 按量付费

    async def _call_variants(
        self,
        client: httpx.AsyncClient,
        account: Account,
        variants: list[dict[str, Any]],
        **call_kwargs: Any,
    ) -> dict[str, Any]:
        """按顺序尝试不同的嵌套参数序列化方式，400 时换下一种。"""
        last_error: ApiError | None = None
        for query in variants:
            try:
                return await self._call(client, account, query=query, **call_kwargs)
            except ApiError as exc:
                if exc.status != 400:
                    raise
                last_error = exc
        raise last_error or ApiError("请求失败")

    async def _fetch_payg(
        self,
        client: httpx.AsyncClient,
        account: Account,
        settings: dict[str, Any],
    ) -> Snapshot:
        started = datetime.now()
        _, _, _, region = self._credentials(account)
        bill_month = self._bill_month(account, settings)
        locale = self._locale(account, settings)
        host = f"modelstudio.{region}.aliyuncs.com"

        dimension = str(account.options.get("dimension") or "BASE_MODEL")
        if dimension not in PAYG_DIMENSIONS:
            dimension = "BASE_MODEL"
        dimension_label = PAYG_DIMENSIONS[dimension]

        common = {
            "regionId": region,
            "locale": locale,
            "topNum": 20,
            "zeroFilter": "true",
        }
        # 只统计「账单费用」（后付费），与百炼控制台费用概览里账单趋势的口径一致
        billing_filter = {
            "dimensions": [
                {"code": "FEE_TYPE", "values": ["billing"], "selectType": "IN"}
            ]
        }
        group_by = json.dumps([{"code": dimension}], ensure_ascii=False)

        def filter_variants() -> list[dict[str, Any]]:
            flat = {
                "filter.dimensions.1.code": "FEE_TYPE",
                "filter.dimensions.1.values.1": "billing",
                "filter.dimensions.1.selectType": "IN",
            }
            as_json = {"filter": json.dumps(billing_filter, ensure_ascii=False)}
            return [
                {**common, "billMonth": bill_month, "groupBy": group_by, **as_json},
                {**common, "billMonth": bill_month, "groupBy": group_by, **flat},
            ]

        year, month = int(bill_month[:4]), int(bill_month[5:7])
        start = date(year, month, 1)
        last_day = (date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)).day
        end = date(year, month, last_day)

        def trend_variants() -> list[dict[str, Any]]:
            base = {
                **common,
                "granularity": "DAY",
                "groupBy": group_by,
                "filter": json.dumps(billing_filter, ensure_ascii=False),
            }
            flat_filter = {
                "filter.dimensions.1.code": "FEE_TYPE",
                "filter.dimensions.1.values.1": "billing",
                "filter.dimensions.1.selectType": "IN",
            }
            as_json = {
                **base,
                "timePeriod": json.dumps(
                    {"start": start.isoformat(), "end": end.isoformat()}, ensure_ascii=False
                ),
            }
            flat = {
                **common,
                "granularity": "DAY",
                "groupBy": group_by,
                **flat_filter,
                "timePeriod.start": start.isoformat(),
                "timePeriod.end": end.isoformat(),
            }
            return [as_json, flat]

        tasks = {
            "overview": self._call_variants(
                client,
                account,
                filter_variants(),
                host=host,
                path="/modelstudio/billing/overview",
                action="GetBillingOverview",
                version=MODEL_STUDIO_VERSION,
            ),
            "trend": self._call_variants(
                client,
                account,
                trend_variants(),
                host=host,
                path="/modelstudio/billing/trend",
                action="GetBillingTrend",
                version=MODEL_STUDIO_VERSION,
            ),
            "balance": self._account_balance(client, account),
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        payload = dict(zip(tasks.keys(), results))

        errors: dict[str, str] = {}
        data: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, BaseException):
                errors[key] = str(value)
            else:
                data[key] = value

        if "overview" in errors and "trend" in errors:
            return self._error_snapshot(account, started, errors["overview"])

        snapshot = Snapshot(
            account_id=account.id,
            platform=self.platform,
            mode=account.mode,
            label=account.label,
            fetched_at=now_iso(),
        )
        snapshot.filters = {
            "bill_month": {"label": "账期", "type": "month", "value": bill_month},
            "dimension": {
                "label": "维度",
                "type": "segmented",
                "value": dimension,
                "options": [
                    {"value": key, "label": value} for key, value in PAYG_DIMENSIONS.items()
                ],
            },
        }

        overview_data = (data.get("overview") or {}).get("data") or {}
        currency = overview_data.get("currency") or "CNY"
        total = to_float(overview_data.get("totalAmount"))
        tax = to_float(overview_data.get("taxAmount"))
        groups = overview_data.get("groups") or []

        metrics: list[Metric] = []
        if total is not None:
            metrics.append(
                Metric(
                    key="month_billing",
                    label=f"{bill_month} 账单费用",
                    value=total,
                    display=format_money(total, currency),
                    unit=currency,
                    hint="仅统计后付费账单费用（不含订阅购买费用）",
                )
            )
        if tax is not None:
            metrics.append(
                Metric(
                    key="month_tax",
                    label="税费合计",
                    value=tax,
                    display=format_money(tax, currency),
                    unit=currency,
                )
            )

        balance = data.get("balance")
        if isinstance(balance, dict):
            balance_data = balance.get("Data") or {}
            available = to_float(balance_data.get("AvailableAmount"))
            cash = to_float(balance_data.get("AvailableCashAmount"))
            credit = to_float(balance_data.get("CreditAmount"))
            balance_currency = balance_data.get("Currency") or "CNY"
            if available is not None:
                metrics.insert(
                    0,
                    Metric(
                        key="available_amount",
                        label="账户可用额度",
                        value=available,
                        display=format_money(available, balance_currency),
                        unit=balance_currency,
                        hint="现金余额 + 信控额度 - 未结清金额（阿里云账户级）",
                        level="ok" if available > 0 else "danger",
                    ),
                )
            if cash is not None:
                metrics.insert(
                    1,
                    Metric(
                        key="cash_balance",
                        label="现金余额",
                        value=cash,
                        display=format_money(cash, balance_currency),
                        unit=balance_currency,
                    ),
                )
            if credit is not None and credit > 0:
                metrics.append(
                    Metric(
                        key="credit_amount",
                        label="信控额度",
                        value=credit,
                        display=format_money(credit, balance_currency),
                        unit=balance_currency,
                    )
                )
        elif "balance" in errors:
            snapshot.notes.append(
                f"账户余额不可用（{errors['balance']}）。可为 RAM 用户授予 bss:DescribeAcccount 权限后重试。"
            )

        snapshot.metrics = metrics

        # 环形图：账单费用按当前维度拆分
        donut_items = []
        for group in groups:
            amount = to_float(group.get("amount"))
            donut_items.append(
                DonutItem(
                    name=str(group.get("name") or group.get("key")),
                    value=amount or 0.0,
                    display=format_money(amount, currency),
                    percentage=to_float(group.get("percentage")),
                )
            )
        donut_total = total if total is not None else sum(item.value for item in donut_items)
        snapshot.donut = Donut(
            title=f"账单费用 · 按 {dimension_label}",
            total=donut_total,
            total_display=format_money(donut_total, currency),
            currency=currency,
            items=donut_items,
        )

        # 堆叠柱形图：按天 × 当前维度
        trend_data = (data.get("trend") or {}).get("data") or {}
        points: list[StackedPoint] = []
        category_totals: dict[str, float] = {}
        for entry in trend_data.get("resultByTime") or []:
            period = str(entry.get("period") or "")
            total_obj = entry.get("total") or {}
            amount = to_float(total_obj.get("amount"))
            parts = []
            for detail in entry.get("periodDetails") or []:
                part_amount = to_float(detail.get("amount")) or 0.0
                name = str(detail.get("name") or detail.get("key"))
                parts.append(
                    StackedPart(
                        name=name,
                        value=part_amount,
                        display=format_money(part_amount, currency),
                    )
                )
                category_totals[name] = category_totals.get(name, 0.0) + part_amount
            points.append(
                StackedPoint(
                    label=_format_period(period),
                    total=amount or 0.0,
                    total_display=format_money(amount, currency),
                    parts=parts,
                )
            )
        categories = [
            name for name, _ in sorted(category_totals.items(), key=lambda kv: -kv[1])
        ]
        snapshot.stacked = Stacked(
            title=f"账单趋势 · 按天 × {dimension_label}",
            currency=currency,
            categories=categories,
            points=points,
        )

        for key, message in errors.items():
            snapshot.notes.append(f"{key} 查询失败：{message}")

        snapshot.raw = {
            "billing_overview": data.get("overview"),
            "billing_trend": data.get("trend"),
            "account_balance": data.get("balance"),
            "errors": errors,
        }
        snapshot.latency_ms = int((datetime.now() - started).total_seconds() * 1000)
        return snapshot

    async def _account_balance(
        self, client: httpx.AsyncClient, account: Account
    ) -> dict[str, Any]:
        """阿里云账务中心 QueryAccountBalance（RPC 风格）。"""
        query = {
            "Action": "QueryAccountBalance",
            "Version": BSS_VERSION,
            "Format": "json",
        }
        return await self._call(
            client,
            account,
            host="business.aliyuncs.com",
            path="/",
            action="QueryAccountBalance",
            version=BSS_VERSION,
            query=query,
            method="POST",
        )

    # ------------------------------------------------------------ Token Plan

    async def _fetch_token_plan(
        self,
        client: httpx.AsyncClient,
        account: Account,
        settings: dict[str, Any],
    ) -> Snapshot:
        started = datetime.now()
        _, _, _, region = self._credentials(account)
        host = f"modelstudio.{region}.aliyuncs.com"

        tasks = {
            "stats": self._call(
                client,
                account,
                host=host,
                path="/tokenplan/subscription/stats",
                action="GetSubscriptionStats",
                version=MODEL_STUDIO_VERSION,
                query={},
            ),
            "seat_detail": self._call(
                client,
                account,
                host=host,
                path="/tokenplan/subscription/seat-detail",
                action="GetSubscriptionSeatDetails",
                version=MODEL_STUDIO_VERSION,
                query={"PageNo": 1, "PageSize": 50},
            ),
            "shared_packages": self._call(
                client,
                account,
                host=host,
                path="/tokenplan/subscription/shared-packages",
                action="ListSubscriptionSharedPackages",
                version=MODEL_STUDIO_VERSION,
                query={"PageNo": 1, "PageSize": 50},
            ),
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        payload = dict(zip(tasks.keys(), results))
        errors: dict[str, str] = {}
        data: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, BaseException):
                errors[key] = str(value)
            else:
                data[key] = value

        if "stats" in errors and "seat_detail" in errors:
            return self._error_snapshot(account, started, errors["stats"])

        snapshot = Snapshot(
            account_id=account.id,
            platform=self.platform,
            mode=account.mode,
            label=account.label,
            fetched_at=now_iso(),
        )

        stats_data = (data.get("stats") or {}).get("Data") or {}
        items = stats_data.get("Items") or []

        total_credits = 0.0
        remaining_credits = 0.0
        total_seats = 0
        assigned_seats = 0
        refresh_times: list[float] = []
        for item in items:
            total_credits += to_float(item.get("SeatCredits")) or 0.0
            remaining_credits += to_float(item.get("SeatRemainingCredits")) or 0.0
            total_seats += int(to_float(item.get("TotalSeats")) or 0)
            assigned_seats += int(to_float(item.get("AssignedSeats")) or 0)
            refresh = to_float(item.get("SeatRefreshTime"))
            if refresh:
                refresh_times.append(refresh)

        # 席位明细补充（stats 缺字段时以席位权益为准）
        seat_items = ((data.get("seat_detail") or {}).get("Data") or {}).get("Items") or []
        seat_total = 0.0
        seat_remaining = 0.0
        for seat in seat_items:
            for equity in seat.get("EquityList") or []:
                seat_total += to_float(equity.get("CycleTotalValue")) or 0.0
                seat_remaining += to_float(equity.get("CycleSurplusValue")) or 0.0

        if total_credits <= 0 and seat_total > 0:
            total_credits = seat_total
            remaining_credits = seat_remaining
        elif seat_remaining > remaining_credits:
            remaining_credits = seat_remaining

        used = max(total_credits - remaining_credits, 0.0)
        ratio = (used / total_credits) if total_credits > 0 else None

        metrics: list[Metric] = []
        if total_credits > 0:
            metrics.append(
                Metric(
                    key="remaining_credits",
                    label="剩余 Credits",
                    value=remaining_credits,
                    display=format_number(remaining_credits),
                    unit="credits",
                    total=total_credits,
                    progress=(remaining_credits / total_credits) if total_credits else None,
                    hint=f"本周期总额度 {format_number(total_credits)} Credits",
                    level="ok" if ratio is not None and ratio < 0.8 else ("warn" if ratio is not None and ratio < 0.95 else "danger"),
                )
            )
            metrics.append(
                Metric(
                    key="used_credits",
                    label="已用 Credits",
                    value=used,
                    display=format_number(used),
                    unit="credits",
                    total=total_credits,
                    progress=ratio,
                    hint=format_percent(ratio),
                    level="info",
                )
            )
        if total_seats:
            metrics.append(
                Metric(
                    key="seats",
                    label="席位（已分配 / 总量）",
                    value=float(assigned_seats),
                    display=f"{assigned_seats} / {total_seats}",
                    total=float(total_seats),
                    progress=assigned_seats / total_seats if total_seats else None,
                    unit="seats",
                )
            )
        end_time = stats_data.get("SubscriptionEndTime")
        if end_time:
            metrics.append(
                Metric(
                    key="subscription_end",
                    label="订阅到期",
                    value=None,
                    display=format_timestamp(end_time),
                    hint="订阅周期自购买日起算，按月刷新，不结转余量",
                )
            )
        if refresh_times:
            metrics.append(
                Metric(
                    key="seat_refresh",
                    label="下周期刷新时间",
                    value=None,
                    display=format_timestamp(max(refresh_times)),
                )
            )

        snapshot.metrics = metrics

        for item in items:
            seat_type = str(item.get("SeatType") or "")
            credits = to_float(item.get("SeatCredits")) or 0.0
            remaining = to_float(item.get("SeatRemainingCredits")) or 0.0
            snapshot.breakdown.append(
                BreakdownItem(
                    name=SEAT_TYPE_LABELS.get(seat_type, seat_type or "席位"),
                    value=remaining,
                    display=f"{format_number(remaining)} / {format_number(credits)}",
                    percentage=(remaining / credits) if credits else None,
                    dimension="席位档位",
                    hint=f"已分配 {int(to_float(item.get('AssignedSeats')) or 0)} / {int(to_float(item.get('TotalSeats')) or 0)} 席",
                )
            )
        for seat in seat_items:
            equity = (seat.get("EquityList") or [{}])[0]
            snapshot.breakdown.append(
                BreakdownItem(
                    name=str(seat.get("SeatId") or seat.get("InstanceCode") or "席位"),
                    value=to_float(equity.get("CycleSurplusValue")) or 0.0,
                    display=format_number(to_float(equity.get("CycleSurplusValue"))),
                    percentage=(
                        (to_float(equity.get("CycleSurplusValue")) or 0.0)
                        / (to_float(equity.get("CycleTotalValue")) or 0.0)
                        if to_float(equity.get("CycleTotalValue"))
                        else None
                    ),
                    dimension="席位明细",
                    hint=f"{str(seat.get('SpecType') or '')} · {str(seat.get('Status') or '')} · {seat.get('AccountName') or ''}".strip(" ·"),
                )
            )

        shared_items = ((data.get("shared_packages") or {}).get("Data") or {}).get("Items") or []
        for pkg in shared_items:
            equity = (pkg.get("EquityList") or [{}])[0]
            snapshot.breakdown.append(
                BreakdownItem(
                    name=str(pkg.get("InstanceCode") or "共享包"),
                    value=to_float(equity.get("CycleSurplusValue")) or 0.0,
                    display=f"{format_number(to_float(equity.get('CycleSurplusValue')))} / {format_number(to_float(equity.get('CycleTotalValue')))}",
                    percentage=(
                        (to_float(equity.get("CycleSurplusValue")) or 0.0)
                        / (to_float(equity.get("CycleTotalValue")) or 0.0)
                        if to_float(equity.get("CycleTotalValue"))
                        else None
                    ),
                    dimension="共享包",
                    hint=str(pkg.get("Status") or ""),
                )
            )

        for key, message in errors.items():
            snapshot.notes.append(f"{key} 查询失败：{message}")

        snapshot.raw = {
            "subscription_stats": data.get("stats"),
            "seat_detail": data.get("seat_detail"),
            "shared_packages": data.get("shared_packages"),
            "errors": errors,
        }
        snapshot.latency_ms = int((datetime.now() - started).total_seconds() * 1000)
        return snapshot

    # ------------------------------------------------------------------ 工具

    def _error_snapshot(self, account: Account, started: datetime, message: str) -> Snapshot:
        return Snapshot(
            account_id=account.id,
            platform=self.platform,
            mode=account.mode,
            label=account.label,
            status="error",
            error=message or "未知错误",
            fetched_at=now_iso(),
            latency_ms=int((datetime.now() - started).total_seconds() * 1000),
        )


def _format_period(period: str) -> str:
    if len(period) == 8 and period.isdigit():
        return f"{period[4:6]}-{period[6:8]}"
    if len(period) == 6 and period.isdigit():
        return period
    return period
