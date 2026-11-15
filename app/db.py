import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from enum import Enum
from typing import List, Optional

import app.models as models

# Whitelist of tables -> columns. Identifiers can't be bound, so only
# names from this dict are ever formatted into SQL. Values always use :name.
_COLUMNS = {
    "user": ("origin_id", "astronaut_id", "name"),
    "reading": ("origin_id", "astronaut_id", "timestamp", "hr", "spo2",
                "temp", "bp_sys", "bp_dia", "resp", "activity"),
    "alert": ("origin_id", "astronaut_id", "timestamp", "severity",
              "metric", "message", "acknowledged", "activity", "value"),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reading(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    origin_id INTEGER,              -- id of the first row in a revision chain
    astronaut_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    hr REAL, spo2 REAL, temp REAL, bp_sys REAL, bp_dia REAL, resp REAL,
    activity TEXT NOT NULL DEFAULT 'rest');
CREATE INDEX IF NOT EXISTS idx_reading_astro_ts ON reading(astronaut_id, timestamp);

CREATE TABLE IF NOT EXISTS alert(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    origin_id INTEGER,
    astronaut_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    severity TEXT NOT NULL,
    metric TEXT NOT NULL,
    message TEXT NOT NULL,
    value REAL,
    activity TEXT NOT NULL DEFAULT 'rest',
    acknowledged INTEGER NOT NULL DEFAULT 0);

CREATE TABLE IF NOT EXISTS user(
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    origin_id INTEGER,
    astronaut_id TEXT NOT NULL,
    name TEXT NOT NULL);
"""


def _adapt(value):
    """Python -> SQLite for the types sqlite3 doesn't handle well."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


class DbController:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()  # FastAPI runs def routes in a threadpool
        with self._lock:
            self.conn.executescript(_SCHEMA)

    # ---------- internals ----------

    @contextmanager
    def _tx(self):
        """Locked cursor that commits on success and rolls back on error."""
        with self._lock:
            cur = self.conn.cursor()
            try:
                yield cur
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                cur.close()

    @staticmethod
    def _insert_row(cur: sqlite3.Cursor, table: str, data: dict) -> int:
        cols = _COLUMNS[table]  # KeyError on an unknown table
        cur.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join(':' + c for c in cols)})",
            {c: _adapt(data.get(c)) for c in cols},
        )
        return cur.lastrowid

    def _add(self, table: str, model) -> int:
        with self._tx() as cur:
            return self._insert_row(cur, table, model.model_dump())

    def _insert_revised(self, table: str, row_id: int, fields: dict) -> int:
        if not fields:
            raise ValueError("No fields provided to update")
        editable = set(_COLUMNS[table]) - {"origin_id"}
        unknown = set(fields) - editable
        if unknown:
            raise ValueError(
                f"Invalid field(s) for {table}: {sorted(unknown)}")

        with self._tx() as cur:  # select + insert are one atomic step
            cur.execute(
                f"SELECT * FROM {table} WHERE id = :id", {"id": row_id})
            row = cur.fetchone()
            if row is None:
                raise LookupError(f"No {table} row with id={row_id}")
            data = {**dict(row), **fields}
            data["origin_id"] = row["origin_id"] or row["id"]
            return self._insert_row(cur, table, data)  # id of the NEW row

    def _select(self, table: str, clauses=(), params=None,
                limit: Optional[int] = None, order_by: str = "id"):
        """Latest revision of each row, oldest first. clauses are constants."""
        if table not in _COLUMNS:
            raise ValueError(f"Unknown table: {table}")
        params = dict(params or {})
        sql = (f"SELECT * FROM {table} WHERE id IN "
               f"(SELECT MAX(id) FROM {table} GROUP BY COALESCE(origin_id, id))")
        for clause in clauses:
            sql += f" AND {clause}"
        sql += f" ORDER BY {order_by} DESC, id DESC"
        if limit is not None:
            sql += " LIMIT :limit"
            params["limit"] = limit
        with self._lock:
            rows = self.conn.execute(sql, params).fetchall()
        return rows[::-1]

    @staticmethod
    def _as(model, rows):
        return [model(**dict(r)) for r in rows]

    # ---------- getters ----------

    def get_user(self, astronaut_id: str) -> Optional[models.User]:
        rows = self._select("user", ["astronaut_id = :a"], {
            "a": astronaut_id}, limit=1)
        return self._as(models.User, rows)[0] if rows else None
    
    def get_name_map(self) -> dict[str, str]:
        rows = self._select("user")   # newest revision per user, no filters
        return {r["astronaut_id"]: r["name"] for r in rows}

    def get_readings(self, astronaut_id: str,
                     limit: Optional[int] = None) -> List[models.Reading]:
        rows = self._select("reading", ["astronaut_id = :a"],
                            {"a": astronaut_id}, limit=limit,
                            order_by="timestamp")
        return self._as(models.Reading, rows)

    def get_latest_reading(self, astronaut_id: str) -> Optional[models.Reading]:
        readings = self.get_readings(astronaut_id, limit=1)
        return readings[0] if readings else None

    def get_latest_readings(self) -> List[models.Reading]:
        """Newest reading for every astronaut (dashboard cards)."""
        with self._lock:
            ids = [r[0] for r in
                   self.conn.execute("SELECT DISTINCT astronaut_id FROM reading")]
        return [r for a in ids if (r := self.get_latest_reading(a))]

    def get_alerts(self, id: Optional[int], astronaut_id: Optional[str] = None,
                   severity: Optional[str] = None, active_only: bool = False,
                   limit: Optional[int] = None) -> List[models.Alert]:
        clauses, params = [], {}
        if astronaut_id:
            clauses.append("astronaut_id = :a")
            params["a"] = astronaut_id
        if severity:
            clauses.append("severity = :s")
            params["s"] = severity
        if active_only:
            clauses.append("acknowledged = 0")
        rows = self._select("alert", clauses, params, limit=limit)
        return self._as(models.Alert, rows)

    # ---------- setters ----------

    def add_user(self, user: models.User) -> int:
        return self._add("user", user)

    def add_reading(self, reading: models.Reading) -> int:
        return self._add("reading", reading)

    def add_alert(self, alert: models.Alert) -> int:
        return self._add("alert", alert)

    # ---------- "updates" (insert a revised copy) ----------

    def update_user(self, user_id: int, **fields) -> int:
        return self._insert_revised("user", user_id, fields)

    def update_reading(self, reading_id: int, **fields) -> int:
        return self._insert_revised("reading", reading_id, fields)

    def update_alert(self, alert_id: int, **fields) -> int:
        return self._insert_revised("alert", alert_id, fields)


DbInstance = DbController("./db.sqlite")
