"""Fetch the CRM payment ledger for financial reporting (read-only)."""
import argparse
import json
from datetime import date
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
    output = PROJECT / f"output/live_{start}_{end}" / "payments_snapshot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    config = dotenv_values(PROJECT / ".env")
    response = requests.get(
        config["CRM_API_BASE_URL"].rstrip("/") + "/admin/payments",
        headers={"x-api-key": config["CRM_API_KEY"]},
        params={"page": 1, "limit": 1000}, timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    payments = payload.get("payments")
    if not isinstance(payments, list):
        raise ValueError("Unexpected CRM payments response")
    output.write_text(json.dumps({"payments": payments, "totals": payload.get("totals")}, indent=2))
    print(f"Payments saved: {len(payments)}")


if __name__ == "__main__":
    main()
