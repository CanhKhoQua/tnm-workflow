# TNM Workflow — Implementation Plan (As-Built)

**Goal:** Automated daily sales dashboard — fetches Metabase data, formats it, and delivers to Microsoft Teams on a schedule via n8n.

**Architecture:** n8n (Docker) → HTTP POST → Flask webapp → subprocess `python main.py` → Metabase API → Teams Adaptive Card.

**Tech Stack:** Python 3.12, Flask, pytest, requests, pyyaml, python-dotenv, n8n (Docker)

---

## File Map

| File | Responsibility |
|---|---|
| `scripts/main.py` | Entry point: reads config, fetches dashboard data, aggregates, sends |
| `scripts/config.py` | Loads `configs/<name>.yaml` + `.env` into frozen `Config` dataclass |
| `scripts/metabase_client.py` | Metabase API: `fetch_dashboard`, `fetch_raw_data`, `fetch_dashcard_value` |
| `scripts/models.py` | `DailySummary`, `Section`, `DashboardMessage` dataclasses |
| `scripts/channels/base.py` | Abstract `BaseChannel.send(message)` |
| `scripts/channels/teams.py` | Teams Incoming Webhook — Adaptive Card v1.5 builder |
| `scripts/channels/zalo.py` | Zalo stub — logs and skips |
| `scripts/webapp/app.py` | Flask app: web UI + `/workflow/<name>/run` API endpoint |
| `scripts/webapp/templates/` | Jinja2 HTML templates (index, edit) |
| `tests/test_main.py` | Integration tests for main pipeline |
| `tests/test_metabase_client.py` | Unit tests for Metabase client (mocked HTTP) |
| `tests/test_config.py` | Unit tests for config loader |
| `configs/<name>.yaml` | Per-workflow config — gitignored (contains webhook URL) |
| `workflows/Teams_webhook.json` | n8n workflow JSON — version controlled |
| `docker-compose.yml` | Runs `webapp` (Flask :5000) + `n8n` (:5678) |
| `Dockerfile` | Flask webapp container image |
| `requirements.txt` | Python dependencies |
| `pytest.ini` | pytest config — testpaths + pythonpath |
| `.env.example` | Template for `.env` |
| `.gitignore` | Excludes `.env`, `configs/`, caches |

---

## Phase 1 — Core Pipeline

### 1. Models (`scripts/models.py`)

Frozen dataclasses:
- `Section(title, facts: tuple[tuple[str,str], ...])` — one dashboard section
- `DailySummary(title, sections, chart_data)` — full message sent to channels
- `DashboardMessage` — legacy simple format (cards list)

### 2. Config Loader (`scripts/config.py`)

Reads `configs/<name>.yaml` + environment variables into a frozen `Config`:

```python
Config(
    schedule,          # cron string (informational only)
    dashboard_id,      # int
    collection_id,     # int | None — filter dashcards by collection
    dashcard_ids,      # tuple[int,...] | None — filter by specific dashcard IDs
    channels,          # ChannelsConfig(teams, zalo)
    metabase_url,      # from METABASE_URL env var
    metabase_api_key,  # from METABASE_API_KEY env var
    teams_webhook_url, # from YAML or TEAMS_WEBHOOK_URL env var
    zalo_access_token, # from YAML or ZALO_ACCESS_TOKEN env var
)
```

Validates: raises `ValueError` if a channel is enabled but its credential is missing.

### 3. Metabase Client (`scripts/metabase_client.py`)

Auth via `X-API-KEY` header on a shared `requests.Session`.

Key methods:
- `fetch_dashboard(dashboard_id)` — `GET /api/dashboard/{id}`, returns full dashboard dict
- `fetch_raw_data(dashboard_id, dashcard_id, card_id, parameters)` — POST query, returns `{rows, cols}`
- `fetch_dashcard_value(...)` — POST query, returns aggregated numeric string
- `export_card_image(card_id)` — `POST /api/card/{id}/query/png`, returns bytes or None on 404

### 4. Main Pipeline (`scripts/main.py`)

1. Load config + create `MetabaseClient`
2. Fetch dashboard metadata → extract parameters and dashcard list
3. Filter dashcards by `dashcard_ids` or `collection_id` if set
4. For each dashcard, POST query with dashboard default parameters
5. Aggregate `rows`/`cols` per dashcard:
   - Detect pivot tables via `pivot-grouping` column
   - Detect date columns by `base_type`
   - Detect numeric columns by `base_type`
   - Classify dimension as "district" or "product" by Vietnamese prefix matching
   - Accumulate MTD total, today total, last-month total
   - Build product and district breakdowns
   - Build 7-day grouped bar chart data
6. Construct `DailySummary` with sections
7. Send via each enabled channel

### 5. Teams Channel (`scripts/channels/teams.py`)

Builds Adaptive Card v1.5 payload with `msteams.width: Full`:
- Emphasis header container (dashboard name + date)
- Overview: KPI columns (MTD, Hôm nay) + last-month full-width row
- Products: 2-per-row grid, top 6 visible + toggle for rest
- Districts: 70/30 columns, top district highlighted green
- Chart: `Chart.VerticalBar.Grouped` — last 7 days, one series per product

---

## Phase 2 — Web UI + Docker

### 6. Flask Webapp (`scripts/webapp/app.py`)

**Config management UI** — create, edit, delete `configs/<name>.yaml` via browser.

Edit form uses live Metabase API dropdowns:
- `GET /api/dashboards` — list available dashboards
- `GET /api/dashboard/<id>/dashcards` — list dashcards for picker

**Run endpoint (called by n8n):**
```
POST /workflow/<name>/run
→ subprocess: python main.py --config configs/<name>.yaml
→ returns: {"ok": bool, "stdout": str, "stderr": str, "elapsed": float}
```

### 7. Docker (`docker-compose.yml` + `Dockerfile`)

Two services on a shared Docker network:
- `webapp` — Flask, port 5000, mounts project root as volume
- `n8n` — n8n 1.91.3, port 5678, `n8n_data` named volume for persistence

n8n calls `http://webapp:5000/...` (internal hostname).

---

## Phase 3 — n8n Workflow

### 8. Workflow JSON (`workflows/Teams_webhook.json`)

One Schedule Trigger fans out to multiple HTTP Request nodes in parallel:

```
Schedule Trigger ─┬─► POST /workflow/West/run
                  └─► POST /workflow/East/run
```

**To add a new workflow config:**
1. Create `configs/<NewName>.yaml`
2. Add an HTTP Request node in n8n pointing to `/workflow/<NewName>/run`
3. Export workflow JSON → save to `workflows/` → commit

---

## Setup on a New Machine

```bash
# 1. Clone repo
git clone <repo-url>
cd tnm-workflow

# 2. Create .env
cp .env.example .env
# Edit: METABASE_URL, METABASE_API_KEY, N8N_BASIC_AUTH_USER, N8N_BASIC_AUTH_PASSWORD

# 3. Create configs/ (gitignored — copy manually or via webapp UI)
mkdir configs

# 4. Start services
docker compose up -d

# 5. Open webapp at http://localhost:5000 — create workflow configs
# 6. Open n8n at http://localhost:5678 — import workflows/Teams_webhook.json
# 7. Activate workflow in n8n
```

---

## What Was Removed / Never Built

| Item | Reason |
|---|---|
| `templates/daily-dashboard.json.j2` | Obsolete — Jinja2 approach replaced by HTTP-based n8n |
| `built_workflows/` | Obsolete — workflows exported directly from n8n UI |
| `pulled_workflows/` | Never used |
| `build_workflow.py` | Never implemented |
| `formatter.py` | Removed — never imported; formatting is done inline in channels |
| `scripts/pick_dashboard.py` | Removed — never imported; config is managed via YAML directly |
| `scripts/explore_metabase.py` | Removed — dev/debug utility, not part of the production pipeline |
| `config.yaml` (root) | Replaced by `configs/<name>.yaml` per-workflow pattern |
| `scripts/pick_cards.py` | Replaced by `scripts/pick_dashboard.py` (also removed) |
