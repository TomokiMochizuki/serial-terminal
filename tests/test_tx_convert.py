# -*- coding: utf-8 -*-
"""送信欄の ASCII↔HEX 切替時の自動変換テスト (DISPLAY がある環境のみ)。"""
import os
import sys

import pytest

import serial_terminal as st

needs_display = pytest.mark.skipif(
    sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"),
    reason="GUI test requires a display")


@pytest.fixture
def tab(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    st.set_language("ja")
    app = st.App()
    port_tab = app.nametowidget(app.notebook.tabs()[0])
    yield port_tab
    app.destroy()
    st.set_language("ja")


def _switch(tab, mode):
    tab.tx_mode_var.set(mode)
    tab._tx_mode_changed()


def _data(tab):
    return tab.tx_text.get("1.0", "end-1c")


@needs_display
class TestTxFieldConversion:
    def test_ascii_to_hex_rewrites_data(self, tab):
        tab.tx_text.insert("1.0", "ab")
        _switch(tab, "hex")
        assert _data(tab) == "61 62"

    def test_hex_to_ascii_round_trip(self, tab):
        tab.tx_text.insert("1.0", "abc")
        _switch(tab, "hex")
        _switch(tab, "ascii")
        assert _data(tab) == "abc"

    def test_empty_data_no_conversion(self, tab):
        _switch(tab, "hex")
        assert _data(tab) == ""
        assert tab._tx_prev_mode == "hex"

    def test_same_mode_click_is_noop(self, tab):
        tab.tx_text.insert("1.0", "abc")
        _switch(tab, "ascii")
        assert _data(tab) == "abc"

    def test_uses_selected_encoding(self, tab):
        tab.enc_var.set("shift_jis")
        tab.tx_text.insert("1.0", "あ")
        _switch(tab, "hex")
        assert _data(tab) == "82 a0"

    def test_failed_conversion_reverts_radio(self, tab, monkeypatch):
        # 不正なHEXをASCIIへ切替 → 警告を出しデータは保持、ラジオはHEXに戻る
        monkeypatch.setattr(st.messagebox, "showwarning",
                            lambda *a, **k: None)
        tab.tx_text.insert("1.0", "zz")
        tab._tx_prev_mode = "hex"
        tab.tx_mode_var.set("hex")
        _switch(tab, "ascii")
        assert _data(tab) == "zz"
        assert tab.tx_mode_var.get() == "hex"
        assert tab._tx_prev_mode == "hex"
