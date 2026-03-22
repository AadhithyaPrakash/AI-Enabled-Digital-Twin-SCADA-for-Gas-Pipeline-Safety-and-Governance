# AI-Enabled Digital Twin SCADA for Gas Pipeline Safety and Governance

A final year B.E. research project demonstrating AI-based anomaly detection in simulated gas pipeline monitoring, evaluated against traditional rule-based SCADA alarms.

**Research question:** Can an autoencoder-based AI model detect pipeline faults earlier than threshold-based SCADA rules?

---

## Architecture

```
Pipeline Engineer UI  →  Simulation Engine  →  Telemetry Stream
                                                      │
                                              ┌───────┴───────┐
                                        SCADA Rules      AI Autoencoder
                                        (alarm_rules)    (anomaly_detector)
                                              │               │
                                              └───────┬───────┘
                                                 PostgreSQL DB
                                                      │
                                            Operations Dashboard
                                                  AI Lab Page
```

### Layers

| Layer | Module | Purpose |
|---|---|---|
| Digital Twin | `digital_twin/` | Physics-based gas pipeline simulator |
| SCADA | `scada/` | Two-tier rule engine + PostgreSQL historian |
| AI Engine | `ai_engine/` | Autoencoder anomaly detection pipeline |
| Database | `database/` | PostgreSQL schema + connection management |
| HMI | `hmi/` | Flask app — Pipeline Engineer, Dashboard, AI Lab |

---

## Setup

### Prerequisites
- Python 3.10+
- PostgreSQL 14+ running locally
- Create database: `CREATE DATABASE "SCADA";`

### Install
```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### Environment
```bash
cp .env.example .env
# Edit .env — set DB_PASSWORD at minimum
```

---

## Running the system

### 1. Start the HMI
```bash
python -m hmi.app
# → http://localhost:5000
```

### 2. Workflow (in the browser)

**Step 1 — Normal pipeline run (training data)**
- Go to **Pipeline Engineer** → select *Normal Pipeline* → Run Simulation
- This seeds the database with clean normal telemetry

**Step 2 — Train the AI**
- Go to **AI Lab** → click *Train AI Model*
- Trains a 4→16→8→3→8→16→4 autoencoder on clean simulator data
- Threshold calibrated as `min(mean + 2.5σ, p95)` of reconstruction errors

**Step 3 — Run a fault scenario**
- Go to **Pipeline Engineer** → select any fault scenario → Run Simulation
- Watch the Dashboard for SCADA alarms and AI anomaly events

**Step 4 — Compare results**
- Go to **AI Lab** → **Experiment Results** panel
- See which system detected the fault first and by how many steps

---

## Pages

| URL | Description |
|---|---|
| `/engineer` | Pipeline topology designer + scenario selector |
| `/dashboard` | Live telemetry charts + event feed (SCADA + AI) |
| `/ai-lab` | Model training, SCADA vs AI comparison, score timeline |

---

## Fault scenarios

| Scenario | Fault | What changes |
|---|---|---|
| Normal Pipeline | None | Baseline — train AI here |
| Pressure Leak | `leak` | Pressure drops, flow spikes, vibration spikes |
| Pipeline Blockage | `blockage` | Pressure builds upstream, flow drops |
| Sensor Drift | `sensor_drift` | Gradual pressure drift — SCADA stays silent |
| Silent Degradation | `sensor_drift` | Same as drift, early onset — best AI showcase |
| Valve Stuck | `blockage` | Upstream pressure rise, flow collapse |
| Compressor Failure | `blockage` | Fast flow collapse |
| Full System Fault | `leak` | Maximum stress |

---

## AI Engine modules

| File | Purpose |
|---|---|
| `dataset_builder.py` | Generates clean normal-operation dataset from simulator (not DB) |
| `train_autoencoder.py` | Full training pipeline: data → scale → train → threshold → save |
| `inference_engine.py` | Reloadable model wrapper; 500-point score history |
| `anomaly_detector.py` | Per-run experiment tracker; SCADA vs AI latency comparison |
| `model_registry.py` | JSON registry at `models/registry.json` |

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/simulation/start` | Start simulation with scenario config |
| POST | `/api/simulation/stop` | Stop running simulation |
| GET | `/api/system/status` | Simulation state + step progress |
| GET | `/api/telemetry/live` | Last N sensor readings |
| GET | `/api/events/live` | Last N SCADA alarm events |
| GET | `/api/ai-events/live` | Last N AI anomaly events |
| GET | `/api/ai/status` | Model version, threshold, training state |
| POST | `/api/ai/train` | Start background model training |
| GET | `/api/ai/experiment` | SCADA vs AI detection comparison |
| GET | `/api/ai/scores` | Full anomaly score history (current run) |

---

## Database tables

| Table | Purpose |
|---|---|
| `sensor_data` | Raw telemetry (all steps) |
| `events` | SCADA rule alarms |
| `ai_events` | AI anomaly detections with feature-level explanation (JSONB) |
| `ai_model_metadata` | Trained model threshold values |

---

## Standards referenced

ASME B31.8 · API RP 1110 · ISO 13623 · PNGRB · ISA-95 · IEC-61508
