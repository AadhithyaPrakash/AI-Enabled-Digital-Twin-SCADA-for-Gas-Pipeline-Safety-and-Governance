"""
ai_engine/dataset_builder.py
============================
Generates a CLEAN normal-operation dataset for AI training.

Key design decision: data is generated directly from the Digital Twin simulator
(not from the DB) so it is guaranteed to be 100% normal — no contamination
from previous fault-scenario runs.

Usage:
    from ai_engine.dataset_builder import build_normal_dataset
    path, meta = build_normal_dataset(steps=500)
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Tuple

import pandas as pd

log = logging.getLogger('ai.dataset')

REPO_ROOT   = Path(__file__).resolve().parents[1]
DATASET_DIR = REPO_ROOT / 'datasets'
FEATURES    = ['pressure_bar', 'flow_m3s', 'temperature_c', 'vibration']


def build_normal_dataset(
    steps: int = 500,
    label: str = 'normal',
    save_csv: bool = True,
) -> Tuple[pd.DataFrame, dict]:
    """
    Run the Digital Twin in normal mode (no faults) and return a clean dataset.

    Returns:
        df   : DataFrame with columns = FEATURES
        meta : dict with dataset statistics and file path
    """
    # Import here so we don't load TF at module-import time
    import digital_twin.config as dt_cfg
    from digital_twin.simulator import generate_normal_reading

    log.info('[DATASET] Generating %d normal steps …', steps)

    rows = []
    for _ in range(steps):
        reading = generate_normal_reading()
        rows.append({f: reading[f] for f in FEATURES})

    df = pd.DataFrame(rows, columns=FEATURES)

    # Compute feature statistics (used for threshold calibration and explainability)
    stats = {
        feat: {
            'mean':  float(df[feat].mean()),
            'std':   float(df[feat].std()),
            'min':   float(df[feat].min()),
            'max':   float(df[feat].max()),
            'p95':   float(df[feat].quantile(0.95)),
        }
        for feat in FEATURES
    }

    meta: dict = {
        'label':      label,
        'steps':      steps,
        'created_at': datetime.utcnow().isoformat(),
        'features':   FEATURES,
        'stats':      stats,
        'csv_path':   None,
    }

    if save_csv:
        DATASET_DIR.mkdir(parents=True, exist_ok=True)
        ts  = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        csv_path = DATASET_DIR / f'{label}_{ts}.csv'
        df.to_csv(csv_path, index=False)
        meta['csv_path'] = str(csv_path)
        log.info('[DATASET] Saved → %s', csv_path)

    return df, meta


def load_latest_normal_dataset() -> Tuple[pd.DataFrame, Path]:
    """Load the most recently generated normal dataset CSV."""
    csvs = sorted(DATASET_DIR.glob('normal_*.csv'))
    if not csvs:
        raise FileNotFoundError(
            'No normal dataset found. Run build_normal_dataset() first.'
        )
    path = csvs[-1]
    return pd.read_csv(path), path
