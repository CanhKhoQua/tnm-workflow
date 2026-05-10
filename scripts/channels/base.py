from __future__ import annotations

from abc import ABC, abstractmethod

from models import DashboardMessage, ReportSummary


class BaseChannel(ABC):
    @abstractmethod
    def send(self, message: DashboardMessage | ReportSummary) -> None:
        raise NotImplementedError
