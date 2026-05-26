# tests/test_filename_sanitization.py
from src.services.youtube_service import sanitize_filename


def test_removes_windows_invalid_chars():
    assert sanitize_filename('a<b>c:d"e/f\\g|h?i*j') == "a_b_c_d_e_f_g_h_i_j"


def test_reserved_names_get_suffix():
    assert sanitize_filename("CON") == "CON_"
    assert sanitize_filename("NUL") == "NUL_"
    assert sanitize_filename("COM1") == "COM1_"


def test_strips_trailing_dots_and_spaces():
    assert sanitize_filename("hello. ") == "hello"


def test_truncates_long_names():
    long = "a" * 300
    result = sanitize_filename(long)
    assert len(result) <= 200


def test_normal_name_unchanged():
    assert sanitize_filename("Radiohead - Creep") == "Radiohead - Creep"
