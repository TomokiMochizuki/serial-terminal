# -*- coding: utf-8 -*-
"""list_serial_ports / _serialcomm_ports のテスト。

pyserial の comports() は com0com など独自バスクラスの仮想ポートを
取りこぼすため、SERIALCOMM レジストリの内容をマージする挙動を検証する。
"""
from collections import namedtuple

import serial_terminal as st

PortInfo = namedtuple("PortInfo", ["device"])


def test_merges_serialcomm_ports(monkeypatch):
    """comports() に無いポートが SERIALCOMM 側にあればマージされる。"""
    monkeypatch.setattr(st.serial.tools.list_ports, "comports",
                        lambda: [PortInfo("COM1")])
    monkeypatch.setattr(st, "_serialcomm_ports",
                        lambda: ["COM1", "COM11", "COM12"])
    assert st.list_serial_ports() == ["COM1", "COM11", "COM12"]


def test_no_duplicates(monkeypatch):
    """両方に含まれるポートは重複しない。"""
    monkeypatch.setattr(st.serial.tools.list_ports, "comports",
                        lambda: [PortInfo("COM3")])
    monkeypatch.setattr(st, "_serialcomm_ports", lambda: ["COM3"])
    assert st.list_serial_ports() == ["COM3"]


def test_sorted_numerically(monkeypatch):
    """COM 番号は辞書順ではなく数値順に並ぶ。"""
    monkeypatch.setattr(st.serial.tools.list_ports, "comports", lambda: [])
    monkeypatch.setattr(st, "_serialcomm_ports",
                        lambda: ["COM12", "COM2", "COM1"])
    assert st.list_serial_ports() == ["COM1", "COM2", "COM12"]


def test_non_win32_returns_empty(monkeypatch):
    """非 Windows では SERIALCOMM 列挙は空を返す。"""
    monkeypatch.setattr(st.sys, "platform", "linux")
    assert st._serialcomm_ports() == []
