# tnm-workflow

Automated sales reporting — fetches data from Metabase and sends formatted daily, weekly, and monthly reports to Microsoft Teams and/or Zalo, with an HTML report viewable via the webapp or hosted on Cloudflare R2.

**Stack:** Python 3.12 · Flask · APScheduler · Docker · Metabase API · Teams Adaptive Card · Cloudflare R2 · Claude Code

---

## How It Works

```
APScheduler (built into Flask, per-workflow cron)
  → python main.py --config configs/<name>.yaml --mode daily|weekly|monthly
    → Metabase API (fetch dashboard cards in parallel)
    → Generate HTML report → save to reports/ (+ optional R2 upload)
    → Teams Adaptive Card + Zalo message (with link to report)
```

- **Flask webapp** provides a UI to manage workflows, configure schedules, view reports, and trigger runs manually
- **APScheduler** runs inside Flask — each workflow has its own cron job configured via the UI
- **Python scripts** fetch data, aggregate it, generate an HTML report, and send to channels
- **Cloudflare R2** (optional) hosts HTML reports publicly so Teams cards can link to them

---

## Quick Start

### Prerequisites

- Python 3.10+ and pip
- Node.js 18+ and npm (for pm2)
- A running Metabase instance with an API key
- A Microsoft Teams incoming webhook URL

### 1. Clone and configure

```bash
git clone <repo-url>
cd tnm-workflow
cp .env.example .env
```

Edit `.env`:
```
METABASE_URL=http://your-metabase.com
METABASE_API_KEY=your-api-key-here

# Optional: Cloudflare R2 for public report hosting
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=
R2_PUBLIC_URL=
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Start the app

**Option A — pm2 (recommended: auto-starts on boot for Linux)**

Install pm2 once:
```bash
npm install -g pm2
```

Start and register:
```bash
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup / pm2 resurrect
```

> `pm2 startup` prints a command — copy and run it once. This registers pm2 with Windows Task Scheduler so the app restarts automatically after every reboot.

**Option B — Docker (recommended for servers)**
```bash
docker compose up -d
```

**Option C — manual (development only)**
```bash
cd scripts
python webapp/app.py
```

The webapp runs on **http://localhost:5000**.

### 4. Create a workflow

Open **http://localhost:5000** → click **New Workflow**.

Fill in:
- **Workflow name** — used as the config filename (e.g. `East`, `West`)
- **Dashboard ID** — select from the Metabase dropdown
- **Dashcard IDs** — leave empty for all, or pick specific cards via the selector
- **Schedule** — enable and set mode (daily / weekly / monthly), day, and time (ICT)
- **Teams webhook URL** — your incoming webhook URL
- **Report URL** — base URL of this webapp (e.g. `http://your-server:5000`); used for the "Xem chi tiết" link in Teams cards. Leave blank if using R2.

### 5. Test manually

In the webapp: select a mode → click **Run Now**.

---

## pm2 Management

After first start, use these commands:

```bash
pm2 status                        # View running processes
pm2 logs tnm-workflow-5000        # View app logs
pm2 restart tnm-workflow-5000     # Restart after code changes
pm2 stop tnm-workflow-5000        # Stop
pm2 start tnm-workflow-5000       # Start again
pm2 monit                         # Live monitor panel
```

If you update `ecosystem.config.cjs`:
```bash
pm2 delete tnm-workflow-5000
pm2 start ecosystem.config.cjs
pm2 save
```

---

## Report Output

Each run generates:

1. **HTML report** saved to `reports/` — KPI cards, stacked bar chart (per product, unique colours, hover/tap tooltips), and a pivot table (district → customer × date or district → customer × product). Responsive for desktop and mobile.
2. **Teams Adaptive Card** with KPIs and a link to the HTML report
3. **Zalo message** (if enabled)

Reports are accessible at:
- `http://localhost:5000/reports` — list all reports
- `http://localhost:5000/reports/<filename>.html` — view a specific report
- Or via Cloudflare R2 public URL if R2 is configured

---

## Project Structure

```
tnm-workflow/
├── scripts/
│   ├── main.py                  # Entry point: --config --mode daily|weekly|monthly
│   ├── config.py                # Config loader (YAML + env)
│   ├── metabase_client.py       # Metabase API client
│   ├── models.py                # ReportSummary, Section dataclasses
│   ├── core/
│   │   ├── aggregator.py        # Parallel Metabase fetch + data aggregation
│   │   ├── builder.py           # Build ReportSummary from aggregated data
│   │   ├── html_report.py       # Generate HTML report (chart + pivot table)
│   │   └── storage.py           # Cloudflare R2 upload
│   ├── channels/
│   │   ├── teams.py             # Teams Adaptive Card sender
│   │   └── zalo.py              # Zalo sender
│   └── webapp/
│       ├── app.py               # Flask UI + APScheduler + run API + reports
│       └── templates/
├── configs/                     # Per-workflow YAML — gitignored (contains secrets)
├── reports/                     # Generated HTML reports — gitignored
├── ecosystem.config.cjs         # pm2 process config
├── start.cjs                    # Node wrapper to spawn Python (used by pm2)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Workflow Config (`configs/<name>.yaml`)

Managed via the webapp UI. Example:

```yaml
schedule_enabled: true
mode: weekly          # daily | weekly | monthly
hour: 17
minute: 0
day_of_week: mon      # weekly only: mon tue wed thu fri sat sun
day: 1                # monthly only: 1–28
dashboard_id: 6
dashcard_ids:         # null = include all dashcards on the dashboard
  - 58
  - 59
channels:
  teams:
    enabled: true
  zalo:
    enabled: false
teams_webhook_url: https://...
zalo_access_token: ""
webapp_url: http://your-server:5000   # optional: base URL for report links
```

`configs/` is gitignored — copy YAML files manually when moving to a new machine.

---

## Report Modes

| Mode | Period | Typical schedule |
|---|---|---|
| `daily` | Yesterday | Every weekday at 17:00 |
| `weekly` | Last ISO week (Mon–Sun) | Every Monday at 17:00 |
| `monthly` | Previous calendar month | 1st of each month at 17:00 |

---

## Cloudflare R2 Setup (Optional)

R2 lets you host HTML reports publicly without exposing the Flask webapp.

1. Create an R2 bucket in the Cloudflare dashboard
2. Enable public access and note the public URL
3. Create an API token with **Workers R2 Storage: Edit** permission
4. Add to `.env`:
```
R2_ACCOUNT_ID=your-account-id
R2_ACCESS_KEY_ID=your-access-key
R2_SECRET_ACCESS_KEY=your-secret-key
R2_BUCKET_NAME=your-bucket-name
R2_PUBLIC_URL=https://pub-xxx.r2.dev
```

Reports are uploaded automatically and linked from Teams cards.

---

## Transferring to a New Machine

Requirements: Python 3.10+, Node.js 18+, npm.

```bash
git clone <repo-url>
cd tnm-workflow
cp .env.example .env              # Fill in real secrets
mkdir configs                     # Copy your *.yaml config files here manually
pip install -r requirements.txt
npm install -g pm2
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup                       # Copy and run the printed command once
```

Schedules are stored in `configs/*.yaml` and restored automatically when the app starts.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest
```

---

## Adding a New Workflow (New Business / Region)

1. Open the webapp → **New Workflow**
2. Fill in the Metabase dashboard ID, dashcard IDs, Teams webhook, and schedule
3. Click **Save** — the schedule is registered immediately, no restart needed

---

## Adding a New Channel

1. Create `scripts/channels/<channel>.py`
2. Implement a `send(summary: ReportSummary) -> None` function
3. Add an `enabled` toggle to the config YAML schema in `config.py`
4. Wire it up in `scripts/main.py`
