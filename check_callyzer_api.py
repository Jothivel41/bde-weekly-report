"""Read one bounded call-history page; never print tokens or call records."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import requests
from dotenv import dotenv_values
from callyzer import BASE_URLS


def main():
    config = dotenv_values(Path(__file__).with_name('.env'))
    base = config.get('CALLYZER_API_BASE_URL', '').rstrip('/')
    token = config.get('CALLYZER_API_TOKEN', '').strip()
    if base not in BASE_URLS or not token:
        raise SystemExit('Configure the official Callyzer API URL and token in .env.')
    zone = ZoneInfo('Asia/Kolkata')
    filters = {
        'call_from': int(datetime(2026, 11, 17, tzinfo=zone).timestamp()),
        'call_to': int(datetime(2026, 11, 17, 23, 59, 59, tzinfo=zone).timestamp()),
        'call_types': ['Outgoing'], 'page_no': 1, 'page_size': 1,
        'call_method': config.get('CALLYZER_CALL_METHOD', 'PhoneCall'),
        'call_mode': config.get('CALLYZER_CALL_MODE', 'Voice'),
    }
    try:
        response = requests.post(base + '/call-log/history', json=filters,
                                 headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'},
                                 timeout=(10, 30), allow_redirects=False)
    except requests.RequestException as error:
        raise SystemExit(type(error).__name__) from None
    print('Window: 17 Nov 2026, 00:00:00–23:59:59 IST; account-wide outgoing calls')
    print('HTTP:', response.status_code)
    try:
        payload = response.json()
    except ValueError:
        raise SystemExit('Non-JSON response') from None
    if isinstance(payload, dict):
        summary = {k: payload[k] for k in ('message', 'total_records', 'page_no') if k in payload}
        rows = payload.get('result')
        summary['result_type'] = type(rows).__name__
        if isinstance(rows, list):
            summary['returned_rows'] = len(rows)
            if rows and isinstance(rows[0], dict):
                summary['record_fields'] = list(rows[0])
        print(json.dumps(summary).replace(token, '[REDACTED]'))
    raise SystemExit(0 if response.status_code == 200 and isinstance(payload, dict) and payload.get('message') == 'Success' else 1)


if __name__ == '__main__':
    main()
