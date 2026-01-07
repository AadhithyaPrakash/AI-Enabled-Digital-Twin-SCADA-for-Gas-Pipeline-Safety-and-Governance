from digital_twin.simulator import run_simulation
from scada.ingestion import ingest_data

print("[SYSTEM] Starting DT → SCADA → DB test")

df = run_simulation(fault_mode="leak")

for _, row in df.iterrows():
    alarms = ingest_data(row.to_dict())

    if alarms:
        print("[SCADA ALARM]", alarms)

print("[SYSTEM] Test completed")
