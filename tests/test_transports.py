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


def _pump_until(transport, predicate, rounds=50, timeout=0.1):
    """read() を回して predicate が真になるまでのデータを集めて返す。"""
    data = b""
    for _ in range(rounds):
        data += transport.read(timeout)
        if predicate(data):
            return data
    return data


class TestTcpServerTransport:
    def test_accept_receive_and_reconnect(self):
        events = []
        port = free_port()
        srv = st.TcpServerTransport(port, on_status_change=events.append)
        srv.open()
        try:
            assert srv.is_open
            # --- クライアント1接続 → 受信 ---
            c1 = socket.create_connection(("127.0.0.1", port), timeout=2)
            _pump_until(srv, lambda d: srv._conn is not None)
            assert len(events) == 1           # 接続通知
            c1.sendall(b"hello")
            assert _pump_until(srv, lambda d: d) == b"hello"
            # --- 切断 → 自動で再待受 ---
            c1.close()
            _pump_until(srv, lambda d: srv._conn is None)
            assert len(events) == 2           # 切断通知
            # --- クライアント2が再接続できる ---
            c2 = socket.create_connection(("127.0.0.1", port), timeout=2)
            _pump_until(srv, lambda d: srv._conn is not None)
            c2.sendall(b"again")
            assert _pump_until(srv, lambda d: d) == b"again"
            c2.close()
        finally:
            srv.close()
        assert not srv.is_open

    def test_second_client_rejected(self):
        port = free_port()
        srv = st.TcpServerTransport(port)
        srv.open()
        try:
            c1 = socket.create_connection(("127.0.0.1", port), timeout=2)
            _pump_until(srv, lambda d: srv._conn is not None)
            c2 = socket.create_connection(("127.0.0.1", port), timeout=2)
            _pump_until(srv, lambda d: False, rounds=5)  # 拒否処理を回す
            c2.settimeout(2)
            assert c2.recv(1) == b""          # サーバ側から即クローズされた
            c1.close()
            c2.close()
        finally:
            srv.close()

    def test_write_without_client_raises(self):
        port = free_port()
        srv = st.TcpServerTransport(port)
        srv.open()
        try:
            with pytest.raises(st.TransportError):
                srv.write(b"x")
        finally:
            srv.close()

    def test_bind_conflict_raises(self):
        port = free_port()
        a = st.TcpServerTransport(port)
        a.open()
        try:
            b = st.TcpServerTransport(port)
            with pytest.raises(st.TransportError):
                b.open()
        finally:
            a.close()
