from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db_connection import audit_cursor


def main():
    with audit_cursor() as cursor:
        cursor.execute(
            "SELECT current_database(), current_user, "
            "current_setting('transaction_read_only')"
        )
        database, user, read_only = cursor.fetchone()

    print("Database connection successful")
    print("Database:", database)
    print("User:", user)
    print("Read only:", read_only)


if __name__ == "__main__":
    main()
