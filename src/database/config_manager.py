import sqlite3

DEFAULTS: dict[str, str] = {
    "lastfm_api_key": "",
    "download_folder": "",
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
}


def get_setting(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    if row and row[0] is not None:
        return row[0]
    return DEFAULTS.get(key, "")


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_all_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    result = dict(DEFAULTS)
    for row in rows:
        if row[1] is not None:
            result[row[0]] = row[1]
    return result
