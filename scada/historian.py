# scada/historian.py
import json
from datetime import datetime
from typing import Iterable, Optional

import pandas as pd
from psycopg2.extras import execute_values

from database.db_connector import get_db_connection
from database.schema_manager import ensure_schema


def _as_datetime(value):
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return value

def write_sensor_data(data):
    """
    Store raw SCADA sensor data in PostgreSQL.
    """
    write_sensor_data_batch([data])


def write_sensor_data_batch(
    rows: Iterable[dict],
    *,
    conn: Optional[object] = None,
    page_size: int = 1000,
) -> int:
    """
    Batch insert sensor rows into `sensor_data`.

    Returns number of rows inserted.
    """
    ensure_schema()

    records = list(rows)
    if not records:
        return 0

    own_conn = conn is None
    connection = get_db_connection() if own_conn else conn

    insert_sql = """
        INSERT INTO sensor_data
        (timestamp, pressure_bar, flow_m3s, temperature_c, vibration, valve_state)
        VALUES %s
    """
    values = [
        (
            _as_datetime(r["timestamp"]),
            float(r["pressure_bar"]),
            float(r["flow_m3s"]),
            float(r["temperature_c"]),
            float(r["vibration"]),
            int(r["valve_state"]),
        )
        for r in records
    ]

    try:
        with connection, connection.cursor() as cur:
            execute_values(cur, insert_sql, values, page_size=page_size)
        return len(values)
    finally:
        if own_conn:
            connection.close()


def write_event(event):
    """
    Store SCADA alarm events.
    """
    ensure_schema()
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO events
                (timestamp, event_type, severity, parameter, value)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    _as_datetime(event["timestamp"]),
                    event["type"],
                    event["severity"],
                    event["parameter"],
                    float(event["value"]),
                ),
            )
    finally:
        conn.close()

def write_ai_event(timestamp, score, threshold, status, explanation):
    ensure_schema()
    conn = get_db_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ai_events
                (timestamp, anomaly_score, threshold, status, explanation)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    _as_datetime(timestamp),
                    float(score),
                    None if threshold is None else float(threshold),
                    status,
                    json.dumps(explanation),
                ),
            )
    finally:
        conn.close()
