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
def tab(tmp_path, monkeypatch, _gui_capture_safe):
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


@needs_display
class TestTcpServerStatusLabel:
    """TCPサーバの接続/切断がUIスレッドに正しく反映されること
    (受信スレッドからの状態通知はメインスレッドで処理する必要がある)。"""

    def test_peer_connection_updates_tab_label(self, tab):
        import socket
        import time
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        _select_type(tab, "tcp_server")
        tab.listen_port_var.set(str(port))
        tab.connect()
        try:
            c = socket.create_connection(("127.0.0.1", port), timeout=2)
            connected_label = None
            for _ in range(60):
                tab.app.update()
                time.sleep(0.05)
                lbl = tab.notebook.tab(tab, "text")
                if "←" in lbl:        # "←" を含む = 接続中表示
                    connected_label = lbl
                    break
            assert connected_label is not None, \
                "接続中のタブ名がUIに反映されなかった"
            # --- 切断 → 待受表示へ戻る ---
            c.close()
            relisten_label = None
            for _ in range(60):
                tab.app.update()
                time.sleep(0.05)
                lbl = tab.notebook.tab(tab, "text")
                if "←" not in lbl and tab.transport._conn is None:
                    relisten_label = lbl
                    break
            assert relisten_label is not None, \
                "切断後の待受表示がUIに反映されなかった"
        finally:
            tab.disconnect()
