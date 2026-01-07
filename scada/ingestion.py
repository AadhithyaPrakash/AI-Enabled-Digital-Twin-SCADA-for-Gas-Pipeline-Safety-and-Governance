# scada/ingestion.py

from scada.alarm_rules import evaluate_scada_alarms
from scada.historian import write_sensor_data, write_event, write_ai_event
from ai_engine.detect import compute_anomaly_score, load_threshold ,explain_anomaly

THRESHOLD=load_threshold()

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
    
    # Step 4: compute AI anomaly score
    score, is_anomaly = compute_anomaly_score(data)
    print(f"[AI DEBUG] Anomaly score: {score:.4f}, anomaly: {is_anomaly}")
    if is_anomaly:
        explanation=explain_anomaly(data)
        write_ai_event(
            timestamp=data["timestamp"],
            score=score,
            threshold=THRESHOLD,
            status="ANOMALY_DETECTED",
            explanation=explanation
        )

    return alarms, score, is_anomaly
