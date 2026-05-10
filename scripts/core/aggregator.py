from __future__ import annotations

import logging

from models import ReportMode

logger = logging.getLogger(__name__)

_DATE_TYPES = ("type/Date", "type/DateTime", "type/DateTimeWithTZ", "type/DateTimeWithLocalTZ")
_NUM_TYPES = ("type/Integer", "type/Float", "type/Decimal", "type/BigInteger", "type/Number")
_DISTRICT_PREFIXES = ("Huyện ", "Thành phố ", "Quận ", "Thị xã ", "Thị trấn ", "Tỉnh ")
_GEO_SEMANTIC_TYPES = frozenset({"type/City", "type/State", "type/Country", "type/ZipCode"})
_METABASE_INTERNAL = {"pivot-grouping"}

# Shared parameter IDs confirmed across all dashboards
_CURRENT_PARAM_ID = "786cc6cb"
_COMPARISON_PARAM_ID = "8cf57752"

_MODE_CURRENT_VALUE: dict[ReportMode, str] = {
    ReportMode.WEEKLY: "lastweek",
    ReportMode.MONTHLY: "lastmonth",
    # DAILY uses a dynamic ISO date range passed as current_range to build_metabase_params
}


def fmt(value: float) -> str:
    return f"{int(value):,}" if value == int(value) else f"{value:,}"


def is_date(col: dict) -> bool:
    return col.get("base_type", "").startswith(_DATE_TYPES)


def is_num(col: dict) -> bool:
    return (
        col.get("base_type", "").startswith(_NUM_TYPES)
        and col.get("name") not in _METABASE_INTERNAL
    )


def is_pivot_card(cols: list) -> bool:
    return any(c.get("name") == "pivot-grouping" for c in cols)


def data_rows(rows: list, cols: list) -> list:
    pg_idx = next((i for i, c in enumerate(cols) if c.get("name") == "pivot-grouping"), None)
    if pg_idx is None:
        return rows
    return [row for row in rows if pg_idx < len(row) and row[pg_idx] == 0]


def sum_rows(rows: list, cols: list) -> float:
    num_idx = [i for i, c in enumerate(cols) if is_num(c)]
    return sum(
        row[i] for row in rows for i in num_idx
        if i < len(row) and isinstance(row[i], (int, float))
    )


def breakdown(rows: list, cols: list) -> list[tuple[str, str]]:
    num_idx = [i for i, c in enumerate(cols) if is_num(c)]
    dim = next((i for i, c in enumerate(cols) if not is_num(c) and not is_date(c)), None)
    if dim is None or not num_idx:
        return []
    groups: dict[str, float] = {}
    for row in rows:
        key = str(row[dim]) if dim < len(row) and row[dim] is not None else "?"
        for i in num_idx:
            if i < len(row) and isinstance(row[i], (int, float)):
                groups[key] = groups.get(key, 0.0) + row[i]
    return [(lbl, fmt(v)) for lbl, v in sorted(groups.items(), key=lambda x: x[1], reverse=True)]


def wide_breakdown(rows: list, cols: list) -> list[tuple[str, str]]:
    num_cols = [(i, c) for i, c in enumerate(cols) if is_num(c)]
    if len(num_cols) <= 1:
        return []
    result = []
    for i, col in num_cols:
        total = sum(row[i] for row in rows if i < len(row) and isinstance(row[i], (int, float)))
        name = col.get("display_name") or col.get("name") or f"Sản phẩm {i}"
        result.append((name, fmt(total)))
    return sorted(result, key=lambda x: float(x[1].replace(",", "") or 0), reverse=True)


def product_breakdown(rows: list, cols: list) -> list[tuple[str, str]]:
    result = breakdown(rows, cols)
    return result if result else wide_breakdown(rows, cols)


def merge_breakdown(
    existing: list[tuple[str, str]], new: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    merged: dict[str, float] = {}
    for label, val in existing:
        try:
            merged[label] = float(val.replace(",", ""))
        except ValueError:
            pass
    for label, val in new:
        try:
            merged[label] = merged.get(label, 0.0) + float(val.replace(",", ""))
        except ValueError:
            pass
    return [(k, fmt(v)) for k, v in sorted(merged.items(), key=lambda x: x[1], reverse=True)]


def classify_dimension(rows: list, cols: list) -> str:
    dim = next((i for i, c in enumerate(cols) if not is_num(c) and not is_date(c)), None)
    if dim is None:
        return "product"
    # Check semantic_type first (robust, language-independent)
    if cols[dim].get("semantic_type") in _GEO_SEMANTIC_TYPES:
        return "district"
    # Fallback: inspect row values for Vietnamese administrative prefixes
    for row in rows:
        if dim < len(row) and row[dim] is not None:
            if any(str(row[dim]).startswith(p) for p in _DISTRICT_PREFIXES):
                return "district"
    return "product"


def date_label(raw: object) -> str:
    s = str(raw)[:10]
    try:
        _, m, d = s.split("-")
        return f"{d}/{m}"
    except Exception:
        return s


def build_daily_chart(rows: list, cols: list, title: str, n_days: int = 7) -> dict | None:
    date_idx = next((i for i, c in enumerate(cols) if is_date(c)), None)
    num_idx_list = [i for i, c in enumerate(cols) if is_num(c)]
    dim_idx = next((i for i, c in enumerate(cols) if not is_num(c) and not is_date(c)), None)
    if date_idx is None or not num_idx_list:
        return None

    if dim_idx is not None:
        num_i = num_idx_list[0]
        product_dates: dict[str, dict[str, float]] = {}
        for row in rows:
            if any(idx >= len(row) for idx in (date_idx, dim_idx, num_i)):
                continue
            if not isinstance(row[num_i], (int, float)):
                continue
            product = str(row[dim_idx]) if row[dim_idx] is not None else "?"
            dl = date_label(row[date_idx])
            bucket = product_dates.setdefault(product, {})
            bucket[dl] = bucket.get(dl, 0.0) + row[num_i]
        all_dates = sorted({d for pd in product_dates.values() for d in pd})
        recent = all_dates[-n_days:]
        totals = {p: sum(d.values()) for p, d in product_dates.items()}
        ordered = sorted(totals, key=lambda x: totals[x], reverse=True)
        series = [
            {"legend": p, "values": [{"x": d, "y": int(product_dates[p].get(d, 0))} for d in recent]}
            for p in ordered
        ]
    else:
        all_dates = sorted({date_label(row[date_idx]) for row in rows if date_idx < len(row)})
        recent = all_dates[-n_days:]
        recent_set = set(recent)
        series = []
        for i in num_idx_list:
            col = cols[i]
            name = col.get("display_name") or col.get("name") or f"Col{i}"
            date_to_val: dict[str, float] = {}
            for row in rows:
                if date_idx >= len(row) or i >= len(row):
                    continue
                if not isinstance(row[i], (int, float)):
                    continue
                dl = date_label(row[date_idx])
                if dl in recent_set:
                    date_to_val[dl] = date_to_val.get(dl, 0.0) + row[i]
            series.append({
                "legend": name,
                "values": [{"x": d, "y": int(date_to_val.get(d, 0))} for d in recent],
            })

    if not series:
        return None
    return {
        "type": "Chart.VerticalBar.Grouped",
        "title": title,
        "xAxisTitle": "Ngày",
        "yAxisTitle": "Số lượng (bao)",
        "colorSet": "diverging",
        "data": series,
    }



def build_metabase_params(
    parameters: list,
    mode: ReportMode,
    comparison_range: str | None = None,
    current_range: str | None = None,
) -> list[dict]:
    current_value = current_range or _MODE_CURRENT_VALUE.get(mode)
    result = []
    for p in parameters:
        pid = p["id"]
        if pid == _CURRENT_PARAM_ID:
            if current_value:
                result.append({"id": pid, "type": p["type"], "value": current_value})
        elif pid == _COMPARISON_PARAM_ID:
            if comparison_range:
                result.append({"id": pid, "type": p["type"], "value": comparison_range})
        elif p.get("default") is not None:
            result.append({"id": pid, "type": p["type"], "value": p["default"]})
    return result


def _fetch_one(client, config, dashboard_params: list, dashcard: dict) -> dict | None:
    """Fetch a single dashcard and return its parsed result, or None on failure."""
    card = dashcard.get("card")
    if not card:
        return None
    dashcard_id = dashcard["id"]
    if config.dashcard_ids is not None and dashcard_id not in config.dashcard_ids:
        return None

    card_id = dashcard["card_id"]
    mapped = {m["parameter_id"] for m in dashcard.get("parameter_mappings", [])}
    try:
        raw = client.fetch_raw_data(
            config.dashboard_id, dashcard_id, card_id, parameters=dashboard_params
        )
    except Exception as e:
        logger.error("Failed to fetch dashcard %d: %s", dashcard_id, e)
        return None

    rows = raw.get("rows", [])
    cols = raw.get("cols", [])
    if not rows or not cols:
        return None

    return {
        "dashcard_id": dashcard_id,
        "mapped": mapped,
        "rows": rows,
        "cols": cols,
    }


def fetch_and_aggregate(
    client,
    config,
    mode: ReportMode,
    comparison_range: str | None = None,
    current_range: str | None = None,
) -> dict:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    dashboard = client.fetch_dashboard(config.dashboard_id)
    parameters = dashboard.get("parameters", [])
    dashboard_params = build_metabase_params(parameters, mode, comparison_range, current_range)

    dashcards = [dc for dc in dashboard.get("dashcards", []) if dc.get("card")]

    # Fetch all cards in parallel
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(len(dashcards), 8)) as pool:
        futures = {
            pool.submit(_fetch_one, client, config, dashboard_params, dc): dc
            for dc in dashcards
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    # Sort by dashcard_id to keep deterministic merge order
    results.sort(key=lambda r: r["dashcard_id"])

    total = 0.0
    comparison_total = 0.0
    product_facts: list[tuple[str, str]] = []
    district_facts: list[tuple[str, str]] = []
    chart_rows: list = []
    chart_cols: list = []
    detail_rows: list = []
    detail_cols: list = []

    for r in results:
        mapped = r["mapped"]
        rows = r["rows"]
        cols = r["cols"]
        is_current = _CURRENT_PARAM_ID in mapped
        is_comparison = _COMPARISON_PARAM_ID in mapped

        has_date = any(is_date(c) for c in cols)
        is_pivot = is_pivot_card(cols)
        effective = data_rows(rows, cols)
        kind = classify_dimension(effective, cols)

        if is_current:
            if has_date and not is_pivot:
                total += sum_rows(effective, cols)
                extra = product_breakdown(effective, cols)
                if not chart_rows:
                    chart_rows, chart_cols = effective, cols
            elif not has_date:
                extra = breakdown(effective, cols)
            else:
                extra = []
                if not detail_rows:
                    detail_rows, detail_cols = effective, cols

            if extra:
                if kind == "district":
                    district_facts = merge_breakdown(district_facts, extra) if district_facts else extra
                else:
                    product_facts = merge_breakdown(product_facts, extra) if product_facts else extra

        elif is_comparison and has_date and not is_pivot:
            comparison_total += sum_rows(effective, cols)

    return {
        "dashboard_name": dashboard.get("name") or "Báo cáo",
        "total": total,
        "comparison_total": comparison_total,
        "product_facts": product_facts,
        "district_facts": district_facts,
        "chart_rows": chart_rows,
        "chart_cols": chart_cols,
        "detail_rows": detail_rows,
        "detail_cols": detail_cols,
    }
