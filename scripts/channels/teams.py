from __future__ import annotations

import requests

from channels.base import BaseChannel
from models import DashboardMessage, ReportMode, ReportSummary

_OVERVIEW_SECTION = "Tổng quan"
_DISTRICT_SECTION = "Theo quận/huyện"
_VISIBLE_PRODUCT_ROWS = 3

_MODE_ICONS = {
    ReportMode.WEEKLY: "📅",
    ReportMode.MONTHLY: "📆",
    ReportMode.DAILY: "📋",
}

_SECTION_ICONS = {
    "Tổng quan": "📊",
    "Theo mặt hàng": "🏷️",
    "Theo quận/huyện": "📍",
    "Tổng lượng thực xuất": "📦",
}

_EXPORTS_SECTION = "Tổng lượng thực xuất"


def _nonzero(value: str) -> bool:
    try:
        return float(value.replace(",", "")) != 0
    except ValueError:
        return False


class TeamsChannel(BaseChannel):
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def send(self, message: DashboardMessage | ReportSummary) -> None:
        resp = requests.post(self.webhook_url, json=self._build_payload(message))
        resp.raise_for_status()

    def _build_payload(self, message: DashboardMessage | ReportSummary) -> dict:
        if isinstance(message, ReportSummary):
            body = self._summary_body(message)
        else:
            facts = [{"title": c.label, "value": c.value} for c in message.cards]
            body = [
                {"type": "TextBlock", "text": message.title, "size": "Large", "weight": "Bolder"},
                {"type": "FactSet", "facts": facts},
            ]
        return {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "https://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "msteams": {"width": "Full"},
                    "body": body,
                },
            }],
        }

    def _summary_body(self, summary: ReportSummary) -> list:
        icon = _MODE_ICONS.get(summary.mode, "📦")
        parts = summary.title.rsplit("—", 1)
        title_text = f"{icon} {parts[0].strip()}"
        period_text = parts[1].strip() if len(parts) == 2 else summary.period_label

        body: list = [{
            "type": "Container",
            "style": "emphasis",
            "bleed": True,
            "items": [
                {"type": "TextBlock", "text": title_text, "size": "Large", "weight": "Bolder", "wrap": True},
                {"type": "TextBlock", "text": period_text, "size": "Small", "isSubtle": True, "spacing": "None"},
            ],
        }]

        for section in summary.sections:
            section_icon = _SECTION_ICONS.get(section.title, "")
            label = f"{section_icon} {section.title}" if section_icon else section.title
            body.append({
                "type": "TextBlock",
                "text": label,
                "weight": "Bolder",
                "size": "Medium",
                "spacing": "Large",
            })

            if section.title == _OVERVIEW_SECTION:
                body.extend(_overview_blocks(section.facts, summary.mode))
            elif section.title == _DISTRICT_SECTION:
                body.append(_district_block(section.facts))
            elif section.title == _EXPORTS_SECTION:
                body.append(_exports_table_block(section.facts))
            else:
                body.extend(_product_blocks(section.facts))

        if summary.chart_data:
            body.append({
                "type": "TextBlock",
                "text": "📈 Biểu đồ",
                "weight": "Bolder",
                "size": "Medium",
                "spacing": "Large",
            })
            body.append(summary.chart_data)

        if summary.report_url:
            body.append({
                "type": "ActionSet",
                "spacing": "Large",
                "actions": [{
                    "type": "Action.OpenUrl",
                    "title": "Xem chi tiết",
                    "url": summary.report_url,
                    "style": "positive",
                }],
            })

        return body


def _overview_blocks(facts: tuple, mode: ReportMode) -> list:
    """KPI card(s) for the overview section.

    Weekly: one full-width card with the week total.
    Monthly: two side-by-side cards — current month and previous month.
    """
    fact_list = list(facts)
    if not fact_list:
        return []

    current_label, current_value = fact_list[0]

    if mode in (ReportMode.WEEKLY, ReportMode.DAILY):
        return [{
            "type": "ColumnSet",
            "spacing": "Medium",
            "columns": [_kpi_column(current_label, current_value, "bao", "good", width="100")],
        }]

    cols = [_kpi_column(current_label, current_value, "bao", "good")]
    if len(fact_list) > 1:
        prev_label, prev_value = fact_list[1]
        cols.append(_kpi_column(prev_label, prev_value, "bao", "warning"))
    return [{"type": "ColumnSet", "spacing": "Medium", "columns": cols}]


def _kpi_column(label: str, value: str, subtitle: str, style: str, width: str = "50") -> dict:
    return {
        "type": "Column",
        "width": width,
        "items": [{
            "type": "Container",
            "style": style,
            "minHeight": "110px",
            "items": [
                {
                    "type": "TextBlock",
                    "text": label,
                    "horizontalAlignment": "Center",
                    "weight": "Bolder",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": value,
                    "size": "Large",
                    "weight": "Bolder",
                    "horizontalAlignment": "Center",
                    "spacing": "Small",
                    "wrap": False,
                },
                {
                    "type": "TextBlock",
                    "text": subtitle,
                    "size": "Small",
                    "isSubtle": True,
                    "horizontalAlignment": "Center",
                    "spacing": "None",
                },
            ],
        }],
    }


def _make_product_row(pair: list[tuple[str, str]], offset: int) -> dict:
    cols = []
    for j, (name, value) in enumerate(pair):
        value_block: dict = {"type": "TextBlock", "text": value, "weight": "Bolder"}
        if offset + j < 2:
            value_block["color"] = "Good"
        cols.append({
            "type": "Column",
            "width": "50",
            "items": [
                {"type": "TextBlock", "text": name, "wrap": True},
                value_block,
            ],
        })
    return {"type": "ColumnSet", "spacing": "Small", "columns": cols}


def _product_blocks(facts: tuple) -> list:
    """Grid of 2-per-row. First 6 items visible; rest hidden under toggle."""
    items = list(facts)
    cutoff = _VISIBLE_PRODUCT_ROWS * 2
    visible = items[:cutoff]
    hidden = items[cutoff:]

    visible_rows = [_make_product_row(visible[i:i + 2], i) for i in range(0, len(visible), 2)]

    result: list = [{
        "type": "Container",
        "style": "default",
        "spacing": "Medium",
        "items": visible_rows,
    }]

    if hidden:
        hidden_rows = [
            {
                "type": "ColumnSet",
                "spacing": "Small",
                "columns": [
                    {
                        "type": "Column",
                        "width": "50",
                        "items": [
                            {"type": "TextBlock", "text": name, "wrap": True},
                            {"type": "TextBlock", "text": value, "weight": "Bolder"},
                        ],
                    }
                    for name, value in hidden[i:i + 2]
                ],
            }
            for i in range(0, len(hidden), 2)
        ]
        result.extend([
            {
                "type": "ActionSet",
                "spacing": "Medium",
                "actions": [{
                    "type": "Action.ToggleVisibility",
                    "title": "Xem thêm mặt hàng",
                    "targetElements": ["moreProducts"],
                }],
            },
            {
                "type": "Container",
                "id": "moreProducts",
                "isVisible": False,
                "spacing": "Small",
                "items": hidden_rows,
            },
        ])

    return result


def _exports_table_block(facts: tuple) -> dict:
    """Table: Mặt hàng | Thực xuất (bao) with a grand total row."""
    items = list(facts)
    rows = []

    # Header row
    rows.append({
        "type": "ColumnSet",
        "columns": [
            {"type": "Column", "width": "70", "items": [
                {"type": "TextBlock", "text": "Mặt hàng", "weight": "Bolder", "size": "Small", "color": "Accent"},
            ]},
            {"type": "Column", "width": "30", "items": [
                {"type": "TextBlock", "text": "Thực xuất (bao)", "weight": "Bolder", "size": "Small",
                 "horizontalAlignment": "Right", "color": "Accent"},
            ]},
        ],
    })

    grand = 0
    for name, value in items:
        try:
            grand += int(value.replace(",", ""))
        except ValueError:
            pass
        rows.append({
            "type": "ColumnSet",
            "spacing": "Small",
            "columns": [
                {"type": "Column", "width": "70", "items": [
                    {"type": "TextBlock", "text": name, "wrap": True},
                ]},
                {"type": "Column", "width": "30", "items": [
                    {"type": "TextBlock", "text": value, "weight": "Bolder",
                     "horizontalAlignment": "Right"},
                ]},
            ],
        })

    rows.append({
        "type": "ColumnSet",
        "spacing": "Small",
        "separator": True,
        "columns": [
            {"type": "Column", "width": "70", "items": [
                {"type": "TextBlock", "text": "Tổng cộng", "weight": "Bolder"},
            ]},
            {"type": "Column", "width": "30", "items": [
                {"type": "TextBlock", "text": f"{grand:,}", "weight": "Bolder",
                 "color": "Good", "horizontalAlignment": "Right"},
            ]},
        ],
    })

    return {"type": "Container", "style": "emphasis", "spacing": "Medium", "items": rows}


def _district_block(facts: tuple) -> dict:
    """70/30 rows inside emphasis container; top district is bold + green."""
    rows = []
    for i, (name, value) in enumerate(facts):
        is_top = i == 0
        name_block: dict = {"type": "TextBlock", "text": name}
        value_block: dict = {"type": "TextBlock", "text": value, "horizontalAlignment": "Right"}
        if is_top:
            name_block["weight"] = "Bolder"
            value_block["weight"] = "Bolder"
            value_block["color"] = "Good"

        row: dict = {
            "type": "ColumnSet",
            "columns": [
                {"type": "Column", "width": "70", "items": [name_block]},
                {"type": "Column", "width": "30", "items": [value_block]},
            ],
        }
        if i > 0:
            row["spacing"] = "Small"
        rows.append(row)

    return {"type": "Container", "style": "emphasis", "items": rows}
