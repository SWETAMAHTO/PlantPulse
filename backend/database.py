import sqlite3
import os

#Database file location
DATABASE_PATH = os.path.join(
    os.path.dirname(__file__),
    "plantpulse.db"
)

#Connect to database
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

#Create plants table
def create_tables():
    conn = get_db_connection()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS plants(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plant_name TEXT,
    image_filename TEXT NOT NULL,
    health_status TEXT,
    disease TEXT,
    watering_advice TEXT,
    symptoms TEXT,
    treatment TEXT,
    scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.commit()
    conn.close()

def migrate_database():
    conn = get_db_connection()

    columns = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(plants)"
        ).fetchall()
    ]

    if "symptoms" not in columns:
        conn.execute(
            "ALTER TABLE plants ADD COLUMN symptoms TEXT"
        )

    if "treatment" not in columns:
        conn.execute(
            "ALTER TABLE plants ADD COLUMN treatment TEXT"
        )

    conn.commit()
    conn.close()

#Initialize database
def init_db():
    create_tables()
    migrate_database()
    print("PlantPulse database created successfully!")