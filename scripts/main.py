from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from channels.teams import TeamsChannel
from channels.zalo import ZaloChannel
from config import load_config
from core.aggregator import fetch_and_aggregate
from core.builder import build_report, get_period_info
from core.html_report import generate as generate_html
from core.storage import r2_configured, upload_report
from metabase_client import MetabaseClient
from models import ReportMode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    t0 = time.perf_counter()

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument(
        "--mode",
        choices=[m.value for m in ReportMode],
        required=True,
        help="weekly (Monday), monthly (1st of month), or daily (every day at 5 PM)",
    )
    args, _ = parser.parse_known_args()

    load_dotenv()
    config = load_config(args.config)
    mode = ReportMode(args.mode)
    client = MetabaseClient(config.metabase_url, config.metabase_api_key)

    period_label, comparison_range, current_range = get_period_info(mode)

    try:
        aggregated = fetch_and_aggregate(client, config, mode, comparison_range, current_range)
    except Exception as e:
        logger.error("Failed to fetch data: %s", e)
        sys.exit(1)

    # Build once without URL to generate the HTML filename, then rebuild with URL
    base_summary = build_report(aggregated, mode, period_label)
    html_path = generate_html(base_summary, aggregated["detail_rows"], aggregated["detail_cols"])
    logger.info("HTML report: %s", html_path)

    report_url: str | None = None
    if r2_configured(config):
        try:
            report_url = upload_report(html_path, config)
        except Exception as e:
            logger.error("R2 upload failed, continuing without report link: %s", e)
    elif config.webapp_url:
        report_url = f"{config.webapp_url.rstrip('/')}/reports/{Path(html_path).name}"

    summary = build_report(aggregated, mode, period_label, report_url=report_url)

    channels = []
    if config.channels.teams.enabled:
        assert config.teams_webhook_url is not None
        channels.append(TeamsChannel(config.teams_webhook_url))
    if config.channels.zalo.enabled:
        assert config.zalo_access_token is not None
        channels.append(ZaloChannel(config.zalo_access_token))

    for channel in channels:
        try:
            channel.send(summary)
            logger.info("Sent via %s", channel.__class__.__name__)
        except Exception as e:
            logger.error("Failed to send via %s: %s", channel.__class__.__name__, e)
            sys.exit(1)

    logger.info("Done in %.2fs", time.perf_counter() - t0)


if __name__ == "__main__":
    main()
