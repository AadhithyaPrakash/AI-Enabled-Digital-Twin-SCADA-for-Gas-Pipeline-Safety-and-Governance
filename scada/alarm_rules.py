# scada/alarm_rules.py
"""
Two-tier SCADA rule engine:

Tier 1 — CRITICAL / HIGH : hard limit violations (existing behaviour)
Tier 2 — WARNING         : near-threshold, rate-of-change, vibration spikes

Both tiers produce events that appear in the dashboard event feed.
"""
import logging

import digital_twin.config as dt_cfg

log = logging.getLogger('scada.rules')

# ── Rolling state for rate-of-change detection ────────────────────────────────
_prev = {
    'pressure_bar':  None,
    'flow_m3s':      None,
    'temperature_c': None,
    'vibration':     None,
}

# How many standard deviations from nominal counts as a WARNING
# These are fraction-of-range thresholds, not statistical
NEAR_THRESHOLD_FRAC = 0.10   # within 10 % of limit → WARNING
ROC_PRESSURE_WARN   = 2.0    # bar/step sudden change → WARNING
ROC_FLOW_WARN       = 2.0    # m³/s/step sudden change → WARNING
# Normal vibration is now ~0.50 (after simulator fix).
# Faults add 0.5–1.2 (blockage) or 1.0–2.0 (leak) on top.
VIBRATION_WARN      = 0.90   # blockage-range → WARNING
VIBRATION_HIGH      = 1.60   # leak-range     → HIGH
TEMPERATURE_WARN    = 35.0   # °C above normal band → WARNING


def evaluate_scada_alarms(data: dict) -> list:
    """
    Evaluate all SCADA rule tiers against a single telemetry reading.
    Returns a list of alarm dicts ready for historian.write_event().
    """
    alarms = []

    p   = data.get('pressure_bar', 0.0)
    f   = data.get('flow_m3s',     0.0)
    t   = data.get('temperature_c',0.0)
    vib = data.get('vibration',    0.0)

    p_min = getattr(dt_cfg, 'PRESSURE_MIN', 50.0)
    p_max = getattr(dt_cfg, 'PRESSURE_MAX', 70.0)
    f_min = getattr(dt_cfg, 'FLOW_MIN',     20.0)
    f_max = getattr(dt_cfg, 'FLOW_MAX',     30.0)

    # ── Tier 1 : Hard limit violations ───────────────────────────────────────

    if p < p_min:
        alarms.append(_alarm('PRESSURE_LOW',  'HIGH',   'pressure', p,
                             f'Pressure {p:.2f} bar below minimum {p_min} bar'))

    if p > p_max:
        alarms.append(_alarm('PRESSURE_HIGH', 'HIGH',   'pressure', p,
                             f'Pressure {p:.2f} bar above maximum {p_max} bar'))

    if f < f_min:
        alarms.append(_alarm('FLOW_LOW',      'MEDIUM', 'flow',     f,
                             f'Flow {f:.2f} m³/s below minimum {f_min} m³/s'))

    if f > f_max:
        alarms.append(_alarm('FLOW_HIGH',     'MEDIUM', 'flow',     f,
                             f'Flow {f:.2f} m³/s above maximum {f_max} m³/s'))

    # ── Tier 2a : Near-threshold warnings ────────────────────────────────────

    p_range = p_max - p_min
    f_range = f_max - f_min

    # Pressure approaching lower limit
    if p_min < p < p_min + p_range * NEAR_THRESHOLD_FRAC:
        alarms.append(_alarm('PRESSURE_LOW_WARNING', 'LOW', 'pressure', p,
                             f'Pressure {p:.2f} bar nearing low limit {p_min} bar'))

    # Pressure approaching upper limit
    if p_max - p_range * NEAR_THRESHOLD_FRAC < p < p_max:
        alarms.append(_alarm('PRESSURE_HIGH_WARNING', 'LOW', 'pressure', p,
                             f'Pressure {p:.2f} bar nearing high limit {p_max} bar'))

    # Flow approaching lower limit
    if f_min < f < f_min + f_range * NEAR_THRESHOLD_FRAC:
        alarms.append(_alarm('FLOW_LOW_WARNING', 'LOW', 'flow', f,
                             f'Flow {f:.2f} m³/s nearing low limit {f_min} m³/s'))

    # Flow approaching upper limit
    if f_max - f_range * NEAR_THRESHOLD_FRAC < f < f_max:
        alarms.append(_alarm('FLOW_HIGH_WARNING', 'LOW', 'flow', f,
                             f'Flow {f:.2f} m³/s nearing high limit {f_max} m³/s'))

    # ── Tier 2b : Rate-of-change detection ───────────────────────────────────

    if _prev['pressure_bar'] is not None:
        dp = abs(p - _prev['pressure_bar'])
        if dp >= ROC_PRESSURE_WARN:
            alarms.append(_alarm('PRESSURE_SPIKE', 'MEDIUM', 'pressure', p,
                                 f'Pressure change {dp:.2f} bar/step (spike detected)'))

    if _prev['flow_m3s'] is not None:
        df = abs(f - _prev['flow_m3s'])
        if df >= ROC_FLOW_WARN:
            alarms.append(_alarm('FLOW_SPIKE', 'MEDIUM', 'flow', f,
                                 f'Flow change {df:.2f} m³/s/step (spike detected)'))

    # ── Tier 2c : Vibration monitoring ───────────────────────────────────────

    if vib >= VIBRATION_HIGH:
        alarms.append(_alarm('VIBRATION_HIGH', 'HIGH', 'vibration', vib,
                             f'Vibration {vib:.3f} critically high'))
    elif vib >= VIBRATION_WARN:
        alarms.append(_alarm('VIBRATION_WARNING', 'LOW', 'vibration', vib,
                             f'Vibration {vib:.3f} above warning level'))

    # ── Tier 2d : Temperature monitoring ─────────────────────────────────────

    if t >= TEMPERATURE_WARN:
        alarms.append(_alarm('TEMPERATURE_WARNING', 'LOW', 'temperature', t,
                             f'Temperature {t:.1f} °C above warning level'))

    # ── Log and update rolling state ─────────────────────────────────────────

    for a in alarms:
        sev = a['severity']
        if sev == 'HIGH':
            log.warning('[SCADA ALARM] %s  %s=%.3f', a['type'], a['parameter'], a['value'])
        else:
            log.info('[SCADA WARNING] %s  %s=%.3f', a['type'], a['parameter'], a['value'])

    _prev['pressure_bar']  = p
    _prev['flow_m3s']      = f
    _prev['temperature_c'] = t
    _prev['vibration']     = vib

    return alarms


def reset_rolling_state():
    """Call at simulation start to clear stale rate-of-change history."""
    for k in _prev:
        _prev[k] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _alarm(event_type: str, severity: str, parameter: str,
           value: float, description: str = '') -> dict:
    return {
        'type':        event_type,
        'severity':    severity,
        'parameter':   parameter,
        'value':       float(value),
        'description': description,
    }
