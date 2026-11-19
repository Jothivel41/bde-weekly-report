import csv
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_connection import OUTPUT_DIR, audit_cursor


SCHEMAS = """
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name NOT IN ('information_schema', 'pg_catalog')
  AND schema_name !~ '^pg_(toast|temp)'
ORDER BY schema_name
"""

TABLES = """
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
  AND table_schema !~ '^pg_(toast|temp)'
ORDER BY table_schema, table_name
"""

RELEVANT_TABLES = """
SELECT table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
  AND table_schema !~ '^pg_(toast|temp)'
  AND table_name ILIKE ANY(%s)
ORDER BY table_schema, table_name
"""

KEYWORDS = (
    "lead", "user", "team", "follow", "activ", "stage", "program",
    "course", "payment", "sale", "order", "audit", "enrol", "call",
    "org", "employee", "role", "shift",
)


def main():
    queries = (
        ("06_schemas.csv", SCHEMAS, None),
        ("07_tables.csv", TABLES, None),
        ("08_relevant_tables.csv", RELEVANT_TABLES,
         ([f"%{keyword}%" for keyword in KEYWORDS],)),
    )
    results = []
    with audit_cursor() as cursor:
        for filename, query, parameters in queries:
            cursor.execute(query, parameters)
            headers = [column.name for column in cursor.description]
            results.append((filename, headers, cursor.fetchall()))

    OUTPUT_DIR.mkdir(exist_ok=True)
    for filename, headers, rows in results:
        path = OUTPUT_DIR / filename
        with path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(rows)
        print(f"{filename}: {len(rows)} rows")


if __name__ == "__main__":
    main()
