import json
import socket
import sqlite3
from src.database.database import (
    get_all_tracks, get_track, insert_track, update_track_status,
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
from src.utils.logger import get_logger
from src.utils.event_bus import event_bus

log = get_logger("api")

AUTO_PLAYLIST_LIMIT = 15


def _ok(data=None) -> str:
    return json.dumps({"success": True, **({"data": data} if data is not None else {})})


def _err(message: str) -> str:
    return json.dumps({"success": False, "error": message})


class ClaudeFMAPI:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._player = PlayerService()
        self._youtube: YouTubeService | None = None
        self._lastfm: LastFMService | None = None
        self._lrclib: LRCLibService | None = None

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

    def _lyrics_hook(self):
        if get_setting(self._conn, "auto_fetch_lyrics") == "true":
            return self._get_lrclib().fetch_and_embed_async
        return None

    # ── Library ──────────────────────────────────────────────────────────────

    def get_library(self, filters_json: str = "{}") -> str:
        try:
            filters = json.loads(filters_json)
            order = filters.get("order_by", "date_downloaded DESC")
            fmt = filters.get("audio_format")
            tracks = get_all_tracks(self._conn, order_by=order, audio_format=fmt)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            log.error(f"get_library: {e}", exc_info=True)
            return _err(str(e))

    def get_track(self, track_id: int) -> str:
        try:
            track = get_track(self._conn, track_id)
            if not track:
                return _err("Track not found")
            return _ok(track.model_dump(mode="json"))
        except Exception as e:
            return _err(str(e))

    def get_artists(self) -> str:
        try:
            return json.dumps(get_all_artists(self._conn))
        except Exception as e:
            return _err(str(e))

    def get_albums(self) -> str:
        try:
            return json.dumps(get_all_albums(self._conn))
        except Exception as e:
            return _err(str(e))

    def get_tracks_by_artist(self, artist: str) -> str:
        try:
            tracks = get_tracks_by_artist(self._conn, artist)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    def get_tracks_by_album(self, album: str, artist: str) -> str:
        try:
            tracks = get_tracks_by_album(self._conn, album, artist)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    def search_local(self, query: str, limit: int | None = None) -> str:
        try:
            lim = limit or int(get_setting(self._conn, "search_results_limit"))
            tracks = search_tracks_local(self._conn, query, limit=lim)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    # ── Last.fm ───────────────────────────────────────────────────────────────

    def search_lastfm(self, query: str, search_type: str) -> str:
        try:
            limit = int(get_setting(self._conn, "search_results_limit"))
            results = self._get_lastfm().search(query, search_type, limit=limit)
            return json.dumps(results)
        except Exception as e:
            log.error(f"search_lastfm: {e}", exc_info=True)
            return _err(str(e))

    def get_artist_top_tracks(self, artist_name: str) -> str:
        try:
            tracks = self._get_lastfm().get_artist_top_tracks(artist_name)
            return json.dumps(tracks)
        except Exception as e:
            return _err(str(e))

    def get_album_tracks(self, album_title: str, artist_name: str) -> str:
        try:
            tracks = self._get_lastfm().get_album_tracks(album_title, artist_name)
            return json.dumps(tracks)
        except Exception as e:
            return _err(str(e))

    # ── Downloads ─────────────────────────────────────────────────────────────

    def queue_download(self, track_id: int) -> str:
        try:
            self._get_youtube().queue_download(track_id, on_complete=self._lyrics_hook())
            return _ok()
        except Exception as e:
            log.error(f"queue_download: {e}", exc_info=True)
            return _err(str(e))

    def download_lastfm_track(self, title: str, artist: str, album: str | None = None) -> str:
        try:
            t = Track(title=title, artist=artist, album=album)
            track_id = insert_track(self._conn, t)
            self._get_youtube().queue_download(track_id, on_complete=self._lyrics_hook())
            return json.dumps({"success": True, "track_id": track_id})
        except Exception as e:
            return _err(str(e))

    # ── Playback ──────────────────────────────────────────────────────────────

    def play(self, track_id: int, context_json: str = "{}") -> str:
        try:
            context = json.loads(context_json)
            track = get_track(self._conn, track_id)
            if not track or not track.file_path:
                return _err("Track not found or not downloaded")
            track_ids = context.get("track_ids", [track_id])
            start_index = track_ids.index(track_id) if track_id in track_ids else 0
            self._player.queue.set_context(track_ids, start_index)
            self._player.play(track.file_path)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def pause(self) -> str:
        self._player.pause()
        return _ok()

    def resume(self) -> str:
        self._player.resume()
        return _ok()

    def next_track(self) -> str:
        try:
            next_id = self._player.queue.next_id()
            if next_id is None:
                event_bus.emit("queue_ended", {})
                return json.dumps({"success": True, "ended": True})
            track = get_track(self._conn, next_id)
            if track and track.file_path:
                self._player.play(track.file_path)
            return json.dumps({"success": True, "track_id": next_id})
        except Exception as e:
            return _err(str(e))

    def prev_track(self) -> str:
        try:
            prev_id = self._player.queue.prev_id()
            if prev_id is None:
                return _ok()
            track = get_track(self._conn, prev_id)
            if track and track.file_path:
                self._player.play(track.file_path)
            return json.dumps({"success": True, "track_id": prev_id})
        except Exception as e:
            return _err(str(e))

    def seek(self, position: float) -> str:
        try:
            self._player.seek(position)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def get_position(self) -> str:
        return json.dumps({"position": self._player.get_position()})

    def set_volume(self, level: float) -> str:
        try:
            self._player.set_volume(level)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def get_player_state(self) -> str:
        q = self._player.queue
        return json.dumps({
            "current_id": q.current_id(),
            "position": self._player.get_position(),
            "paused": self._player.is_paused,
            "volume": self._player.get_volume(),
            "ended": q.ended,
        })

    # ── Playlists ─────────────────────────────────────────────────────────────

    def get_playlists(self) -> str:
        try:
            playlists = get_all_playlists(self._conn)
            return json.dumps([p.model_dump(mode="json") for p in playlists])
        except Exception as e:
            return _err(str(e))

    def create_playlist(self, name: str, playlist_type: str = "manual") -> str:
        try:
            if playlist_type == "auto" and get_auto_playlist_count(self._conn) >= AUTO_PLAYLIST_LIMIT:
                delete_oldest_auto_playlist(self._conn)
            p = Playlist(name=name, type=playlist_type)
            pid = insert_playlist(self._conn, p)
            return json.dumps({"success": True, "id": pid})
        except Exception as e:
            return _err(str(e))

    def get_playlist_tracks(self, playlist_id: int) -> str:
        try:
            tracks = get_playlist_tracks(self._conn, playlist_id)
            return json.dumps([t.model_dump(mode="json") for t in tracks])
        except Exception as e:
            return _err(str(e))

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> str:
        return json.dumps(get_all_settings(self._conn))

    def save_setting(self, key: str, value: str) -> str:
        try:
            set_setting(self._conn, key, value)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def rescan_library(self) -> str:
        try:
            download_folder = get_setting(self._conn, "download_folder")
            try:
                additional = json.loads(get_setting(self._conn, "additional_folders"))
            except (json.JSONDecodeError, TypeError):
                additional = []
            folders = ([download_folder] if download_folder else []) + additional
            if folders:
                start_background_scan(self._conn, folders)
            return _ok()
        except Exception as e:
            return _err(str(e))

    # ── Playlist mutations ────────────────────────────────────────────────────

    def delete_playlist(self, playlist_id: int) -> str:
        try:
            delete_playlist(self._conn, playlist_id)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def rename_playlist(self, playlist_id: int, name: str) -> str:
        try:
            update_playlist_name(self._conn, playlist_id, name)
            return _ok()
        except Exception as e:
            return _err(str(e))

    # ── Lyrics ────────────────────────────────────────────────────────────────

    def fetch_lyrics(self, track_id: int) -> str:
        try:
            status = self._get_lrclib().fetch_and_embed(track_id)
            if status is None:
                return _err("Track not found")
            return _ok({"lyrics_status": status})
        except Exception as e:
            log.error(f"fetch_lyrics: {e}", exc_info=True)
            return _err(str(e))

    def fetch_missing_lyrics(self) -> str:
        try:
            self._get_lrclib().fetch_missing_lyrics()
            return _ok()
        except Exception as e:
            log.error(f"fetch_missing_lyrics: {e}", exc_info=True)
            return _err(str(e))

    def get_lyrics(self, track_id: int) -> str:
        try:
            result = self._get_lrclib().get_lyrics(track_id)
            if result is None:
                return _err("Track not found")
            return _ok(result)
        except Exception as e:
            log.error(f"get_lyrics: {e}", exc_info=True)
            return _err(str(e))

    def add_to_playlist(self, playlist_id: int, track_id: int) -> str:
        try:
            add_track_to_playlist(self._conn, playlist_id, track_id)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def remove_from_playlist(self, playlist_id: int, track_id: int) -> str:
        try:
            remove_track_from_playlist(self._conn, playlist_id, track_id)
            return _ok()
        except Exception as e:
            return _err(str(e))

    # ── Connectivity / account checks ─────────────────────────────────────────

    def check_lastfm_connection(self) -> str:
        try:
            self._get_lastfm().search("test", "track", limit=1)
            return _ok()
        except Exception as e:
            return _err(str(e))

    def check_internet(self) -> str:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return json.dumps({"online": True})
        except OSError:
            return json.dumps({"online": False})
