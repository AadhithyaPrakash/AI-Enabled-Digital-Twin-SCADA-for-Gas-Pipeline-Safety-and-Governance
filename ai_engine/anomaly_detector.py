"""
ai_engine/anomaly_detector.py
==============================
High-level anomaly detection layer.

Responsibilities:
  - Wraps inference_engine with threshold logic
  - Tracks experiment state per simulation run:
      · first AI anomaly step + timestamp
      · first SCADA alarm step + timestamp
      · detection latency comparison
  - Provides experiment summary for the dashboard

Usage:
    from ai_engine.anomaly_detector import detector
    result = detector.evaluate(data, step, scada_alarms)
    summary = detector.experiment_summary()
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Optional

log = logging.getLogger('ai.detector')

# Threshold policy:
#   1. Use model registry value if available
#   2. Fall back to DB metadata value if registry/model is unavailable
#   3. Fall back to DEFAULT if no model exists
AI_THRESHOLD_DEFAULT = 0.07
FEATURES = ['pressure_bar', 'flow_m3s', 'temperature_c', 'vibration']


class AnomalyDetector:
    """
    Per-simulation-run anomaly detection with experiment tracking.
    reset() must be called at the start of each simulation run.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._reset_state()

    def _reset_state(self):
        self._step_count        = 0
        self._ai_first_step     = None   # step when first AI anomaly fired
        self._ai_first_ts       = None   # timestamp of first AI anomaly
        self._scada_first_step  = None   # step when first SCADA alarm fired
        self._scada_first_ts    = None
        self._anomaly_count     = 0
        self._scada_alarm_count = 0
        self._scores: list[float] = []   # all scores this run
        self._threshold_used: Optional[float] = None
        # Consecutive confirmation: require N steps in a row above threshold
        # before treating as a real anomaly. Eliminates single-step noise spikes
        # on normal data while catching sustained fault patterns.
        self._consecutive_above: int = 0
        self._CONFIRM_STEPS: int = 2

    def reset(self):
        """Call at the start of each simulation run."""
        with self._lock:
            self._reset_state()
        log.info('[DETECTOR] Reset for new simulation run')

    # ── Core evaluation ───────────────────────────────────────────────────────

    def evaluate(self, data: dict, step: int,
                 scada_alarms: list) -> dict:
        """
        Evaluate a single telemetry reading.

        Args:
            data         : telemetry dict
            step         : current simulation step (0-based)
            scada_alarms : list of alarm dicts from alarm_rules

        Returns dict with keys:
            score, threshold, is_anomaly, explanation, latency_advantage
        """
        from ai_engine.inference_engine import engine

        result = {
            'score':              0.0,
            'threshold':          AI_THRESHOLD_DEFAULT,
            'is_anomaly':         False,
            'explanation':        {},
            'top_feature':        None,
            'latency_advantage':  None,  # seconds AI was earlier than SCADA
        }

        # Determine effective threshold
        threshold = self._effective_threshold(engine)
        result['threshold'] = threshold

        # Run inference
        try:
            score, errors = engine.score(data)
        except FileNotFoundError:
            # Model not trained yet — silent pass
            return result
        except Exception as exc:
            log.warning('[DETECTOR] Inference error: %s', exc)
            return result

        explanation = engine.explain(data, score, errors)
        raw_above   = score > threshold   # this step alone exceeds threshold

        # Consecutive confirmation: only fire a confirmed anomaly after
        # _CONFIRM_STEPS consecutive steps above threshold. This eliminates
        # single-step noise spikes without delaying fault detection meaningfully.
        with self._lock:
            if raw_above:
                self._consecutive_above += 1
            else:
                self._consecutive_above = 0
            confirmed = self._consecutive_above >= self._CONFIRM_STEPS

        is_anomaly = confirmed

        # Build result — score is always accurate; is_anomaly is confirmed only
        result.update({
            'score':        round(score, 6),
            'is_anomaly':   is_anomaly,
            'explanation':  explanation,
            'top_feature':  explanation.get('top_feature'),
        })

        # Structured log
        if is_anomaly:
            log.warning(
                '[AI EVENT] step=%d  score=%.4f  threshold=%.4f  '
                'top_feature=%s  p=%.2f  f=%.2f  t=%.1f  vib=%.3f',
                step, score, threshold,
                explanation.get('top_feature', '?'),
                data.get('pressure_bar', 0),
                data.get('flow_m3s', 0),
                data.get('temperature_c', 0),
                data.get('vibration', 0),
            )
        elif raw_above:
            log.debug('[AI] step=%d  score=%.4f (above threshold, confirming…)', step, score)
        else:
            log.debug('[AI] step=%d  score=%.4f', step, score)

        # Update experiment tracking
        now = data.get('timestamp') or datetime.utcnow()
        with self._lock:
            self._step_count += 1
            self._scores.append(score)
            self._threshold_used = threshold

            if is_anomaly:
                self._anomaly_count += 1
                if self._ai_first_step is None:
                    self._ai_first_step = step
                    self._ai_first_ts   = now
                    log.info('[EXPERIMENT] First confirmed AI anomaly at step %d', step)

            if scada_alarms:
                high_alarms = [a for a in scada_alarms
                               if a.get('severity') in ('HIGH', 'MEDIUM')]
                if high_alarms:
                    self._scada_alarm_count += len(high_alarms)
                    if self._scada_first_step is None:
                        self._scada_first_step = step
                        self._scada_first_ts   = now
                        log.info('[EXPERIMENT] First SCADA alarm at step %d', step)

            # Compute latency advantage (positive = AI was earlier)
            if (self._ai_first_step is not None and
                    self._scada_first_step is not None):
                result['latency_advantage'] = (
                    self._scada_first_step - self._ai_first_step
                )

        return result

    # ── Experiment summary ────────────────────────────────────────────────────

    def experiment_summary(self) -> dict:
        """
        Return experiment statistics for the current/last simulation run.
        Used by /api/ai/experiment endpoint.
        """
        with self._lock:
            scores = list(self._scores)
            ai_step    = self._ai_first_step
            scada_step = self._scada_first_step

        latency_steps  = None
        latency_verdict = 'No fault detected yet'

        if ai_step is not None and scada_step is not None:
            latency_steps = scada_step - ai_step
            if latency_steps > 0:
                latency_verdict = f'AI detected {latency_steps} steps earlier than SCADA'
            elif latency_steps < 0:
                latency_verdict = f'SCADA detected {abs(latency_steps)} steps earlier than AI'
            else:
                latency_verdict = 'AI and SCADA detected simultaneously'
        elif ai_step is not None:
            latency_verdict = f'AI detected anomaly at step {ai_step} (SCADA silent)'
        elif scada_step is not None:
            latency_verdict = f'SCADA alarm at step {scada_step} (AI silent)'

        score_mean = float(sum(scores) / len(scores)) if scores else 0.0
        score_max  = float(max(scores)) if scores else 0.0

        return {
            'steps_run':            self._step_count,
            'ai_first_anomaly_step': ai_step,
            'ai_first_anomaly_ts':  self._ai_first_ts.isoformat()
                                    if isinstance(self._ai_first_ts, datetime)
                                    else str(self._ai_first_ts) if self._ai_first_ts else None,
            'scada_first_alarm_step': scada_step,
            'scada_first_alarm_ts': self._scada_first_ts.isoformat()
                                    if isinstance(self._scada_first_ts, datetime)
                                    else str(self._scada_first_ts) if self._scada_first_ts else None,
            'latency_steps':        latency_steps,
            'latency_verdict':      latency_verdict,
            'ai_anomaly_count':     self._anomaly_count,
            'scada_alarm_count':    self._scada_alarm_count,
            'score_mean':           round(score_mean, 6),
            'score_max':            round(score_max, 6),
            'threshold_used':       self._threshold_used,
            'ai_advantage':         latency_steps is not None and latency_steps > 0,
        }

    # ── Threshold resolution ──────────────────────────────────────────────────

    def _effective_threshold(self, engine) -> float:
        """
        Resolve threshold.
        Priority: engine registry value -> DB value -> default.
        """
        # Engine loaded from registry (best source).
        # Use trained threshold as-is; capping can create false positives.
        if engine.is_loaded and engine.threshold is not None:
            thr = float(engine.threshold)
            if thr > 0:
                return thr

        db_val = self._load_threshold_from_db()
        if db_val is not None and db_val > 0:
            return float(db_val)

        return AI_THRESHOLD_DEFAULT

    @staticmethod
    def _load_threshold_from_db() -> Optional[float]:
        """Load the latest trained threshold from ai_model_metadata."""
        try:
            from database.db_connector import get_db_connection
            conn = get_db_connection()
            try:
                with conn, conn.cursor() as cur:
                    cur.execute(
                        'SELECT threshold FROM ai_model_metadata '
                        'ORDER BY trained_at DESC NULLS LAST, id DESC LIMIT 1'
                    )
                    row = cur.fetchone()
                    return float(row[0]) if row and row[0] is not None else None
            finally:
                conn.close()
        except Exception:
            return None


# Module-level singleton
detector = AnomalyDetector()
