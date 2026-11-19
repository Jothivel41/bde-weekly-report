"""Check documented read-only CRM endpoints without printing credentials or leads."""
import json
from pathlib import Path

import requests
from dotenv import dotenv_values


def main():
    config = dotenv_values(Path(__file__).with_name('.env'))
    base = config.get('CRM_API_BASE_URL', '').rstrip('/')
    key = config.get('CRM_API_KEY', '')
    if not base.startswith('https://') or not key:
        raise SystemExit('Set an HTTPS CRM_API_BASE_URL and CRM_API_KEY in .env.')
    passed = True
    with requests.Session() as session:
        session.headers['x-api-key'] = key
        for path in ('/admin/leads?page=1&limit=1', '/admin/stages'):
            try:
                response = session.get(base + path, timeout=25, allow_redirects=False)
            except requests.RequestException as error:
                print(path, type(error).__name__)
                passed = False
                continue
            result = {'endpoint': path, 'status': response.status_code}
            try:
                data = response.json()
                result['response_type'] = type(data).__name__
                if isinstance(data, dict):
                    result['fields'] = list(data)
                org_ids = set()
                def inspect(value):
                    if isinstance(value, dict):
                        for field, item in value.items():
                            if field in ('organization_id', 'organizationId', 'orgId', 'org_id') and isinstance(item, str):
                                org_ids.add(item)
                            elif isinstance(item, (dict, list)):
                                inspect(item)
                    elif isinstance(value, list):
                        for item in value:
                            inspect(item)
                inspect(data)
                result['organization_ids_in_response'] = sorted(org_ids)
            except ValueError:
                result['response_type'] = 'non-JSON'
                passed = False
            passed = passed and response.status_code == 200
            print(json.dumps(result))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
