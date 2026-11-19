"""Fetch outgoing Callyzer call history for the BDEs in the report."""

from datetime import date, datetime, time, timedelta
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from dotenv import load_dotenv

IST = ZoneInfo("Asia/Kolkata")
BASE_URLS = {
    "https://api1.callyzer.co/api/v2.3",
    "https://sandbox.api.callyzer.co/api/v2.3",
}
PAGE_SIZE = 99
PHONE = re.compile(r"\+?([1-9][0-9]{0,2})-([0-9]+)")


def digits(value):
    return "".join(char for char in str(value or "") if char in "0123456789")


def mapped_employees(bdes):
    by_phone = {}
    for member in bdes:
        match = PHONE.fullmatch(str(member.get("callyzer_number") or "").strip())
        if not match:
            raise ValueError("Each BDE needs callyzer_number in countrycode-number format")
        api_number = "-".join(match.groups())
        key = "".join(match.groups())
        if key in by_phone:
            raise ValueError("A Callyzer employee number is mapped to multiple BDEs")
        by_phone[key] = (api_number, member["id"])
    if not by_phone:
        raise ValueError("Callyzer requires at least one mapped BDE")
    return by_phone


def call_row(row, employees, account_timezone, start, end):
    if row["call_type"].casefold() != "outgoing":
        return None
    raw_employee = str(row["emp_number"])
    country = digits(row.get("emp_country_code"))
    employee = digits(raw_employee)
    if not raw_employee.startswith("+") and not PHONE.fullmatch(raw_employee):
        employee = country + employee
    if employee not in employees:
        raise ValueError("Callyzer returned an outgoing call for an unmapped BDE")

    timestamp = datetime.fromisoformat(row["call_date"] + "T" + row["call_time"])
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=account_timezone)
    if not start <= timestamp.astimezone(IST).date() <= end:
        raise ValueError("Callyzer returned a call outside the selected IST dates. Check the account timezone.")

    try:
        seconds = int(str(row["duration"]))
    except ValueError:
        raise ValueError("Callyzer returned an invalid call duration") from None
    if seconds < 0:
        raise ValueError("Callyzer returned a negative call duration")

    raw_contact = str(row.get("client_number") or "")
    contact = digits(raw_contact)
    country = digits(row.get("client_country_code"))
    if not contact:
        raise ValueError("A Callyzer call has no destination number for Unique Calls")
    if not raw_contact.startswith("+") and not PHONE.fullmatch(raw_contact):
        contact = country + contact

    # Callyzer's employee summary classifies durations greater than two seconds as connected.
    connected = seconds > 2
    return {
        "call_id": row["id"],
        "bde_id": employees[employee][1],
        "started_at": timestamp.isoformat(),
        "contact_key": contact,
        "connected": connected,
        "talk_seconds": seconds if connected else 0,
    }


def history_pages(session, url, filters):
    page = 1
    received = 0
    expected = None
    while True:
        try:
            response = session.post(
                url, json={**filters, "page_no": page, "page_size": PAGE_SIZE},
                timeout=(10, 60), allow_redirects=False,
            )
        except requests.RequestException:
            raise ValueError("Could not reach the Callyzer call-history API") from None
        if response.status_code != 200:
            detail = {
                401: "Verify the Callyzer API token",
                403: "Verify the token permissions and API subscription",
                429: "The API rate limit was reached. Retry later",
            }.get(response.status_code, "Verify the Callyzer configuration")
            raise ValueError(f"Callyzer returned HTTP {response.status_code}. {detail}.")
        try:
            payload = response.json()
        except ValueError:
            raise ValueError("Callyzer returned a non-JSON response") from None
        if not isinstance(payload, dict) or payload.get("message") != "Success":
            raise ValueError("Callyzer did not return a successful call-history response")
        rows = payload.get("result")
        total = payload.get("total_records")
        if rows is None and total == 0:
            rows = []
        if not isinstance(rows, list) or type(total) is not int or total < 0:
            raise ValueError("Unexpected Callyzer call-history response format")
        if payload.get("page_no", page) != page or (expected is not None and total != expected):
            raise ValueError("Callyzer history changed during pagination. Retry after syncing completes.")
        expected = total
        received += len(rows)
        if received > expected or (not rows and received < expected):
            raise ValueError("The Callyzer history response was incomplete or inconsistent")
        yield from rows
        if received == expected:
            return
        page += 1


def fetch_calls(source):
    load_dotenv(Path(__file__).resolve().parent / ".env")
    token = os.getenv("CALLYZER_API_TOKEN", "").strip()
    if not token:
        raise ValueError("Set CALLYZER_API_TOKEN in the local .env")
    base = os.getenv("CALLYZER_API_BASE_URL", "https://api1.callyzer.co/api/v2.3").rstrip("/")
    if base not in BASE_URLS:
        raise ValueError("Use the official Callyzer v2.3 production or sandbox base URL")
    method = os.getenv("CALLYZER_CALL_METHOD", "PhoneCall")
    mode = os.getenv("CALLYZER_CALL_MODE", "Voice")
    if method not in {"PhoneCall", "WhatsAppCall"} or mode not in {"Voice", "Video"}:
        raise ValueError("Invalid Callyzer call method or mode")
    try:
        account_timezone = ZoneInfo(os.getenv("CALLYZER_ACCOUNT_TIMEZONE", "Asia/Kolkata"))
    except ZoneInfoNotFoundError:
        raise ValueError("Set CALLYZER_ACCOUNT_TIMEZONE to the account's IANA time zone") from None
    start = date.fromisoformat(source["coverage"]["start"])
    end = date.fromisoformat(source["coverage"]["end"])
    if not timedelta() <= end - start < timedelta(days=180):
        raise ValueError("Callyzer requires a valid reporting range of at most 180 calendar dates")
    employees = mapped_employees(source["bdes"])
    filters = {
        "call_from": int(datetime.combine(start, time.min, IST).timestamp()),
        "call_to": int(datetime.combine(end, time(23, 59, 59), IST).timestamp()),
        "call_types": ["Outgoing"],
        "emp_numbers": [registered for registered, _ in employees.values()],
        "is_exclude_numbers": True,
        "call_method": method,
        "call_mode": mode,
    }
    with requests.Session() as session:
        session.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        rows = history_pages(session, f"{base}/call-log/history", filters)
        calls = [call for row in rows if (call := call_row(row, employees, account_timezone, start, end)) is not None]
    return calls
