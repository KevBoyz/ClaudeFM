import sqlite3
import winreg
from pathlib import Path


def _windows_music_folder() -> str:
    """Read the user's Music folder path from the Windows registry, falling back to ``~/Music``."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        path, _ = winreg.QueryValueEx(key, "My Music")
        key.Close()
        return path
    except Exception:
        return str(Path.home() / "Music")


DEFAULTS: dict[str, str] = {  # fallback values used when a key is absent from the DB
    "lastfm_api_key": "",
    "download_folder": _windows_music_folder(),
    "additional_folders": "[]",
    "audio_format": "m4a",
    "cache_enabled": "true",
    "search_results_limit": "5",
    "theme": "dark",
    "sidebar_collapsed": "false",
    "player_last_track_id": "",
    "player_last_position": "0",
    "player_last_context": "",
    "download_concurrency": "2",
    "auto_fetch_lyrics": "true",
    "auto_fetch_artwork": "true",
    "player_volume": "1.0",
}


def get_setting(conn: sqlite3.Connection, key: str) -> str:
    """Return a setting value from the DB, falling back to ``DEFAULTS``, then empty string."""
    row = conn.execute(
        "SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row and row[0] is not None:
        return row[0]
    return DEFAULTS.get(key, "")


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert a setting key/value pair (INSERT … ON CONFLICT DO UPDATE)."""
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    """Return all settings merged with DEFAULTS (DB values take priority)."""
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(DEFAULTS)
    for row in rows:
        if row[1] is not None:
            result[row[0]] = row[1]
    return result
