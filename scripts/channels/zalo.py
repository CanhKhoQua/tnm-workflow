from __future__ import annotations

import logging

from channels.base import BaseChannel
from models import DashboardMessage, ReportSummary

logger = logging.getLogger(__name__)


class ZaloChannel(BaseChannel):
    def __init__(self, access_token: str) -> None:
        self.access_token = access_token

    def send(self, message: DashboardMessage | ReportSummary) -> None:
        logger.info("Zalo channel is not yet configured. Skipping send.")
