"""
hmi/app.py
Flask application — serves the two-page HMI and all JSON API endpoints.

Run from project root:
    python -m hmi.app

Design rule: data endpoints ALWAYS return HTTP 200 with {ok, data} shape.
             Never return 500 — the frontend can handle empty data, not crashes.
"""
import json
import logging
import traceback
from flask import Flask, jsonify, render_template, request, redirect, url_for
from database.db_connector import get_db_connection
from database.schema_manager import ensure_schema
from hmi.simulation_service import simulation_service

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('hmi')

app = Flask(__name__, template_folder='templates', static_folder='static')


# ── Ensure DB schema exists at startup ───────────────────────────────────────
try:
    ensure_schema()
    log.info('✅ Database schema ready')
except Exception as e:
    log.warning(f'⚠️  Schema check failed (DB may not be running): {e}')


# ── Helpers ───────────────────────────────────────────────────────────────────
def db_ok():
    """Returns True if the database is reachable."""
    try:
        conn = get_db_connection()
        conn.close()
        return True
    except Exception:
        return False


def safe_json_response(func):
    """
    Decorator: wraps a route so that ANY exception becomes a 200 JSON
    response with {ok: false, error: ..., data: []} instead of a 500.
    """
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            log.error(f'Endpoint {func.__name__} failed: {exc}\n{traceback.format_exc()}')
            return jsonify({'ok': False, 'error': str(exc), 'data': []}), 200
    return wrapper


# ── Page routes ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return redirect(url_for('engineer'))

@app.route('/engineer')
def engineer():
    return render_template('engineer.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


# ── Simulation control ────────────────────────────────────────────────────────
@app.route('/api/simulation/start', methods=['POST'])
def api_start():
    body = request.get_json(silent=True) or {}
    pipeline_cfg = body.get('pipeline_cfg', {})
    sim_cfg = {
        'fault_mode':       body.get('fault_mode') or None,
        'fault_start_step': int(body.get('fault_start_step', 150)),
        'steps':            int(body.get('steps', 300)),
        'step_seconds':     float(body.get('step_seconds', 1)),
        'scenario_name':    body.get('scenario_name', 'Custom'),
    }
    log.info(f'Simulation start requested — fault={sim_cfg["fault_mode"]}, steps={sim_cfg["steps"]}')
    ok, msg = simulation_service.start(pipeline_cfg, sim_cfg)
    status  = simulation_service.get_status()
    return jsonify({'ok': ok, 'message': msg, 'state': status['state']}), (200 if ok else 409)


@app.route('/api/simulation/stop', methods=['POST'])
def api_stop():
    ok, msg = simulation_service.stop()
    status  = simulation_service.get_status()
    log.info(f'Simulation stop requested — {msg}')
    return jsonify({'ok': ok, 'message': msg, 'state': status['state']})


# ── System status ─────────────────────────────────────────────────────────────
@app.route('/api/system/status')
def api_status():
    status = simulation_service.get_status()
    status['db_connected'] = db_ok()
    return jsonify(status)


# ── Telemetry ─────────────────────────────────────────────────────────────────
@app.route('/api/telemetry/live')
@safe_json_response
def api_telemetry():
    limit = min(int(request.args.get('limit', 300)), 1000)
    conn  = get_db_connection()
    cur   = conn.cursor()
    try:
        cur.execute("""
            SELECT timestamp, pressure_bar, flow_m3s, temperature_c, vibration, valve_state
            FROM sensor_data
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))
        rows = list(reversed(cur.fetchall()))
    finally:
        cur.close()
        conn.close()

    data = [
        {
            'timestamp':     r[0].isoformat(),
            'pressure_bar':  r[1],
            'flow_m3s':      r[2],
            'temperature_c': r[3],
            'vibration':     r[4],
            'valve_state':   r[5],
        }
        for r in rows
    ]
    return jsonify({'ok': True, 'data': data, 'count': len(data)})


# ── SCADA events ──────────────────────────────────────────────────────────────
@app.route('/api/events/live')
@safe_json_response
def api_events():
    limit = min(int(request.args.get('limit', 100)), 500)
    conn  = get_db_connection()
    cur   = conn.cursor()
    try:
        cur.execute("""
            SELECT timestamp, event_type, severity, parameter, value
            FROM events
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    data = [
        {
            'timestamp':  r[0].isoformat(),
            'event_type': r[1],
            'severity':   r[2],
            'parameter':  r[3],
            'value':      r[4],
        }
        for r in rows
    ]
    return jsonify({'ok': True, 'data': data, 'count': len(data)})


# ── AI events ─────────────────────────────────────────────────────────────────
@app.route('/api/ai-events/live')
@safe_json_response
def api_ai_events():
    limit = min(int(request.args.get('limit', 100)), 500)
    conn  = get_db_connection()
    cur   = conn.cursor()
    try:
        cur.execute("""
            SELECT timestamp, anomaly_score, threshold, status, explanation
            FROM ai_events
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    data = []
    for r in rows:
        expl = r[4]
        if isinstance(expl, str):
            try:    expl = json.loads(expl)
            except: expl = {}
        data.append({
            'timestamp':     r[0].isoformat(),
            'anomaly_score': float(r[1]),
            'threshold':     float(r[2]),
            'status':        r[3],
            'explanation':   expl or {},
        })
    return jsonify({'ok': True, 'data': data, 'count': len(data)})


# ── AI Lab page ───────────────────────────────────────────────────────────────────────
@app.route('/ai-lab')
def ai_lab():
    return render_template('ai_lab.html')


# ── AI model status ──────────────────────────────────────────────────────────────────
@app.route('/api/ai/status')
@safe_json_response
def api_ai_status():
    """Model registry status + training state."""
    from ai_engine.train_autoencoder import training_status
    from ai_engine.model_registry   import registry
    from ai_engine.inference_engine  import engine

    latest = registry.latest()
    train  = training_status()

    return jsonify({
        'ok': True,
        'model': {
            'version':          latest['version']      if latest else None,
            'trained_at':       latest['trained_at']   if latest else None,
            'threshold':        latest['threshold']    if latest else None,
            'threshold_method': latest.get('threshold_method','') if latest else None,
            'dataset_size':     latest.get('dataset_size',0)      if latest else 0,
            'training_loss':    latest.get('training_loss',None)  if latest else None,
            'val_loss':         latest.get('val_loss',None)        if latest else None,
            'epochs_run':       latest.get('epochs_run',0)         if latest else 0,
        },
        'training': {
            'running':     train['running'],
            'started_at':  train['started_at'],
            'finished_at': train['finished_at'],
            'error':       train['error'],
        },
        'engine': {
            'loaded':    engine.is_loaded,
            'version':   engine.version,
            'threshold': engine.threshold,
        },
        'registry_count': len(registry.all()),
        'registry':       registry.all(),
    })


# ── AI training trigger ───────────────────────────────────────────────────────────────
@app.route('/api/ai/train', methods=['POST'])
def api_ai_train():
    """Start background AI training."""
    body   = request.get_json(silent=True) or {}
    steps  = int(body.get('steps', 500))
    epochs = int(body.get('epochs', 50))
    if simulation_service.state == 'running':
        return jsonify({'ok': False, 'message': 'Stop the simulation before training'}), 409
    from ai_engine.train_autoencoder import start_background_training
    ok, msg = start_background_training(steps=steps, epochs=epochs)
    log.info('AI training requested — steps=%d  epochs=%d  ok=%s', steps, epochs, ok)
    return jsonify({'ok': ok, 'message': msg}), (200 if ok else 409)


# ── Experiment comparison ──────────────────────────────────────────────────────────────
@app.route('/api/ai/experiment')
@safe_json_response
def api_ai_experiment():
    """SCADA vs AI detection comparison for the current/last simulation run."""
    from ai_engine.anomaly_detector import detector
    summary = detector.experiment_summary()
    summary['scenario_name'] = simulation_service.get_status().get('scenario_name', '')
    return jsonify({'ok': True, 'data': summary})


# ── Live AI score history ─────────────────────────────────────────────────────────────
@app.route('/api/ai/scores')
@safe_json_response
def api_ai_scores():
    """
    All anomaly scores from the current/last simulation run.
    Provides the continuous score timeline (not just anomaly events).
    """
    from ai_engine.inference_engine import engine
    limit = min(int(request.args.get('limit', 500)), 1000)
    hist  = engine.score_history()[-limit:]
    return jsonify({
        'ok':        True,
        'data':      hist,
        'threshold': engine.threshold,
        'count':     len(hist),
    })


# ── Data reset ───────────────────────────────────────────────────────────────
@app.route('/api/data/reset', methods=['POST'])
def api_data_reset():
    """TRUNCATE all simulation tables and clear in-memory AI state."""
    if simulation_service.state == 'running':
        return jsonify({'ok': False, 'message': 'Stop the simulation before resetting data'}), 409

    try:
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            for table in ['sensor_data', 'events', 'ai_events', 'ai_model_metadata']:
                cur.execute(f'TRUNCATE TABLE {table} RESTART IDENTITY CASCADE')
        conn.close()
        log.info('[RESET] All tables truncated')
    except Exception as exc:
        log.error('[RESET] DB truncate failed: %s', exc)
        return jsonify({'ok': False, 'message': str(exc)}), 200

    # Clear in-memory AI state so the score chart and experiment panel go blank
    try:
        from ai_engine.inference_engine import engine
        with engine._lock:
            engine._score_history.clear()
    except Exception:
        pass

    try:
        from ai_engine.anomaly_detector import detector
        detector.reset()
    except Exception:
        pass

    log.info('[RESET] In-memory AI state cleared')
    return jsonify({'ok': True, 'message': 'All data cleared'})


# ── Debug endpoint (for troubleshooting) ─────────────────────────────────────
@app.route('/api/debug/status')
def api_debug():
    """Returns DB row counts and simulation state for debugging."""
    info = {'db_connected': False, 'tables': {}, 'simulation': simulation_service.get_status()}
    try:
        conn = get_db_connection()
        cur  = conn.cursor()
        for table in ['sensor_data', 'events', 'ai_events', 'ai_model_metadata']:
            try:
                cur.execute(f'SELECT COUNT(*) FROM {table}')
                info['tables'][table] = cur.fetchone()[0]
            except Exception as e:
                info['tables'][table] = f'error: {e}'
        cur.close()
        conn.close()
        info['db_connected'] = True
    except Exception as e:
        info['db_error'] = str(e)
    return jsonify(info)


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
