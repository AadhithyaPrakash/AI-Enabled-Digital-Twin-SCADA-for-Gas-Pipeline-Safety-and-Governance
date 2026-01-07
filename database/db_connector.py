import psycopg2
def get_db_connection():
    return psycopg2.connect(
        dbname="SCADA",
        user="postgres",
        password="welcome",
        host="localhost",
        port="5432"
    )
