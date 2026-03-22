import os

import psycopg2


def get_db_connection():
    """
    Returns a new PostgreSQL connection.

    Connection parameters can be overridden via environment variables:
    DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT.
    """
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "1231"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
        application_name=os.getenv("DB_APP_NAME", "dt-scada"),
    )
