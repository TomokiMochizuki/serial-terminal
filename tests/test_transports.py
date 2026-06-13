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


class TestSerialTransport:
    def _make(self, port):
        return st.SerialTransport(
            port=port, baudrate=9600,
            bytesize=st.serial.EIGHTBITS, parity=st.serial.PARITY_NONE,
            stopbits=st.serial.STOPBITS_ONE)

    def test_loopback_roundtrip(self):
        # pyserial 組み込みの loop:// でハードウェア無しにテストする
        t = self._make("loop://")
        t.open()
        try:
            assert t.is_open
            t.write(b"abc")
            data = b""
            for _ in range(20):
                data += t.read(0.1)
                if len(data) >= 3:
                    break
            assert data == b"abc"
        finally:
            t.close()
        assert not t.is_open

    def test_open_failure_raises_transport_error(self):
        t = self._make("/dev/nonexistent-port-xyz")
        with pytest.raises(st.TransportError):
            t.open()

    def test_close_is_idempotent(self):
        t = self._make("loop://")
        t.open()
        t.close()
        t.close()  # 2回目も例外を出さない

    def test_tab_label_is_port_name(self):
        t = self._make("loop://")
        assert t.tab_label == "loop://"
