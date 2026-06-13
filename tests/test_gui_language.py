# -*- coding: utf-8 -*-
"""GUI 言語切替の統合テスト (DISPLAY がある環境のみ)。"""
import os
import sys

import pytest

import serial_terminal as st

needs_display = pytest.mark.skipif(
    sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"),
    reason="GUI test requires a display")


@pytest.fixture
def app(tmp_path, monkeypatch, _gui_capture_safe):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    st.set_language("ja")
    application = st.App()
    yield application
    application.destroy()
    st.set_language("ja")


@needs_display
class TestLanguageSwitch:
    def test_initial_japanese_labels(self, app):
        tab = app.nametowidget(app.notebook.tabs()[0])
        assert tab.conn_btn["text"] == "接続"
        assert app.notebook.tab(tab, "text") == "未接続"

    def test_switch_to_english_updates_widgets(self, app):
        app.switch_language("en")
        tab = app.nametowidget(app.notebook.tabs()[0])
        assert tab.conn_btn["text"] == "Connect"
        assert app.notebook.tab(tab, "text") == "Not connected"

    def test_switch_back_to_japanese(self, app):
        app.switch_language("en")
        app.switch_language("ja")
        tab = app.nametowidget(app.notebook.tabs()[0])
        assert tab.conn_btn["text"] == "接続"

    def test_switch_persists_setting(self, app):
        app.switch_language("en")
        assert st.load_settings().get("language") == "en"

    def test_combobox_values_translated(self, app):
        tab = app.nametowidget(app.notebook.tabs()[0])
        app.switch_language("en")
        values = tab.rx_nl_combo["values"]
        assert "As-is" in values
        app.switch_language("ja")
        values = tab.rx_nl_combo["values"]
        assert "そのまま" in values

    def test_new_tab_after_switch_uses_current_language(self, app):
        app.switch_language("en")
        app.add_tab()
        tab = app.nametowidget(app.notebook.tabs()[-1])
        assert tab.conn_btn["text"] == "Connect"
