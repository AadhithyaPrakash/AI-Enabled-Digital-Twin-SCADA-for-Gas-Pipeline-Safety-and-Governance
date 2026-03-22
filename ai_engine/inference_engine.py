"""
ai_engine/inference_engine.py
==============================
Model loading + per-sample inference.

Key design decisions:
  - NO lru_cache: artifacts are reloadable after re-training without restart
  - Loads from model registry (latest version) with fallback to legacy paths
  - Exposes reload() so train_autoencoder can hot-swap the model
  - Keeps a rolling window of recent scores for trend analysis

Usage:
    from ai_engine.inference_engine import engine
    score, errors = engine.score(data)
    explanation   = engine.explain(data)
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np
import pandas as pd

log = logging.getLogger('ai.inference')

REPO_ROOT   = Path(__file__).resolve().parents[1]
FEATURES    = ['pressure_bar', 'flow_m3s', 'temperature_c', 'vibration']

# Legacy fallback paths (backward compatibility)
LEGACY_MODEL  = REPO_ROOT / 'ai_engine' / 'autoencoder_model.keras'
LEGACY_SCALER = REPO_ROOT / 'ai_engine' / 'scaler.pkl'


class InferenceEngine:
    """
    Thin wrapper around a trained Keras autoencoder.
    Thread-safe reload support for hot model swapping after training.
    """

    def __init__(self):
        self._lock   = threading.Lock()
        self._model  = None
        self._scaler = None
        self._loaded = False
        self._version: Optional[int] = None
        self._threshold: Optional[float] = None
        # Rolling score history — kept for full run (500 steps covers all scenarios)
        self._score_history: list[float] = []
        self._history_maxlen = 500

    # ── Loading ───────────────────────────────────────────────────────────────

    def _try_load(self):
        """Load artifacts from registry or fallback paths. Thread-unsafe; call under lock."""
        from tensorflow.keras.models import load_model

        # Try registry first
        try:
            from ai_engine.model_registry import registry
            entry = registry.latest()
            if entry:
                mpath = Path(entry['model_path'])
                spath = Path(entry['scaler_path'])
                if mpath.exists() and spath.exists():
                    self._model   = load_model(mpath, compile=False)
                    self._scaler  = joblib.load(spath)
                    self._version = entry['version']
                    self._threshold = float(entry['threshold'])
                    log.info('[INFERENCE] Loaded registry v%d  threshold=%.6f',
                             self._version, self._threshold)
                    self._loaded = True
                    return
        except Exception as e:
            log.debug('[INFERENCE] Registry load failed: %s', e)

        # Fallback to legacy paths
        if LEGACY_MODEL.exists() and LEGACY_SCALER.exists():
            self._model   = load_model(LEGACY_MODEL, compile=False)
            self._scaler  = joblib.load(LEGACY_SCALER)
            self._version = 0
            self._threshold = None
            log.info('[INFERENCE] Loaded legacy model artifacts')
            self._loaded = True
            return

        raise FileNotFoundError(
            'No trained model found. Train with: python -m ai_engine.train_autoencoder'
        )

    def _ensure_loaded(self):
        """Load on first use (lazy). Thread-safe."""
        with self._lock:
            if not self._loaded:
                self._try_load()

    def reload(self):
        """Hot-reload after re-training. Called by train_autoencoder."""
        with self._lock:
            self._loaded = False
            self._model  = None
            self._scaler = None
            self._score_history.clear()
        self._ensure_loaded()
        log.info('[INFERENCE] Reloaded — v%s', self._version)

    # ── Inference ─────────────────────────────────────────────────────────────

    def score(self, data: dict) -> Tuple[float, dict]:
        """
        Compute reconstruction error for a single telemetry reading.

        Returns:
            score   : mean squared reconstruction error (float)
            errors  : per-feature absolute reconstruction error (dict)
        """
        self._ensure_loaded()

        df     = pd.DataFrame([[data[f] for f in FEATURES]], columns=FEATURES)
        scaled = self._scaler.transform(df)
        recon  = self._model.predict(scaled, verbose=0)

        mse    = float(np.mean((scaled - recon) ** 2))
        errors = {f: float(abs(scaled[0, i] - recon[0, i]))
                  for i, f in enumerate(FEATURES)}

        # Update rolling history
        with self._lock:
            self._score_history.append(mse)
            if len(self._score_history) > self._history_maxlen:
                self._score_history.pop(0)

        return mse, errors

    def explain(self, data: dict, score: float, errors: dict) -> dict:
        """
        Build a human-readable explanation for a given anomaly.

        Identifies the dominant contributing feature and its deviation
        relative to normal operating conditions.
        """
        sorted_errors = dict(sorted(errors.items(), key=lambda x: x[1], reverse=True))
        top_feature   = next(iter(sorted_errors))
        top_error     = sorted_errors[top_feature]

        # Deviation as % above normal value
        normal_val = data.get(top_feature, 0) or 1e-9
        deviation_pct = round(abs(top_error / (normal_val + 1e-9)) * 100, 1)

        return {
            'feature_errors':  {k: round(v, 6) for k, v in sorted_errors.items()},
            'top_feature':     top_feature,
            'top_error':       round(top_error, 6),
            'deviation_pct':   deviation_pct,
            'score':           round(score, 6),
            'threshold':       round(self.threshold or 0, 6),
        }

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def threshold(self) -> Optional[float]:
        return self._threshold

    @property
    def version(self) -> Optional[int]:
        return self._version

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def score_history(self) -> list[float]:
        with self._lock:
            return list(self._score_history)

    def rolling_mean(self, window: int = 10) -> Optional[float]:
        """Rolling mean of recent scores — useful for trend detection."""
        hist = self.score_history()
        if len(hist) < window:
            return None
        return float(np.mean(hist[-window:]))


# Module-level singleton
engine = InferenceEngine()
