from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterator

import httpx

from ..models import Account
from ..format import format_number, format_percent, format_timestamp, now_iso, to_float
from ..http_client import ApiError, request_json
from ..snapshot import BreakdownItem, Metric, SeriesPoint, Snapshot
from .base import Provider

REMAINS_PATH = "/v1/token_plan/remains"

_REMAINING_WORDS = {"remaining", "remain", "remains", "rest", "surplus", "left", "available"}
_TOTAL_WORDS = {"total", "limit", "quota", "quotaLimit", "capacity", "max"}
_USED_WORDS = {"used", "consumed", "consume", "usage"}
_TIME_WORDS = {"reset", "resetAt", "resetTime", "refresh", "expire", "expires", "expiry", "endTime", "end", "validUntil"}
_NAME_WORDS = ("name", "label", "title", "model", "tier", "plan", "id", "key", "type", "code", "period", "date")

MINIMAX_NOTES = (
    "M Plan 用量受 5 小时窗口与周窗口约束，窗口从首次使用时开始计时，结束后额度恢复到档位上限。",
    "文本、图像、语音等非视频模型受两个窗口共同限制；视频模型仅受周窗口限制。",
    "未用完的套餐额度不会结转到下一个计费周期；积分包自购买之日起 1 年内有效。",
)


class MinimaxProvider(Provider):
    platform = "minimax"

    async def fetch(
        self,
        client: httpx.AsyncClient,
        account: Account,
        settings: dict[str, Any],
    ) -> Snapshot:
        started = datetime.now()
        api_key = account.credentials.get("api_key", "").strip()
        if not api_key:
            return self._error(account, started, "未配置订阅 Key")

        base_url = (
            account.options.get("minimax_base_url")
            or settings.get("minimax_base_url")
            or "https://www.minimax.cn"
        ).rstrip("/")
        url = f"{base_url}{REMAINS_PATH}"

        try:
            payload = await request_json(
                client,
                "GET",
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        except ApiError as exc:
            return self._error(account, started, str(exc))

        base_resp = payload.get("base_resp")
        if isinstance(base_resp, dict):
            code = base_resp.get("status_code")
            if code not in (None, 0, "0", "success"):
                message = str(base_resp.get("status_msg") or f"status_code={code}")
                snapshot = self._error(account, started, message)
                snapshot.raw = payload
                return snapshot

        snapshot = Snapshot(
            account_id=account.id,
            platform=self.platform,
            mode=account.mode,
            label=account.label,
            fetched_at=now_iso(),
        )
        snapshot.notes.extend(MINIMAX_NOTES)

        metrics, breakdown, series = _parse_model_remains(payload)
        if metrics:
            snapshot.metrics = metrics
            snapshot.breakdown = breakdown
            snapshot.series = series
        else:
            snapshot.metrics, snapshot.breakdown, snapshot.series = _analyze(payload)
        snapshot.raw = payload
        snapshot.latency_ms = int((datetime.now() - started).total_seconds() * 1000)
        return snapshot

    def _error(self, account: Account, started: datetime, message: str) -> Snapshot:
        return Snapshot(
            account_id=account.id,
            platform=self.platform,
            mode=account.mode,
            label=account.label,
            status="error",
            error=message,
            fetched_at=now_iso(),
            latency_ms=int((datetime.now() - started).total_seconds() * 1000),
        )


# --------------------------------------------------------------------- 解析


MODEL_LABELS = {
    "general": "通用模型",
    "video": "视频模型",
}

WINDOW_LABELS = {
    "interval": "5 小时窗口",
    "weekly": "周窗口",
}

# 5 小时窗口的时间字段没有 interval_ 前缀，周窗口的有
WINDOW_TIME_KEYS = {
    "interval": {"end": "end_time", "countdown": "remains_time", "start": "start_time"},
    "weekly": {"end": "weekly_end_time", "countdown": "weekly_remains_time", "start": "weekly_start_time"},
}


def _duration_text(milliseconds: float | None) -> str:
    if not milliseconds or milliseconds <= 0:
        return ""
    total = int(milliseconds / 1000)
    hours, remainder = divmod(total, 3600)
    minutes = remainder // 60
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days} 天 {hours} 小时后重置"
    if hours:
        return f"{hours} 小时 {minutes} 分后重置"
    return f"{minutes} 分钟后重置"


def _parse_model_remains(
    payload: dict[str, Any],
) -> tuple[list[Metric], list[BreakdownItem], list[SeriesPoint]]:
    """解析官方未公开但结构稳定的 model_remains 响应。

    每个条目按模型类别（general / video）给出 5 小时窗口与周窗口的
    总额度、已用额度、剩余百分比与窗口结束时间。
    """
    entries = payload.get("model_remains")
    if not isinstance(entries, list) or not entries:
        return [], [], []

    metrics: list[Metric] = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_name = str(entry.get("model_name") or "unknown")
        label = MODEL_LABELS.get(model_name, model_name)

        for scope in ("interval", "weekly"):
            percent = to_float(entry.get(f"current_{scope}_remaining_percent"))
            total = to_float(entry.get(f"current_{scope}_total_count"))
            usage = to_float(entry.get(f"current_{scope}_usage_count"))
            time_keys = WINDOW_TIME_KEYS[scope]
            remains_time = to_float(entry.get(time_keys["countdown"]))
            if percent is None and total is None:
                continue

            ratio = percent / 100.0 if percent is not None else None
            if ratio is None and total:
                ratio = max(0.0, (total - (usage or 0.0)) / total)

            window = WINDOW_LABELS[scope]
            hint_parts = []
            if total is not None:
                hint_parts.append(f"已用 {format_number(usage)} / {format_number(total)}")
            countdown = _duration_text(remains_time)
            if countdown:
                hint_parts.append(countdown)
            end_time = entry.get(time_keys["end"])
            if end_time is not None:
                end_text = format_timestamp(end_time)
                if end_text != "-":
                    hint_parts.append(f"至 {end_text}")

            level = "ok"
            if ratio is not None:
                if ratio <= 0.1:
                    level = "danger"
                elif ratio <= 0.3:
                    level = "warn"

            metrics.append(
                Metric(
                    key=f"{scope}_remaining:{model_name}",
                    label=f"{label} · {window}",
                    value=round(ratio * 100, 2) if ratio is not None else None,
                    display=format_percent(ratio),
                    unit="percent",
                    total=total,
                    progress=ratio,
                    hint=" · ".join(hint_parts) or None,
                    level=level,
                )
            )

    return metrics, [], []


def _classify(name: str) -> str | None:
    words = [w.lower() for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    if not words:
        return None
    for word in words:
        if word in _REMAINING_WORDS:
            return "remaining"
        if word in _TOTAL_WORDS:
            return "total"
        if word in _USED_WORDS:
            return "used"
    compact = "".join(words)
    for prefix, kind in (
        ("remaining", "remaining"),
        ("remain", "remaining"),
        ("surplus", "remaining"),
        ("available", "remaining"),
        ("total", "total"),
        ("limit", "total"),
        ("quota", "total"),
        ("used", "used"),
        ("consumed", "used"),
    ):
        if compact.startswith(prefix):
            return kind
    return None


def _is_time_like(name: str) -> bool:
    words = {w.lower() for w in re.split(r"[^A-Za-z0-9]+", name) if w}
    return bool(words & {w.lower() for w in _TIME_WORDS})


def _walk(node: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _walk(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")
    else:
        yield path, node


def _humanize(path: str) -> str:
    """把 a.b[0].c 这样的路径转成 "a b 0 c"。"""
    parts = re.split(r"[.\[]", path)
    words: list[str] = []
    for part in parts:
        part = part.rstrip("]")
        if not part:
            continue
        words.extend(w for w in re.split(r"[^A-Za-z0-9]+", part) if w)
    return " ".join(words) if words else path


def _analyze(payload: dict[str, Any]) -> tuple[list[Metric], list[BreakdownItem], list[SeriesPoint]]:
    metrics: list[Metric] = []
    breakdown: list[BreakdownItem] = []
    series: list[SeriesPoint] = []
    seen: set[str] = set()

    def add_metric(
        key: str,
        label: str,
        value: float,
        total: float | None = None,
        hint: str | None = None,
    ) -> None:
        if key in seen:
            return
        seen.add(key)
        progress = (value / total) if total else None
        metrics.append(
            Metric(
                key=key,
                label=label,
                value=value,
                display=format_number(value),
                unit="credits",
                total=total,
                progress=progress,
                hint=hint,
                level="ok" if (progress is None or progress > 0.2) else "danger",
            )
        )

    # 1) 同层级 remaining / total 配对，算出使用进度
    consumed: set[str] = set()
    for node, path in _iter_dicts(payload, ""):
        local: dict[str, tuple[str, float, str]] = {}
        for key, value in node.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            kind = _classify(str(key))
            if kind:
                child_path = f"{path}.{key}" if path else str(key)
                local[kind] = (str(key), float(value), child_path)
        if "remaining" in local and "total" in local:
            remaining_key, remaining, remaining_path = local["remaining"]
            total_key, total, _ = local["total"]
            if total > 0:
                consumed.add(remaining_path)
                add_metric(
                    f"remaining:{path or 'root'}",
                    _humanize(remaining_path),
                    remaining,
                    total=total,
                    hint=f"额度上限 {format_number(total)}，已用 {format_percent((total - remaining) / total)}",
                )

    # 2) 数值叶子分类（跳过已参与配对的）
    for path, value in _walk(payload):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if path in consumed:
            continue
        leaf = re.split(r"[.\[]", path)[-1]
        kind = _classify(leaf)
        if kind is None:
            continue
        add_metric(f"{kind}:{path}", _humanize(path), float(value))

    # 3) 列表 → 构成条
    for list_path, items in _iter_lists(payload, ""):
        entries = [item for item in items if isinstance(item, dict)]
        if len(entries) < 2:
            continue
        values: list[tuple[str, float]] = []
        for index, entry in enumerate(entries):
            name = _pick_name(entry) or f"#{index + 1}"
            number = _pick_number(entry)
            if number is None:
                continue
            values.append((name, number))
        if len(values) < 2:
            continue
        total = sum(value for _, value in values) or 0.0
        for name, value in values:
            breakdown.append(
                BreakdownItem(
                    name=name,
                    value=value,
                    display=format_number(value),
                    percentage=(value / total) if total else None,
                    dimension=list_path or "构成",
                )
            )

    # 4) 列表 → 趋势（找得到时间标签就用）
    for list_path, items in _iter_lists(payload, ""):
        entries = [item for item in items if isinstance(item, dict)]
        if len(entries) < 2:
            continue
        points: list[SeriesPoint] = []
        for index, entry in enumerate(entries):
            number = _pick_number(entry)
            if number is None:
                continue
            label = _pick_name(entry) or f"#{index + 1}"
            points.append(SeriesPoint(label=label, value=number, display=format_number(number)))
        if len(points) >= 2 and not series:
            series = points

    # 5) 时间字段
    for path, value in _walk(payload):
        leaf = re.split(r"[.\[]", path)[-1]
        if not _is_time_like(leaf):
            continue
        number = to_float(value)
        if number is None or number <= 0:
            continue
        text = format_timestamp(number)
        if text == "-":
            continue
        key = f"time:{path}"
        if key in seen:
            continue
        seen.add(key)
        metrics.append(
            Metric(
                key=key,
                label=f"{_humanize(path)}",
                value=None,
                display=text,
                unit="time",
            )
        )

    return metrics, breakdown, series


def _iter_dicts(node: Any, path: str) -> Iterator[tuple[dict[str, Any], str]]:
    if isinstance(node, dict):
        yield node, path
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            yield from _iter_dicts(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_dicts(value, f"{path}[{index}]")


def _iter_lists(node: Any, path: str) -> Iterator[tuple[str, list[Any]]]:
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if isinstance(value, list):
                yield child, value
            yield from _iter_lists(value, child)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _iter_lists(value, f"{path}[{index}]")


def _pick_name(entry: dict[str, Any]) -> str | None:
    for word in _NAME_WORDS:
        for key, value in entry.items():
            if key.lower() == word and isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _pick_number(entry: dict[str, Any]) -> float | None:
    for key, value in entry.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        kind = _classify(str(key))
        if kind:
            return float(value)
    return None
