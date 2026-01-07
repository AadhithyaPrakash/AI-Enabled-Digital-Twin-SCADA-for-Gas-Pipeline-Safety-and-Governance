import pandas as pd
from database.db_connector import get_db_connection

def compare_scada_vs_ai():
    conn = get_db_connection()

    scada_df = pd.read_sql("""
        SELECT timestamp
        FROM events
        ORDER BY timestamp
    """, conn)

    ai_df = pd.read_sql("""
        SELECT timestamp
        FROM ai_events
        ORDER BY timestamp
    """, conn)

    conn.close()

    if scada_df.empty or ai_df.empty:
        print("⚠️ Not enough data for comparison")
        return

    scada_first = scada_df.iloc[0]["timestamp"]
    ai_first = ai_df.iloc[0]["timestamp"]

    delay = (ai_first - scada_first).total_seconds()

    print("SCADA vs AI Detection Comparison\n")

    print("First SCADA alarm :", scada_first)
    print("First AI anomaly  :", ai_first)
    print(f"Detection gap     : {delay:.2f} seconds")

if __name__ == "__main__":
    compare_scada_vs_ai()
