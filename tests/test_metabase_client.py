import pytest
import requests as req
import responses
from metabase_client import MetabaseClient

URL = "http://metabase.local"
KEY = "test-api-key"


@responses.activate
def test_fetch_dashboard_returns_json():
    responses.add(
        responses.GET,
        f"{URL}/api/dashboard/1",
        json={"id": 1, "name": "Sales", "dashcards": []},
        status=200,
    )
    result = MetabaseClient(URL, KEY).fetch_dashboard(1)
    assert result["id"] == 1
    assert result["dashcards"] == []


@responses.activate
def test_fetch_dashcard_value_returns_first_cell():
    responses.add(
        responses.POST,
        f"{URL}/api/dashboard/1/dashcard/101/card/42/query",
        json={"data": {"rows": [["$12,500"]], "cols": [{"name": "Total"}]}},
        status=200,
    )
    assert MetabaseClient(URL, KEY).fetch_dashcard_value(1, 101, 42) == "$12,500"


@responses.activate
def test_fetch_dashcard_value_returns_na_when_no_rows():
    responses.add(
        responses.POST,
        f"{URL}/api/dashboard/1/dashcard/101/card/42/query",
        json={"data": {"rows": [], "cols": []}},
        status=200,
    )
    assert MetabaseClient(URL, KEY).fetch_dashcard_value(1, 101, 42) == "N/A"


@responses.activate
def test_fetch_dashcard_value_returns_na_when_row_is_empty():
    responses.add(
        responses.POST,
        f"{URL}/api/dashboard/1/dashcard/101/card/42/query",
        json={"data": {"rows": [[]], "cols": []}},
        status=200,
    )
    assert MetabaseClient(URL, KEY).fetch_dashcard_value(1, 101, 42) == "N/A"


@responses.activate
def test_fetch_dashcard_value_raises_on_http_error():
    responses.add(
        responses.POST,
        f"{URL}/api/dashboard/1/dashcard/101/card/42/query",
        status=401,
    )
    with pytest.raises(req.exceptions.HTTPError):
        MetabaseClient(URL, KEY).fetch_dashcard_value(1, 101, 42)


@responses.activate
def test_export_card_image_returns_bytes():
    responses.add(
        responses.POST,
        f"{URL}/api/card/42/query/png",
        body=b"fake-png-bytes",
        status=200,
        content_type="image/png",
    )
    assert MetabaseClient(URL, KEY).export_card_image(42) == b"fake-png-bytes"


@responses.activate
def test_api_key_sent_as_header():
    responses.add(
        responses.POST,
        f"{URL}/api/dashboard/1/dashcard/101/card/42/query",
        json={"data": {"rows": [["100"]], "cols": []}},
        status=200,
    )
    MetabaseClient(URL, KEY).fetch_dashcard_value(1, 101, 42)
    assert responses.calls[0].request.headers["X-API-KEY"] == KEY
