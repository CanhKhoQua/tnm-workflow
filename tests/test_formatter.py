from unittest.mock import patch
from models import CardData
from formatter import build_message


def test_build_message_title_includes_today():
    with patch("formatter.date") as mock_date:
        mock_date.today.return_value.strftime.return_value = "2026-04-27"
        msg = build_message([CardData(label="Sales", value="$100", image_bytes=None)])
    assert "2026-04-27" in msg.title


def test_build_message_includes_all_cards():
    cards = [
        CardData(label="Total Sales", value="$12,500", image_bytes=None),
        CardData(label="Revenue", value="$8,200", image_bytes=b"png"),
    ]
    msg = build_message(cards)
    assert len(msg.cards) == 2
    assert msg.cards[0].label == "Total Sales"
    assert msg.cards[1].label == "Revenue"


def test_build_message_preserves_image_bytes():
    msg = build_message([CardData(label="Sales", value="$100", image_bytes=b"png-data")])
    assert msg.cards[0].image_bytes == b"png-data"
