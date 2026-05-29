import base64
import json
import socket
import sqlite3
from functools import wraps
from src.database.database import (
    get_all_tracks, get_track, insert_track, update_track_status, delete_track,
    get_tracks_by_artist, get_tracks_by_album, search_tracks_local,
    get_all_artists, get_all_albums,
    insert_playlist, get_all_playlists, get_playlist_tracks,
    get_auto_playlist_count, delete_oldest_auto_playlist,
    delete_playlist, update_playlist_name, add_track_to_playlist, remove_track_from_playlist,
)
from src.database.config_manager import get_setting, set_setting, get_all_settings
from src.database.file_manager import start_background_scan
from src.models.track import Track
from src.models.playlist import Playlist
from src.services.lastfm_service import LastFMService
from src.services.youtube_service import YouTubeService
from src.services.player_service import PlayerService
from src.services.lrclib_service import LRCLibService
from src.services.cover_art_service import CoverArtService
from src.services.enrichment_scheduler import EnrichmentScheduler
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("api")

AUTO_PLAYLIST_LIMIT = 15


def _ok(data=None) -> str:
    return json.dumps({"success": True, **({"data": data} if data is not None else {})})


def _err(message: str) -> str:
    return json.dumps({"success": False, "error": message})


def _api_method(_fn=None, *, raw: bool = False):
    """Wrap a JS-callable method so its body can raise/return naturally.

    - body returns ``None`` -> ``_ok()``
    - body returns any other value -> ``_ok(value)`` (or ``json.dumps(value)`` if ``raw``)
    - body raises ``ValueError`` -> ``_err(str(e))`` (not logged at ERROR)
    - body raises anything else -> ``_err(str(e))`` + ``log.error(..., exc_info=True)``
    """
    def decorate(fn):
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            try:
                value = fn(self, *args, **kwargs)
            except ValueError as e:
                return _err(str(e))
            except Exception as e:
                log.error(f"{fn.__name__}: {e}", exc_info=True)
                return _err(str(e))
            if raw:
                return json.dumps(value)
            if value is None:
                return _ok()
            return _ok(value)
        return wrapper

    return decorate if _fn is None else decorate(_fn)


class ClaudeFMAPI:
    """pywebview js_api bridge — every public method is callable from JS via ``window.pywebview.api``.

    All methods return JSON strings. Most use the ``{"success": bool, ...}``
    envelope (via ``_ok``/``_err``); a few return raw arrays/dicts (see CLAUDE.md
    for the exceptions). Services are instantiated lazily so the API object can
    be created before settings (e.g. the Last.fm API key) are configured.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._player = PlayerService()
        self._youtube: YouTubeService | None = None
        self._lastfm: LastFMService | None = None
        self._lrclib: LRCLibService | None = None
        self._cover_art: CoverArtService | None = None
        self._enrichment: EnrichmentScheduler | None = None

    def _get_youtube(self) -> YouTubeService:
        if self._youtube is None:
            self._youtube = YouTubeService(self._conn)
        return self._youtube

    def _get_lastfm(self) -> LastFMService:
        if self._lastfm is None:
            api_key = get_setting(self._conn, "lastfm_api_key")
            self._lastfm = LastFMService(self._conn, api_key)
        return self._lastfm

    def _get_lrclib(self) -> LRCLibService:
        if self._lrclib is None:
            self._lrclib = LRCLibService(self._conn)
        return self._lrclib

    def _get_cover_art(self) -> CoverArtService:
        if self._cover_art is None:
            self._cover_art = CoverArtService(self._conn, self._get_lastfm())
        return self._cover_art

    def _get_enrichment(self) -> EnrichmentScheduler:
        if self._enrichment is None:
            self._enrichment = EnrichmentScheduler(
                self._conn, self._get_lrclib(), self._get_cover_art()
            )
        return self._enrichment

    def _post_download_hook(self):
        """Return a combined callback that runs artwork + lyrics fetching after a download.

        Checks the auto_fetch_artwork and auto_fetch_lyrics settings at call time
        so settings changes take effect on the next download without restarting.
        """
        hooks = []
        if get_setting(self._conn, "auto_fetch_artwork") == "true":
            hooks.append(self._get_cover_art().fetch_and_embed_async)
        if get_setting(self._conn, "auto_fetch_lyrics") == "true":
            hooks.append(self._get_lrclib().fetch_and_embed_async)
        if not hooks:
            return None
        def combined(track_id: int) -> None:
            for h in hooks:
                h(track_id)
        return combined

    # ── Library ──────────────────────────────────────────────────────────────

    @_api_method(raw=True)
    def get_library(self, filters_json: str = "{}") -> str:
        """Return all tracks as a JSON array, optionally filtered/sorted via ``filters_json``.

        ``filters_json`` may contain ``order_by`` and ``audio_format`` keys.
        Returns a raw array (no ``success`` wrapper) on success, ``_err`` on failure.
        """
        filters = json.loads(filters_json)
        order = filters.get("order_by", "date_downloaded DESC")
        fmt = filters.get("audio_format")
        tracks = get_all_tracks(self._conn, order_by=order, audio_format=fmt)
        return [t.model_dump(mode="json") for t in tracks]

    @_api_method
    def get_track(self, track_id: int) -> str:
        track = get_track(self._conn, track_id)
        if not track:
            raise ValueError("Track not found")
        return track.model_dump(mode="json")

    @_api_method(raw=True)
    def get_artists(self) -> str:
        return get_all_artists(self._conn)

    @_api_method(raw=True)
    def get_albums(self) -> str:
        return get_all_albums(self._conn)

    @_api_method(raw=True)
    def get_tracks_by_artist(self, artist: str) -> str:
        return [t.model_dump(mode="json") for t in get_tracks_by_artist(self._conn, artist)]

    @_api_method(raw=True)
    def get_tracks_by_album(self, album: str, artist: str) -> str:
        return [t.model_dump(mode="json") for t in get_tracks_by_album(self._conn, album, artist)]

    @_api_method(raw=True)
    def search_local(self, query: str, limit: int | None = None) -> str:
        lim = limit or int(get_setting(self._conn, "search_results_limit"))
        return [t.model_dump(mode="json") for t in search_tracks_local(self._conn, query, limit=lim)]

    # ── Last.fm ───────────────────────────────────────────────────────────────

    @_api_method(raw=True)
    def search_lastfm(self, query: str, search_type: str) -> str:
        limit = int(get_setting(self._conn, "search_results_limit"))
        return self._get_lastfm().search(query, search_type, limit=limit)

    @_api_method(raw=True)
    def get_artist_top_tracks(self, artist_name: str) -> str:
        return self._get_lastfm().get_artist_top_tracks(artist_name)

    @_api_method(raw=True)
    def get_album_tracks(self, album_title: str, artist_name: str) -> str:
        return self._get_lastfm().get_album_tracks(album_title, artist_name)

    @_api_method
    def remove_from_library(self, track_id: int) -> str:
        delete_track(self._conn, track_id)

    # ── Downloads ─────────────────────────────────────────────────────────────

    @_api_method
    def queue_download(self, track_id: int) -> str:
        self._get_youtube().queue_download(track_id, on_complete=self._post_download_hook())

    @_api_method(raw=True)
    def download_lastfm_track(self, title: str, artist: str, album: str | None = None) -> str:
        """Insert a track stub from Last.fm metadata and immediately queue a download.

        The returned payload includes ``track_id`` so the frontend can track
        download progress events without a separate lookup.
        """
        t = Track(title=title, artist=artist, album=album)
        track_id = insert_track(self._conn, t)
        self._get_youtube().queue_download(track_id, on_complete=self._post_download_hook())
        return {"success": True, "track_id": track_id}

    # ── Playback ──────────────────────────────────────────────────────────────

    @_api_method
    def play(self, track_id: int, context_json: str = "{}") -> str:
        """Start playing ``track_id``, optionally within a broader playback context.

        ``context_json`` may contain ``track_ids`` — a list of IDs representing
        the surrounding queue (e.g. the full album or library view). The player
        cursor is set to ``track_id``'s position in that list.
        """
        context = json.loads(context_json)
        track = get_track(self._conn, track_id)
        if not track or not track.file_path:
            raise ValueError("Track not found or not downloaded")
        track_ids = context.get("track_ids", [track_id])
        start_index = track_ids.index(track_id) if track_id in track_ids else 0
        self._player.queue.set_context(track_ids, start_index)
        self._player.play(track.file_path)

    @_api_method
    def pause(self) -> str:
        self._player.pause()

    @_api_method
    def resume(self) -> str:
        self._player.resume()

    @_api_method
    def stop(self) -> str:
        self._player.stop()

    @_api_method(raw=True)
    def next_track(self) -> str:
        """Advance the queue and play the next track; skips unplayable tracks (failed/missing).
        Emits ``queue_ended`` if the queue is exhausted."""
        while True:
            next_id = self._player.queue.next_id()
            if next_id is None:
                event_bus.emit("queue_ended", {})
                return {"success": True, "ended": True}
            track = get_track(self._conn, next_id)
            if track and track.file_path and track.file_status == "available":
                self._player.play(track.file_path)
                return {"success": True, "track_id": next_id}
            log.debug(f"Skipping unplayable track {next_id} (status={getattr(track, 'file_status', None)})")

    @_api_method(raw=True)
    def prev_track(self) -> str:
        while True:
            prev_id = self._player.queue.prev_id()
            if prev_id is None:
                return {"success": True}
            track = get_track(self._conn, prev_id)
            if track and track.file_path and track.file_status == "available":
                self._player.play(track.file_path)
                return {"success": True, "track_id": prev_id}
            log.debug(f"Skipping unplayable track {prev_id} going backwards (status={getattr(track, 'file_status', None)})")

    @_api_method
    def seek(self, position: float) -> str:
        self._player.seek(position)

    @_api_method(raw=True)
    def get_position(self) -> str:
        return {"position": self._player.get_position()}

    @_api_method
    def set_volume(self, level: float) -> str:
        self._player.set_volume(level)

    @_api_method(raw=True)
    def get_player_state(self) -> str:
        q = self._player.queue
        return {
            "current_id": q.current_id(),
            "position": self._player.get_position(),
            "paused": self._player.is_paused,
            "volume": self._player.get_volume(),
            "ended": q.ended,
        }

    # ── Playlists ─────────────────────────────────────────────────────────────

    @_api_method(raw=True)
    def get_playlists(self) -> str:
        return [p.model_dump(mode="json") for p in get_all_playlists(self._conn)]

    @_api_method(raw=True)
    def create_playlist(self, name: str, playlist_type: str = "manual") -> str:
        """Create a playlist, enforcing the 15-auto-playlist cap by deleting the oldest if needed."""
        if playlist_type == "auto" and get_auto_playlist_count(self._conn) >= AUTO_PLAYLIST_LIMIT:
            delete_oldest_auto_playlist(self._conn)
        p = Playlist(name=name, type=playlist_type)
        pid = insert_playlist(self._conn, p)
        return {"success": True, "id": pid}

    @_api_method(raw=True)
    def get_playlist_tracks(self, playlist_id: int) -> str:
        return [t.model_dump(mode="json") for t in get_playlist_tracks(self._conn, playlist_id)]

    # ── Settings ──────────────────────────────────────────────────────────────

    @_api_method(raw=True)
    def get_settings(self) -> str:
        return get_all_settings(self._conn)

    @_api_method
    def save_setting(self, key: str, value: str) -> str:
        set_setting(self._conn, key, value)
        self._get_enrichment().apply_settings()
        display = "***" if key == "lastfm_api_key" else value
        log.info(f"Setting saved: {key} = {display}")

    @_api_method
    def rescan_library(self) -> str:
        """Trigger a background full_scan across the download folder and any additional folders."""
        download_folder = get_setting(self._conn, "download_folder")
        try:
            additional = json.loads(get_setting(self._conn, "additional_folders"))
        except (json.JSONDecodeError, TypeError):
            additional = []
        folders = ([download_folder] if download_folder else []) + additional
        if folders:
            start_background_scan(self._conn, folders)

    # ── Playlist mutations ────────────────────────────────────────────────────

    @_api_method
    def delete_playlist(self, playlist_id: int) -> str:
        delete_playlist(self._conn, playlist_id)

    @_api_method
    def rename_playlist(self, playlist_id: int, name: str) -> str:
        update_playlist_name(self._conn, playlist_id, name)

    # ── Lyrics ────────────────────────────────────────────────────────────────

    @_api_method
    def fetch_lyrics(self, track_id: int) -> str:
        status = self._get_lrclib().fetch_and_embed(track_id)
        if status is None:
            raise ValueError("Track not found")
        return {"lyrics_status": status}

    @_api_method
    def fetch_missing_lyrics(self) -> str:
        self._get_lrclib().fetch_missing_lyrics()

    @_api_method
    def get_lyrics(self, track_id: int) -> str:
        result = self._get_lrclib().get_lyrics(track_id)
        if result is None:
            raise ValueError("Track not found")
        return result

    @_api_method
    def run_enrichment_lyrics(self) -> str:
        self._get_enrichment().run_lyrics()

    @_api_method
    def run_enrichment_artwork(self) -> str:
        self._get_enrichment().run_artwork()

    @_api_method
    def get_track_artwork(self, track_id: int) -> str:
        image_bytes = self._get_cover_art().get_cover_bytes(track_id)
        if not image_bytes:
            raise ValueError("No artwork")
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode()
        return {"data_url": data_url}

    @_api_method
    def add_to_playlist(self, playlist_id: int, track_id: int) -> str:
        add_track_to_playlist(self._conn, playlist_id, track_id)

    @_api_method
    def remove_from_playlist(self, playlist_id: int, track_id: int) -> str:
        remove_track_from_playlist(self._conn, playlist_id, track_id)

    # ── Connectivity / account checks ─────────────────────────────────────────

    @_api_method
    def check_lastfm_connection(self) -> str:
        self._get_lastfm().search("test", "track", limit=1)

    @_api_method(raw=True)
    def check_internet(self) -> str:
        """Probe 8.8.8.8:53 with a 3 s timeout; returns ``{"online": bool}`` (no success wrapper)."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return {"online": True}
        except OSError:
            return {"online": False}
