import numpy as np
import pandas as pd
import joblib
from tensorflow.keras.models import load_model
from sklearn.preprocessing import MinMaxScaler
from database.db_connector import get_db_connection

FEATURES = ["pressure_bar", "flow_m3s", "temperature_c", "vibration"]

model = load_model("ai_engine/autoencoder_model.keras")
scaler = joblib.load("ai_engine/scaler.pkl")


def load_threshold():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT threshold
        FROM ai_model_metadata
        ORDER BY trained_at DESC
        LIMIT 1
    """)

    threshold = cur.fetchone()

    cur.close()
    conn.close()
    return  float(threshold[0]) if threshold else None


def compute_anomaly_score(data):
    df = pd.DataFrame([[data[f] for f in FEATURES]], columns=FEATURES)
    values = scaler.transform(df)

    recon = model.predict(values, verbose=0)
    error = np.mean((values - recon) ** 2)

    return error, error > load_threshold()


# ✅ MISSING FUNCTION — NOW ADDED
def explain_anomaly(data):
    """
    Returns feature-wise reconstruction error
    for explainable AI decisions
    """
    df = pd.DataFrame([[data[f] for f in FEATURES]], columns=FEATURES)
    values = scaler.transform(df)

    recon = model.predict(values, verbose=0)

    feature_errors = np.abs(values - recon)[0]

    explanation = dict(zip(FEATURES, feature_errors))

    # sort by highest contribution
    explanation = dict(
        sorted(explanation.items(), key=lambda x: x[1], reverse=True)
    )

    return explanation
