# digital_twin/simulator.py

import time
import math
import random
import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

try:
    from digital_twin.config import *
    from digital_twin.fault_injection import (
        inject_leak,
        inject_blockage,
        inject_sensor_drift,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from digital_twin.config import *
    from digital_twin.fault_injection import (
        inject_leak,
        inject_blockage,
        inject_sensor_drift,
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
    # coefficient was 0.05 — with velocity ≈ 50 m/s that gave vibration ≈ 2.9 (always ALARM)
    # 0.002 keeps normal vibration at ~0.50 ± 0.05; faults add 0.5–2.0 on top
    vibration = NORMAL_VIBRATION + 0.002 * velocity + random.uniform(0, 0.05)

    return {
        "timestamp": datetime.utcnow(),
        "pressure_bar": round(pressure, 2),
        "flow_m3s": round(flow, 2),
        "temperature_c": round(temperature, 2),
        "vibration": round(vibration, 2),
        "valve_state": 1
    }


# Simulation Loop

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_CSV = REPO_ROOT / "data" / "raw" / "dt_pipeline_data.csv"


def run_simulation(
    fault_mode=None,
    fault_start_step=150,
    total_steps=TOTAL_STEPS,
    time_step_seconds=TIME_STEP_SECONDS,
    *,
    persist_to_db: bool = False,
):
    records = []

    print("[DT] Digital Twin started")
    start_time = datetime.utcnow()

    for step in range(total_steps):
        data = generate_normal_reading()
        data["timestamp"] = start_time + timedelta(
            seconds=step * float(time_step_seconds),
            microseconds=step,
        )

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

        time.sleep(time_step_seconds)

    if persist_to_db:
        from scada.historian import write_sensor_data_batch

        inserted = write_sensor_data_batch(records)
        print(f"[DT] Inserted {inserted} rows into database table sensor_data")

    return pd.DataFrame(records)


def save_simulation_csv(df: pd.DataFrame, output_path: Path = DEFAULT_OUTPUT_CSV) -> Path:
    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


# Standalone Execution

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Digital Twin pipeline simulation.")
    parser.add_argument(
        "--fault-mode",
        choices=["leak", "blockage", "sensor_drift", "none"],
        default="leak",
        help="Fault mode to inject (default: leak).",
    )
    parser.add_argument(
        "--fault-start-step",
        type=int,
        default=150,
        help="Step at which fault injection starts (default: 150).",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=TOTAL_STEPS,
        help=f"Number of simulation steps (default: {TOTAL_STEPS}).",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=TIME_STEP_SECONDS,
        help=f"Sleep time per step in seconds (default: {TIME_STEP_SECONDS}).",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT_CSV.relative_to(REPO_ROOT)),
        help="CSV output path (relative paths are resolved from repo root).",
    )
    parser.add_argument(
        "--to-db",
        action="store_true",
        help="Insert generated rows into the configured PostgreSQL database.",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Do not write CSV output.",
    )

    args = parser.parse_args()
    fault_mode = None if args.fault_mode == "none" else args.fault_mode

    df = run_simulation(
        fault_mode=fault_mode,
        fault_start_step=args.fault_start_step,
        total_steps=args.steps,
        time_step_seconds=args.sleep,
        persist_to_db=args.to_db,
    )

    if not args.no_csv:
        out_path = save_simulation_csv(df, Path(args.output))
        print(f"[DT] Data saved to {out_path}")
