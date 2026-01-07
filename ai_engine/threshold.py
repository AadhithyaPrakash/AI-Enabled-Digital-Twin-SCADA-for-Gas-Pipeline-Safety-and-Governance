import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model
from sklearn.preprocessing import MinMaxScaler
from database.db_connector import get_db_connection
from datetime import datetime

FEATURES = ["pressure_bar", "flow_m3s", "temperature_c", "vibration"]

scaler = MinMaxScaler()
model = load_model("ai_engine/autoencoder_model.keras")

def compute_threshold(percentile=99):
    conn = get_db_connection()
    df = pd.read_sql(
        f"SELECT {', '.join(FEATURES)} FROM sensor_data ORDER BY timestamp ASC",
        conn
    )
    conn.close()

    X = scaler.fit_transform(df)
    recon = model.predict(X, verbose=0)
    errors = np.mean((X - recon) ** 2, axis=1)

    threshold = np.percentile(errors, percentile)
    print(f"✅ Anomaly threshold (p{percentile}):", threshold)

    return threshold

def save_threshold_to_db(threshold):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO ai_model_metadata (model_name, threshold, trained_at)
        VALUES (%s, %s, %s)
    """, ("autoencoder_v1", float(threshold), datetime.now()))

    conn.commit()
    cur.close()
    conn.close()

if __name__ == "__main__":
    threshold = compute_threshold()
    save_threshold_to_db(threshold)
