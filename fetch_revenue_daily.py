"""Fetch daily CRM revenue-dashboard data for the report period, read-only."""
import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import dotenv_values


PROJECT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2026-09-01")
    parser.add_argument("--end", default="2026-11-19")
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    output = PROJECT / f"output/live_{start}_{end}" / "revenue_daily.json"
    cached = json.loads(output.read_text()) if output.exists() else {}
    config = dotenv_values(PROJECT / ".env")
    base = config["CRM_API_BASE_URL"].rstrip("/")
    with requests.Session() as session:
        session.headers["x-api-key"] = config["CRM_API_KEY"]
        day = start
        while day <= end:
            key = day.isoformat()
            if key not in cached:
                response = session.get(
                    base + "/admin/revenue/dashboard",
                    params={"dateFrom": key, "dateTo": key}, timeout=40,
                )
                response.raise_for_status()
                payload = response.json()
                if not payload.get("range") or "bde" not in payload.get("breakdowns", {}):
                    raise ValueError(f"Unexpected revenue dashboard response for {key}")
                cached[key] = {
                    "range": payload["range"],
                    "bde": payload["breakdowns"]["bde"],
                    "kpis": payload["kpis"],
                }
                output.write_text(json.dumps(cached, indent=2))
                print(f"Revenue {key}: {len(cached[key]['bde'])} BDE rows")
            day += timedelta(days=1)


if __name__ == "__main__":
    main()
