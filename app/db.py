import sqlite3
from typing import List
import models


class DBInstance:
    conn: sqlite3.Connection

    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        pass

    @property
    def cursor(self) -> sqlite3.Cursor:
        return self.conn.cursor()

    def get_users(self, astronaut_id: str) -> List[models.User]:
        cursor = self.cursor
        cursor.execute("SELECT * from users WHERE astronaut_id=?",
                       (astronaut_id))
        return [models.User(**dict(row)) for row in cursor.fetchall()]

    def get_readings(self, astronaut_id: str) -> List[models.Reading]:
        cursor = self.cursor
        cursor.execute("SELECT * from users WHERE astronaut_id=?",
                       (astronaut_id))
        return [models.Reading(**dict(row)) for row in cursor.fetchall()]

    def get_alerts(self, astronaut_id: str) -> List[models.Alert]:
        cursor = self.cursor
        cursor.execute("SELECT * from alert WHERE astronaut_id=?",
                       (astronaut_id))
        return [models.Alert(**dict(row)) for row in cursor.fetchall()]

    def add_user(self, user: models.User) -> int:
        cursor = self.cursor
        cursor.execute(
            "INSERT INTO user (astronaut_id, name) VALUES (?, ?)",
            (user.astronaut_id, user.name),
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_reading(self, reading: models.Reading) -> int:
        cursor = self.cursor
        cursor.execute(
            """INSERT INTO reading
               (astronaut_id, timestamp, hr, spo2, temp, bp_sys, bp_dia, resp,
            activity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                reading.astronaut_id,
                reading.timestamp,
                reading.hr,
                reading.spo2,
                reading.temp,
                reading.bp_sys,
                reading.bp_dia,
                reading.resp,
                reading.activity,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_alert(self, alert: models.Alert) -> int:
        cursor = self.cursor
        cursor.execute(
            """INSERT INTO alert
               (astronaut_id, timestamp, hr, spo2, temp, bp_sys, bp_dia, resp,
            activity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                alert.astronaut_id,
                alert.timestamp,
                alert.hr,
                alert.spo2,
                alert.temp,
                alert.bp_sys,
                alert.bp_dia,
                alert.resp,
                alert.activity,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    pass


dbInstance = DBInstance("./db.sqlite")


def initializeDatabase():
    # Create Reading Table
    script = """
    CREATE TABLE IF NOT EXISTS reading(
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        astronaut_id TEXT NOT NULL,
        timestamp TEXT,
        hr REAL,
        spo2 REAL,
        temp REAL,
        bp_sys REAL,
        bp_dia REAL,
        resp REAL,
        activity TEXT);

    CREATE TABLE IF NOT EXISTS alert(
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        astronaut_id TEXT NOT NULL,
        timestamp TEXT,
        hr REAL,
        spo2 REAL,
        temp REAL,
        bp_sys REAL,
        bp_dia REAL,
        resp REAL,
        activity TEXT);

    CREATE TABLE IF NOT EXISTS user(
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        astronaut_id TEXT NOT NULL,
        name TEXT NOT NULL UNIQUE,
        FOREIGN KEY (astronaut_id) REFERENCES alert(astronaut_id),
        FOREIGN KEY (astronaut_id) REFERENCES reading(astronaut_id));

    """
    # Create Alert Table
    dbInstance.cursor.executescript(script)
    pass


if __name__ == "__main__":
    initializeDatabase()
    pass
