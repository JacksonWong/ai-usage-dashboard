from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Metric:
    key: str
    label: str
    value: float | None = None
    display: str = "-"
    unit: str = ""
    total: float | None = None
    progress: float | None = None
    hint: str | None = None
    level: str = "info"  # ok | warn | danger | info

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BreakdownItem:
    name: str
    value: float = 0.0
    display: str = "-"
    percentage: float | None = None
    dimension: str = ""
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SeriesPoint:
    label: str
    value: float = 0.0
    display: str = "-"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DonutItem:
    name: str
    value: float = 0.0
    display: str = "-"
    percentage: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Donut:
    title: str = ""
    total: float = 0.0
    total_display: str = "-"
    currency: str = ""
    items: list[DonutItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "total": self.total,
            "total_display": self.total_display,
            "currency": self.currency,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class StackedPart:
    name: str
    value: float = 0.0
    display: str = "-"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StackedPoint:
    label: str
    total: float = 0.0
    total_display: str = "-"
    parts: list[StackedPart] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "total": self.total,
            "total_display": self.total_display,
            "parts": [part.to_dict() for part in self.parts],
        }


@dataclass
class Stacked:
    title: str = ""
    currency: str = ""
    categories: list[str] = field(default_factory=list)
    points: list[StackedPoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "currency": self.currency,
            "categories": list(self.categories),
            "points": [point.to_dict() for point in self.points],
        }


@dataclass
class Snapshot:
    account_id: int
    platform: str
    mode: str
    label: str
    status: str = "ok"  # ok | error
    error: str | None = None
    fetched_at: str = ""
    latency_ms: int = 0
    metrics: list[Metric] = field(default_factory=list)
    breakdown: list[BreakdownItem] = field(default_factory=list)
    series: list[SeriesPoint] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    donut: Donut | None = None
    stacked: Stacked | None = None
    filters: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "platform": self.platform,
            "mode": self.mode,
            "label": self.label,
            "status": self.status,
            "error": self.error,
            "fetched_at": self.fetched_at,
            "latency_ms": self.latency_ms,
            "metrics": [m.to_dict() for m in self.metrics],
            "breakdown": [b.to_dict() for b in self.breakdown],
            "series": [s.to_dict() for s in self.series],
            "notes": self.notes,
            "raw": self.raw,
            "donut": self.donut.to_dict() if self.donut else None,
            "stacked": self.stacked.to_dict() if self.stacked else None,
            "filters": self.filters,
        }
