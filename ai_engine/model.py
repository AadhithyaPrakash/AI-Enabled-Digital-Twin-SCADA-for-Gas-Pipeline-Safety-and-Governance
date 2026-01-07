import pandas as pd
import psycopg2
import joblib
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Input, Dense
from database.db_connector import get_db_connection

FEATURES = ["pressure_bar", "flow_m3s", "temperature_c", "vibration"]

scaler = MinMaxScaler()

def load_training_data(limit=3000):
    conn = get_db_connection()
    query = f"""
        SELECT {', '.join(FEATURES)}
        FROM sensor_data
        ORDER BY timestamp ASC
        LIMIT {limit}
    """
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def build_autoencoder(input_dim):
    inputs = Input(shape=(input_dim,))
    encoded = Dense(8, activation="relu")(inputs)
    encoded = Dense(4, activation="relu")(encoded)
    decoded = Dense(8, activation="relu")(encoded)
    outputs = Dense(input_dim, activation="linear")(decoded)

    model = Model(inputs, outputs)
    model.compile(optimizer="adam", loss="mse")
    return model

def train_autoencoder():
    df = load_training_data()
    X = scaler.fit_transform(df)

    model = build_autoencoder(X.shape[1])
    model.fit(X, X, epochs=30, batch_size=32, validation_split=0.1)

    model.save("ai_engine/autoencoder_model.keras")
    print("✅ Autoencoder trained and saved")
    joblib.dump(scaler, "ai_engine/scaler.pkl")

if __name__ == "__main__":
    train_autoencoder()
