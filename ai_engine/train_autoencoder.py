"""
ai_engine/train_autoencoder.py
===============================
Clean training pipeline for the anomaly detection autoencoder.

Architecture:  4 -> 16 -> 8 -> 3 (latent) -> 8 -> 16 -> 4
Loss:          MSE reconstruction
Threshold:     mean(errors) + 2.5 * std(errors)
               - more sensitive than p99, adapts to actual score distribution

Typical usage:
    python -m ai_engine.train_autoencoder

Or via API:
    POST /api/ai/train   {"steps": 500}
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

log = logging.getLogger('ai.train')

REPO_ROOT = Path(__file__).resolve().parents[1]
FEATURES  = ['pressure_bar', 'flow_m3s', 'temperature_c', 'vibration']

# ── Training state (used by API to track background training) ─────────────────
_training_state = {
    'running':    False,
    'started_at': None,
    'finished_at': None,
    'error':      None,
    'last_result': None,   # filled with registry entry on success
}
_training_lock = threading.Lock()


def training_status() -> dict:
    with _training_lock:
        return dict(_training_state)


# ── Core training function ────────────────────────────────────────────────────

def train(
    steps: int = 500,
    epochs: int = 50,
    batch_size: int = 32,
    validation_split: float = 0.1,
    threshold_sigmas: float = 2.5,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Full training pipeline:
      1. Generate clean normal dataset
      2. Fit MinMaxScaler
      3. Train autoencoder
      4. Compute adaptive threshold
      5. Save artifacts and register

    Returns the model registry entry dict.
    """
    def emit(msg: str):
        log.info(msg)
        if progress_cb:
            progress_cb(msg)

    emit(f'[TRAIN] Starting - {steps} normal steps, {epochs} epochs')

    # ── Step 1: Dataset ───────────────────────────────────────────────────────
    from ai_engine.dataset_builder import build_normal_dataset
    df, dataset_meta = build_normal_dataset(steps=steps, label='normal')
    emit(f'[TRAIN] Dataset built - {len(df)} rows')

    # ── Step 2: Preprocessing ─────────────────────────────────────────────────
    scaler = MinMaxScaler(feature_range=(0, 1))
    X = scaler.fit_transform(df[FEATURES].values)
    emit('[TRAIN] Data normalised (MinMaxScaler)')

    # ── Step 3: Build + train model ───────────────────────────────────────────
    from tensorflow.keras.layers import Dense, Input
    from tensorflow.keras.models   import Model
    from tensorflow.keras.callbacks import EarlyStopping

    inputs  = Input(shape=(4,))
    encoded = Dense(16, activation='relu')(inputs)
    encoded = Dense(8,  activation='relu')(encoded)
    latent  = Dense(3,  activation='relu')(encoded)   # bottleneck
    decoded = Dense(8,  activation='relu')(latent)
    decoded = Dense(16, activation='relu')(decoded)
    outputs = Dense(4,  activation='linear')(decoded)

    model = Model(inputs, outputs, name='pipeline_autoencoder')
    model.compile(optimizer='adam', loss='mse')
    emit(f'[TRAIN] Autoencoder built - params: {model.count_params()}')

    early_stop = EarlyStopping(monitor='val_loss', patience=5,
                                restore_best_weights=True, verbose=0)
    history = model.fit(
        X, X,
        epochs=epochs,
        batch_size=batch_size,
        validation_split=validation_split,
        callbacks=[early_stop],
        verbose=0,
    )
    epochs_run   = len(history.history['loss'])
    train_loss   = float(history.history['loss'][-1])
    val_loss     = float(history.history.get('val_loss', [0.0])[-1])
    emit(f'[TRAIN] Training complete - {epochs_run} epochs  loss={train_loss:.6f}  val={val_loss:.6f}')

    # ── Step 4: Threshold calibration ─────────────────────────────────────────
    recon  = model.predict(X, verbose=0)
    errors = np.mean((X - recon) ** 2, axis=1)

    err_mean = float(np.mean(errors))
    err_std  = float(np.std(errors))
    err_p95  = float(np.percentile(errors, 95))
    err_max  = float(np.max(errors))

    # Use mean + N*std threshold; cap at p95 to avoid over-sensitivity
    threshold_sigma = err_mean + threshold_sigmas * err_std
    threshold = min(threshold_sigma, err_p95)

    emit(f'[TRAIN] Threshold: mean={err_mean:.6f}  std={err_std:.6f}'
         f'  mean+{threshold_sigmas}*std={threshold_sigma:.6f}'
         f'  p95={err_p95:.6f}  max={err_max:.6f}'
         f'  -> SELECTED={threshold:.6f}')

    # ── Step 5: Save artifacts ────────────────────────────────────────────────
    from ai_engine.model_registry import registry

    version     = registry.next_version()
    model_path  = registry.model_path(version)
    scaler_path = registry.scaler_path(version)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)
    joblib.dump(scaler, scaler_path)
    emit(f'[TRAIN] Artifacts saved -> {model_path.name}, {scaler_path.name}')

    # Also copy as "latest" for backward compatibility with existing code
    latest_model  = REPO_ROOT / 'ai_engine' / 'autoencoder_model.keras'
    latest_scaler = REPO_ROOT / 'ai_engine' / 'scaler.pkl'
    model.save(latest_model)
    joblib.dump(scaler, latest_scaler)

    # ── Step 6: Register ──────────────────────────────────────────────────────
    entry = registry.save(
        version=version,
        threshold=threshold,
        threshold_method=f'min(mean+{threshold_sigmas}*std, p95)',
        dataset_path=dataset_meta.get('csv_path', ''),
        dataset_size=len(df),
        feature_stats=dataset_meta['stats'],
        training_loss=train_loss,
        val_loss=val_loss,
        epochs_run=epochs_run,
    )

    # ── Step 7: Update DB threshold ───────────────────────────────────────────
    try:
        from database.db_connector  import get_db_connection
        from database.schema_manager import ensure_schema
        ensure_schema()
        conn = get_db_connection()
        with conn, conn.cursor() as cur:
            cur.execute(
                'INSERT INTO ai_model_metadata (model_name, threshold, trained_at) '
                'VALUES (%s, %s, %s)',
                (f'autoencoder_v{version}', float(threshold), datetime.utcnow()),
            )
        conn.close()
        emit(f'[TRAIN] Threshold stored in DB: {threshold:.6f}')
    except Exception as exc:
        log.warning('[TRAIN] Could not write threshold to DB: %s', exc)

    # ── Step 8: Reload inference engine ───────────────────────────────────────
    try:
        from ai_engine.inference_engine import engine as _engine
        _engine.reload()
        emit('[TRAIN] Inference engine reloaded with new model')
    except Exception as exc:
        log.warning('[TRAIN] Could not reload inference engine: %s', exc)

    emit(f'[TRAIN] Done - v{version}  threshold={threshold:.6f}')
    return entry


# ── Background training (for API use) ────────────────────────────────────────

def start_background_training(steps: int = 500, epochs: int = 50):
    """Launch training in a daemon thread. Returns immediately."""
    with _training_lock:
        if _training_state['running']:
            return False, 'Training already in progress'
        _training_state.update(running=True, started_at=datetime.utcnow().isoformat(),
                                finished_at=None, error=None, last_result=None)

    def _run():
        msgs = []
        try:
            result = train(steps=steps, epochs=epochs,
                           progress_cb=lambda m: msgs.append(m))
            with _training_lock:
                _training_state.update(running=False,
                                        finished_at=datetime.utcnow().isoformat(),
                                        last_result=result, error=None)
        except Exception as exc:
            log.error('[TRAIN] Background training failed: %s', exc, exc_info=True)
            with _training_lock:
                _training_state.update(running=False,
                                        finished_at=datetime.utcnow().isoformat(),
                                        error=str(exc))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return True, 'Training started'


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--steps',  type=int, default=500)
    parser.add_argument('--epochs', type=int, default=50)
    args = parser.parse_args()
    result = train(steps=args.steps, epochs=args.epochs)
    print(f'\nTraining complete - version {result["version"]}  '
          f'threshold={result["threshold"]:.6f}')
