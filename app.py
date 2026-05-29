from src.api.api import ClaudeFMAPI
from src.utils.event_bus import event_bus
from src.database.file_manager import quick_scan, start_background_scan
from src.database.config_manager import get_setting, get_all_settings, set_setting
from src.database.database import get_connection, init_db
from src.utils.logger import get_logger
import sys
import json
import ctypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


log = get_logger("app")


def main():
    """Application entry point: init DB, quick scan, create pywebview window, wire lifecycle hooks."""
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "com.claudefm.app")
    log.info("ClaudeFM starting")

    conn = get_connection()
    init_db(conn)
    log.info("Database initialised")

    folders_json = get_setting(conn, "additional_folders")
    download_folder = get_setting(conn, "download_folder")
    try:
        folders = json.loads(folders_json)
    except (json.JSONDecodeError, TypeError):
        folders = []
    if download_folder:
        folders = [download_folder] + folders
    quick_scan(conn)
    log.info("Quick scan complete")

    api = ClaudeFMAPI(conn)

    import webview

    window = webview.create_window(
        "ClaudeFM",
        url=str(Path(__file__).parent / "src" / "interface" / "home.html"),
        js_api=api,
        width=1200,
        height=750,
        min_size=(900, 600),
    )

    event_bus.set_window(window)

    def on_loaded():
        """Called by pywebview when the HTML page has finished loading.

        Redirects to the settings page if the Last.fm key or download folder is
        not configured. Restores the last playback position, then starts a
        background library scan.
        """
        settings = get_all_settings(conn)
        if not settings.get("lastfm_api_key") or not settings.get("download_folder"):
            window.evaluate_js("router.navigate('settings')")
        last_id = settings.get("player_last_track_id", "")
        last_pos = settings.get("player_last_position", "0")
        if last_id:
            window.evaluate_js(
                f"onEvent({{\"type\":\"restore_player\",\"track_id\":{last_id},\"position\":{last_pos}}})"
            )
        if folders:
            start_background_scan(conn, folders)

    def on_closing():
        """Persist playback state and shut down workers before the window closes."""
        api.shutdown()
        log.info("ClaudeFM closing")

    window.events.loaded += on_loaded
    window.events.closing += on_closing

    icon_path = Path(__file__).parent / "src" / "interface" / \
        "assets" / "icons" / "favicon.ico"
    webview.start(debug=False, icon=str(icon_path))


if __name__ == "__main__":
    main()
