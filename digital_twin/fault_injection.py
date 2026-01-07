

import random

def inject_leak(data):
    """
    Leak:
    - Pressure decreases
    - Flow increases
    - Vibration increases
    """
    data["pressure_bar"] -= random.uniform(8, 15)
    data["flow_m3s"] += random.uniform(3, 6)
    data["vibration"] += random.uniform(1.0, 2.0)
    return data


def inject_blockage(data):
    """
    Blockage:
    - Pressure increases
    - Flow decreases
    """
    data["pressure_bar"] += random.uniform(6, 12)
    data["flow_m3s"] -= random.uniform(4, 8)
    data["vibration"] += random.uniform(0.5, 1.2)
    return data


def inject_sensor_drift(data, drift_factor=0.05):
    """
    Gradual sensor drift
    """
    data["pressure_bar"] *= (1 + drift_factor)
    return data
