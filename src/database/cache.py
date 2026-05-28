import json
import sqlite3
from datetime import datetime, timedelta

CACHE_TTL_DAYS = 30


class LastFMCache:
    """SQLite-backed cache for Last.fm API responses with a 30-day TTL.

    Entries are stored in the ``cache`` table as JSON blobs keyed by a
    colon-joined, lowercased string derived from the query parameters.
    Expired entries are deleted on read rather than by a background job.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def key(self, *parts) -> str:
        """Build a normalised cache key from arbitrary parts (lowercased, colon-joined)."""
        return ":".join(str(p).lower() for p in parts)

    def get(self, key: str) -> list | None:
        """Return cached data for ``key``, or None if absent or expired (expired rows are deleted)."""
        row = self._conn.execute(
            "SELECT response, expires_at FROM cache WHERE key=?", (key,)
        ).fetchone()
        if not row:
            return None
        if datetime.fromisoformat(row["expires_at"]) < datetime.now():
            self._conn.execute("DELETE FROM cache WHERE key=?", (key,))
            self._conn.commit()
            return None
        return json.loads(row["response"])

    def set(self, key: str, data: list) -> None:
        now = datetime.now()
        expires = now + timedelta(days=CACHE_TTL_DAYS)
        self._conn.execute(
            "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET response=excluded.response, cached_at=excluded.cached_at, expires_at=excluded.expires_at",
            (key, json.dumps(data), now.isoformat(), expires.isoformat()),
        )
        self._conn.commit()
