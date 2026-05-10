from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReportMode(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    DAILY = "daily"


@dataclass(frozen=True)
class CardData:
    label: str
    value: str
    image_bytes: bytes | None = None


@dataclass(frozen=True)
class DashboardMessage:
    title: str
    cards: tuple[CardData, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "cards", tuple(self.cards))


@dataclass(frozen=True)
class Section:
    title: str
    facts: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", tuple(self.facts))


@dataclass(frozen=True)
class ReportSummary:
    mode: ReportMode
    title: str
    period_label: str
    sections: tuple[Section, ...]
    chart_data: dict | None = None
    report_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", tuple(self.sections))


# Kept for any external references not yet migrated
DailySummary = ReportSummary
