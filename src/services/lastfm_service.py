import json
import sqlite3
from datetime import datetime, timedelta

import pylast

from src.utils.logger import get_logger

log = get_logger("lastfm")

CACHE_TTL_DAYS = 30


class LastFMService:
    def __init__(self, conn: sqlite3.Connection, api_key: str):
        self._conn = conn
        self._api_key = api_key
        self._network = None

    def _get_network(self):
        if self._network is None:
            self._network = pylast.LastFMNetwork(api_key=self._api_key)
        return self._network

    def _cache_key(self, *parts) -> str:
        return ":".join(str(p).lower() for p in parts)

    def _get_cache(self, key: str) -> list | None:
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

    def _set_cache(self, key: str, data: list) -> None:
        now = datetime.now()
        expires = now + timedelta(days=CACHE_TTL_DAYS)
        self._conn.execute(
            "INSERT INTO cache (key, response, cached_at, expires_at) VALUES (?,?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET response=excluded.response, cached_at=excluded.cached_at, expires_at=excluded.expires_at",
            (key, json.dumps(data), now.isoformat(), expires.isoformat()),
        )
        self._conn.commit()

    def search(self, query: str, search_type: str, limit: int = 5) -> list[dict]:
        """search_type: 'artist' | 'track' | 'album'"""
        if not self._api_key:
            return []
        key = self._cache_key("search", search_type, query)
        cached = self._get_cache(key)
        if cached is not None:
            return cached[:limit]
        try:
            net = self._get_network()
            if search_type == "artist":
                results = self._search_artists(net, query, limit)
            elif search_type == "track":
                results = self._search_tracks(net, query, limit)
            else:
                results = self._search_albums(net, query, limit)
            self._set_cache(key, results)
            return results
        except Exception as e:
            log.error(f"Last.fm search failed: {e}", exc_info=True)
            return []

    def _search_artists(self, net, query: str, limit: int) -> list[dict]:
        items = net.search_for_artist(query).get_next_page()[:limit]
        return [{"type": "artist", "name": a.get_name(), "mbid": a.get_mbid()} for a in items]

    def _search_tracks(self, net, query: str, limit: int) -> list[dict]:
        items = net.search_for_track("", query).get_next_page()[:limit]
        return [{"type": "track", "title": t.get_name(), "artist": t.get_artist().get_name(), "mbid": t.get_mbid()} for t in items]

    def _search_albums(self, net, query: str, limit: int) -> list[dict]:
        items = net.search_for_album(query).get_next_page()[:limit]
        return [{"type": "album", "title": a.get_name(), "artist": a.get_artist().get_name(), "mbid": a.get_mbid()} for a in items]

    def get_artist_top_tracks(self, artist_name: str, limit: int = 10) -> list[dict]:
        key = self._cache_key("top_tracks", artist_name)
        cached = self._get_cache(key)
        if cached is not None:
            return cached
        try:
            net = self._get_network()
            artist = net.get_artist(artist_name)
            tracks = artist.get_top_tracks(limit=limit)
            result = [{"type": "track", "title": t.item.get_name(), "artist": artist_name} for t in tracks]
            self._set_cache(key, result)
            return result
        except Exception as e:
            log.error(f"get_artist_top_tracks failed: {e}", exc_info=True)
            return []

    def get_album_tracks(self, album_title: str, artist_name: str) -> list[dict]:
        key = self._cache_key("album_tracks", artist_name, album_title)
        cached = self._get_cache(key)
        if cached is not None:
            return cached
        try:
            net = self._get_network()
            album = net.get_album(artist_name, album_title)
            tracks = album.get_tracks()
            result = [{"type": "track", "title": t.get_name(), "artist": artist_name, "album": album_title} for t in tracks]
            self._set_cache(key, result)
            return result
        except Exception as e:
            log.error(f"get_album_tracks failed: {e}", exc_info=True)
            return []
