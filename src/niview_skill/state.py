import sqlite3
import time
from pathlib import Path
from typing import Self


class EventStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen (
                event_id TEXT PRIMARY KEY,
                device_id INTEGER NOT NULL,
                create_date INTEGER NOT NULL,
                path TEXT NOT NULL,
                seen_at INTEGER NOT NULL
            )
            """
        )
        self.conn.commit()

    def seen(self, event_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM seen WHERE event_id = ?", (event_id,)
        ).fetchone()
        return row is not None

    def add(self, event_id: str, device_id: int, create_date: int, path: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO seen(event_id, device_id, create_date, path, seen_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (event_id, device_id, create_date, path, int(time.time())),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
