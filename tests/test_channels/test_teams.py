import json

import responses as responses_lib
from models import CardData, DashboardMessage
from channels.teams import TeamsChannel

WEBHOOK = "https://outlook.office.com/webhook/test"


def _msg():
    return DashboardMessage(
        title="Daily Sales Dashboard — 2026-04-27",
        cards=[
            CardData(label="Total Sales", value="$12,500", image_bytes=b"png"),
            CardData(label="Revenue", value="$8,200", image_bytes=None),
        ],
    )


@responses_lib.activate
def test_teams_posts_to_webhook_url():
    responses_lib.add(responses_lib.POST, WEBHOOK, json={"result": "ok"}, status=200)
    TeamsChannel(WEBHOOK).send(_msg())
    assert len(responses_lib.calls) == 1


@responses_lib.activate
def test_teams_payload_contains_title():
    responses_lib.add(responses_lib.POST, WEBHOOK, json={"result": "ok"}, status=200)
    TeamsChannel(WEBHOOK).send(_msg())
    body = json.loads(responses_lib.calls[0].request.body)
    blocks = body["attachments"][0]["content"]["body"]
    titles = [b["text"] for b in blocks if b.get("type") == "TextBlock"]
    assert "Daily Sales Dashboard — 2026-04-27" in titles


@responses_lib.activate
def test_teams_payload_contains_card_facts():
    responses_lib.add(responses_lib.POST, WEBHOOK, json={"result": "ok"}, status=200)
    TeamsChannel(WEBHOOK).send(_msg())
    body = json.loads(responses_lib.calls[0].request.body)
    blocks = body["attachments"][0]["content"]["body"]
    facts = [b for b in blocks if b.get("type") == "FactSet"][0]["facts"]
    assert {"title": "Total Sales", "value": "$12,500"} in facts
    assert {"title": "Revenue", "value": "$8,200"} in facts
