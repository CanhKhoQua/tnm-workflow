import logging

from models import CardData, DashboardMessage
from channels.zalo import ZaloChannel


def _msg():
    return DashboardMessage(
        title="Daily Sales Dashboard — 2026-04-27",
        cards=[CardData(label="Total Sales", value="$12,500", image_bytes=None)],
    )


def test_zalo_logs_skip_message(caplog):
    with caplog.at_level(logging.INFO):
        ZaloChannel(access_token="").send(_msg())
    assert "Zalo" in caplog.text


def test_zalo_send_does_not_raise():
    ZaloChannel(access_token="").send(_msg())
