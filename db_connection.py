from contextlib import closing, contextmanager
from pathlib import Path
import os

import psycopg2
from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_DIR / "output"

PLACEHOLDERS = {
    "DB_HOST": "your_host",
    "DB_NAME": "your_database",
    "DB_USER": "your_readonly_username",
    "DB_PASSWORD": "your_password",
}


def get_connection():
    load_dotenv(PROJECT_DIR / ".env")
    missing = [
        name for name, placeholder in PLACEHOLDERS.items()
        if os.getenv(name) in (None, "", placeholder)
    ]
    if missing:
        raise ValueError("Set these values in .env: " + ", ".join(missing))

    sslmode = os.getenv("DB_SSLMODE")
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=10,
        options="-c default_transaction_read_only=on -c statement_timeout=15000",
        **({"sslmode": sslmode} if sslmode else {}),
    )


@contextmanager
def audit_cursor():
    with closing(get_connection()) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            if cursor.fetchone()[0] != "on":
                raise RuntimeError("The audit requires a read-only transaction.")
            yield cursor
