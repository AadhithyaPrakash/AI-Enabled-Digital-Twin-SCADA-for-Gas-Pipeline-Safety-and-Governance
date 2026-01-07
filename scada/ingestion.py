# scada/ingestion.py

from scada.alarm_rules import evaluate_scada_alarms
from scada.historian import write_sensor_data, write_event

def ingest_data(data):
    """
    SCADA ingestion pipeline:
    1. Store raw sensor data
    2. Evaluate alarms
    3. Store alarm events
    """
    # Step 1: persist raw data
    write_sensor_data(data)

    # Step 2: evaluate alarms
    alarms = evaluate_scada_alarms(data)

    # Step 3: persist alarms
    for alarm in alarms:
        alarm["timestamp"] = data["timestamp"]
        write_event(alarm)

    return alarms
