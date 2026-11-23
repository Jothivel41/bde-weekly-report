"""Merge recently changed CRM leads and the current payment ledger into a saved report snapshot."""
import argparse
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parent
KEEP = (
    "id", "organizationId", "assignedToId", "assignedAt", "createdAt", "updatedAt",
    "stage", "status", "stageDetails", "stageEnteredAt", "enrollmentId", "enrollmentDate",
    "activities", "collectionAmounts",
)


def parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def request_with_retry(session, url, **kwargs):
    for attempt in range(3):
        try:
            response = session.get(url, timeout=90, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="output/live_2026-01-01_2026-11-20")
    parser.add_argument("--target", default="output/live_2026-01-01_2026-11-22")
    parser.add_argument("--since", required=True, help="UTC ISO timestamp of the source snapshot")
    args = parser.parse_args()
    base, target = ROOT / args.base, ROOT / args.target
    since = parse_timestamp(args.since)
    if not (base / "leads_snapshot.json").exists():
        raise ValueError("Base snapshot is missing leads_snapshot.json")
    target.mkdir(parents=True, exist_ok=True)
    if base.resolve() != target.resolve():
        for source in base.glob("*.json"):
            shutil.copy2(source, target / source.name)

    config = dotenv_values(ROOT / ".env")
    base_url = config["CRM_API_BASE_URL"].rstrip("/")
    headers = {"x-api-key": config["CRM_API_KEY"]}
    session = requests.Session()
    session.headers.update(headers)

    changed = []
    page = 1
    while True:
        payload = request_with_retry(
            session, base_url + "/admin/leads",
            params={"page": page, "limit": 100, "sort": "recently_modified"},
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ValueError("Unexpected CRM lead response")
        fresh = [row for row in rows if row.get("updatedAt") and parse_timestamp(row["updatedAt"]) > since]
        changed.extend(fresh)
        if len(fresh) < len(rows):
            break
        page += 1
        if not rows:
            break

    previous = {row["id"]: row for row in json.loads((base / "leads_snapshot.json").read_text())}
    previous.update({row["id"]: {key: row.get(key) for key in KEEP} for row in changed})
    merged_leads = list(previous.values())
    (target / "leads_snapshot.json").write_text(json.dumps(merged_leads, ensure_ascii=False))

    payment_payload = request_with_retry(
        session, base_url + "/admin/payments", params={"page": 1, "limit": 1000}
    )
    payments = payment_payload.get("payments")
    if not isinstance(payments, list):
        raise ValueError("Unexpected CRM payment response")
    prior_payments = json.loads((base / "payments_snapshot.json").read_text())["payments"]
    merged_payments = {row["id"]: row for row in prior_payments}
    merged_payments.update({row["id"]: row for row in payments})
    (target / "payments_snapshot.json").write_text(json.dumps({
        "payments": list(merged_payments.values()), "totals": payment_payload.get("totals"),
    }, ensure_ascii=False))
    (target / "crm_incremental_manifest.json").write_text(json.dumps({
        "base_snapshot": str(base.name), "since": args.since,
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "changed_leads": len(changed), "merged_leads": len(merged_leads),
        "new_or_changed_payment_rows": len(payments), "merged_payment_rows": len(merged_payments),
        "readonly": True,
    }, indent=2))
    print(json.dumps({"changed_leads": len(changed), "merged_leads": len(merged_leads),
                      "recent_payment_rows": len(payments), "merged_payment_rows": len(merged_payments)}))


if __name__ == "__main__":
    main()
