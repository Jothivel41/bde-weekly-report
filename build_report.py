"""Build the standalone Course team HTML report from normalized exports."""

import argparse
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from html import escape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parent
IST = ZoneInfo("Asia/Kolkata")
DAY = timedelta(days=1)
STAGES = {
    "hot": "hot",
    "dead": "deadJunk",
    "junk": "deadJunk",
    "dead/junk": "deadJunk",
    "dead_junk": "deadJunk",
    "cold": "cold",
    "warm": "warm",
}
DAILY_FIELDS = ("followups", "pending", "stageMoves", "enrolled", "sales", "nbfcApproved", "nbfcRejected", "saleValue")
COUNTERS = ("arrived", "leads", "hot", "deadJunk", "cold", "warm", *DAILY_FIELDS)
PHONE_KEY = re.compile(r"[A-Za-z0-9_+-]{1,128}")


def parse_timestamp(value):
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.utcoffset() is None:
        raise ValueError(f"Timestamp needs a UTC offset: {value}")
    return timestamp.astimezone(IST)


def count(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def revenue(value):
    amount = Decimal(str(value))
    cents = amount * 100
    if not amount.is_finite() or cents != cents.to_integral_value() or abs(cents) > 2**53 - 1:
        raise ValueError("Revenue must be a finite rupee amount with up to two decimal places")
    return int(cents)


def build_data(source):
    start = date.fromisoformat(source["coverage"]["start"])
    end = date.fromisoformat(source["coverage"]["end"])
    if end < start:
        raise ValueError("Coverage end must be on or after its start")

    vertical_config = json.loads((PROJECT / "team_hierarchy.json").read_text())["verticals"]
    verticals = list(dict.fromkeys([row["name"] for row in vertical_config] +
                                  [member["vertical"] for member in source["bdes"]]))
    members = {}
    for member in source["bdes"]:
        key = member["id"]
        if not isinstance(key, str) or not key.strip() or key in members:
            raise ValueError("BDE IDs must be non-empty and unique")
        members[key] = {
            "id": len(members) + 1,
            "name": escape(member["name"]),
            "vertical": verticals.index(member["vertical"]),
            "lead": escape(member["team_lead"]),
        }
    if not members:
        raise ValueError("Provide at least one BDE")

    def day_key(bde_id, day):
        if bde_id not in members:
            raise ValueError(f"Unknown BDE ID: {bde_id}")
        if not start <= day <= end:
            raise ValueError(f"Record date lies outside coverage: {day}")
        return f"{members[bde_id]['id']}/{day.isoformat()}"

    days = defaultdict(lambda: dict.fromkeys(COUNTERS + ("revenue",), 0))
    seen_arrivals = set()
    for row in source.get("arrivals", []):
        arrival_id = row["arrival_id"]
        if not arrival_id or arrival_id in seen_arrivals:
            raise ValueError("Arrival IDs must be non-empty and unique")
        seen_arrivals.add(arrival_id)
        days[day_key(row["bde_id"], parse_timestamp(row["arrived_at"]).date())]["arrived"] += 1

    seen_leads = set()
    for row in source["leads"]:
        lead_id = row["lead_id"]
        if not lead_id or lead_id in seen_leads:
            raise ValueError("Lead IDs must be non-empty and unique")
        seen_leads.add(lead_id)
        daily = days[day_key(row["bde_id"], parse_timestamp(row["received_at"]).date())]
        daily["leads"] += 1
        stage = STAGES.get(row["stage"].strip().lower())
        if stage:
            daily[stage] += 1

    seen_crm = set()
    for row in source["daily_crm"]:
        key = day_key(row["bde_id"], date.fromisoformat(row["date"]))
        if key in seen_crm:
            raise ValueError(f"Duplicate daily CRM row: {key}")
        seen_crm.add(key)
        for field in DAILY_FIELDS:
            value = row[field]
            days[key][field] = None if value is None else (
                revenue(value) if field == "saleValue" else count(value, field)
            )
        days[key]["revenue"] = None if row["revenue"] is None else revenue(row["revenue"])

    seen_calls = {}
    hours_by_day = defaultdict(dict)
    for row in source["calls"]:
        timestamp = parse_timestamp(row["started_at"])
        key = day_key(row["bde_id"], timestamp.date())
        call_id = row["call_id"]
        contact = row["contact_key"]
        if not isinstance(call_id, str) or not call_id.strip():
            raise ValueError("Call ID must be a non-empty string")
        if not isinstance(contact, str) or not PHONE_KEY.fullmatch(contact):
            raise ValueError(f"Call {call_id} needs a normalized number or an opaque contact key")
        connected = row["connected"]
        if type(connected) is not bool:
            raise ValueError(f"Call {call_id} needs a boolean connected flag")
        seconds = count(row["talk_seconds"], "talk_seconds")
        if not connected and seconds:
            raise ValueError(f"Unconnected call {call_id} must have zero talk seconds")
        identity = (key, timestamp, contact, connected, seconds)
        if call_id in seen_calls:
            if seen_calls[call_id] != identity:
                raise ValueError(f"Conflicting data for call ID {call_id}")
            continue
        seen_calls[call_id] = identity
        hour = hours_by_day[key].setdefault(timestamp.hour, {
            "hour": timestamp.hour, "attempts": 0, "connected": 0, "talk": 0, "contacts": set(),
        })
        hour["attempts"] += 1
        hour["connected"] += int(connected)
        hour["talk"] += seconds
        hour["contacts"].add(contact)

    # Remap contact keys before embedding the data in shareable HTML.
    contact_ids = {}
    for key, hours in hours_by_day.items():
        days[key]["hours"] = []
        for _, hour in sorted(hours.items()):
            hour["contacts"] = [
                contact_ids.setdefault(contact, len(contact_ids) + 1)
                for contact in sorted(hour["contacts"])
            ]
            days[key]["hours"].append(hour)

    previous_end = end - 7 * DAY
    return {
        "team": list(members.values()),
        "verticals": [escape(name) for name in verticals],
        "verticalManagers": {escape(row["name"]): escape(row["manager"]) for row in vertical_config},
        "coverage": {"start": start.isoformat(), "end": end.isoformat()},
        "asOf": source.get("as_of", "Extraction time not supplied"),
        "ranges": {
            "all": {"start": start.isoformat(), "end": end.isoformat()},
            "latest": {"start": max(start, end - 6 * DAY).isoformat(), "end": end.isoformat()},
            "previous": (
                {"start": max(start, end - 13 * DAY).isoformat(), "end": previous_end.isoformat()}
                if previous_end >= start else None
            ),
        },
        "days": dict(days),
        "sample": source.get("sample") is True,
        "unavailableMetrics": source.get("unavailable_metrics", []),
        "sourceNotes": [escape(note) for note in source.get("source_notes", [])],

    }


def render_report(template, data):
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
    marker = 'id="report-data" type="application/json"></script>'
    if template.count(marker) != 1:
        raise ValueError("Report template is missing its data placeholder")
    return template.replace(marker, f'id="report-data" type="application/json">{payload}</script>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Normalized JSON export")
    parser.add_argument("--output", type=Path, default=PROJECT / "output" / "Weekly_Productivity_Report.html")
    parser.add_argument("--fetch-callyzer", action="store_true", help="Fetch outbound calls for the CRM export's coverage")
    args = parser.parse_args()
    try:
        source = json.loads(args.input.read_text(encoding="utf-8"))
        if args.fetch_callyzer:
            from callyzer import fetch_calls

            if source.get("sample") is True:
                raise ValueError("Use your Course team CRM export when fetching live Callyzer calls")
            source["calls"] = fetch_calls(source)
        template = (PROJECT / "report_template.html").read_text(encoding="utf-8")
        result = render_report(template, build_data(source))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation) as error:
        parser.exit(1, f"Report generation failed: {error}\n")
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
