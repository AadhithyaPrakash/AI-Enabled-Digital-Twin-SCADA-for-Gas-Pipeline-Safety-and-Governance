"""
hmi/simulation_service.py
Background simulation worker — one thread-safe singleton shared across Flask requests.

State machine:  idle → running → stopping → idle
                                           → error
"""
import logging
import threading
import time
from datetime import datetime

import digital_twin.config as dt_cfg
from digital_twin.simulator    import generate_normal_reading
from digital_twin.fault_injection import inject_leak, inject_blockage, inject_sensor_drift
from scada.ingestion import ingest_data, reset_ingestion_state  # noqa: E501

log = logging.getLogger('sim')

# ── States ────────────────────────────────────────────────────────────────────
IDLE     = 'idle'
RUNNING  = 'running'
STOPPING = 'stopping'
ERROR    = 'error'


class SimulationService:
    def __init__(self):
        self._lock   = threading.Lock()
        self._state  = IDLE
        self._thread = None
        self._cfg    = {}
        self._cache  = {
            'step':         0,
            'latest':       None,
            'started_at':   None,
            'last_error':   None,
            'scenario_name': 'Normal Pipeline',
            'fault_active': False,
        }

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def state(self):
        with self._lock:
            return self._state

    def get_status(self) -> dict:
        with self._lock:
            fault_mode       = self._cfg.get('fault_mode') or 'none'
            fault_start_step = int(self._cfg.get('fault_start_step', 150))
            current_step     = self._cache['step']
            return {
                'state':            self._state,
                'step':             current_step,
                'total_steps':      self._cfg.get('steps', dt_cfg.TOTAL_STEPS),
                'fault_mode':       fault_mode,
                'fault_start_step': fault_start_step,
                'fault_active':     self._cache['fault_active'],
                'scenario_name':    self._cfg.get('scenario_name', 'Normal Pipeline'),
                'started_at':       self._cache['started_at'].isoformat()
                                    if self._cache['started_at'] else None,
                'last_error':       self._cache['last_error'],
                # steps until fault fires (useful for dashboard countdown)
                'steps_until_fault': max(0, fault_start_step - current_step)
                                     if fault_mode != 'none' and self._state == RUNNING
                                     else 0,
            }

    def start(self, pipeline_cfg: dict, sim_cfg: dict) -> tuple[bool, str]:
        """
        pipeline_cfg – physical parameters from the Engineer page
        sim_cfg      – {fault_mode, fault_start_step, steps, step_seconds,
                        scenario_name}
        """
        with self._lock:
            if self._state == RUNNING:
                return False, 'Already running'
            self._apply_pipeline_cfg(pipeline_cfg)
            self._cfg = sim_cfg
            self._cache.update(
                step=0, latest=None,
                started_at=datetime.utcnow(), last_error=None,
                scenario_name=sim_cfg.get('scenario_name', 'Custom'),
                fault_active=False,
            )
            self._state = RUNNING

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return True, 'started'

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            if self._state != RUNNING:
                return False, 'Not running'
            self._state = STOPPING
        return True, 'stopping'

    # ── Internals ─────────────────────────────────────────────────────────────

    def _apply_pipeline_cfg(self, cfg: dict):
        """Push engineer-page values into dt_cfg module globals at runtime."""
        mapping = {
            'pipeline_length_m':    'PIPELINE_LENGTH_M',
            'pipeline_diameter_m':  'PIPELINE_DIAMETER_M',
            'gas_density':          'GAS_DENSITY',
            'friction_coefficient': 'FRICTION_COEFFICIENT',
            'normal_pressure_bar':  'NORMAL_PRESSURE_BAR',
            'normal_flow_m3s':      'NORMAL_FLOW_M3S',
            'normal_temperature_c': 'NORMAL_TEMPERATURE_C',
            'normal_vibration':     'NORMAL_VIBRATION',
            'pressure_min':         'PRESSURE_MIN',
            'pressure_max':         'PRESSURE_MAX',
            'flow_min':             'FLOW_MIN',
            'flow_max':             'FLOW_MAX',
            'num_bends':            'NUM_BENDS',
        }
        for key, attr in mapping.items():
            if key in cfg and hasattr(dt_cfg, attr):
                setattr(dt_cfg, attr, float(cfg[key]))

    def _run(self):
        # Reset rolling state (rate-of-change history + AI threshold)
        reset_ingestion_state()

        cfg              = self._cfg
        fault_mode       = cfg.get('fault_mode')
        fault_start_step = int(cfg.get('fault_start_step', 150))
        total_steps      = int(cfg.get('steps', dt_cfg.TOTAL_STEPS))
        step_seconds     = float(cfg.get('step_seconds', dt_cfg.TIME_STEP_SECONDS))
        scenario_name    = cfg.get('scenario_name', 'Custom')

        log.info('[SIM] Starting — scenario="%s"  fault=%s  fault_at_step=%d  steps=%d  dt=%.2fs',
                 scenario_name, fault_mode or 'none', fault_start_step, total_steps, step_seconds)

        try:
            for step in range(total_steps):
                with self._lock:
                    if self._state == STOPPING:
                        log.info('[SIM] Stopped by user at step %d', step)
                        self._state = IDLE
                        return

                data = generate_normal_reading()

                fault_active = fault_mode and step >= fault_start_step
                if fault_active:
                    if fault_mode == 'leak':
                        data = inject_leak(data)
                    elif fault_mode == 'blockage':
                        data = inject_blockage(data)
                    elif fault_mode == 'sensor_drift':
                        data = inject_sensor_drift(data)

                    if step == fault_start_step:
                        log.warning('[SIM] FAULT ACTIVATED — %s at step %d', fault_mode, step)

                try:
                    alarms, score, is_anomaly = ingest_data(data, step=step)
                except Exception as exc:
                    log.error('[SIM] ingest_data failed at step %d: %s', step, exc)
                    alarms, score, is_anomaly = [], 0.0, False

                with self._lock:
                    self._cache['step']         = step + 1
                    self._cache['fault_active'] = bool(fault_active)
                    self._cache['latest']       = {
                        'timestamp':     data['timestamp'].isoformat(),
                        'pressure_bar':  data['pressure_bar'],
                        'flow_m3s':      data['flow_m3s'],
                        'temperature_c': data['temperature_c'],
                        'vibration':     data['vibration'],
                        'valve_state':   data['valve_state'],
                        'alarms':        alarms,
                        'anomaly_score': float(score),
                        'is_anomaly':    bool(is_anomaly),
                    }

                time.sleep(step_seconds)

            log.info('[SIM] Completed — %d steps', total_steps)
            with self._lock:
                self._state = IDLE

        except Exception as exc:
            log.error('[SIM] Crashed: %s', exc, exc_info=True)
            with self._lock:
                self._state = ERROR
                self._cache['last_error'] = str(exc)


# Module-level singleton — imported by app.py
simulation_service = SimulationService()
