# scada/alarm_rules.py

from digital_twin.config import (
    PRESSURE_MIN,
    PRESSURE_MAX,
    FLOW_MIN,
    FLOW_MAX
)

def evaluate_scada_alarms(data):
    """
    Apply threshold-based SCADA alarm rules.
    Returns a list of alarm dicts.
    """
    alarms = []

    if data["pressure_bar"] < PRESSURE_MIN:
        alarms.append({
            "type": "PRESSURE_LOW",
            "severity": "HIGH",
            "parameter": "pressure",
            "value": data["pressure_bar"]
        })

    if data["pressure_bar"] > PRESSURE_MAX:
        alarms.append({
            "type": "PRESSURE_HIGH",
            "severity": "HIGH",
            "parameter": "pressure",
            "value": data["pressure_bar"]
        })

    if data["flow_m3s"] < FLOW_MIN:
        alarms.append({
            "type": "FLOW_LOW",
            "severity": "MEDIUM",
            "parameter": "flow",
            "value": data["flow_m3s"]
        })

    if data["flow_m3s"] > FLOW_MAX:
        alarms.append({
            "type": "FLOW_HIGH",
            "severity": "MEDIUM",
            "parameter": "flow",
            "value": data["flow_m3s"]
        })

    return alarms
