"""
test_db_connection.py
Quick pre-flight check — run this before starting the HMI.

Verifies:
  1. PostgreSQL is reachable with the configured credentials
  2. All required tables exist (runs schema migration if needed)
  3. Prints current row counts in each table

Usage:
    python test_db_connection.py
"""
import sys
from database.db_connector  import get_db_connection
from database.schema_manager import ensure_schema

print("-" * 50)
print("  DT-SCADA  pre-flight check")
print("-" * 50)

# 1. Connection
try:
    conn = get_db_connection()
    conn.close()
    print("[OK] Database connection OK")
except Exception as e:
    print(f"[FAIL] Database connection FAILED: {e}")
    print()
    print("  Check that PostgreSQL is running and .env has correct credentials.")
    print("  Minimum required in .env:")
    print("    DB_NAME=postgres")
    print("    DB_USER=postgres")
    print("    DB_PASSWORD=<your password>")
    sys.exit(1)

# 2. Schema
try:
    ensure_schema()
    print("[OK] Schema ready (all tables exist)")
except Exception as e:
    print(f"[FAIL] Schema migration failed: {e}")
    sys.exit(1)

# 3. Row counts
tables = ['sensor_data', 'events', 'ai_events', 'ai_model_metadata']
try:
    conn = get_db_connection()
    cur  = conn.cursor()
    print()
    print("  Table              Rows")
    print("  -------------------------")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        flag = "  <- run reset_db.sql to clear" if n > 0 and t == 'sensor_data' else ""
        print(f"  {t:<22} {n:>6}{flag}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"[WARN] Could not read row counts: {e}")

print()
print("[OK] All checks passed - ready to start.")
print()
print("  Start the HMI:  python -m hmi.app")
print("  Then open:      http://localhost:5000")
print("-" * 50)
