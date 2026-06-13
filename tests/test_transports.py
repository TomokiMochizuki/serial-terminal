# -*- coding: utf-8 -*-
"""Transport層 (ポート検証 / TCP / UDP / シリアル) の単体テスト。GUI不要。"""
import socket

import pytest

import serial_terminal as st


def free_port(kind=socket.SOCK_STREAM):
    """OSに空きポートを割り当てさせて番号を返す。"""
    with socket.socket(socket.AF_INET, kind) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestParsePortNumber:
    def test_valid(self):
        assert st.parse_port_number("5000") == 5000

    def test_strips_whitespace(self):
        assert st.parse_port_number(" 80 ") == 80

    def test_boundaries(self):
        assert st.parse_port_number("1") == 1
        assert st.parse_port_number("65535") == 65535

    @pytest.mark.parametrize("bad", ["", "abc", "0", "65536", "-1", "1.5"])
    def test_invalid_raises(self, bad):
        with pytest.raises(ValueError):
            st.parse_port_number(bad)
