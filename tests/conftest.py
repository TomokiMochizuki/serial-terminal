# -*- coding: utf-8 -*-
"""GUI テスト共通のフィクスチャ。"""
import pytest


@pytest.fixture
def _gui_capture_safe(request):
    """GUI(Tk)を生成するテストの間だけ pytest の出力キャプチャを退避する。

    pytest は既定で fd レベル(標準出力/エラーの fd 1/2 を一時ファイルに差し替え)
    のキャプチャを行うが、Windows の Tcl/Tk は初期化や各ウィジェットライブラリの
    遅延読込時に標準チャネル(fd)を直接利用する。このため fd が差し替えられた状態
    では Tk ライブラリの読込が間欠的に失敗し、"tk wasn't installed properly" として
    App() 生成が落ちることがある(同一プロセスで複数回 Tk ルートを生成する
    テスト実行時に顕在化)。

    キャプチャを一時的に無効化すると実 fd が復帰し、Tk を確実に初期化できる。
    このフィクスチャを要求したテストの setup/実行/teardown の全区間で有効。
    """
    capmanager = request.config.pluginmanager.getplugin("capturemanager")
    if capmanager is None:
        yield
        return
    with capmanager.global_and_fixture_disabled():
        yield
