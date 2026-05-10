from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytz
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
_CONFIGS_DIR = _PROJECT_ROOT / "configs"
_REPORTS_DIR = _PROJECT_ROOT / "reports"
_MAIN_SCRIPT = _SCRIPTS_DIR / "main.py"
_TZ = pytz.timezone("Asia/Ho_Chi_Minh")

sys.path.insert(0, str(_SCRIPTS_DIR))

load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

app = Flask(__name__)


_DOW_LABELS = {"mon": "T2", "tue": "T3", "wed": "T4", "thu": "T5", "fri": "T6", "sat": "T7", "sun": "CN"}


def _schedule_label(config: dict) -> str:
    if not config.get("schedule_enabled"):
        return "Tắt"
    mode = config.get("mode", "daily")
    h, m = int(config.get("hour", 17)), int(config.get("minute", 0))
    t = f"{h:02d}:{m:02d}"
    if mode == "weekly":
        dow = _DOW_LABELS.get(config.get("day_of_week", "mon"), "T2")
        return f"📆 {dow} {t}"
    if mode == "monthly":
        return f"🗓 Ngày {config.get('day', 1)} {t}"
    return f"📅 Hàng ngày {t}"


def _run_config(path: Path, mode: str) -> None:
    try:
        result = subprocess.run(
            [sys.executable, str(_MAIN_SCRIPT), "--config", str(path), "--mode", mode],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
            cwd=str(_SCRIPTS_DIR),
            env={**os.environ, "PYTHONPATH": str(_SCRIPTS_DIR)},
        )
        if result.returncode == 0:
            logger.info("Scheduled %s run OK: %s", mode, path.stem)
        else:
            logger.error("Scheduled %s run FAILED (%s): %s", mode, path.stem, result.stderr)
    except Exception as exc:
        logger.error("Scheduled %s run ERROR (%s): %s", mode, path.stem, exc)


def _schedule_workflow(scheduler: BackgroundScheduler, stem: str, config: dict) -> None:
    try:
        scheduler.remove_job(stem)
    except Exception:
        pass
    if not config.get("schedule_enabled"):
        return
    mode = config.get("mode", "daily")
    hour = int(config.get("hour", 17))
    minute = int(config.get("minute", 0))
    path = _CONFIGS_DIR / f"{stem}.yaml"
    if mode == "weekly":
        trigger = CronTrigger(day_of_week=config.get("day_of_week", "mon"), hour=hour, minute=minute, timezone=_TZ)
    elif mode == "monthly":
        trigger = CronTrigger(day=int(config.get("day", 1)), hour=hour, minute=minute, timezone=_TZ)
    else:
        trigger = CronTrigger(hour=hour, minute=minute, timezone=_TZ)
    scheduler.add_job(_run_config, trigger, args=[path, mode], id=stem, replace_existing=True)
    logger.info("Scheduled %s: %s %02d:%02d", stem, mode, hour, minute)


def _load_all_workflow_jobs(scheduler: BackgroundScheduler) -> None:
    _CONFIGS_DIR.mkdir(exist_ok=True)
    for path in sorted(_CONFIGS_DIR.glob("*.yaml")):
        try:
            with open(path) as f:
                config = yaml.safe_load(f) or {}
            _schedule_workflow(scheduler, path.stem, config)
        except Exception as exc:
            logger.error("Failed to schedule %s: %s", path.stem, exc)


def _start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=_TZ)
    _load_all_workflow_jobs(scheduler)
    scheduler.start()
    return scheduler


# Guard against Flask debug reloader spawning a second scheduler process
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    _scheduler = _start_scheduler()


def _config_files() -> list[dict]:
    _CONFIGS_DIR.mkdir(exist_ok=True)
    configs = []
    for path in sorted(_CONFIGS_DIR.glob("*.yaml")):
        name = _workflow_name(path)
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            configs.append({
                "name": name,
                "path": str(path),
                "dashboard_id": data.get("dashboard_id"),
                "schedule_label": _schedule_label(data),
                "mode": data.get("mode", "daily"),
                "teams_enabled": data.get("channels", {}).get("teams", {}).get("enabled", False),
                "zalo_enabled": data.get("channels", {}).get("zalo", {}).get("enabled", False),
            })
        except Exception:
            configs.append({"name": name, "path": str(path), "error": True, "schedule_label": "—", "mode": "daily"})
    return configs


def _workflow_name(path: Path) -> str:
    return path.stem


def _config_path(name: str) -> Path:
    return _CONFIGS_DIR / f"{name}.yaml"


def _load_yaml(path: Path) -> dict:
    defaults = {
        "schedule_enabled": True, "mode": "daily",
        "hour": 17, "minute": 0, "day_of_week": "mon", "day": 1,
        "dashboard_id": "", "collection_id": None, "dashcard_ids": [],
        "channels": {"teams": {"enabled": True}, "zalo": {"enabled": False}},
        "teams_webhook_url": "", "zalo_access_token": "", "webapp_url": "",
    }
    if not path.exists():
        return defaults
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    for k, v in defaults.items():
        data.setdefault(k, v)
    return data


def _save_yaml(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False)


@app.route("/")
def index():
    return render_template("index.html", workflows=_config_files())


@app.route("/workflow/new")
def workflow_new():
    return render_template("edit.html", name="", config={
        "schedule_enabled": True, "mode": "daily",
        "hour": 17, "minute": 0, "day_of_week": "mon", "day": 1,
        "dashboard_id": "", "collection_id": "", "dashcard_ids": [],
        "channels": {"teams": {"enabled": True}, "zalo": {"enabled": False}},
        "teams_webhook_url": "", "zalo_access_token": "",
    }, is_new=True)


@app.route("/workflow/<name>")
def workflow_edit(name: str):
    path = _config_path(name)
    config = _load_yaml(path)
    return render_template("edit.html", name=name, config=config, is_new=False)


@app.route("/workflow/save", methods=["POST"])
def workflow_save():
    old_name = request.form.get("old_name", "").strip()
    new_name = request.form.get("name", "").strip()
    if not new_name:
        return "Workflow name is required", 400

    if old_name and old_name != new_name:
        old_path = _config_path(old_name)
        if old_path.exists():
            old_path.unlink()
        try:
            _scheduler.remove_job(old_name)
        except Exception:
            pass

    path = _config_path(new_name)

    raw_dashcard_ids = request.form.get("dashcard_ids", "").strip()
    dashcard_ids: list[int] = []
    for x in raw_dashcard_ids.replace(",", "\n").splitlines():
        x = x.strip()
        if x.isdigit():
            dashcard_ids.append(int(x))

    collection_raw = request.form.get("collection_id", "").strip()
    collection_id = int(collection_raw) if collection_raw.isdigit() else None

    dashboard_raw = request.form.get("dashboard_id", "").strip()
    dashboard_id = int(dashboard_raw) if dashboard_raw.isdigit() else None

    webapp_url = request.form.get("webapp_url", "").strip() or None
    data: dict = {
        "schedule_enabled": "schedule_enabled" in request.form,
        "mode": request.form.get("mode", "daily"),
        "hour": int(request.form.get("hour", 17)),
        "minute": int(request.form.get("minute", 0)),
        "day_of_week": request.form.get("day_of_week", "mon"),
        "day": int(request.form.get("monthly_day", 1)),
        "dashboard_id": dashboard_id,
        "collection_id": collection_id,
        "dashcard_ids": dashcard_ids or None,
        "channels": {
            "teams": {"enabled": "teams_enabled" in request.form},
            "zalo": {"enabled": "zalo_enabled" in request.form},
        },
        "teams_webhook_url": request.form.get("teams_webhook_url", ""),
        "zalo_access_token": request.form.get("zalo_access_token", ""),
        "webapp_url": webapp_url,
    }

    _save_yaml(path, data)
    _schedule_workflow(_scheduler, new_name, data)
    return redirect(url_for("index"))


@app.route("/workflow/<name>/delete", methods=["POST"])
def workflow_delete(name: str):
    path = _config_path(name)
    if path.exists():
        path.unlink()
    try:
        _scheduler.remove_job(name)
    except Exception:
        pass
    return redirect(url_for("index"))


@app.route("/workflow/<name>/run", methods=["POST"])
def workflow_run(name: str):
    import time
    path = _config_path(name)
    main_script = _SCRIPTS_DIR / "main.py"
    mode = request.form.get("mode", "weekly")
    if mode not in ("weekly", "monthly", "daily"):
        return jsonify({"ok": False, "stderr": "Invalid mode"}), 400
    try:
        t0 = time.perf_counter()
        result = subprocess.run(
            [sys.executable, str(main_script), "--config", str(path), "--mode", mode],
            capture_output=True,
            text=True,
            encoding='utf-8',
            timeout=120,
            cwd=str(_SCRIPTS_DIR),
            env={**os.environ, "PYTHONPATH": str(_SCRIPTS_DIR)},
        )
        elapsed = round(time.perf_counter() - t0, 2)
        return jsonify({
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "elapsed": elapsed,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "stderr": "Timed out after 120 seconds"}), 504
    except Exception as e:
        return jsonify({"ok": False, "stderr": str(e)}), 500


@app.route("/reports")
def reports_list():
    _REPORTS_DIR.mkdir(exist_ok=True)
    reports = sorted(
        _REPORTS_DIR.glob("*.html"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    items = [{"name": p.name, "size_kb": round(p.stat().st_size / 1024, 1)} for p in reports]
    return render_template("reports.html", reports=items)


@app.route("/reports/<path:filename>")
def reports_serve(filename: str):
    safe = Path(filename).name
    report_path = _REPORTS_DIR / safe
    if not report_path.exists() or not report_path.is_file():
        return "Report not found", 404
    return send_file(report_path, mimetype="text/html")


@app.route("/reports/<path:filename>/delete", methods=["POST"])
def reports_delete(filename: str):
    safe = Path(filename).name
    report_path = _REPORTS_DIR / safe
    if report_path.exists() and report_path.is_file():
        report_path.unlink()
    return redirect(url_for("reports_list"))


@app.route("/api/dashboards")
def api_dashboards():
    from metabase_client import MetabaseClient
    url = os.environ.get("METABASE_URL", "")
    key = os.environ.get("METABASE_API_KEY", "")
    if not url or not key:
        return jsonify({"error": "METABASE_URL / METABASE_API_KEY not set"}), 503
    try:
        client = MetabaseClient(url, key)
        resp = client.session.get(f"{client.url}/api/dashboard")
        resp.raise_for_status()
        dashboards = [
            {"id": d["id"], "name": d.get("name", f"Dashboard {d['id']}")}
            for d in resp.json()
        ]
        return jsonify(dashboards)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboard/<int:dashboard_id>/dashcards")
def api_dashcards(dashboard_id: int):
    from metabase_client import MetabaseClient
    url = os.environ.get("METABASE_URL", "")
    key = os.environ.get("METABASE_API_KEY", "")
    if not url or not key:
        return jsonify({"error": "METABASE_URL / METABASE_API_KEY not set"}), 503
    try:
        client = MetabaseClient(url, key)
        dashboard = client.fetch_dashboard(dashboard_id)
        cards = [
            {
                "id": dc["id"],
                "card_id": dc.get("card_id"),
                "name": (dc.get("card") or {}).get("name", f"Card {dc.get('card_id')}"),
            }
            for dc in dashboard.get("dashcards", [])
            if dc.get("card_id")
        ]
        return jsonify(cards)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    import os as _os
    app.run(host="0.0.0.0", port=5000, debug=_os.environ.get("FLASK_DEBUG", "0") == "1")
