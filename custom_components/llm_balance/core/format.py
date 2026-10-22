from __future__ import annotations

from datetime import datetime, timezone


def to_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def format_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
        return f"{int(round(value)):,}"
    return f"{value:,.{digits}f}"


def format_money(value: float | None, currency: str = "") -> str:
    if value is None:
        return "-"
    text = f"{value:,.2f}"
    return f"{text} {currency}".strip()


def format_percent(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.{digits}f}%"


def format_timestamp(value: object) -> str:
    """毫秒 / 秒时间戳或 ISO 字符串 → 本地时间显示。"""
    if value is None:
        return "-"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "-"
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M")
    number = to_float(value)
    if number is None:
        return str(value)
    if number > 1e11:  # 毫秒
        number /= 1000.0
    try:
        return datetime.fromtimestamp(number, tz=timezone.utc).astimezone().strftime(
            "%Y-%m-%d %H:%M"
        )
    except (OverflowError, OSError, ValueError):
        return str(value)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
