from models import CardData, DashboardMessage


def test_card_data_stores_all_fields():
    card = CardData(label="Total Sales", value="$12,500", image_bytes=b"fake-png")
    assert card.label == "Total Sales"
    assert card.value == "$12,500"
    assert card.image_bytes == b"fake-png"


def test_card_data_image_bytes_defaults_to_none():
    card = CardData(label="Total Sales", value="$12,500")
    assert card.image_bytes is None


def test_card_data_image_bytes_can_be_set_to_none():
    card = CardData(label="Total Sales", value="$12,500", image_bytes=None)
    assert card.image_bytes is None


def test_dashboard_message_holds_title_and_cards():
    cards = [CardData(label="Sales", value="$100")]
    msg = DashboardMessage(title="Daily Dashboard — 2026-04-27", cards=cards)
    assert msg.title == "Daily Dashboard — 2026-04-27"
    assert len(msg.cards) == 1
    assert msg.cards[0].label == "Sales"
    assert msg.cards[0].value == "$100"


def test_dashboard_message_with_empty_cards():
    msg = DashboardMessage(title="Empty Dashboard", cards=[])
    assert msg.cards == ()
