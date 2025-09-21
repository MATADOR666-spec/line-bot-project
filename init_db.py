# init_db.py
import sqlite3
import os

DB_NAME = "data.db"  # หรือ path ที่ต้องการ เช่น "db/data.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS duty_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        userId TEXT,
        วันที่ TEXT,
        ห้อง TEXT,
        เวรวัน TEXT,
        เลขที่ผู้ส่ง TEXT,
        url1 TEXT,
        url2 TEXT,
        url3 TEXT,
        เวลา TEXT,
        สถานะ TEXT
    )""")
    conn.commit()
    conn.close()
    print("✅ Database created successfully")

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_NAME) or ".", exist_ok=True)
    init_db()
