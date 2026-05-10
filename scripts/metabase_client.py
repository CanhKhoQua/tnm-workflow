from __future__ import annotations

import requests


class MetabaseClient:
    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["X-API-KEY"] = api_key

    def fetch_dashboard(self, dashboard_id: int) -> dict:
        resp = self.session.get(f"{self.url}/api/dashboard/{dashboard_id}")
        resp.raise_for_status()
        return resp.json()

    def fetch_dashcard_value(
        self,
        dashboard_id: int,
        dashcard_id: int,
        card_id: int,
        parameters: list[dict] | None = None,
    ) -> str:
        body = {"parameters": parameters or []}
        resp = self.session.post(
            f"{self.url}/api/dashboard/{dashboard_id}/dashcard/{dashcard_id}/card/{card_id}/query",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        rows = data.get("rows", [])
        cols = data.get("cols", [])
        if not rows or not rows[0]:
            return "N/A"

        # For single-value cards (scalar/metric), return the first cell directly
        if len(rows) == 1 and len(rows[0]) == 1:
            return str(rows[0][0])

        # For multi-row/multi-col cards (pivot, bar, table), find numeric columns
        # and sum them to get a meaningful total
        numeric_indices = [
            i for i, col in enumerate(cols)
            if col.get("base_type", "").startswith(("type/Integer", "type/Float", "type/Decimal", "type/BigInteger", "type/Number"))
        ]
        if not numeric_indices:
            # Fallback: try columns after the first (skip dimension column)
            numeric_indices = list(range(1, len(cols))) if len(cols) > 1 else [0]

        total = sum(
            row[i] for row in rows for i in numeric_indices
            if i < len(row) and isinstance(row[i], (int, float))
        )
        return f"{int(total):,}" if total == int(total) else f"{total:,}"

    def fetch_raw_data(
        self,
        dashboard_id: int,
        dashcard_id: int,
        card_id: int,
        parameters: list[dict] | None = None,
    ) -> dict:
        body = {"parameters": parameters or []}
        resp = self.session.post(
            f"{self.url}/api/dashboard/{dashboard_id}/dashcard/{dashcard_id}/card/{card_id}/query",
            json=body,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})

    def fetch_dashcard_breakdown(
        self,
        dashboard_id: int,
        dashcard_id: int,
        card_id: int,
        parameters: list[dict] | None = None,
    ) -> list[tuple[str, str]]:
        """Return (label, value) pairs grouped by the first non-date dimension column."""
        body = {"parameters": parameters or []}
        resp = self.session.post(
            f"{self.url}/api/dashboard/{dashboard_id}/dashcard/{dashcard_id}/card/{card_id}/query",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        rows = data.get("rows", [])
        cols = data.get("cols", [])

        if not rows or not cols:
            return [("N/A", "N/A")]

        if len(rows) == 1 and len(cols) == 1:
            return [(cols[0]["name"], str(rows[0][0]))]

        _DATE_TYPES = ("type/Date", "type/DateTime", "type/DateTimeWithTZ", "type/DateTimeWithLocalTZ")
        _NUM_TYPES = ("type/Integer", "type/Float", "type/Decimal", "type/BigInteger", "type/Number")

        numeric_indices = [
            i for i, col in enumerate(cols)
            if col.get("base_type", "").startswith(_NUM_TYPES)
        ]
        group_index = next(
            (i for i, col in enumerate(cols)
             if i not in numeric_indices
             and not col.get("base_type", "").startswith(_DATE_TYPES)),
            None,
        )

        if group_index is None or not numeric_indices:
            total = sum(
                row[i] for row in rows for i in numeric_indices
                if i < len(row) and isinstance(row[i], (int, float))
            )
            return [("Total", f"{int(total):,}")]

        groups: dict[str, float] = {}
        for row in rows:
            key = str(row[group_index]) if group_index < len(row) else "?"
            for i in numeric_indices:
                if i < len(row) and isinstance(row[i], (int, float)):
                    groups[key] = groups.get(key, 0.0) + row[i]

        return [
            (label, f"{int(v):,}" if v == int(v) else f"{v:,}")
            for label, v in sorted(groups.items(), key=lambda x: x[1], reverse=True)
        ]

    def export_card_image(self, card_id: int) -> bytes | None:
        resp = self.session.post(f"{self.url}/api/card/{card_id}/query/png")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.content
