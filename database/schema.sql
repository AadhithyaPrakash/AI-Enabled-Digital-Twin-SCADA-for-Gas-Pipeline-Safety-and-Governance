-- database/schema.sql

CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    pressure_bar FLOAT,
    flow_m3s FLOAT,
    temperature_c FLOAT,
    vibration FLOAT,
    valve_state INTEGER
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    event_type VARCHAR(50),
    severity VARCHAR(20),
    parameter VARCHAR(50),
    value FLOAT
);

CREATE TABLE IF NOT EXISTS ai_events (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    anomaly_score FLOAT,
    threshold FLOAT,
    status VARCHAR(20)
);
CREATE TABLE IF NOT EXISTS ai_model_metadata (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(50),
    threshold FLOAT,
    trained_at TIMESTAMP
);
