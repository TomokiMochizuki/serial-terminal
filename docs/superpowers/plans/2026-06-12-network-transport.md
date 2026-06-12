# TCP/UDP対応 (Transport抽象化) 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** シリアル専用ターミナルをTCPクライアント / TCPサーバ / UDPでも使えるようにする (spec: `docs/superpowers/specs/2026-06-12-network-transport-design.md`)。

**Architecture:** `Transport` 共通インターフェース (open/close/read/write/is_open/description) を定義し、`PortTab.ser` を `PortTab.transport` に置換。受信スレッド・送信・表示・ログは全種別共通のまま。UIはタブ内の接続種別コンボでパラメータ欄を切替。

**Tech Stack:** Python 3.9+ / tkinter / pyserial / socket (標準ライブラリ) / pytest

**前提知識:**
- 単一ファイル構成 (`serial_terminal.py`、約1280行)。既存パターンに従い分割しない
- i18n: 文字列は `I18N` 辞書 + `tr(key)`。ウィジェットは `T(widget, key)` で言語切替追従
- テスト実行: `uv run pytest tests/ -q`。GUIテストは `DISPLAY` 必須 (`needs_display` マーカーで自動スキップ)
- コミットは Conventional Commits 形式、日本語メッセージ、attribution なし

---

### Task 1: 定数とi18nキーの追加

**Files:**
- Modify: `serial_terminal.py:41-71` (定数セクション)、`serial_terminal.py:198-201` (I18N辞書末尾)
- Test: `tests/test_i18n.py` (既存の網羅テストが自動検証)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_i18n.py` の末尾に追加:

```python
class TestNetworkI18nKeys:
    def test_conn_type_codes_have_labels(self):
        for code in st.CONN_TYPES:
            assert "ct_" + code in st.I18N, code

    def test_conn_types_order(self):
        assert st.CONN_TYPES == ["serial", "tcp_client", "tcp_server", "udp"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_i18n.py::TestNetworkI18nKeys -v`
Expected: FAIL (`AttributeError: module 'serial_terminal' has no attribute 'CONN_TYPES'`)

- [ ] **Step 3: 実装する**

`serial_terminal.py` の定数セクション (`RX_NEWLINE_CODES` の直後、61行付近) に追加:

```python
# 接続種別 (内部コード)。表示文字列は tr("ct_<code>") で得る。
CONN_TYPES = ["serial", "tcp_client", "tcp_server", "udp"]

CONNECT_TIMEOUT = 5.0      # TCPクライアント接続タイムアウト (秒)
READ_INTERVAL = 0.1        # 受信ポーリング間隔 (秒)
RECV_BUFSIZE = 4096        # TCP受信バッファ
UDP_BUFSIZE = 65535        # UDP受信バッファ (最大データグラム)
```

`I18N` 辞書の末尾 (`"ft_log"` エントリの後、201行付近) に追加:

```python
    # --- 接続種別 / ネットワーク ---
    "conn_type":      {"ja": "種別:", "en": "Type:"},
    "ct_serial":      {"ja": "シリアル", "en": "Serial"},
    "ct_tcp_client":  {"ja": "TCPクライアント", "en": "TCP Client"},
    "ct_tcp_server":  {"ja": "TCPサーバ", "en": "TCP Server"},
    "ct_udp":         {"ja": "UDP", "en": "UDP"},
    "net_host":       {"ja": "Host:", "en": "Host:"},
    "net_port":       {"ja": "Port:", "en": "Port:"},
    "listen_port":    {"ja": "待受Port:", "en": "Listen port:"},
    "udp_dest_host":  {"ja": "宛先Host:", "en": "Dest host:"},
    "udp_dest_port":  {"ja": "宛先Port:", "en": "Dest port:"},
    "udp_local_port": {"ja": "受信Port:", "en": "Local port:"},
    "st_listening":   {"ja": ":%d 待受中", "en": ":%d listening"},
    "st_tcp_peer":    {"ja": ":%d ← %s 接続中", "en": ":%d ← %s connected"},
    "st_tcp_client":  {"ja": "%s:%d 接続中", "en": "%s:%d connected"},
    "st_udp":         {"ja": "UDP:%d → %s:%d", "en": "UDP:%d → %s:%d"},
    "err_port_range": {"ja": "ポート番号は1〜65535の整数で指定してください: %s",
                       "en": "Port number must be an integer 1-65535: %s"},
    "err_host_required": {"ja": "Hostを入力してください。",
                          "en": "Host is required."},
    "err_no_client":  {"ja": "クライアントが接続されていません。",
                       "en": "No client connected."},
    "err_conn_closed": {"ja": "接続が切断されました。",
                        "en": "Connection closed."},
```

あわせて `import socket` を `serial_terminal.py:25` 付近 (`import queue` の直後) に追加する。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_i18n.py -v`
Expected: 全PASS (既存の `test_all_keys_have_both_languages` が新キーのja/en両方の存在も検証する)

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_i18n.py
git commit -m "feat: 接続種別の定数とネットワーク関連i18nキーを追加"
```

---

### Task 2: parse_port_number ユーティリティ

**Files:**
- Modify: `serial_terminal.py` (ユーティリティセクション、`parse_hex` の直前)
- Test: `tests/test_transports.py` (新規作成)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_transports.py` を新規作成:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_transports.py -v`
Expected: FAIL (`AttributeError: ... no attribute 'parse_port_number'`)

- [ ] **Step 3: 実装する**

`serial_terminal.py` のユーティリティセクション (`parse_hex` の直前、295行付近) に追加:

```python
def parse_port_number(text: str) -> int:
    """ポート番号文字列を検証して int を返す。不正なら ValueError。"""
    try:
        port = int(text.strip())
    except ValueError:
        raise ValueError(tr("err_port_range") % text)
    if not 1 <= port <= 65535:
        raise ValueError(tr("err_port_range") % text)
    return port
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_transports.py -v`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_transports.py
git commit -m "feat: ポート番号の入力検証ユーティリティを追加"
```

---

### Task 3: Transport基底クラスと SerialTransport

**Files:**
- Modify: `serial_terminal.py` (新セクション「トランスポート」を `MacroDialog` クラスの直前に追加)
- Test: `tests/test_transports.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_transports.py` に追加:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_transports.py::TestSerialTransport -v`
Expected: FAIL (`AttributeError: ... no attribute 'SerialTransport'`)

- [ ] **Step 3: 実装する**

`serial_terminal.py` に新セクションを追加 (`hexdump_lines` 関数の後、`MacroDialog` クラスの前):

```python
# ---------------------------------------------------------- トランスポート ----

class TransportError(Exception):
    """通信の確立・送受信に失敗したことを示す。"""


class Transport:
    """通信方式 (シリアル/TCP/UDP) の共通インターフェース。

    read() は受信スレッドから呼ばれる。タイムアウト時は b"" を返し、
    切断・エラー時は TransportError を送出する。
    """

    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def read(self, timeout: float) -> bytes:
        raise NotImplementedError

    def write(self, data: bytes):
        raise NotImplementedError

    @property
    def is_open(self) -> bool:
        raise NotImplementedError

    @property
    def description(self) -> str:
        """ステータスバー用の表示文字列。"""
        raise NotImplementedError

    @property
    def tab_label(self) -> str:
        """タブ名用の短い表示文字列。既定は description と同じ。"""
        return self.description


class SerialTransport(Transport):
    """serial.Serial をラップする。port には loop:// 等のURLも指定可能。"""

    def __init__(self, port, baudrate, bytesize, parity, stopbits):
        self.port = port
        self.baudrate = baudrate
        self._kwargs = dict(baudrate=baudrate, bytesize=bytesize,
                            parity=parity, stopbits=stopbits)
        self._ser = None

    def open(self):
        try:
            self._ser = serial.serial_for_url(self.port, timeout=READ_INTERVAL,
                                              **self._kwargs)
        except (serial.SerialException, ValueError, OSError) as e:
            raise TransportError(str(e))

    def close(self):
        if self._ser:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None

    def read(self, timeout):
        # タイムアウトはコンストラクタの timeout= が担うため引数は未使用
        try:
            n = self._ser.in_waiting
            return self._ser.read(n if n else 1)
        except (serial.SerialException, OSError) as e:
            raise TransportError(str(e))

    def write(self, data):
        try:
            self._ser.write(data)
        except (serial.SerialException, OSError) as e:
            raise TransportError(str(e))

    @property
    def is_open(self):
        return bool(self._ser and self._ser.is_open)

    @property
    def description(self):
        return tr("st_open_fmt") % (self.port, self.baudrate)

    @property
    def tab_label(self):
        return self.port
```

注意: `serial_for_url` は `://` を含まない文字列を通常のデバイス名として扱うため、既存の `COM3` / `/dev/ttyUSB0` 指定はそのまま動く。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_transports.py -v`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_transports.py
git commit -m "feat: Transport基底クラスとSerialTransportを追加"
```

---

### Task 4: TcpClientTransport

**Files:**
- Modify: `serial_terminal.py` (トランスポートセクション、`SerialTransport` の後)
- Test: `tests/test_transports.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_transports.py` に追加:

```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_transports.py::TestTcpClientTransport -v`
Expected: FAIL (`AttributeError: ... no attribute 'TcpClientTransport'`)

- [ ] **Step 3: 実装する**

`SerialTransport` の直後に追加:

```python
class TcpClientTransport(Transport):
    """リモートのTCPサーバへ接続するクライアント。"""

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._sock = None

    def open(self):
        try:
            self._sock = socket.create_connection(
                (self.host, self.port), timeout=CONNECT_TIMEOUT)
        except OSError as e:
            raise TransportError(str(e))

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def read(self, timeout):
        sock = self._sock
        if sock is None:
            raise TransportError(tr("err_conn_closed"))
        sock.settimeout(timeout)
        try:
            data = sock.recv(RECV_BUFSIZE)
        except socket.timeout:
            return b""
        except OSError as e:
            raise TransportError(str(e))
        if not data:
            raise TransportError(tr("err_conn_closed"))
        return data

    def write(self, data):
        if self._sock is None:
            raise TransportError(tr("err_conn_closed"))
        try:
            self._sock.sendall(data)
        except OSError as e:
            raise TransportError(str(e))

    @property
    def is_open(self):
        return self._sock is not None

    @property
    def description(self):
        return tr("st_tcp_client") % (self.host, self.port)

    @property
    def tab_label(self):
        return "%s:%d" % (self.host, self.port)
```

注意: `socket.timeout` は Python 3.10+ で `TimeoutError` (OSErrorのサブクラス) の別名。**必ず OSError より前に捕捉**すること (順序を入れ替えるとタイムアウトが切断扱いになる)。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_transports.py -v`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_transports.py
git commit -m "feat: TcpClientTransportを追加"
```

---

### Task 5: TcpServerTransport

**Files:**
- Modify: `serial_terminal.py` (トランスポートセクション、`TcpClientTransport` の後)
- Test: `tests/test_transports.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_transports.py` に追加:

```python
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
```

注意: `test_bind_conflict_raises` は SO_REUSEADDR が同一ポートの**listen中**ソケットとの競合まで許すわけではないことを利用する (Linux/macOS)。

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_transports.py::TestTcpServerTransport -v`
Expected: FAIL (`AttributeError: ... no attribute 'TcpServerTransport'`)

- [ ] **Step 3: 実装する**

`TcpClientTransport` の直後に追加:

```python
class TcpServerTransport(Transport):
    """1クライアントのみ受け入れるTCPサーバ。

    接続中の新規接続は即クローズで拒否し、クライアント切断後は自動で
    待ち受けに戻る。接続/切断は on_status_change(self) で通知する
    (受信スレッドから呼ばれる点に注意)。
    """

    def __init__(self, listen_port, on_status_change=None):
        self.listen_port = listen_port
        self.on_status_change = on_status_change
        self._listen_sock = None
        self._conn = None
        self._peer = None

    def open(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.listen_port))
            sock.listen(1)
        except OSError as e:
            sock.close()
            raise TransportError(str(e))
        self._listen_sock = sock

    def close(self):
        self._drop_client(notify=False)
        if self._listen_sock:
            try:
                self._listen_sock.close()
            except OSError:
                pass
            self._listen_sock = None

    def _drop_client(self, notify=True):
        if self._conn:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None
            self._peer = None
            if notify and self.on_status_change:
                self.on_status_change(self)

    def _reject_pending(self):
        """接続中に来た新規接続を即クローズで拒否する。"""
        self._listen_sock.settimeout(0)
        try:
            extra, _ = self._listen_sock.accept()
            extra.close()
        except OSError:
            pass

    def read(self, timeout):
        if self._listen_sock is None:
            raise TransportError(tr("err_conn_closed"))
        if self._conn is None:
            # 待受中: timeout 付きで accept を試みる
            self._listen_sock.settimeout(timeout)
            try:
                conn, addr = self._listen_sock.accept()
            except socket.timeout:
                return b""
            except OSError as e:
                raise TransportError(str(e))
            self._conn, self._peer = conn, addr
            if self.on_status_change:
                self.on_status_change(self)
            return b""
        self._reject_pending()
        self._conn.settimeout(timeout)
        try:
            data = self._conn.recv(RECV_BUFSIZE)
        except socket.timeout:
            return b""
        except OSError:
            self._drop_client()
            return b""
        if not data:
            self._drop_client()      # 切断 → 再待受へ
            return b""
        return data

    def write(self, data):
        if self._conn is None:
            raise TransportError(tr("err_no_client"))
        try:
            self._conn.sendall(data)
        except OSError as e:
            raise TransportError(str(e))

    @property
    def is_open(self):
        return self._listen_sock is not None

    @property
    def description(self):
        if self._peer:
            return tr("st_tcp_peer") % (self.listen_port,
                                        "%s:%d" % self._peer)
        return tr("st_listening") % self.listen_port

    @property
    def tab_label(self):
        return self.description
```

設計メモ: クライアント切断は TransportError にせず b"" を返して再待受に戻る (サーバを止めない)。サーバ自体が止まるのは listen ソケットのエラーのみ。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_transports.py -v`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_transports.py
git commit -m "feat: TcpServerTransportを追加 (1クライアント、自動再待受)"
```

---

### Task 6: UdpTransport

**Files:**
- Modify: `serial_terminal.py` (トランスポートセクション、`TcpServerTransport` の後)
- Test: `tests/test_transports.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_transports.py` に追加:

```python
class TestUdpTransport:
    def test_bidirectional_roundtrip(self):
        a_port = free_port(socket.SOCK_DGRAM)
        b_port = free_port(socket.SOCK_DGRAM)
        a = st.UdpTransport("127.0.0.1", b_port, a_port)
        b = st.UdpTransport("127.0.0.1", a_port, b_port)
        a.open()
        b.open()
        try:
            a.write(b"\x01\x02")
            assert b.read(1.0) == b"\x01\x02"
            b.write(b"ok")
            assert a.read(1.0) == b"ok"
        finally:
            a.close()
            b.close()

    def test_read_timeout_returns_empty(self):
        t = st.UdpTransport("127.0.0.1", 9, free_port(socket.SOCK_DGRAM))
        t.open()
        try:
            assert t.read(0.1) == b""
        finally:
            t.close()

    def test_receives_from_any_sender(self):
        local = free_port(socket.SOCK_DGRAM)
        t = st.UdpTransport("127.0.0.1", 9, local)   # 宛先はダミー
        t.open()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.sendto(b"anon", ("127.0.0.1", local))
            assert t.read(1.0) == b"anon"
        finally:
            t.close()

    def test_tab_label(self):
        t = st.UdpTransport("10.0.0.1", 5000, 6000)
        assert t.tab_label == "UDP:6000"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_transports.py::TestUdpTransport -v`
Expected: FAIL (`AttributeError: ... no attribute 'UdpTransport'`)

- [ ] **Step 3: 実装する**

`TcpServerTransport` の直後に追加:

```python
class UdpTransport(Transport):
    """コネクションレスUDP。宛先へ sendto し、受信ポートで recvfrom する。"""

    def __init__(self, dest_host, dest_port, local_port):
        self.dest_host = dest_host
        self.dest_port = dest_port
        self.local_port = local_port
        self._sock = None

    def open(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", self.local_port))
        except OSError as e:
            sock.close()
            raise TransportError(str(e))
        self._sock = sock

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def read(self, timeout):
        sock = self._sock
        if sock is None:
            raise TransportError(tr("err_conn_closed"))
        sock.settimeout(timeout)
        try:
            data, _addr = sock.recvfrom(UDP_BUFSIZE)
        except socket.timeout:
            return b""
        except OSError as e:
            raise TransportError(str(e))
        return data

    def write(self, data):
        if self._sock is None:
            raise TransportError(tr("err_conn_closed"))
        try:
            self._sock.sendto(data, (self.dest_host, self.dest_port))
        except OSError as e:
            raise TransportError(str(e))

    @property
    def is_open(self):
        return self._sock is not None

    @property
    def description(self):
        return tr("st_udp") % (self.local_port, self.dest_host,
                               self.dest_port)

    @property
    def tab_label(self):
        return "UDP:%d" % self.local_port
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_transports.py -v`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_transports.py
git commit -m "feat: UdpTransportを追加"
```

---

### Task 7: 接続種別コンボとパラメータ欄の切替UI

**Files:**
- Modify: `serial_terminal.py:532-568` (`_build_ui` の接続バー)、`serial_terminal.py:732-737` (`_retranslate_combos`)
- Test: `tests/test_gui_conn_type.py` (新規作成)

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_gui_conn_type.py` を新規作成:

```python
# -*- coding: utf-8 -*-
"""接続種別切替UIのテスト (DISPLAY がある環境のみ)。"""
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


def _select_type(tab, code):
    tab.conn_type_cmb.current(st.CONN_TYPES.index(code))
    tab._change_conn_type()


@needs_display
class TestConnTypeSwitch:
    def test_default_is_serial(self, tab):
        assert tab.conn_type_code == "serial"
        assert tab.param_frames["serial"].winfo_manager() == "pack"

    def test_switch_to_tcp_client_swaps_frames(self, tab):
        _select_type(tab, "tcp_client")
        assert tab.conn_type_code == "tcp_client"
        assert tab.param_frames["serial"].winfo_manager() == ""
        assert tab.param_frames["tcp_client"].winfo_manager() == "pack"

    def test_switch_all_types_and_back(self, tab):
        for code in ("tcp_server", "udp", "serial"):
            _select_type(tab, code)
            assert tab.param_frames[code].winfo_manager() == "pack"
            others = [c for c in st.CONN_TYPES if c != code]
            assert all(tab.param_frames[c].winfo_manager() == ""
                       for c in others)

    def test_combo_values_translated(self, tab):
        assert "シリアル" in tab.conn_type_cmb["values"]
        tab.app.switch_language("en")
        assert "Serial" in tab.conn_type_cmb["values"]
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_gui_conn_type.py -v`
Expected: FAIL (`AttributeError: ... no attribute 'conn_type_cmb'`)

- [ ] **Step 3: 実装する**

`_build_ui` の接続バー部分 (`serial_terminal.py:532-568`) を次のように再構成する。既存のシリアル用ウィジェット (port/baud/data/parity/stop) は `bar1` 直下から `serial` フレーム配下へ移す (親引数を変えるだけで、変数名・i18nキーは変えない):

```python
    def _build_ui(self):
        # ---- 接続バー ----
        bar1 = ttk.Frame(self, padding=(6, 4))
        bar1.pack(fill="x")

        T(ttk.Label(bar1), "conn_type").pack(side="left")
        self.conn_type_code = "serial"
        self.conn_type_cmb = ttk.Combobox(bar1, width=14, state="readonly")
        self.conn_type_cmb.pack(side="left", padx=(2, 8))
        self.conn_type_cmb.bind("<<ComboboxSelected>>",
                                lambda e: self._change_conn_type())

        # 種別ごとのパラメータフレーム (どれか1つだけ pack する)
        self.param_frames = {
            "serial":     self._build_serial_params(bar1),
            "tcp_client": self._build_tcp_client_params(bar1),
            "tcp_server": self._build_tcp_server_params(bar1),
            "udp":        self._build_udp_params(bar1),
        }

        self.conn_btn = ttk.Button(bar1, width=10,
                                   command=self.toggle_connection)
        self.conn_btn.pack(side="left", padx=(4, 8))

        T(ttk.Button(bar1, command=self.close_tab), "close_tab")\
            .pack(side="right")

        self.param_frames[self.conn_type_code]\
            .pack(side="left", before=self.conn_btn)
```

`_build_ui` の直後にビルダーメソッド群を追加:

```python
    def _build_serial_params(self, parent):
        fr = ttk.Frame(parent)
        T(ttk.Label(fr), "port").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cmb = ttk.Combobox(fr, textvariable=self.port_var, width=22)
        self.port_cmb.pack(side="left", padx=(2, 2))
        T(ttk.Button(fr, width=7, command=self.refresh_ports),
          "refresh").pack(side="left", padx=(0, 8))

        ttk.Label(fr, text="Baud:").pack(side="left")
        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(fr, textvariable=self.baud_var, values=BAUDRATES,
                     width=8).pack(side="left", padx=(2, 8))

        ttk.Label(fr, text="Data:").pack(side="left")
        self.bits_var = tk.StringVar(value="8")
        ttk.Combobox(fr, textvariable=self.bits_var, values=list(BYTESIZES),
                     width=3, state="readonly").pack(side="left", padx=(2, 8))

        ttk.Label(fr, text="Parity:").pack(side="left")
        self.parity_var = tk.StringVar(value="None")
        ttk.Combobox(fr, textvariable=self.parity_var, values=list(PARITIES),
                     width=5, state="readonly").pack(side="left", padx=(2, 8))

        ttk.Label(fr, text="Stop:").pack(side="left")
        self.stop_var = tk.StringVar(value="1")
        ttk.Combobox(fr, textvariable=self.stop_var, values=list(STOPBITS),
                     width=4, state="readonly").pack(side="left", padx=(2, 8))
        return fr

    def _build_tcp_client_params(self, parent):
        fr = ttk.Frame(parent)
        T(ttk.Label(fr), "net_host").pack(side="left")
        self.tcp_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(fr, textvariable=self.tcp_host_var, width=18)\
            .pack(side="left", padx=(2, 8))
        T(ttk.Label(fr), "net_port").pack(side="left")
        self.tcp_port_var = tk.StringVar(value="5000")
        ttk.Entry(fr, textvariable=self.tcp_port_var, width=7)\
            .pack(side="left", padx=(2, 8))
        return fr

    def _build_tcp_server_params(self, parent):
        fr = ttk.Frame(parent)
        T(ttk.Label(fr), "listen_port").pack(side="left")
        self.listen_port_var = tk.StringVar(value="5000")
        ttk.Entry(fr, textvariable=self.listen_port_var, width=7)\
            .pack(side="left", padx=(2, 8))
        return fr

    def _build_udp_params(self, parent):
        fr = ttk.Frame(parent)
        T(ttk.Label(fr), "udp_dest_host").pack(side="left")
        self.udp_host_var = tk.StringVar(value="127.0.0.1")
        ttk.Entry(fr, textvariable=self.udp_host_var, width=18)\
            .pack(side="left", padx=(2, 4))
        T(ttk.Label(fr), "udp_dest_port").pack(side="left")
        self.udp_port_var = tk.StringVar(value="5000")
        ttk.Entry(fr, textvariable=self.udp_port_var, width=7)\
            .pack(side="left", padx=(2, 8))
        T(ttk.Label(fr), "udp_local_port").pack(side="left")
        self.udp_local_var = tk.StringVar(value="5000")
        ttk.Entry(fr, textvariable=self.udp_local_var, width=7)\
            .pack(side="left", padx=(2, 8))
        return fr

    def _change_conn_type(self):
        new_code = CONN_TYPES[self.conn_type_cmb.current()]
        if new_code == self.conn_type_code:
            return
        self.param_frames[self.conn_type_code].pack_forget()
        self.conn_type_code = new_code
        self.param_frames[new_code].pack(side="left", before=self.conn_btn)
```

`_retranslate_combos` (`serial_terminal.py:732-737`) の先頭に2行追加 (既存行は変更しない):

```python
    def _retranslate_combos(self):
        """種別/送信改行/受信改行コンボの選択肢と現在値を現在言語で再生成する。"""
        self.conn_type_cmb["values"] = [tr("ct_" + c) for c in CONN_TYPES]
        self.conn_type_cmb.current(CONN_TYPES.index(self.conn_type_code))
        self.tx_eol_combo["values"] = [tr("eol_" + c) for c in TX_EOL_CODES]
        self.tx_eol_var.set(tr("eol_" + self.tx_eol_code))
        self.rx_nl_combo["values"] = [tr("rxnl_" + c) for c in RX_NEWLINE_CODES]
        self.rx_nl_var.set(tr("rxnl_" + self.nl_filter.mode))
```

注意: `_retranslate_combos` は `_build_ui` 内の `bar2` 構築後 (600行付近) に呼ばれており、その時点で `conn_type_cmb` は構築済みなので順序問題はない。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/test_gui_conn_type.py tests/test_gui_language.py -v`
Expected: 全PASS (既存のGUIテストも壊れていないこと)

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_gui_conn_type.py
git commit -m "feat: 接続種別コンボとパラメータ欄の切替UIを追加"
```

---

### Task 8: PortTab接続処理のTransport化

**Files:**
- Modify: `serial_terminal.py` — `self.ser` の全使用箇所 (509, 739-741, 774-818, 821, 830-840, 978-1002, 1200-1206行付近)
- Test: `tests/test_gui_conn_type.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_gui_conn_type.py` に追加:

```python
def _free_udp_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@needs_display
class TestTransportConnection:
    def test_udp_connect_and_disconnect(self, tab):
        # UDPはピア不要で接続(=ソケット作成)できる
        _select_type(tab, "udp")
        tab.udp_host_var.set("127.0.0.1")
        tab.udp_port_var.set("9")
        tab.udp_local_var.set(str(_free_udp_port()))
        tab.connect()
        try:
            assert tab.transport is not None
            assert tab.transport.is_open
            assert str(tab.conn_type_cmb["state"]) == "disabled"
        finally:
            tab.disconnect()
        assert tab.transport is None
        assert str(tab.conn_type_cmb["state"]) == "readonly"

    def test_invalid_port_shows_warning_not_crash(self, tab, monkeypatch):
        warnings = []
        monkeypatch.setattr(st.messagebox, "showwarning",
                            lambda *a, **k: warnings.append(a))
        _select_type(tab, "tcp_client")
        tab.tcp_port_var.set("not-a-port")
        tab.connect()
        assert tab.transport is None
        assert warnings
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_gui_conn_type.py::TestTransportConnection -v`
Expected: FAIL (`AttributeError: 'PortTab' object has no attribute 'transport'`)

- [ ] **Step 3: 実装する**

(1) `serial_terminal.py:509` の属性を置換:

```python
        self.transport = None                 # Transport (接続中のみ非None)
```

(2) `toggle_connection` / `connect` / `disconnect` (`serial_terminal.py:774-818`) を置換:

```python
    def toggle_connection(self):
        if self.transport and self.transport.is_open:
            self.disconnect()
        else:
            self.connect()

    def _make_transport(self):
        """UI入力からTransportを構築する。入力不正は ValueError。"""
        ctype = self.conn_type_code
        if ctype == "serial":
            port = self.port_var.get().strip()
            if not port:
                raise ValueError(tr("mb_select_port"))
            return SerialTransport(
                port=port,
                baudrate=int(self.baud_var.get()),
                bytesize=BYTESIZES[self.bits_var.get()],
                parity=PARITIES[self.parity_var.get()],
                stopbits=STOPBITS[self.stop_var.get()])
        if ctype == "tcp_client":
            host = self.tcp_host_var.get().strip()
            if not host:
                raise ValueError(tr("err_host_required"))
            return TcpClientTransport(
                host, parse_port_number(self.tcp_port_var.get()))
        if ctype == "tcp_server":
            return TcpServerTransport(
                parse_port_number(self.listen_port_var.get()),
                on_status_change=self._on_transport_status)
        host = self.udp_host_var.get().strip()
        if not host:
            raise ValueError(tr("err_host_required"))
        return UdpTransport(host,
                            parse_port_number(self.udp_port_var.get()),
                            parse_port_number(self.udp_local_var.get()))

    def connect(self):
        try:
            transport = self._make_transport()
        except ValueError as e:
            messagebox.showwarning(tr("mb_connect_title"), str(e),
                                   parent=self)
            return
        try:
            transport.open()
        except TransportError as e:
            messagebox.showerror(tr("mb_conn_err_title"), str(e),
                                 parent=self)
            return
        self.transport = transport
        self.alive = True
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()
        self.conn_btn.config(text=tr("disconnect"))
        self.conn_type_cmb.config(state="disabled")
        self.notebook.tab(self, text=transport.tab_label)
        self._update_status()

    def disconnect(self):
        self.alive = False
        if self.reader_thread:
            self.reader_thread.join(timeout=1.0)
            self.reader_thread = None
        if self.transport:
            self.transport.close()
            self.transport = None
        self.conn_btn.config(text=tr("connect"))
        self.conn_type_cmb.config(state="readonly")
        self._update_status()

    def _on_transport_status(self, transport):
        """受信スレッドからの状態変化通知をUIスレッドへ引き渡す。"""
        def update():
            if self.transport is not transport:
                return
            self.notebook.tab(self, text=transport.tab_label)
            self._update_status()
        try:
            self.after(0, update)
        except (tk.TclError, RuntimeError):
            pass        # ウィンドウ破棄後の通知は無視
```

注意: 旧 `connect()` にあった「ポート未選択の警告」は `_make_transport` の ValueError に統合した。旧 `disconnect()` の `try/except` 付き close は Transport 側の close() が例外を握りつぶすため不要。

(3) `_reader` (`serial_terminal.py:830-840`) を置換:

```python
    def _reader(self):
        """受信スレッド: トランスポートから読み出してキューへ。"""
        while self.alive and self.transport:
            try:
                data = self.transport.read(READ_INTERVAL)
            except TransportError:
                self.rx_queue.put(None)         # 切断シグナル
                break
            if data:
                self.rx_queue.put(bytes(data))
```

(4) `_send_bytes` (`serial_terminal.py:978-1002`) の冒頭を置換 (`self.tx_raw.extend(payload)` 以降は既存のまま):

```python
    def _send_bytes(self, payload: bytes):
        if not (self.transport and self.transport.is_open):
            messagebox.showwarning(tr("mb_send_title"), tr("mb_port_not_open"),
                                   parent=self)
            return False
        try:
            self.transport.write(payload)
        except TransportError as e:
            messagebox.showerror(tr("mb_send_err_title"), str(e), parent=self)
            return False
```

(5) `_retranslate_dynamic` (`serial_terminal.py:739-741`)、`close_tab` (`serial_terminal.py:821`) の条件式を置換:

```python
        connected = bool(self.transport and self.transport.is_open)
```

```python
        if self.transport and self.transport.is_open:
```

(6) `_update_status` (`serial_terminal.py:1200-1206`) を置換:

```python
    def _update_status(self):
        if self.transport and self.transport.is_open:
            s = self.transport.description
        else:
            s = tr("not_connected")
        self.status_var.set("%s | RX: %d bytes  TX: %d bytes"
                            % (s, len(self.rx_raw), len(self.tx_raw)))
```

(7) 置換漏れ確認: `grep -n "self\.ser\b" serial_terminal.py` が0件になること。

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/ -q`
Expected: 全PASS (既存テスト含む)

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_gui_conn_type.py
git commit -m "feat: 接続処理をTransport抽象化に移行しTCP/UDP接続を実装"
```

---

### Task 9: ネットワーク設定の保存と復元

**Files:**
- Modify: `serial_terminal.py` (`connect` と `_build_ui` のビルダーメソッド)
- Test: `tests/test_gui_conn_type.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_gui_conn_type.py` に追加:

```python
@needs_display
class TestNetworkSettingsPersistence:
    def test_successful_connect_saves_defaults(self, tab):
        _select_type(tab, "udp")
        local = str(_free_udp_port())
        tab.udp_host_var.set("127.0.0.1")
        tab.udp_port_var.set("7777")
        tab.udp_local_var.set(local)
        tab.connect()
        tab.disconnect()
        s = st.load_settings()
        assert s["conn_type"] == "udp"
        assert s["udp_host"] == "127.0.0.1"
        assert s["udp_port"] == "7777"
        assert s["udp_local_port"] == local

    def test_new_tab_restores_saved_defaults(self, tab):
        st.save_settings({"conn_type": "tcp_client",
                          "tcp_host": "10.1.2.3", "tcp_port": "1234"})
        tab.app.add_tab()
        new_tab = tab.app.nametowidget(tab.app.notebook.tabs()[-1])
        assert new_tab.conn_type_code == "tcp_client"
        assert new_tab.param_frames["tcp_client"].winfo_manager() == "pack"
        assert new_tab.tcp_host_var.get() == "10.1.2.3"
        assert new_tab.tcp_port_var.get() == "1234"

    def test_invalid_saved_conn_type_falls_back_to_serial(self, tab):
        st.save_settings({"conn_type": "bogus"})
        tab.app.add_tab()
        new_tab = tab.app.nametowidget(tab.app.notebook.tabs()[-1])
        assert new_tab.conn_type_code == "serial"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `uv run pytest tests/test_gui_conn_type.py::TestNetworkSettingsPersistence -v`
Expected: FAIL (settings に conn_type が保存されない / 復元されない)

- [ ] **Step 3: 実装する**

(1) `_build_ui` の冒頭で保存値を読み、初期種別に反映する:

```python
    def _build_ui(self):
        saved = load_settings()

        # ---- 接続バー ----
        bar1 = ttk.Frame(self, padding=(6, 4))
        bar1.pack(fill="x")

        T(ttk.Label(bar1), "conn_type").pack(side="left")
        code = saved.get("conn_type")
        self.conn_type_code = code if code in CONN_TYPES else "serial"
        ...(以降は Task 7 のとおり。param_frames 構築時に saved を渡す)...
        self.param_frames = {
            "serial":     self._build_serial_params(bar1),
            "tcp_client": self._build_tcp_client_params(bar1, saved),
            "tcp_server": self._build_tcp_server_params(bar1, saved),
            "udp":        self._build_udp_params(bar1, saved),
        }
```

(2) ネットワーク系ビルダーメソッドのシグネチャを `(self, parent, saved)` に変更し、StringVar 初期値を保存値優先にする:

```python
        # _build_tcp_client_params 内
        self.tcp_host_var = tk.StringVar(
            value=saved.get("tcp_host", "127.0.0.1"))
        self.tcp_port_var = tk.StringVar(value=saved.get("tcp_port", "5000"))
```

```python
        # _build_tcp_server_params 内
        self.listen_port_var = tk.StringVar(
            value=saved.get("tcp_server_port", "5000"))
```

```python
        # _build_udp_params 内
        self.udp_host_var = tk.StringVar(
            value=saved.get("udp_host", "127.0.0.1"))
        self.udp_port_var = tk.StringVar(value=saved.get("udp_port", "5000"))
        self.udp_local_var = tk.StringVar(
            value=saved.get("udp_local_port", "5000"))
```

(3) `connect` の成功パス (`self.transport = transport` の直後) に保存処理を追加し、メソッドを新設:

```python
        self.transport = transport
        self._save_net_defaults()
```

```python
    def _save_net_defaults(self):
        """接続成功時のネットワーク設定を新規タブの既定値として保存する。"""
        settings = load_settings()
        settings.update({
            "conn_type":       self.conn_type_code,
            "tcp_host":        self.tcp_host_var.get(),
            "tcp_port":        self.tcp_port_var.get(),
            "tcp_server_port": self.listen_port_var.get(),
            "udp_host":        self.udp_host_var.get(),
            "udp_port":        self.udp_port_var.get(),
            "udp_local_port":  self.udp_local_var.get(),
        })
        save_settings(settings)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `uv run pytest tests/ -q`
Expected: 全PASS

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py tests/test_gui_conn_type.py
git commit -m "feat: ネットワーク接続設定を保存し新規タブの既定値に復元"
```

---

### Task 10: ドキュメント更新と総仕上げ

**Files:**
- Modify: `serial_terminal.py:3-20` (モジュールdocstring)、`README.md`

- [ ] **Step 1: モジュールdocstringの機能一覧を更新**

`serial_terminal.py:12-19` の機能一覧を更新 (項目2の文言変更と項目3の挿入):

```python
機能:
 1. ASCII送信欄と受信ビューを分離。受信バイナリ(HEXダンプ)ビューを選択的に表示可能
 2. 1アプリ内で接続ごとにタブを作成(複数接続同時運用)
 3. 接続種別をシリアル / TCPクライアント / TCPサーバ / UDP から選択可能
 4. 定型文(ASCII / HEX どちらの形式でも登録・送信可能、JSONで保存/読込)
 5. 送信時の改行 (なし / \n / \r / \r\n) と受信時の改行表示の扱いを設定可能
 6. ボーレート・データビット・パリティ・ストップビット変更可能
 7. 送受信データの保存 (受信: バイナリ/テキスト選択可、送信: バイナリ、全ログ、連続RAWログ)
 8. 文字エンコード選択 (UTF-8 / Shift_JIS / EUC-JP / ASCII / Latin-1 / UTF-16)
```

- [ ] **Step 2: READMEに接続種別の説明を追記**

`README.md` の機能説明セクションに、接続種別コンボ (シリアル / TCPクライアント / TCPサーバ / UDP) と各パラメータ (Host/Port、待受Port、宛先Host:Port+受信Port)、TCPサーバが1クライアントのみで切断後自動再待受であることを記載する (READMEの既存の文体・見出しレベルに合わせる)。

- [ ] **Step 3: 全テスト実行**

Run: `uv run pytest tests/ -q`
Expected: 全PASS

- [ ] **Step 4: 手動スモークテスト**

```bash
# 起動
uv run serial-terminal
# TCPサーバ: 種別=TCPサーバ, 待受Port=5000, 接続 → 別端末から nc 127.0.0.1 5000
# TCPクライアント: nc -l 5001 を立てて 種別=TCPクライアント Host=127.0.0.1 Port=5001
# UDP: 種別=UDP, 宛先127.0.0.1:6000, 受信5000 ↔ nc -u -p 6000 127.0.0.1 5000
```

確認項目: 接続/切断でタブ名とステータスが変わる、TCPサーバへの2本目の接続が拒否される、切断後に再接続できる、定型文・HEXビュー・ログ保存・送信欄のASCII/HEX変換がネットワーク接続でも動く。

- [ ] **Step 5: コミット**

```bash
git add serial_terminal.py README.md
git commit -m "docs: TCP/UDP対応をドキュメントに反映"
```

---

## Self-Review結果

- **Spec coverage:** 3接続形態 (Task 4-6)、タブ内切替UI (Task 7)、1クライアントTCPサーバ+拒否+再待受 (Task 5)、UDP宛先+受信ポート (Task 6)、設定保存 (Task 9)、エラー処理/ポート検証 (Task 2, 8)、i18n (Task 1, 7)、タブ名/ステータス表記 (Task 3-6 の description/tab_label + Task 8 の _on_transport_status)、既存機能無変更 (Task 8 Step 4 で既存テスト全PASS確認) — 全要件にタスクあり
- **Placeholder scan:** なし (「既存のまま」は変更不要箇所の明示)
- **Type consistency:** `read(timeout) -> bytes` / `TransportError` / `tab_label` / `description` / `conn_type_code` / `param_frames` / `_free_udp_port` の名前は全タスクで一致
