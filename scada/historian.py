# scada/historian.py

from database.db_connector import get_db_connection

def write_sensor_data(data):
    """
    Store raw SCADA sensor data in PostgreSQL.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sensor_data
        (timestamp, pressure_bar, flow_m3s, temperature_c, vibration, valve_state)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        data["timestamp"],
        data["pressure_bar"],
        data["flow_m3s"],
        data["temperature_c"],
        data["vibration"],
        data["valve_state"]
    ))

    conn.commit()
    cur.close()
    conn.close()


def write_event(event):
    """
    Store SCADA alarm events.
    """
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO events
        (timestamp, event_type, severity, parameter, value)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        event["timestamp"],
        event["type"],
        event["severity"],
        event["parameter"],
        event["value"]
    ))

    conn.commit()
    cur.close()
    conn.close()
