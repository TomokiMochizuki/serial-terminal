# -*- coding: utf-8 -*-
"""NewlineFilter (言語非依存コード化後) のテスト。"""
import serial_terminal as st


def make(mode):
    f = st.NewlineFilter()
    f.mode = mode
    return f


class TestRaw:
    def test_passthrough(self):
        f = make("raw")
        assert f.feed("a\r\nb\rc\n") == "a\r\nb\rc\n"

    def test_convert_all_passthrough(self):
        assert make("raw").convert_all("a\r\nb") == "a\r\nb"


class TestCrToLf:
    def test_crlf_to_lf(self):
        f = make("cr_to_lf")
        assert f.feed("a\r\nb") == "a\nb"

    def test_lone_cr_to_lf(self):
        f = make("cr_to_lf")
        assert f.feed("a\rb") == "a\nb"

    def test_crlf_split_across_chunks(self):
        f = make("cr_to_lf")
        out = f.feed("a\r")
        out += f.feed("\nb")
        assert out == "a\nb"

    def test_convert_all(self):
        assert make("cr_to_lf").convert_all("a\r\nb\rc") == "a\nb\nc"


class TestStripCr:
    def test_strip(self):
        f = make("strip_cr")
        assert f.feed("a\r\nb\rc") == "a\nbc"

    def test_convert_all(self):
        assert make("strip_cr").convert_all("a\r\nb\rc") == "a\nbc"


def test_default_mode_is_raw():
    assert st.NewlineFilter().mode == "raw"
