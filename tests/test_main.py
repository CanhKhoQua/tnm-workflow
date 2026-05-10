import pytest
from unittest.mock import patch, MagicMock

from config import Config, ChannelsConfig, ChannelConfig
from models import DailySummary
from main import (
    main,
    _find_period_params,
    _breakdown,
    _wide_breakdown,
    _product_breakdown,
    _classify_dimension,
    _sum_rows,
    _today_sum,
    _merge_breakdown,
)


_CURRENT_PARAM_ID = "abc-current"
_COMPARISON_PARAM_ID = "abc-comparison"

_DATE_COL = {"base_type": "type/Date", "name": "date"}
_NUM_COL = {"base_type": "type/Integer", "name": "quantity"}
_DIM_COL = {"base_type": "type/Text", "name": "product"}
_DISTRICT_COL = {"base_type": "type/Text", "name": "district"}

# Bar chart: long format (date, product, quantity)
_BAR_COLS = [_DATE_COL, _DIM_COL, _NUM_COL]
_BAR_ROWS = [
    ["2026-04-01", "PCB30", 100],
    ["2026-04-01", "PCB40", 200],
    ["2026-04-15", "PCB30", 50],
    ["2026-04-15", "PCB40", 80],
]

# Pivot table: (district, quantity)
_PIVOT_COLS = [_DISTRICT_COL, _NUM_COL]
_PIVOT_ROWS = [
    ["Huyện A", 300],
    ["Huyện B", 130],
    [None, 999],  # null-dimension row (total row) — should be skipped
]

_DASHBOARD = {
    "parameters": [
        {"id": _CURRENT_PARAM_ID, "type": "date/month", "default": "thismonth"},
        {"id": _COMPARISON_PARAM_ID, "type": "date/month", "default": "past1months"},
    ],
    "dashcards": [
        {
            "id": 101,
            "card_id": 42,
            "card": {"name": "Tổng xuất - Bar"},
            "parameter_mappings": [{"parameter_id": _CURRENT_PARAM_ID}],
        },
        {
            "id": 102,
            "card_id": 43,
            "card": {"name": "Tổng xuất Pivot"},
            "parameter_mappings": [{"parameter_id": _CURRENT_PARAM_ID}],
        },
        {
            "id": 103,
            "card_id": 57,
            "card": {"name": "Tổng xuất T-1 - Bar"},
            "parameter_mappings": [{"parameter_id": _COMPARISON_PARAM_ID}],
        },
    ],
}

_COMPARISON_DATA = {
    "rows": [["2026-03-01", "PCB30", 200], ["2026-03-15", "PCB30", 80]],
    "cols": _BAR_COLS,
}


def _cfg(teams=True, zalo=False):
    return Config(
        schedule="0 8 * * 1-5",
        dashboard_id=1,
        collection_id=None,
        dashcard_ids=None,
        channels=ChannelsConfig(
            teams=ChannelConfig(enabled=teams),
            zalo=ChannelConfig(enabled=zalo),
        ),
        metabase_url="http://metabase.local",
        metabase_api_key="key123",
        teams_webhook_url="https://webhook.url",
        zalo_access_token=None,
    )


def test_main_sends_daily_summary_to_teams():
    mock_client = MagicMock()
    mock_client.fetch_dashboard.return_value = _DASHBOARD
    mock_client.fetch_raw_data.side_effect = [
        {"rows": _BAR_ROWS, "cols": _BAR_COLS},
        {"rows": _PIVOT_ROWS, "cols": _PIVOT_COLS},
        {"rows": _COMPARISON_DATA["rows"], "cols": _COMPARISON_DATA["cols"]},
    ]
    mock_teams = MagicMock()

    with patch("main.load_config", return_value=_cfg()), \
         patch("main.MetabaseClient", return_value=mock_client), \
         patch("main.TeamsChannel", return_value=mock_teams):
        main()

    assert mock_teams.send.call_count == 1
    sent = mock_teams.send.call_args[0][0]
    assert isinstance(sent, DailySummary)


def test_main_sections_structure():
    mock_client = MagicMock()
    mock_client.fetch_dashboard.return_value = _DASHBOARD
    mock_client.fetch_raw_data.side_effect = [
        {"rows": _BAR_ROWS, "cols": _BAR_COLS},
        {"rows": _PIVOT_ROWS, "cols": _PIVOT_COLS},
        {"rows": _COMPARISON_DATA["rows"], "cols": _COMPARISON_DATA["cols"]},
    ]
    mock_teams = MagicMock()

    with patch("main.load_config", return_value=_cfg()), \
         patch("main.MetabaseClient", return_value=mock_client), \
         patch("main.TeamsChannel", return_value=mock_teams):
        main()

    sent: DailySummary = mock_teams.send.call_args[0][0]
    titles = [s.title for s in sent.sections]
    assert "Tổng quan" in titles
    assert "Theo mặt hàng" in titles
    assert "Theo quận/huyện" in titles


def test_main_mtd_and_last_month_totals():
    mock_client = MagicMock()
    mock_client.fetch_dashboard.return_value = _DASHBOARD
    mock_client.fetch_raw_data.side_effect = [
        {"rows": _BAR_ROWS, "cols": _BAR_COLS},
        {"rows": _PIVOT_ROWS, "cols": _PIVOT_COLS},
        {"rows": _COMPARISON_DATA["rows"], "cols": _COMPARISON_DATA["cols"]},
    ]
    mock_teams = MagicMock()

    with patch("main.load_config", return_value=_cfg()), \
         patch("main.MetabaseClient", return_value=mock_client), \
         patch("main.TeamsChannel", return_value=mock_teams):
        main()

    sent: DailySummary = mock_teams.send.call_args[0][0]
    overview = dict(sent.sections[0].facts)
    assert overview["MTD (tháng này)"] == "430"   # 100+200+50+80
    assert overview["Tháng trước (MTD)"] == "280"  # 200+80


def test_main_does_not_call_zalo_when_disabled():
    mock_client = MagicMock()
    mock_client.fetch_dashboard.return_value = {
        "parameters": [],
        "dashcards": [
            {
                "id": 101,
                "card_id": 42,
                "card": {"name": "Total"},
                "parameter_mappings": [],
            }
        ],
    }
    mock_client.fetch_raw_data.return_value = {"rows": _BAR_ROWS, "cols": _BAR_COLS}
    mock_zalo = MagicMock()

    with patch("main.load_config", return_value=_cfg(teams=False, zalo=False)), \
         patch("main.MetabaseClient", return_value=mock_client), \
         patch("main.ZaloChannel", return_value=mock_zalo):
        main()

    mock_zalo.send.assert_not_called()


def test_main_exits_on_metabase_failure():
    mock_client = MagicMock()
    mock_client.fetch_dashboard.side_effect = Exception("Connection refused")

    with patch("main.load_config", return_value=_cfg()), \
         patch("main.MetabaseClient", return_value=mock_client):
        with pytest.raises(SystemExit):
            main()


# --- Unit tests for helper functions ---

def test_find_period_params_detects_thismonth():
    params = [
        {"id": "aaa", "default": "thismonth"},
        {"id": "bbb", "default": "past1months"},
    ]
    current, comparison = _find_period_params(params)
    assert current == "aaa"
    assert comparison == "bbb"


def test_find_period_params_returns_none_when_missing():
    current, comparison = _find_period_params([])
    assert current is None
    assert comparison is None


def test_sum_rows_sums_numeric_columns():
    rows = [[10, 20], [30, 40]]
    cols = [_NUM_COL, _NUM_COL]
    assert _sum_rows(rows, cols) == 100


def test_today_sum_filters_by_date():
    rows = [["2026-04-27", 50], ["2026-04-01", 100]]
    cols = [_DATE_COL, _NUM_COL]
    assert _today_sum(rows, cols, "2026-04-27") == 50


def test_breakdown_groups_by_dimension():
    rows = [["PCB30", 100], ["PCB40", 200], ["PCB30", 50]]
    cols = [_DIM_COL, _NUM_COL]
    result = _breakdown(rows, cols)
    assert result[0] == ("PCB40", "200")
    assert result[1] == ("PCB30", "150")


def test_breakdown_labels_null_dimension_rows_as_unknown():
    rows = [["Huyện A", 300], [None, 999], ["Huyện B", 100]]
    cols = [_DISTRICT_COL, _NUM_COL]
    result = dict(_breakdown(rows, cols))
    assert "Huyện A" in result
    assert "Huyện B" in result
    assert "?" in result
    assert result["?"] == "999"


def test_wide_breakdown_uses_column_names():
    pcb30 = {"base_type": "type/Integer", "name": "PCB30", "display_name": "PCB30"}
    pcb40 = {"base_type": "type/Integer", "name": "PCB40", "display_name": "PCB40"}
    rows = [["2026-04-01", 100, 200], ["2026-04-02", 50, 80]]
    cols = [_DATE_COL, pcb30, pcb40]
    result = dict(_wide_breakdown(rows, cols))
    assert result["PCB40"] == "280"
    assert result["PCB30"] == "150"


def test_product_breakdown_uses_long_format_when_dim_exists():
    rows = [
        ["2026-04-01", "PCB30", 100],
        ["2026-04-01", "PCB40", 200],
    ]
    result = dict(_product_breakdown(rows, _BAR_COLS))
    assert result["PCB30"] == "100"
    assert result["PCB40"] == "200"


def test_product_breakdown_uses_wide_format_when_no_dim():
    pcb30 = {"base_type": "type/Integer", "name": "PCB30", "display_name": "PCB30"}
    pcb40 = {"base_type": "type/Integer", "name": "PCB40", "display_name": "PCB40"}
    rows = [["2026-04-01", 100, 200]]
    cols = [_DATE_COL, pcb30, pcb40]
    result = dict(_product_breakdown(rows, cols))
    assert result["PCB30"] == "100"
    assert result["PCB40"] == "200"


def test_classify_dimension_detects_district():
    rows = [["Huyện Gò Công Đông", 100], ["Thành phố Gò Công", 50]]
    cols = [_DISTRICT_COL, _NUM_COL]
    assert _classify_dimension(rows, cols) == "district"


def test_classify_dimension_detects_product():
    rows = [["PCB30", 100], ["PCB40", 200]]
    cols = [_DIM_COL, _NUM_COL]
    assert _classify_dimension(rows, cols) == "product"


def test_classify_dimension_returns_product_when_no_dim():
    rows = [["2026-04-01", 100]]
    cols = [_DATE_COL, _NUM_COL]
    assert _classify_dimension(rows, cols) == "product"


def test_main_districts_do_not_appear_in_product_section():
    district_bar_rows = [
        ["2026-04-01", "Huyện Gò Công Đông", 300],
        ["2026-04-01", "Thành phố Gò Công", 100],
    ]
    product_pivot_rows = [["PCB30", 150], ["PCB40", 200]]
    product_pivot_cols = [_DIM_COL, _NUM_COL]

    mock_client = MagicMock()
    mock_client.fetch_dashboard.return_value = {
        "parameters": [
            {"id": _CURRENT_PARAM_ID, "type": "date/month", "default": "thismonth"},
        ],
        "dashcards": [
            {
                "id": 101,
                "card_id": 42,
                "card": {"name": "By District - Bar"},
                "parameter_mappings": [{"parameter_id": _CURRENT_PARAM_ID}],
            },
            {
                "id": 102,
                "card_id": 43,
                "card": {"name": "By Product"},
                "parameter_mappings": [{"parameter_id": _CURRENT_PARAM_ID}],
            },
        ],
    }
    mock_client.fetch_raw_data.side_effect = [
        {"rows": district_bar_rows, "cols": _BAR_COLS},
        {"rows": product_pivot_rows, "cols": product_pivot_cols},
    ]
    mock_teams = MagicMock()

    with patch("main.load_config", return_value=_cfg()), \
         patch("main.MetabaseClient", return_value=mock_client), \
         patch("main.TeamsChannel", return_value=mock_teams):
        main()

    sent: DailySummary = mock_teams.send.call_args[0][0]
    section_map = {s.title: dict(s.facts) for s in sent.sections}

    assert "Theo mặt hàng" in section_map
    assert "Theo quận/huyện" in section_map
    assert "PCB30" in section_map["Theo mặt hàng"]
    assert "Huyện Gò Công Đông" not in section_map["Theo mặt hàng"]
    assert "Huyện Gò Công Đông" in section_map["Theo quận/huyện"]


def test_merge_breakdown_combines_values():
    existing = [("A", "100"), ("B", "200")]
    new = [("B", "50"), ("C", "75")]
    merged = dict(_merge_breakdown(existing, new))
    assert merged["A"] == "100"
    assert merged["B"] == "250"
    assert merged["C"] == "75"
