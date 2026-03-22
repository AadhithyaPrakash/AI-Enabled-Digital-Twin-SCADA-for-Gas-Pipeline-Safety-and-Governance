# scada/ingestion.py
"""
SCADA ingestion pipeline — one reading per call.

Flow:
    raw reading
        → persist to sensor_data
        → rule engine  → persist to events (if alarm)
        → AI detector  → persist to ai_events (if anomaly)
        → return (alarms, score, is_anomaly)
"""
import logging
import warnings

# Suppress sklearn feature-name mismatch warning (cosmetic only — data is correct).
# Scaler was fitted on numpy arrays; inference uses DataFrames. No data impact.
warnings.filterwarnings(
    'ignore',
    message='X has feature names',
    category=UserWarning,
    module='sklearn',
)

from scada.alarm_rules  import evaluate_scada_alarms, reset_rolling_state
from scada.historian    import write_sensor_data, write_event, write_ai_event

log = logging.getLogger('scada.ingestion')

_current_step = 0   # tracks simulation step within a run


def reset_ingestion_state():
    """
    Reset all per-run state.
    Called once at the start of each simulation run by simulation_service.
    """
    global _current_step
    _current_step = 0

    reset_rolling_state()          # clear rate-of-change history

    # Reset experiment tracker
    try:
        from ai_engine.anomaly_detector import detector
        detector.reset()
    except Exception as e:
        log.warning('[INGESTION] Could not reset anomaly detector: %s', e)

    # Reload AI threshold (picks up any newly trained model)
    try:
        from ai_engine.inference_engine import engine
        if not engine.is_loaded:
            engine._ensure_loaded()   # lazy-load on first use
        log.info('[INGESTION] AI engine ready — v%s  threshold=%s',
                 engine.version, engine.threshold)
    except Exception as e:
        log.warning('[INGESTION] AI engine not ready: %s', e)


def ingest_data(data: dict, step: int = 0) -> tuple:
    """
    Process a single telemetry reading.

    Returns:
        alarms       : list of alarm dicts (may be empty)
        score        : AI reconstruction error float
        is_anomaly   : bool
    """
    global _current_step
    _current_step = step

    # ── Step 1: persist raw reading ──────────────────────────────────────────
    write_sensor_data(data)

    # ── Step 2: SCADA rule engine ─────────────────────────────────────────────
    alarms = evaluate_scada_alarms(data)
    for alarm in alarms:
        alarm['timestamp'] = data['timestamp']
        write_event(alarm)

    # ── Step 3: AI anomaly detection ─────────────────────────────────────────
    score      = 0.0
    is_anomaly = False

    try:
        from ai_engine.anomaly_detector import detector

        result = detector.evaluate(data, step=step, scada_alarms=alarms)
        score      = result['score']
        is_anomaly = result['is_anomaly']

        print(f'[AI DEBUG] step={step}  score={score:.6f}'
              f'  threshold={result["threshold"]:.6f}'
              f'  anomaly={is_anomaly}')

        if is_anomaly:
            expl = result.get('explanation', {})
            write_ai_event(
                timestamp=data['timestamp'],
                score=score,
                threshold=result['threshold'],
                status='ANOMALY_DETECTED',
                explanation=expl.get('feature_errors', expl),
            )

    except Exception as exc:
        log.warning('[INGESTION] AI evaluation skipped: %s', exc)
        score, is_anomaly = 0.0, False

    return alarms, score, is_anomaly
