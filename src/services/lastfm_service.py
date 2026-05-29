import sqlite3
from src.models.enums import SearchType

import pylast

from src.database.cache import LastFMCache
from src.utils.logger import get_logger

log = get_logger("lastfm")


class LastFMService:
    """Facade over pylast that adds a 30-day SQLite cache for all remote calls.

    The ``pylast.LastFMNetwork`` object is created lazily on the first request
    so the service can be instantiated before the API key is configured.
    """

    def __init__(self, conn: sqlite3.Connection, api_key: str):
        self._cache = LastFMCache(conn)
        self._api_key = api_key
        self._network = None

    def _get_network(self):
        """Return the shared pylast network, creating it on first use."""
        if self._network is None:
            self._network = pylast.LastFMNetwork(api_key=self._api_key)
        return self._network

    def _cached_fetch(self, key: str, fetch_fn, error_tag: str) -> list[dict]:
        """Return cached results if available, otherwise call ``fetch_fn``, cache, and return.

        Any exception from ``fetch_fn`` is logged and an empty list returned so
        callers never have to handle network failures explicitly.
        """
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        try:
            result = fetch_fn()
            self._cache.set(key, result)
            return result
        except Exception as e:
            log.error(f"{error_tag} failed: {e}", exc_info=True)
            return []

    def search(self, query: str, search_type: SearchType | str, limit: int = 5) -> list[dict]:
        """Search Last.fm for artists, tracks, or albums by ``search_type``, with caching."""
        if not self._api_key:
            return []
        key = self._cache.key("search", search_type, query)
        if search_type == SearchType.ARTIST:
            fetch = lambda: self._search_artists(self._get_network(), query, limit)
        elif search_type == SearchType.TRACK:
            fetch = lambda: self._search_tracks(self._get_network(), query, limit)
        else:
            fetch = lambda: self._search_albums(self._get_network(), query, limit)
        return self._cached_fetch(key, fetch, "Last.fm search")[:limit]

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
        key = self._cache.key("top_tracks", artist_name)
        return self._cached_fetch(
            key,
            lambda: [
                {"type": "track", "title": t.item.get_name(), "artist": artist_name}
                for t in self._get_network().get_artist(artist_name).get_top_tracks(limit=limit)
            ],
            "get_artist_top_tracks",
        )

    def get_album_tracks(self, album_title: str, artist_name: str) -> list[dict]:
        key = self._cache.key("album_tracks", artist_name, album_title)
        return self._cached_fetch(
            key,
            lambda: [
                {"type": "track", "title": t.get_name(), "artist": artist_name, "album": album_title}
                for t in self._get_network().get_album(artist_name, album_title).get_tracks()
            ],
            "get_album_tracks",
        )

    def get_track_album(self, artist: str, title: str) -> str | None:
        """Return the album name for a track from Last.fm, or None if unknown."""
        if not self._api_key:
            return None
        key = self._cache.key("track_album", artist, title)
        cached = self._cache.get(key)
        if cached is not None:
            return cached[0] if cached else None
        try:
            net = self._get_network()
            album_obj = net.get_track(artist, title).get_album()
            name = album_obj.get_name() if album_obj else None
            self._cache.set(key, [name] if name else [])
            return name
        except Exception as e:
            log.debug(f"get_track_album {artist!r}/{title!r}: {e}")
            return None

    def get_cover_image_url(self, artist: str, album: str | None = None) -> str | None:
        """Return extra-large cover image URL for an album, or None if album is unknown."""
        if not self._api_key or not album:
            return None
        try:
            net = self._get_network()
            url = net.get_album(artist, album).get_cover_image(pylast.SIZE_EXTRA_LARGE)
            return url or None
        except Exception as e:
            log.warning(f"get_cover_image_url {artist!r}/{album!r}: {e}")
            return None
