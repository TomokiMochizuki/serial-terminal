# -*- coding: utf-8 -*-
"""i18n 基盤 (tr / 言語切替 / 設定保存) のテスト。"""
import json

import pytest

import serial_terminal as st


@pytest.fixture(autouse=True)
def reset_language():
    original = st.get_language()
    yield
    st.set_language(original)


class TestTr:
    def test_ja_returns_japanese(self):
        st.set_language("ja")
        assert st.tr("connect") == "接続"

    def test_en_returns_english(self):
        st.set_language("en")
        assert st.tr("connect") == "Connect"

    def test_missing_key_falls_back_to_key(self):
        st.set_language("ja")
        assert st.tr("no_such_key_xyz") == "no_such_key_xyz"

    def test_set_language_rejects_unknown(self):
        with pytest.raises(ValueError):
            st.set_language("fr")

    def test_all_keys_have_both_languages(self):
        for key, entry in st.I18N.items():
            assert set(entry) == {"ja", "en"}, key
            assert entry["ja"], key
            assert entry["en"], key


class TestDetectDefaultLanguage:
    def test_japanese_locale(self, monkeypatch):
        monkeypatch.setattr(st.locale, "getlocale",
                            lambda: ("ja_JP", "UTF-8"))
        assert st.detect_default_language() == "ja"

    def test_english_locale(self, monkeypatch):
        monkeypatch.setattr(st.locale, "getlocale",
                            lambda: ("en_US", "UTF-8"))
        assert st.detect_default_language() == "en"

    def test_none_locale_falls_back_to_en(self, monkeypatch):
        monkeypatch.setattr(st.locale, "getlocale", lambda: (None, None))
        assert st.detect_default_language() == "en"


class TestSettings:
    @pytest.fixture(autouse=True)
    def isolated_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        monkeypatch.setenv("APPDATA", str(tmp_path))
        yield tmp_path

    def test_save_then_load_roundtrip(self):
        st.save_settings({"language": "en"})
        assert st.load_settings() == {"language": "en"}

    def test_load_missing_file_returns_empty(self):
        assert st.load_settings() == {}

    def test_load_broken_json_returns_empty(self, tmp_path):
        path = st.settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{broken", encoding="utf-8")
        assert st.load_settings() == {}

    def test_save_creates_parent_dirs(self, tmp_path):
        st.save_settings({"language": "ja"})
        data = json.loads(st.settings_path().read_text(encoding="utf-8"))
        assert data == {"language": "ja"}


class TestEolCodes:
    def test_tx_eol_bytes_mapping(self):
        assert st.TX_EOL_BYTES == {
            "none": b"", "lf": b"\n", "cr": b"\r", "crlf": b"\r\n"}

    def test_eol_display_translated(self):
        st.set_language("ja")
        assert st.tr("eol_none") == "なし"
        st.set_language("en")
        assert st.tr("eol_none") == "None"

    def test_rx_newline_codes(self):
        assert st.RX_NEWLINE_CODES == ["raw", "cr_to_lf", "strip_cr"]
