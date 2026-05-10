from __future__ import annotations

from pathlib import Path

from models import ReportMode, ReportSummary

_CHART_BAR_MAX_PX = 160
_COL_W = (90, 100, 110)  # desktop; mobile overrides via CSS

# Semantic types used to identify columns without relying on display names
_GEO_SEMANTIC = frozenset({"type/City", "type/State", "type/Country", "type/ZipCode"})
_NAME_SEMANTIC = frozenset({"type/Name"})
_CAT_SEMANTIC = frozenset({"type/Category", "type/Name"})


def _find_col(cols: list, needle: str, semantic_types: frozenset = frozenset()) -> int:
    """Return column index: semantic_type match first, display-name substring fallback.

    Priority:
    1. semantic_type in semantic_types AND needle in display name  (most specific)
    2. semantic_type in semantic_types  (type match alone)
    3. needle substring in display name  (name-only fallback)
    Returns -1 if nothing matches.
    """
    needle_l = needle.lower()
    if semantic_types:
        for i, c in enumerate(cols):  # pass 1: type + name hint
            if c.get("semantic_type") in semantic_types:
                if needle_l in (c.get("display_name") or c.get("name", "")).lower():
                    return i
        for i, c in enumerate(cols):  # pass 2: type alone
            if c.get("semantic_type") in semantic_types:
                return i
    for i, c in enumerate(cols):  # pass 3: name substring
        if needle_l in (c.get("display_name") or c.get("name", "")).lower():
            return i
    return -1


_PALETTE = [
    "#e53935", "#1e88e5", "#43a047", "#fb8c00", "#8e24aa",
    "#00acc1", "#f4511e", "#3949ab", "#00897b", "#c0ca33",
    "#d81b60", "#6d4c41", "#039be5", "#7cb342", "#fdd835",
    "#5e35b1", "#546e7a", "#26a69a", "#ef6c00", "#00b0ff",
    "#673ab7", "#009688", "#ff5722", "#607d8b",
]


def _reports_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "reports"


def _safe_filename(summary: ReportSummary) -> str:
    label = summary.period_label.replace("/", "-").replace(" ", "_").replace("–", "-")
    return f"{summary.mode.value}_{label}.html"


def _sort_key(label: str) -> tuple:
    """Sort T9 < T10 numerically; fall back to lexicographic for other labels."""
    if label.startswith("T") and label[1:].isdigit():
        return (0, int(label[1:]))
    return (1, label)


def _stacked_bar_chart_html(chart_data: dict, mode: ReportMode) -> str:
    data = chart_data.get("data", [])
    if not data:
        return ""

    # Collect all x labels and sort numerically
    all_x: list[str] = [p["x"] for p in data[0]["values"]]
    xs = sorted(all_x, key=_sort_key)

    # Build x → {series_index → y} lookup
    x_vals: dict[str, dict[int, int]] = {x: {} for x in xs}
    for s_idx, series in enumerate(data):
        for pt in series["values"]:
            x = pt["x"]
            if x in x_vals:
                x_vals[x][s_idx] = pt["y"]

    # x totals and chart scale
    x_totals = {x: sum(x_vals[x].values()) for x in xs}
    max_total = max(x_totals.values(), default=1) or 1

    series_order = sorted(
        range(len(data)),
        key=lambda i: sum(p["y"] for p in data[i]["values"]),
        reverse=True,
    )

    display = [(data[i]["legend"], _PALETTE[rank % len(_PALETTE)], i)
               for rank, i in enumerate(series_order)]

    x_axis_label = chart_data.get("xAxisTitle", "Ngày")

    bars = []
    for x in xs:
        total = x_totals[x]
        bar_h = max(4, round(total / max_total * _CHART_BAR_MAX_PX))

        # Tooltip lines (product: value, then Tổng)
        tip_lines = []
        for i in series_order:
            v = x_vals[x].get(i, 0)
            if v:
                tip_lines.append(f"{data[i]['legend']}: {v:,}")
        tip_lines.append(f"Tổng: {total:,}")
        tip_attr = "||".join(tip_lines)

        # Stack segments bottom→top (column-reverse); skip zero-value segments
        segs = []
        for legend, color, s_idx in reversed(display):
            v = x_vals[x].get(s_idx, 0)
            if v and total:
                segs.append(
                    f'<div class="seg" style="flex:{v / total:.4f};background:{color}"></div>'
                )

        bars.append(
            f'<div class="bar-item" data-tip="{tip_attr}">'
            f'<div class="bar-val">{int(total):,}</div>'
            f'<div class="bar-stack" style="height:{bar_h}px">{"".join(segs)}</div>'
            f'<div class="bar-label">{x}</div>'
            f'</div>'
        )

    legend_items = [
        f'<span class="leg-item">'
        f'<span class="leg-dot" style="background:{color}"></span>{legend}'
        f'</span>'
        for legend, color, _ in display
    ]
    return (
        f'<div class="chart-wrap">'
        f'<div class="chart-bars">{"".join(bars)}</div>'
        f'<div class="chart-x-title">{x_axis_label}</div>'
        f'<div class="chart-legend">{"".join(legend_items)}</div>'
        f'<div id="chart-tooltip" class="chart-tooltip"></div>'
        f'</div>'
    )


def _total_cell(val: float, grand: float, bold: bool = False) -> str:
    """Render a total cell with an Excel-style data bar behind the number."""
    pct = round(val / grand * 100) if grand > 0 else 0
    style = (
        f"background:linear-gradient(90deg,rgba(46,125,50,.28) {pct}%,"
        f"#f1f8e9 {pct}%);text-align:right;font-variant-numeric:tabular-nums;"
    )
    inner = f"<strong>{int(val):,}</strong>" if bold else f"{int(val):,}"
    return f'<td class="total-col" style="{style}">{inner}</td>'


def _cell(val: float) -> str:
    if val == 0:
        return '<td class="num zero">—</td>'
    return f'<td class="num">{int(val):,}</td>'


def _pivot_table_html(detail_rows: list, detail_cols: list) -> str:
    from core.aggregator import date_label, is_date, is_num

    if not detail_rows or not detail_cols:
        return "<p>Không có dữ liệu chi tiết.</p>"

    district_idx = _find_col(detail_cols, "quận", _GEO_SEMANTIC)
    if district_idx == -1:
        district_idx = _find_col(detail_cols, "huyện", _GEO_SEMANTIC)
    customer_idx = _find_col(detail_cols, "khách", _NAME_SEMANTIC)
    product_idx = _find_col(detail_cols, "tên hàng", _CAT_SEMANTIC)
    date_idx = next((i for i, c in enumerate(detail_cols) if is_date(c)), 2)
    qty_idx = next((i for i, c in enumerate(detail_cols) if is_num(c)), len(detail_cols) - 1)

    matrix: dict[tuple[str, str, str], dict[str, float]] = {}
    date_set: set[str] = set()

    for row in detail_rows:
        if any(idx >= len(row) for idx in (district_idx, customer_idx, product_idx, date_idx, qty_idx)):
            continue
        if not isinstance(row[qty_idx], (int, float)):
            continue
        key = (
            str(row[district_idx] or ""),
            str(row[customer_idx] or ""),
            str(row[product_idx] or ""),
        )
        dl = date_label(row[date_idx])
        date_set.add(dl)
        prev = matrix.setdefault(key, {})
        prev[dl] = prev.get(dl, 0.0) + row[qty_idx]

    if not matrix:
        return "<p>Không có dữ liệu chi tiết.</p>"

    dates = sorted(date_set)
    row_totals = {key: sum(v.values()) for key, v in matrix.items()}
    grand = sum(row_totals.values())

    w0, w1, w2 = _COL_W
    left1 = w0
    left2 = w0 + w1

    th_dates = "".join(f'<th class="date-col">{d}</th>' for d in dates)
    lines = [
        '<div class="table-wrap">',
        '<table class="pivot-table">',
        f'<thead><tr>'
        f'<th class="sticky-col" style="left:0;min-width:{w0}px">Quận/Huyện</th>'
        f'<th class="sticky-col" style="left:{left1}px;min-width:{w1}px">Khách hàng</th>'
        f'<th class="sticky-col col-sep" style="left:{left2}px;min-width:{w2}px">Mặt hàng</th>'
        f'{th_dates}<th class="total-col">Tổng</th></tr></thead>',
        '<tbody>',
    ]

    districts: dict[str, dict[str, list[tuple[str, str, str]]]] = {}
    for key in sorted(matrix):
        d, c, _ = key
        districts.setdefault(d, {}).setdefault(c, []).append(key)

    for dist_num, (district, customers) in enumerate(sorted(districts.items())):
        dk = str(dist_num)
        all_keys = [k for ks in customers.values() for k in ks]
        d_total = sum(row_totals[k] for k in all_keys)
        d_cells = "".join(
            _cell(sum(matrix.get(k, {}).get(date, 0) for k in all_keys))
            for date in dates
        )
        lines.append(
            f'<tr class="district-row">'
            f'<td colspan="3" class="sticky-col col-sep" style="left:0;min-width:{w0+w1+w2}px">'
            f'<button class="tog" onclick="toggleDist(this,\'{dk}\')">▾</button>'
            f' <strong>{district}</strong></td>'
            f'{d_cells}{_total_cell(d_total, grand, bold=True)}</tr>'
        )

        for customer, keys in sorted(customers.items()):
            c_total = sum(row_totals[k] for k in keys)
            c_cells = "".join(
                _cell(sum(matrix.get(k, {}).get(date, 0) for k in keys))
                for date in dates
            )
            lines.append(
                f'<tr class="customer-row" data-dist="{dk}">'
                f'<td class="sticky-col" style="left:0;min-width:{w0}px"></td>'
                f'<td colspan="2" class="sticky-col col-sep" style="left:{left1}px;min-width:{w1+w2}px"><em>{customer}</em></td>'
                f'{c_cells}{_total_cell(c_total, grand)}</tr>'
            )

            for key in sorted(keys, key=lambda k: row_totals[k], reverse=True):
                _, _, product = key
                p_cells = "".join(
                    _cell(int(matrix[key][date])) if matrix[key].get(date) else '<td class="num zero">—</td>'
                    for date in dates
                )
                lines.append(
                    f'<tr class="product-row" data-dist="{dk}">'
                    f'<td class="sticky-col" style="left:0;min-width:{w0}px"></td>'
                    f'<td class="sticky-col" style="left:{left1}px;min-width:{w1}px"></td>'
                    f'<td class="sticky-col col-sep" style="left:{left2}px;min-width:{w2}px">{product}</td>'
                    f'{p_cells}{_total_cell(row_totals[key], grand)}</tr>'
                )

    g_cells = "".join(
        f'<td class="num"><strong>{int(sum(matrix[k].get(date, 0) for k in matrix)):,}</strong></td>'
        for date in dates
    )
    lines.append(
        f'<tr class="grand-row">'
        f'<td colspan="3" class="sticky-col col-sep" style="left:0;min-width:{w0+w1+w2}px"><strong>Tổng cộng</strong></td>'
        f'{g_cells}<td class="total-col" style="background:#c8e6c9;text-align:right">'
        f'<strong>{int(grand):,}</strong></td></tr>'
    )
    lines += ["</tbody></table></div>"]
    return "\n".join(lines)


_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:13px;
     color:#1a1a1a;background:#f4f6f8}
.page{max-width:1400px;margin:0 auto;padding:20px}
header{background:linear-gradient(135deg,#1b5e20,#2e7d32);color:#fff;
       padding:18px 24px;border-radius:10px;margin-bottom:20px;
       box-shadow:0 2px 8px rgba(27,94,32,.3)}
header h1{font-size:19px;font-weight:700;letter-spacing:.3px}
header p{font-size:12px;opacity:.75;margin-top:5px}
.kpi-row{display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.kpi{background:#fff;border-radius:10px;padding:16px 20px;flex:1;min-width:160px;
     box-shadow:0 1px 4px rgba(0,0,0,.08);border-top:3px solid #2e7d32}
.kpi .label{font-size:11px;color:#777;text-transform:uppercase;letter-spacing:.6px}
.kpi .value{font-size:28px;font-weight:700;color:#1b5e20;margin-top:6px}
.section{background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:14px;
         box-shadow:0 1px 4px rgba(0,0,0,.08)}
.section h2{font-size:13px;font-weight:600;color:#333;border-bottom:2px solid #e8f5e9;
            padding-bottom:8px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:8px}
.item{display:flex;justify-content:space-between;padding:6px 10px;
      background:#f9fbe7;border-radius:5px;gap:8px}
.item .name{color:#444;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .qty{font-weight:600;color:#2e7d32;white-space:nowrap}

/* Stacked bar chart */
.chart-wrap{overflow-x:auto;padding-bottom:4px;position:relative}
.chart-bars{display:flex;align-items:flex-end;gap:6px;padding:0 4px;
            border-bottom:2px solid #e0e0e0;margin-bottom:6px;min-height:180px}
.bar-item{display:flex;flex-direction:column;align-items:center;flex:1;
          min-width:40px;max-width:80px;cursor:pointer}
.bar-val{font-size:10px;color:#555;margin-bottom:4px;white-space:nowrap;font-weight:600}
.bar-stack{display:flex;flex-direction:column-reverse;width:76%;border-radius:4px 4px 0 0;
           overflow:hidden;min-height:4px}
.seg{min-height:2px;transition:opacity .1s}
.bar-item:hover .seg{opacity:.82}
.bar-label{font-size:10px;color:#666;margin-top:5px;white-space:nowrap}
.chart-x-title{text-align:center;font-size:11px;color:#aaa;margin-top:4px}
.chart-legend{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.leg-item{display:flex;align-items:center;gap:5px;font-size:11px;color:#555;white-space:nowrap}
.leg-dot{width:10px;height:10px;border-radius:2px;flex-shrink:0}
.chart-tooltip{position:fixed;pointer-events:none;background:rgba(30,30,30,.92);
               color:#fff;font-size:11px;line-height:1.6;padding:7px 10px;
               border-radius:6px;white-space:pre;display:none;z-index:999;
               box-shadow:0 2px 8px rgba(0,0,0,.3)}

/* Pivot table */
.table-wrap{overflow-x:auto;overflow-y:auto;max-height:640px;border-radius:6px;
            border:1px solid #e0e0e0}
.pivot-table{border-collapse:separate;border-spacing:0;width:100%;font-size:12px}
.pivot-table th{background:#1b5e20;color:#fff;padding:7px 10px;text-align:left;
                white-space:nowrap;position:sticky;top:0;z-index:1}
.pivot-table th.date-col,.pivot-table th.total-col{text-align:right}
.pivot-table th.sticky-col{z-index:3}
.pivot-table td{padding:5px 10px;border-bottom:1px solid #f0f0f0;white-space:nowrap}
.pivot-table td.num{text-align:right;font-variant-numeric:tabular-nums}
.pivot-table td.zero{text-align:right;color:#ccc}
.sticky-col{position:sticky;background:inherit;z-index:2}
.col-sep{border-right:2px solid #c8e6c9!important}
.district-row>td{background:#e8f5e9;font-size:12.5px}
.district-row:hover>td{background:#dcedc8}
.customer-row>td{background:#f9fbe7}
.customer-row:hover>td{background:#f1f8e9}
.product-row>td{background:#fff}
.product-row:hover>td{background:#fafafa}
.grand-row>td{background:#c8e6c9;font-weight:700;border-top:2px solid #2e7d32;
              position:sticky;bottom:0;z-index:2}
.total-col{font-weight:600;min-width:80px;background:#f1f8e9}
.tog{background:none;border:none;cursor:pointer;font-size:12px;color:#2e7d32;
     padding:0 4px;line-height:1;vertical-align:middle}
.tog:hover{color:#1b5e20}
@media (max-width:768px){
  .pivot-table td,.pivot-table th{font-size:11px;padding:4px 6px}
  .sticky-col{max-width:72px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .table-wrap{max-height:480px}
}
"""

_JS = """
(function(){
  var tip = document.getElementById('chart-tooltip');
  var activeTip = null;
  function showTip(x, y, lines) {
    if (!lines.length) return;
    tip.innerHTML = lines.join('\\n');
    tip.style.display = 'block';
    var left = x > window.innerWidth / 2 ? x - tip.offsetWidth - 14 : x + 14;
    tip.style.left = Math.max(4, left) + 'px';
    tip.style.top  = Math.max(4, y - 10) + 'px';
  }
  document.querySelectorAll('.bar-item').forEach(function(el){
    el.addEventListener('mousemove', function(e){
      showTip(e.clientX, e.clientY, el.dataset.tip ? el.dataset.tip.split('||') : []);
    });
    el.addEventListener('mouseleave', function(){ tip.style.display = 'none'; });
    el.addEventListener('touchstart', function(e){
      var lines = el.dataset.tip ? el.dataset.tip.split('||') : [];
      if (!lines.length) return;
      if (activeTip === el) {
        tip.style.display = 'none';
        activeTip = null;
      } else {
        var t = e.touches[0];
        showTip(t.clientX, t.clientY, lines);
        activeTip = el;
      }
      e.preventDefault();
    }, {passive: false});
  });
  document.addEventListener('touchstart', function(e){
    if (activeTip && !activeTip.contains(e.target)) {
      tip.style.display = 'none';
      activeTip = null;
    }
  });
})();

function toggleDist(btn, key) {
  var rows = document.querySelectorAll('[data-dist="' + key + '"]');
  var hidden = rows.length > 0 && rows[0].style.display === 'none';
  for (var i = 0; i < rows.length; i++) {
    rows[i].style.display = hidden ? '' : 'none';
  }
  btn.textContent = hidden ? '▾' : '▸';
}
"""


def _exports_product_pivot_html(detail_rows: list, detail_cols: list) -> str:
    """Pivot: Quận/Huyện > Tên khách hàng rows, products as columns — same style as Chi tiết theo ngày."""
    from core.aggregator import is_num

    if not detail_rows or not detail_cols:
        return ""

    district_idx = _find_col(detail_cols, "quận", _GEO_SEMANTIC)
    if district_idx == -1:
        district_idx = _find_col(detail_cols, "huyện", _GEO_SEMANTIC)
    customer_idx = _find_col(detail_cols, "khách", _NAME_SEMANTIC)
    product_idx = _find_col(detail_cols, "tên hàng", _CAT_SEMANTIC)
    qty_idx = next((i for i, c in enumerate(detail_cols) if is_num(c)), -1)

    if any(idx == -1 for idx in (district_idx, customer_idx, product_idx, qty_idx)):
        return ""

    data: dict[str, dict[str, dict[str, float]]] = {}
    product_set: set[str] = set()

    for row in detail_rows:
        if max(district_idx, customer_idx, product_idx, qty_idx) >= len(row):
            continue
        if not isinstance(row[qty_idx], (int, float)):
            continue
        district = str(row[district_idx] or "")
        customer = str(row[customer_idx] or "")
        product = str(row[product_idx] or "")
        data.setdefault(district, {}).setdefault(customer, {})
        data[district][customer][product] = (
            data[district][customer].get(product, 0.0) + float(row[qty_idx])
        )
        product_set.add(product)

    if not data:
        return ""

    product_grand: dict[str, float] = {
        p: sum(c.get(p, 0) for customers in data.values() for c in customers.values())
        for p in product_set
    }
    products = sorted(product_set, key=lambda p: product_grand[p], reverse=True)
    grand_total = sum(product_grand.values())

    w0, w1 = _COL_W[0], _COL_W[1]
    left1 = w0

    th_products = "".join(f'<th class="date-col">{p}</th>' for p in products)

    lines = [
        '<div class="table-wrap">',
        '<table class="pivot-table">',
        f'<thead><tr>'
        f'<th class="sticky-col" style="left:0;min-width:{w0}px">Quận/Huyện</th>'
        f'<th class="sticky-col col-sep" style="left:{left1}px;min-width:{w1}px">Tên khách hàng</th>'
        f'{th_products}<th class="total-col">Tổng</th></tr></thead>',
        '<tbody>',
    ]

    for dist_num, district in enumerate(sorted(data.keys())):
        dk = f"ep{dist_num}"
        customers = data[district]
        d_prods = {p: sum(c.get(p, 0) for c in customers.values()) for p in products}
        d_total = sum(d_prods.values())
        d_cells = "".join(_cell(d_prods[p]) for p in products)
        lines.append(
            f'<tr class="district-row">'
            f'<td colspan="2" class="sticky-col col-sep" style="left:0;min-width:{w0+w1}px">'
            f'<button class="tog" onclick="toggleDist(this,\'{dk}\')">▾</button>'
            f' <strong>{district}</strong></td>'
            f'{d_cells}{_total_cell(d_total, grand_total, bold=True)}</tr>'
        )

        for customer in sorted(customers.keys()):
            prods = customers[customer]
            row_total = sum(prods.values())
            c_cells = "".join(_cell(prods.get(p, 0)) for p in products)
            lines.append(
                f'<tr class="customer-row" data-dist="{dk}">'
                f'<td class="sticky-col" style="left:0;min-width:{w0}px"></td>'
                f'<td class="sticky-col col-sep" style="left:{left1}px;min-width:{w1}px"><em>{customer}</em></td>'
                f'{c_cells}{_total_cell(row_total, grand_total)}</tr>'
            )

    g_cells = "".join(
        f'<td class="num"><strong>{int(product_grand.get(p, 0)):,}</strong></td>'
        for p in products
    )
    lines.append(
        f'<tr class="grand-row">'
        f'<td colspan="2" class="sticky-col col-sep" style="left:0;min-width:{w0+w1}px"><strong>Tổng cộng</strong></td>'
        f'{g_cells}<td class="total-col" style="background:#c8e6c9;text-align:right">'
        f'<strong>{int(grand_total):,}</strong></td></tr>'
    )
    lines += ['</tbody></table></div>']

    return (
        '<div class="section">'
        '<h2>📦 Tổng lượng thực xuất</h2>'
        + "\n".join(lines)
        + '</div>'
    )


def generate(summary: ReportSummary, detail_rows: list, detail_cols: list) -> str:
    """Write the HTML detail report to reports/. Returns the file path as a string."""
    out_dir = _reports_dir()
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / _safe_filename(summary)

    kpi_html = ""
    for section in summary.sections:
        if section.title == "Tổng quan":
            kpis = "".join(
                f'<div class="kpi"><div class="label">{k}</div>'
                f'<div class="value">{v}</div></div>'
                for k, v in section.facts
            )
            kpi_html = f'<div class="kpi-row">{kpis}</div>'
            break

    breakdown_html = ""
    for section in summary.sections:
        if section.title == "Tổng quan":
            continue
        if section.title == "Tổng lượng thực xuất":
            breakdown_html += _exports_product_pivot_html(detail_rows, detail_cols)
            continue
        items = "".join(
            f'<div class="item"><span class="name">{k}</span>'
            f'<span class="qty">{v}</span></div>'
            for k, v in section.facts
        )
        breakdown_html += (
            f'<div class="section"><h2>{section.title}</h2>'
            f'<div class="grid">{items}</div></div>'
        )

    chart_html = (
        _stacked_bar_chart_html(summary.chart_data, summary.mode)
        if summary.chart_data
        else ""
    )
    chart_section = (
        f'<div class="section"><h2>Biểu đồ</h2>{chart_html}</div>'
        if chart_html else ""
    )

    pivot_section = (
        f'<div class="section"><h2>Chi tiết theo ngày</h2>'
        f'{_pivot_table_html(detail_rows, detail_cols)}</div>'
    )

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{summary.title}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="page">
  <header><h1>{summary.title}</h1>
  <p>Báo cáo {summary.mode.value} · {summary.period_label}</p></header>
  {kpi_html}
  {breakdown_html}
  {chart_section}
  {pivot_section}
</div>
<script>{_JS}</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")
    return str(out_path)
