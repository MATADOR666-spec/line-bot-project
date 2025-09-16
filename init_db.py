from database import execute_db

execute_db("DROP TABLE IF EXISTS profiles")
execute_db("DROP TABLE IF EXISTS duty_logs")

execute_db("""
CREATE TABLE profiles (
    userId TEXT PRIMARY KEY,
    ชื่อ TEXT,
    ห้อง TEXT,
    เลขที่ TEXT,
    บทบาท TEXT,
    เวรวัน TEXT,
    วันที่สมัคร TEXT,
    สถานะ TEXT
)
""")

execute_db("""
CREATE TABLE duty_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    userId TEXT,
    ห้อง TEXT,
    เวรวัน TEXT,
    วันที่ TEXT,
    url1 TEXT,
    url2 TEXT,
    url3 TEXT,
    เวลา TEXT,
    สถานะ TEXT
)
""")

print("✅ Database initialized!")
