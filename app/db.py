import sqlite3


class DBInstance:
    conn: sqlite3.Connection

    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        pass

    @property
    def cursor(self) -> sqlite3.Cursor:
        return self.conn.cursor()

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
        activity TEXT,
        FOREIGN KEY (astronaut_id) REFERENCES alert(astronaut_id));

    CREATE TABLE IF NOT EXISTS user(
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        astronaut_id TEXT NOT NULL,
        name TEXT NOT NULL UNIQUE );

    """
    # Create Alert Table
    dbInstance.cursor.executescript(script)
    pass


if __name__ == "__main__":
    initializeDatabase()
    pass
