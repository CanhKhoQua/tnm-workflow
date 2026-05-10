# TNM Workflow — Daily Dashboard Automation Design

**Goal:** Automatically fetch sales data from Metabase dashboards and send a formatted daily report to Microsoft Teams (and optionally Zalo) on a schedule.

**Architecture:** n8n (self-hosted via Docker) triggers on a cron schedule and calls the Flask webapp via HTTP. The Flask webapp runs `scripts/main.py` as a subprocess. Python handles all logic: Metabase API queries, data aggregation, message formatting, and channel delivery. n8n workflow JSON files are version-controlled in `workflows/`.

**Tech Stack:** Python 3.12, Flask, n8n (Docker), Metabase API, Teams Incoming Webhook (Adaptive Card v1.5), Zalo OA (stubbed)

---

## Project Structure

```
tnm-workflow/
├── scripts/
│   ├── main.py                   # Entry point: fetch → aggregate → send pipeline
│   ├── config.py                 # Loads per-workflow YAML + .env into typed Config
│   ├── metabase_client.py        # Metabase API: fetch dashboard, dashcard raw data
│   ├── models.py                 # DailySummary, Section, DashboardMessage dataclasses
│   ├── channels/
│   │   ├── base.py               # Abstract BaseChannel: send(message)
│   │   ├── teams.py              # Teams Incoming Webhook (Adaptive Card v1.5)
│   │   └── zalo.py               # Zalo stub — logs and skips until API configured
│   └── webapp/
│       ├── app.py                # Flask app: web UI + /workflow/<name>/run API
│       └── templates/            # Jinja2 HTML templates (index, edit)
├── configs/                      # Per-workflow YAML configs — gitignored
│   └── <name>.yaml               # e.g. West.yaml, East.yaml
├── workflows/                    # n8n workflow JSON files — version controlled
│   └── Teams_webhook.json
├── tests/                        # pytest test suite
├── docker-compose.yml            # Runs webapp (Flask) + n8n
├── Dockerfile                    # Flask webapp container image
├── requirements.txt
├── .env                          # Secrets: Metabase credentials, n8n auth — gitignored
├── .env.example
└── .gitignore
```

---

## Configuration

### `configs/<name>.yaml` — Per-workflow settings (gitignored)

```yaml
schedule: "0 8 * * 1-5"       # Cron expression (informational — n8n holds the actual trigger)
dashboard_id: 3                 # Metabase dashboard ID
collection_id: null             # Filter dashcards by collection ID (optional)
dashcard_ids:                   # Specific dashcard IDs to include (null = all)
  - 40
  - 41
channels:
  teams:
    enabled: true
  zalo:
    enabled: false
teams_webhook_url: https://...  # Power Automate or Office 365 incoming webhook URL
zalo_access_token: ""
```

### `.env` — Secrets (never committed)

```
METABASE_URL=http://your-metabase.com
METABASE_API_KEY=your-api-key-here
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=changeme
```

---

## Data Flow

```
1. n8n Schedule Trigger fires (cron per workflow config)
   ↓
2. n8n HTTP Request → POST http://webapp:5000/workflow/<name>/run
   ↓
3. Flask webapp (app.py) spawns subprocess:
   python main.py --config configs/<name>.yaml
   ↓
4. main.py loads Config from YAML + env, creates MetabaseClient
   ↓
5. MetabaseClient fetches dashboard metadata
   GET /api/dashboard/{id}
   → dashcard list, parameters, date filter defaults
   ↓
6. For each matching dashcard:
   POST /api/dashboard/{id}/dashcard/{dc_id}/card/{card_id}/query
   → {data: {rows, cols}}
   ↓
7. main.py aggregates raw data:
   → MTD total, today total, last-month MTD total
   → product breakdown (by first non-date dimension column)
   → district breakdown (detected by Vietnamese prefix matching)
   → 7-day grouped bar chart data
   ↓
8. Builds DailySummary:
   → Section "Tổng quan":   MTD / Hôm nay / Tháng trước KPIs
   → Section "Theo mặt hàng": product totals grid
   → Section "Theo quận/huyện": district totals list
   → chart_data block (Chart.VerticalBar.Grouped)
   ↓
9. TeamsChannel sends Adaptive Card v1.5 to webhook URL
   ↓
10. Flask returns JSON {"ok": true/false, "stdout": ..., "elapsed": ...}
    n8n marks run success or failure
```

**Error handling:** Non-zero exit from `main.py` → Flask returns `{"ok": false}` → n8n marks run failed (can be configured to retry or alert).

---

## n8n Workflow Design

Workflow JSON files live in `workflows/` and are imported into n8n via the UI (**⋯ → Import from file**). One workflow can trigger multiple configs in parallel by connecting one Schedule Trigger to multiple HTTP Request nodes.

**Current workflow (`workflows/Teams_webhook.json`):**
```
Schedule Trigger ─┬─► HTTP Request → POST /workflow/West/run
                  └─► HTTP Request → POST /workflow/East/run
```

To add a new config (e.g. North): add `configs/North.yaml`, add a new HTTP Request node in n8n, re-export JSON to `workflows/`.

---

## Flask Webapp

Runs at `http://localhost:5000`. Two responsibilities:

**Web UI** — CRUD for workflow configs:
- `GET /` — list all configs
- `GET /workflow/new` — create form
- `GET /workflow/<name>` — edit form
- `POST /workflow/save` — save config YAML
- `POST /workflow/<name>/delete` — delete config

**Run API** (called by n8n):
- `POST /workflow/<name>/run` — runs `main.py --config configs/<name>.yaml`, returns `{"ok", "stdout", "stderr", "elapsed"}`

**Helper APIs** (used by edit form dropdowns):
- `GET /api/dashboards` — list Metabase dashboards
- `GET /api/dashboard/<id>/dashcards` — list dashcards for a dashboard

---

## Teams Message Format

Adaptive Card v1.5 with `msteams.width: Full`:

| Section | Format |
|---|---|
| Header | Emphasis container: dashboard name + date |
| Tổng quan | Two KPI columns (MTD / Hôm nay) + full-width last-month row |
| Theo mặt hàng | 2-per-row grid; top 6 visible, rest behind toggle |
| Theo quận/huyện | 70/30 column rows; top district highlighted green |
| Chart | `Chart.VerticalBar.Grouped` — last 7 days, one series per product |

---

## Metabase API Integration

- **Auth:** `X-API-KEY` header on every request (no session token needed)
- **Dashboard metadata:** `GET /api/dashboard/{id}` → dashcards list + parameters
- **Card data:** `POST /api/dashboard/{id}/dashcard/{dc_id}/card/{card_id}/query` → `{data: {rows, cols}}`
- **Dashboard parameters** (date filters with defaults) are forwarded as `parameters[]` in request body

---

## Channel Architecture

Each channel extends `BaseChannel`:

```python
class BaseChannel:
    def send(self, message: DailySummary) -> None: ...
```

Adding a new channel (e.g. Slack): create `scripts/channels/slack.py` + add toggle to `configs/<name>.yaml`. No changes to `main.py`.

---

## Decisions Deferred

| Decision | Current state | Next step |
|---|---|---|
| Zalo API | Stubbed — logs and skips | Implement when OA account is configured |
| n8n error alerting | No failure notification | Add IF node + Teams/email alert on failure |
| Hosting | Local Docker | Move to server/VM when needed |
