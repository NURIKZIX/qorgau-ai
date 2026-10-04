from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from .engine import Event


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
          id INTEGER PRIMARY KEY, candidate TEXT NOT NULL, exam TEXT NOT NULL,
          mode TEXT NOT NULL, started TEXT NOT NULL, ended TEXT,
          duration REAL DEFAULT 0, status TEXT NOT NULL DEFAULT 'running',
          settings TEXT NOT NULL, note TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES sessions(id),
          kind TEXT NOT NULL, start REAL NOT NULL, end REAL,
          detail TEXT NOT NULL, evidence TEXT, review TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE INDEX IF NOT EXISTS events_session ON events(session_id, start);
        """)
        self.connection.commit()

    def recover(self):
        # The application holds a QLockFile: no second process is recording.
        with self.connection:
            for row in self.connection.execute("SELECT id, duration FROM sessions WHERE status='running'").fetchall():
                self.connection.execute("UPDATE sessions SET status='interrupted', ended=? WHERE id=?", (utc_now(), row["id"]))
                self.connection.execute("UPDATE events SET end=MAX(start, ?) WHERE session_id=? AND end IS NULL", (row["duration"], row["id"]))

    def start(self, candidate, exam, mode, settings):
        with self.connection:
            cursor = self.connection.execute("INSERT INTO sessions(candidate,exam,mode,started,settings) VALUES(?,?,?,?,?)",
                (candidate, exam, mode, utc_now(), json.dumps(asdict(settings), ensure_ascii=False)))
        return cursor.lastrowid

    def add_event(self, session_id: int, event: Event):
        with self.connection:
            cursor = self.connection.execute("INSERT INTO events(session_id,kind,start,end,detail,evidence) VALUES(?,?,?,?,?,?)",
                (session_id, event.kind, event.start, event.end, event.detail, event.evidence))
        event.id = cursor.lastrowid

    def close_event(self, event):
        with self.connection:
            self.connection.execute("UPDATE events SET end=? WHERE id=?", (event.end, event.id))

    def heartbeat(self, session_id, duration):
        with self.connection:
            self.connection.execute("UPDATE sessions SET duration=? WHERE id=? AND status='running'", (duration, session_id))

    def finish(self, session_id, duration, status="completed"):
        with self.connection:
            self.connection.execute("UPDATE sessions SET ended=?,duration=?,status=? WHERE id=?", (utc_now(), duration, status, session_id))

    def sessions(self):
        return [dict(row) for row in self.connection.execute("SELECT s.*, (SELECT COUNT(*) FROM events e WHERE e.session_id=s.id) event_count FROM sessions s ORDER BY s.id DESC")]

    def session(self, session_id):
        row = self.connection.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise ValueError("Сессия не найдена")
        return dict(row)

    def events(self, session_id):
        return [dict(row) for row in self.connection.execute("SELECT * FROM events WHERE session_id=? ORDER BY start,id", (session_id,))]

    def review(self, event_id, verdict):
        if verdict not in ("pending", "confirmed", "dismissed"):
            raise ValueError("Invalid review")
        with self.connection:
            self.connection.execute("UPDATE events SET review=? WHERE id=?", (verdict, event_id))

    def note(self, session_id, note):
        with self.connection:
            self.connection.execute("UPDATE sessions SET note=? WHERE id=?", (note, session_id))

    def close(self):
        self.connection.close()
