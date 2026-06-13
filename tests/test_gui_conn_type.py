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
