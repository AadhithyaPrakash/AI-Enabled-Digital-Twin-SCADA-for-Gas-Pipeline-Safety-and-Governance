"""
ai_engine/model_registry.py
============================
Simple JSON-based model registry.

Stores model version metadata:
  - version number
  - trained_at timestamp
  - threshold (and how it was computed)
  - feature scaler stats
  - training loss history
  - dataset path used

All metadata lives in:   models/registry.json
Model artifacts live in: models/autoencoder_v{N}.keras
Scaler artifacts live in: models/scaler_v{N}.pkl

Usage:
    from ai_engine.model_registry import ModelRegistry
    reg = ModelRegistry()
    reg.save(version=1, threshold=0.072, ...)
    meta = reg.latest()
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger('ai.registry')

REPO_ROOT    = Path(__file__).resolve().parents[1]
MODELS_DIR   = REPO_ROOT / 'models'
REGISTRY_FILE = MODELS_DIR / 'registry.json'


class ModelRegistry:
    """Lightweight JSON registry for trained autoencoder models."""

    def __init__(self):
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self._data: list[dict] = self._load()

    # ── Paths ─────────────────────────────────────────────────────────────────

    @staticmethod
    def model_path(version: int) -> Path:
        return MODELS_DIR / f'autoencoder_v{version}.keras'

    @staticmethod
    def scaler_path(version: int) -> Path:
        return MODELS_DIR / f'scaler_v{version}.pkl'

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(self, *, version: int, threshold: float, threshold_method: str,
             dataset_path: str, dataset_size: int,
             feature_stats: dict, training_loss: float,
             val_loss: float = 0.0, epochs_run: int = 0) -> dict:
        """Register a newly trained model."""
        entry = {
            'version':          version,
            'trained_at':       datetime.utcnow().isoformat(),
            'threshold':        round(threshold, 8),
            'threshold_method': threshold_method,
            'dataset_path':     dataset_path,
            'dataset_size':     dataset_size,
            'feature_stats':    feature_stats,
            'training_loss':    round(float(training_loss), 8),
            'val_loss':         round(float(val_loss), 8),
            'epochs_run':       epochs_run,
            'model_path':       str(self.model_path(version)),
            'scaler_path':      str(self.scaler_path(version)),
        }
        self._data.append(entry)
        self._save()
        log.info('[REGISTRY] Saved model v%d  threshold=%.6f  method=%s',
                 version, threshold, threshold_method)
        return entry

    def latest(self) -> Optional[dict]:
        """Return metadata for the most recently trained model, or None."""
        return self._data[-1] if self._data else None

    def all(self) -> list[dict]:
        return list(self._data)

    def next_version(self) -> int:
        if not self._data:
            return 1
        return self._data[-1]['version'] + 1

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if REGISTRY_FILE.exists():
            try:
                return json.loads(REGISTRY_FILE.read_text())
            except Exception:
                return []
        return []

    def _save(self):
        REGISTRY_FILE.write_text(
            json.dumps(self._data, indent=2, default=str)
        )


# Module-level singleton
registry = ModelRegistry()
