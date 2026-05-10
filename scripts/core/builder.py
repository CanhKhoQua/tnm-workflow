from __future__ import annotations

import datetime

from core.aggregator import build_daily_chart, fmt
from models import ReportMode, ReportSummary, Section


def get_period_info(
    mode: ReportMode, today: datetime.date | None = None
) -> tuple[str, str | None, str | None]:
    """Return (period_label, comparison_range, current_range).

    - comparison_range: ISO date range for monthly comparison, None otherwise.
    - current_range: ISO date range for daily mode (e.g. '2026-05-01~2026-05-01'), None otherwise.
    """
    if today is None:
        today = datetime.date.today()

    if mode == ReportMode.DAILY:
        yesterday = today - datetime.timedelta(days=1)
        first_of_month = today.replace(day=1)
        label = f"Tháng {today.month}/{today.year} (đến {yesterday.strftime('%d/%m')})"
        current_range = f"{first_of_month.isoformat()}~{yesterday.isoformat()}"
        return label, None, current_range

    if mode == ReportMode.WEEKLY:
        days_since_monday = today.weekday()
        last_monday = today - datetime.timedelta(days=days_since_monday + 7)
        last_sunday = last_monday + datetime.timedelta(days=6)
        week_num = last_monday.isocalendar()[1]
        label = f"Tuần {week_num} ({last_monday.strftime('%d/%m')}–{last_sunday.strftime('%d/%m/%Y')})"
        return label, None, None

    # MONTHLY: report previous calendar month, compare with the month before that
    first_of_this_month = today.replace(day=1)
    prev_month_end = first_of_this_month - datetime.timedelta(days=1)
    label = f"Tháng {prev_month_end.month}/{prev_month_end.year}"

    prev_prev_end = prev_month_end.replace(day=1) - datetime.timedelta(days=1)
    prev_prev_start = prev_prev_end.replace(day=1)
    comparison_range = f"{prev_prev_start.isoformat()}~{prev_prev_end.isoformat()}"

    return label, comparison_range, None


def build_report(
    aggregated: dict,
    mode: ReportMode,
    period_label: str,
    report_url: str | None = None,
) -> ReportSummary:
    dashboard_name = aggregated["dashboard_name"]
    total = aggregated["total"]
    comparison_total = aggregated["comparison_total"]
    product_facts: list[tuple[str, str]] = aggregated["product_facts"]
    district_facts: list[tuple[str, str]] = aggregated["district_facts"]
    chart_rows = aggregated["chart_rows"]
    chart_cols = aggregated["chart_cols"]

    overview_facts: list[tuple[str, str]] = [(period_label, f"{fmt(total)} bao")]
    if comparison_total and mode == ReportMode.MONTHLY:
        overview_facts.append(("Tháng trước đó", f"{fmt(comparison_total)} bao"))

    sections: list[Section] = [Section(title="Tổng quan", facts=tuple(overview_facts))]
    if product_facts:
        sections.append(Section(title="Theo mặt hàng", facts=tuple(product_facts)))
    if district_facts:
        sections.append(Section(title="Theo quận/huyện", facts=tuple(district_facts)))
    if mode == ReportMode.DAILY and product_facts:
        sections.append(Section(title="Tổng lượng thực xuất", facts=tuple(product_facts)))

    if mode == ReportMode.WEEKLY:
        n_days = 7
    elif mode == ReportMode.DAILY:
        n_days = 31  # show all days in the month-to-date range
    else:
        n_days = 31
    chart_data = build_daily_chart(chart_rows, chart_cols, dashboard_name, n_days=n_days)

    return ReportSummary(
        mode=mode,
        title=f"{dashboard_name} — {period_label}",
        period_label=period_label,
        sections=tuple(sections),
        chart_data=chart_data,
        report_url=report_url,
    )
