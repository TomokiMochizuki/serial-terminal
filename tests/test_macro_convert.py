# -*- coding: utf-8 -*-
"""定型文ダイアログの ASCII↔HEX 変換ロジックのテスト。"""
import pytest

import serial_terminal as st


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


class TestRoundTrip:
    @pytest.mark.parametrize("text", ["abc", "hello world", "a\nb\tc", "あいう"])
    def test_ascii_hex_ascii(self, text):
        hex_str = st.ascii_to_hex_str(text)
        assert st.hex_str_to_ascii(hex_str) == text
