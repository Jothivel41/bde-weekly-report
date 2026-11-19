import argparse
import csv
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_connection import OUTPUT_DIR, audit_cursor


COLUMNS = """
SELECT ordinal_position, column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = %s AND table_name = %s
ORDER BY ordinal_position
"""


REPORT_TABLES = (
    "organizations", "admin_users", "leads", "lead_stage_configs",
    "lead_activities", "lead_audit_logs", "follow_ups", "callyzer_calls",
    "programs", "lead_program_enrollments", "lead_payments",
)


def export_report_columns(schema):
    records = []
    missing = []
    with audit_cursor() as cursor:
        for table in REPORT_TABLES:
            cursor.execute(COLUMNS, (schema, table))
            rows = cursor.fetchall()
            if not rows:
                missing.append(table)
            records.extend((schema, table, *row) for row in rows)

    OUTPUT_DIR.mkdir(exist_ok=True)
    output = OUTPUT_DIR / "09_report_columns.csv"
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("schema", "table", "ordinal_position", "column_name",
                         "data_type", "is_nullable", "column_default"))
        writer.writerows(records)
    print(f"{output.name}: {len(records)} columns")
    if missing:
        print("No visible columns for: " + ", ".join(missing))


def main():
    parser = argparse.ArgumentParser(description="List column metadata for one table.")
    parser.add_argument("schema")
    parser.add_argument("table", nargs="?")
    parser.add_argument("--report-tables", action="store_true", help="Export metadata for Course team candidate tables")
    args = parser.parse_args()
    if args.report_tables:
        if args.table:
            parser.error("Choose a table or --report-tables")
        export_report_columns(args.schema)
        return
    if not args.table:
        parser.error("Provide a table or --report-tables")

    with audit_cursor() as cursor:
        cursor.execute(COLUMNS, (args.schema, args.table))
        rows = cursor.fetchall()
        if not rows:
            parser.exit(1, "No visible columns for the selected schema and table.\n")
        writer = csv.writer(sys.stdout)
        writer.writerow(column.name for column in cursor.description)
        writer.writerows(rows)


if __name__ == "__main__":
    main()
