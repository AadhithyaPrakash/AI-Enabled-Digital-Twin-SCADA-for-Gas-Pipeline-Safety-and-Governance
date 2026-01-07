# digital_twin/simulator.py

import time
import math
import random
import pandas as pd
from datetime import datetime

from digital_twin.config import *
from digital_twin.fault_injection import (
    inject_leak,
    inject_blockage,
    inject_sensor_drift
)


# Derived Parameters

PIPE_AREA = math.pi * (PIPELINE_DIAMETER_M / 2) ** 2
EFFECTIVE_LENGTH = PIPELINE_LENGTH_M + (
    NUM_BENDS * BEND_EQUIVALENT_LENGTH_FACTOR * PIPELINE_DIAMETER_M
)


# Physics-Based Reading Generator

def generate_normal_reading():
    flow = NORMAL_FLOW_M3S + random.uniform(-0.5, 0.5)

    velocity = flow / PIPE_AREA
    pressure = NORMAL_PRESSURE_BAR - FRICTION_COEFFICIENT * (flow ** 2)

    temperature = NORMAL_TEMPERATURE_C + random.uniform(-0.3, 0.3)
    vibration = NORMAL_VIBRATION + 0.05 * velocity + random.uniform(0, 0.1)

    return {
        "timestamp": datetime.utcnow(),
        "pressure_bar": round(pressure, 2),
        "flow_m3s": round(flow, 2),
        "temperature_c": round(temperature, 2),
        "vibration": round(vibration, 2),
        "valve_state": 1
    }


# Simulation Loop

def run_simulation(fault_mode=None, fault_start_step=150):
    records = []

    print("[DT] Digital Twin started")

    for step in range(TOTAL_STEPS):
        data = generate_normal_reading()

        # Fault injection
        if fault_mode and step >= fault_start_step:
            if fault_mode == "leak":
                data = inject_leak(data)
            elif fault_mode == "blockage":
                data = inject_blockage(data)
            elif fault_mode == "sensor_drift":
                data = inject_sensor_drift(data)

        records.append(data)

        print(
            f"[DT] {data['timestamp']} | "
            f"P={data['pressure_bar']} bar | "
            f"F={data['flow_m3s']} m3/s | "
            f"Vib={data['vibration']}"
        )

        time.sleep(TIME_STEP_SECONDS)

    return pd.DataFrame(records)

# Standalone Execution

if __name__ == "__main__":
    df = run_simulation(fault_mode="leak")
    df.to_csv("data/raw/dt_pipeline_data.csv", index=False)
    print("[DT] Data saved to data/raw/dt_pipeline_data.csv")
