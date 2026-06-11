# -*- coding: utf-8 -*-
"""定型文ダイアログの ASCII↔HEX 変換ロジックのテスト。"""
import os
import sys

import pytest

import serial_terminal as st

needs_display = pytest.mark.skipif(
    sys.platform not in ("win32", "darwin") and not os.environ.get("DISPLAY"),
    reason="GUI test requires a display")


class TestAsciiToHex:
    def test_basic(self):
        assert st.ascii_to_hex_str("abc") == "61 62 63"

    def test_empty(self):
        assert st.ascii_to_hex_str("") == ""

    def test_utf8_japanese(self):
        assert st.ascii_to_hex_str("あ", encoding="utf-8") == "e3 81 82"

    def test_shift_jis_japanese(self):
        assert st.ascii_to_hex_str("あ", encoding="shift_jis") == "82 a0"

    def test_newline_included(self):
        assert st.ascii_to_hex_str("a\nb") == "61 0a 62"

    def test_unencodable_raises(self):
        with pytest.raises(UnicodeEncodeError):
            st.ascii_to_hex_str("あ", encoding="ascii")


class TestHexToAscii:
    def test_basic(self):
        assert st.hex_str_to_ascii("61 62 63") == "abc"

    def test_empty(self):
        assert st.hex_str_to_ascii("") == ""

    def test_accepts_parse_hex_formats(self):
        assert st.hex_str_to_ascii("0x61,0X62;63") == "abc"

    def test_utf8_japanese(self):
        assert st.hex_str_to_ascii("e3 81 82", encoding="utf-8") == "あ"

    def test_whitespace_controls_allowed(self):
        assert st.hex_str_to_ascii("61 09 0d 0a 62") == "a\t\r\nb"

    def test_invalid_hex_raises(self):
        with pytest.raises(ValueError):
            st.hex_str_to_ascii("6g")

    def test_odd_digits_raises(self):
        with pytest.raises(ValueError):
            st.hex_str_to_ascii("616")

    def test_undecodable_raises(self):
        with pytest.raises(ValueError):
            st.hex_str_to_ascii("ff fe", encoding="utf-8")

    def test_control_char_raises(self):
        with pytest.raises(ValueError):
            st.hex_str_to_ascii("61 00 62")

    def test_del_char_raises(self):
        with pytest.raises(ValueError):
            st.hex_str_to_ascii("61 7f 62")


class TestRoundTrip:
    @pytest.mark.parametrize("text", ["abc", "hello world", "a\nb\tc", "あいう"])
    def test_ascii_hex_ascii(self, text):
        hex_str = st.ascii_to_hex_str(text)
        assert st.hex_str_to_ascii(hex_str) == text


@needs_display
class TestMacroDialogConversion:
    @pytest.fixture
    def dialog(self):
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        dlg = st.MacroDialog(root, "dlg_macro_add", encoding="utf-8")
        yield dlg
        dlg.destroy()
        root.destroy()

    def _switch(self, dlg, mode):
        dlg.mode_var.set(mode)
        dlg._mode_changed()

    def _data(self, dlg):
        return dlg.data_text.get("1.0", "end-1c")

    def test_ascii_to_hex_rewrites_data(self, dialog):
        dialog.data_text.insert("1.0", "abc")
        self._switch(dialog, "hex")
        assert self._data(dialog) == "61 62 63"

    def test_hex_to_ascii_rewrites_data(self, dialog):
        dialog.data_text.insert("1.0", "abc")
        self._switch(dialog, "hex")
        self._switch(dialog, "ascii")
        assert self._data(dialog) == "abc"

    def test_empty_data_no_conversion(self, dialog):
        self._switch(dialog, "hex")
        assert self._data(dialog) == ""
        assert dialog._prev_mode == "hex"

    def test_same_mode_click_is_noop(self, dialog):
        dialog.data_text.insert("1.0", "abc")
        self._switch(dialog, "ascii")
        assert self._data(dialog) == "abc"

    def test_failed_conversion_reverts_radio(self, dialog, monkeypatch):
        # 不正なHEXをASCIIへ切替 → 警告を出しデータは保持、ラジオはHEXに戻る
        monkeypatch.setattr(st.messagebox, "showwarning",
                            lambda *a, **k: None)
        dialog.data_text.insert("1.0", "zz")
        dialog._prev_mode = "hex"
        dialog.mode_var.set("hex")
        self._switch(dialog, "ascii")
        assert self._data(dialog) == "zz"
        assert dialog.mode_var.get() == "hex"
