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


class TestTcpClientTransport:
    def test_roundtrip_and_disconnect(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]

            t = st.TcpClientTransport("127.0.0.1", port)
            t.open()
            try:
                assert t.is_open
                conn, _ = listener.accept()
                with conn:
                    t.write(b"ping")
                    assert conn.recv(4) == b"ping"
                    conn.sendall(b"pong")
                    data = b""
                    for _ in range(20):
                        data += t.read(0.1)
                        if data:
                            break
                    assert data == b"pong"
                # 相手側クローズ → 切断検知 (recv が b"" を返す)
                with pytest.raises(st.TransportError):
                    for _ in range(20):
                        t.read(0.1)
            finally:
                t.close()

    def test_read_timeout_returns_empty(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            t = st.TcpClientTransport("127.0.0.1",
                                      listener.getsockname()[1])
            t.open()
            try:
                assert t.read(0.1) == b""
            finally:
                t.close()

    def test_connection_refused_raises(self):
        port = free_port()  # bindしただけで閉じたポート → 接続拒否
        t = st.TcpClientTransport("127.0.0.1", port)
        with pytest.raises(st.TransportError):
            t.open()

    def test_tab_label(self):
        t = st.TcpClientTransport("192.168.0.10", 5000)
        assert t.tab_label == "192.168.0.10:5000"
