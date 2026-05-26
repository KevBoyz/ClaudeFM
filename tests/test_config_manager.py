# tests/test_config_manager.py
from src.database.database import init_db
from src.database.config_manager import get_setting, set_setting, get_all_settings, DEFAULTS


def test_get_default_when_not_set(db_conn):
    init_db(db_conn)
    val = get_setting(db_conn, "audio_format")
    assert val == "m4a"


def test_set_and_get_setting(db_conn):
    init_db(db_conn)
    set_setting(db_conn, "audio_format", "mp3")
    assert get_setting(db_conn, "audio_format") == "mp3"


def test_get_all_settings_returns_defaults_for_unset(db_conn):
    init_db(db_conn)
    settings = get_all_settings(db_conn)
    assert settings["search_results_limit"] == "5"
    assert settings["cache_enabled"] == "true"
    assert settings["theme"] == "dark"


def test_set_and_retrieve_sidebar_state(db_conn):
    init_db(db_conn)
    set_setting(db_conn, "sidebar_collapsed", "true")
    assert get_setting(db_conn, "sidebar_collapsed") == "true"


def test_auto_fetch_lyrics_default_true(db_conn):
    init_db(db_conn)
    assert get_setting(db_conn, "auto_fetch_lyrics") == "true"


def test_player_volume_default_one(db_conn):
    init_db(db_conn)
    assert get_setting(db_conn, "player_volume") == "1.0"
