#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serial Binary/ASCII Terminal
============================
クロスプラットフォーム (Windows / WSL / Ubuntu / macOS) 対応
シリアルポート バイナリ・ASCII 送受信エディタ

依存ライブラリ: pyserial
    pip install pyserial

機能:
 1. ASCII送信欄と受信ビューを分離。受信バイナリ(HEXダンプ)ビューを選択的に表示可能
 2. 1アプリ内でCOMポートごとにタブを作成(複数ポート同時運用)
 3. 定型文(ASCII / HEX どちらの形式でも登録・送信可能、JSONで保存/読込)
 4. 送信時の改行 (なし / \n / \r / \r\n) と受信時の改行表示の扱いを設定可能
 5. ボーレート・データビット・パリティ・ストップビット変更可能
 6. 送受信データの保存 (受信: バイナリ/テキスト選択可、送信: バイナリ、全ログ、連続RAWログ)
 7. 文字エンコード選択 (UTF-8 / Shift_JIS / EUC-JP / ASCII / Latin-1 / UTF-16)
"""

import codecs
import json
import locale
import os
import queue
import threading
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    raise SystemExit("pyserial が必要です。次のコマンドでインストールしてください:\n"
                     "  pip install pyserial")

# ---------------------------------------------------------------- 定数 ----

ENCODINGS = ["utf-8", "shift_jis", "euc_jp", "ascii",
             "latin-1", "utf-16-le", "utf-16-be"]

BAUDRATES = ["300", "1200", "2400", "4800", "9600", "19200", "38400",
             "57600", "115200", "230400", "460800", "921600",
             "1000000", "2000000"]

# 送信時に付加する改行 (内部コード → bytes)。表示文字列は tr("eol_<code>") で得る。
TX_EOL_BYTES = {
    "none": b"",
    "lf":   b"\n",
    "cr":   b"\r",
    "crlf": b"\r\n",
}
TX_EOL_CODES = list(TX_EOL_BYTES)

# 受信表示時の改行の扱い (内部コード)。表示文字列は tr("rxnl_<code>") で得る。
RX_NEWLINE_CODES = ["raw", "cr_to_lf", "strip_cr"]

PARITIES  = {"None": serial.PARITY_NONE,
             "Even": serial.PARITY_EVEN,
             "Odd":  serial.PARITY_ODD}
STOPBITS  = {"1": serial.STOPBITS_ONE,
             "1.5": serial.STOPBITS_ONE_POINT_FIVE,
             "2": serial.STOPBITS_TWO}
BYTESIZES = {"8": serial.EIGHTBITS, "7": serial.SEVENBITS,
             "6": serial.SIXBITS,  "5": serial.FIVEBITS}

MONO_FONT = ("Consolas", 10) if tk.TkVersion else ("Courier", 10)


# ------------------------------------------------------------------ i18n ----

LANGUAGES = ("ja", "en")

I18N = {
    # --- アプリ / トップバー ---
    "add_tab":        {"ja": "＋ ポートタブを追加", "en": "+ Add port tab"},
    "tab_hint":       {"ja": "  各タブが1つのCOMポートに対応します",
                       "en": "  Each tab handles one COM port"},
    "lang_label":     {"ja": "言語:", "en": "Language:"},
    # --- 接続バー ---
    "port":           {"ja": "ポート:", "en": "Port:"},
    "refresh":        {"ja": "更新", "en": "Refresh"},
    "connect":        {"ja": "接続", "en": "Connect"},
    "disconnect":     {"ja": "切断", "en": "Disconnect"},
    "close_tab":      {"ja": "タブを閉じる", "en": "Close Tab"},
    # --- 設定バー ---
    "encoding":       {"ja": "エンコード:", "en": "Encoding:"},
    "tx_eol":         {"ja": "送信改行:", "en": "TX EOL:"},
    "rx_nl":          {"ja": "受信改行:", "en": "RX EOL:"},
    "hexview":        {"ja": "バイナリ(HEX)ビュー", "en": "Binary (HEX) view"},
    "local_echo":     {"ja": "ローカルエコー", "en": "Local echo"},
    "autoscroll":     {"ja": "自動スクロール", "en": "Auto scroll"},
    "clear_view":     {"ja": "表示クリア", "en": "Clear view"},
    # --- 保存メニュー ---
    "save_menu":      {"ja": "保存 ▾", "en": "Save ▾"},
    "save_rx_bin":    {"ja": "受信データをバイナリ保存 (.bin)",
                       "en": "Save RX data as binary (.bin)"},
    "save_rx_txt":    {"ja": "受信データをテキスト保存 (現在のエンコード)",
                       "en": "Save RX data as text (current encoding)"},
    "save_tx_bin":    {"ja": "送信データをバイナリ保存 (.bin)",
                       "en": "Save TX data as binary (.bin)"},
    "save_tx_txt":    {"ja": "送信データをテキスト保存",
                       "en": "Save TX data as text"},
    "save_log":       {"ja": "送受信ログ保存 (時刻+方向+HEX+ASCII)",
                       "en": "Save session log (time+dir+HEX+ASCII)"},
    "rawlog":         {"ja": "受信RAWを連続ログ (ファイルへ逐次追記)",
                       "en": "Continuous RAW RX log (append to file)"},
    # --- メイン領域 ---
    "rx_frame":       {"ja": "受信", "en": "Receive"},
    "tx_frame":       {"ja": "送信", "en": "Send"},
    "tx_hex_radio":   {"ja": "HEX (例: AA BB 0D 0A)",
                       "en": "HEX (e.g. AA BB 0D 0A)"},
    "tx_hint":        {"ja": "  Ctrl+Enterで送信", "en": "  Ctrl+Enter to send"},
    "send":           {"ja": "送信", "en": "Send"},
    # --- 定型文 ---
    "macro_frame":    {"ja": "定型文 (ダブルクリックで送信)",
                       "en": "Macros (double-click to send)"},
    "m_name":         {"ja": "名前", "en": "Name"},
    "m_mode":         {"ja": "形式", "en": "Format"},
    "m_data":         {"ja": "データ", "en": "Data"},
    "m_add":          {"ja": "追加", "en": "Add"},
    "m_edit":         {"ja": "編集", "en": "Edit"},
    "m_delete":       {"ja": "削除", "en": "Delete"},
    "m_load":         {"ja": "読込", "en": "Load"},
    "m_save":         {"ja": "保存", "en": "Save"},
    # --- 定型文ダイアログ ---
    "dlg_macro_add":  {"ja": "定型文の追加", "en": "Add Macro"},
    "dlg_macro_edit": {"ja": "定型文の編集", "en": "Edit Macro"},
    "d_name":         {"ja": "名前:", "en": "Name:"},
    "d_mode":         {"ja": "形式:", "en": "Format:"},
    "d_data":         {"ja": "データ:", "en": "Data:"},
    "d_ending":       {"ja": "送信時に改行設定を付加する (ASCIIのみ有効)",
                       "en": "Append line ending on send (ASCII only)"},
    "d_cancel":       {"ja": "キャンセル", "en": "Cancel"},
    # --- 改行の表示名 ---
    "eol_none":       {"ja": "なし", "en": "None"},
    "eol_lf":         {"ja": "LF (\\n)", "en": "LF (\\n)"},
    "eol_cr":         {"ja": "CR (\\r)", "en": "CR (\\r)"},
    "eol_crlf":       {"ja": "CRLF (\\r\\n)", "en": "CRLF (\\r\\n)"},
    "rxnl_raw":       {"ja": "そのまま", "en": "As-is"},
    "rxnl_cr_to_lf":  {"ja": "CR→LF変換", "en": "CR→LF"},
    "rxnl_strip_cr":  {"ja": "CR削除", "en": "Strip CR"},
    # --- ステータス ---
    "not_connected":  {"ja": "未接続", "en": "Not connected"},
    "st_open_fmt":    {"ja": "%s @ %s bps  接続中", "en": "%s @ %s bps  connected"},
    "st_saved":       {"ja": "保存しました: ", "en": "Saved: "},
    # --- メッセージボックス ---
    "mb_connect_title":    {"ja": "接続", "en": "Connect"},
    "mb_select_port":      {"ja": "ポートを選択してください。",
                            "en": "Please select a port."},
    "mb_conn_err_title":   {"ja": "接続エラー", "en": "Connection Error"},
    "mb_disconnect_title": {"ja": "切断", "en": "Disconnected"},
    "mb_conn_lost":        {"ja": "ポートとの接続が失われました。",
                            "en": "Connection to the port was lost."},
    "mb_confirm_title":    {"ja": "確認", "en": "Confirm"},
    "mb_close_confirm":    {"ja": "ポートが開いています。切断してタブを閉じますか?",
                            "en": "The port is open. Disconnect and close this tab?"},
    "mb_send_title":       {"ja": "送信", "en": "Send"},
    "mb_port_not_open":    {"ja": "ポートが開いていません。",
                            "en": "The port is not open."},
    "mb_send_err_title":   {"ja": "送信エラー", "en": "Send Error"},
    "mb_tx_data_err_title": {"ja": "送信データエラー", "en": "TX Data Error"},
    "mb_macro_err_title":  {"ja": "定型文エラー", "en": "Macro Error"},
    "mb_load_err_title":   {"ja": "読込エラー", "en": "Load Error"},
    "mb_save_title":       {"ja": "保存", "en": "Save"},
    "mb_no_data":          {"ja": "保存するデータがありません。",
                            "en": "No data to save."},
    "mb_no_log":           {"ja": "ログがありません。", "en": "No log entries."},
    "mb_clear_title":      {"ja": "クリア", "en": "Clear"},
    "mb_clear_buffers":    {"ja": "保存用の送受信バッファも消去しますか?",
                            "en": "Also clear the stored RX/TX buffers?"},
    "mb_enc_title":        {"ja": "エンコード", "en": "Encoding"},
    "mb_enc_unsupported":  {"ja": "未対応のエンコードです: ",
                            "en": "Unsupported encoding: "},
    "mb_log_title":        {"ja": "ログ", "en": "Log"},
    "err_input_title":     {"ja": "入力エラー", "en": "Input Error"},
    "err_name_required":   {"ja": "名前を入力してください。",
                            "en": "Please enter a name."},
    "err_hex_title":       {"ja": "HEXエラー", "en": "HEX Error"},
    "err_hex_odd":         {"ja": "HEX文字列の桁数が奇数です: %r",
                            "en": "Odd number of hex digits: %r"},
    "err_hex_invalid":     {"ja": "HEXとして解釈できない文字が含まれています: %r",
                            "en": "Contains characters that cannot be parsed as hex: %r"},
    "err_unprintable":     {"ja": "表示できない制御文字が含まれています: %r",
                            "en": "Contains non-printable control characters: %r"},
    "warn_convert_title":  {"ja": "形式変換", "en": "Format Conversion"},
    "warn_to_hex_failed":  {"ja": "HEXに変換できませんでした:\n",
                            "en": "Could not convert to HEX:\n"},
    "warn_to_ascii_failed": {"ja": "テキストに変換できませんでした:\n",
                             "en": "Could not convert to text:\n"},
    # --- ファイルダイアログのフィルタ名 ---
    "ft_json":  {"ja": "JSON", "en": "JSON"},
    "ft_all":   {"ja": "すべて", "en": "All files"},
    "ft_bin":   {"ja": "バイナリ", "en": "Binary"},
    "ft_txt":   {"ja": "テキスト", "en": "Text"},
    "ft_log":   {"ja": "ログ", "en": "Log"},
}

_current_lang = "ja"
_retranslate_callbacks = []     # 言語切替時に呼ぶコールバック


def get_language() -> str:
    return _current_lang


def set_language(lang: str):
    global _current_lang
    if lang not in LANGUAGES:
        raise ValueError("unsupported language: %r" % lang)
    _current_lang = lang


def tr(key: str) -> str:
    """翻訳キーから現在言語の文字列を返す。キー欠落時はキーをそのまま返す。"""
    entry = I18N.get(key)
    if entry is None:
        return key
    return entry[_current_lang]


def on_language_change(callback):
    """言語切替時に呼ばれるコールバックを登録する。"""
    _retranslate_callbacks.append(callback)


def retranslate_all():
    """登録済みコールバックを全実行。破棄済みウィジェット由来のものは除去。"""
    for cb in _retranslate_callbacks[:]:
        try:
            cb()
        except tk.TclError:
            _retranslate_callbacks.remove(cb)


def T(widget, key: str, option: str = "text"):
    """ウィジェットのオプションに tr(key) を設定し、言語切替に追従させる。"""
    def apply():
        widget.configure(**{option: tr(key)})
    apply()
    on_language_change(apply)
    return widget


def detect_default_language() -> str:
    """OSロケールが日本語なら ja、それ以外 (不明含む) は en。"""
    try:
        lang = locale.getlocale()[0]
    except ValueError:
        lang = None
    if lang and lang.lower().startswith("ja"):
        return "ja"
    return "en"


# ------------------------------------------------------------------ 設定 ----

def settings_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME",
                                   str(Path.home() / ".config")))
    return base / "serial-terminal" / "settings.json"


def load_settings() -> dict:
    try:
        with open(settings_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict):
    try:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ----------------------------------------------------------- ユーティリティ ----

def parse_hex(text: str) -> bytes:
    """'AA BB 0d,0x0A' のような文字列を bytes に変換する。"""
    cleaned = (text.replace("0x", " ").replace("0X", " ")
                   .replace(",", " ").replace(";", " "))
    cleaned = "".join(cleaned.split())
    if not cleaned:
        return b""
    if len(cleaned) % 2 != 0:
        raise ValueError(tr("err_hex_odd") % text)
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError(tr("err_hex_invalid") % text)


def ascii_to_hex_str(text: str, encoding: str = "utf-8") -> str:
    """テキストを '61 62 63' 形式のスペース区切り小文字HEXに変換する。

    エンコード不能な文字があれば UnicodeEncodeError を送出。
    """
    return " ".join("%02x" % b for b in text.encode(encoding, errors="strict"))


def hex_str_to_ascii(text: str, encoding: str = "utf-8") -> str:
    """HEX文字列をデコードしてテキストに変換する。

    不正なHEX・デコード不能・表示不能な制御文字 (\\t \\r \\n は許容) を
    含む場合は ValueError を送出。
    """
    data = parse_hex(text)
    try:
        decoded = data.decode(encoding, errors="strict")
    except (UnicodeDecodeError, LookupError) as e:
        raise ValueError(str(e))
    if any(ord(ch) < 0x20 and ch not in "\t\r\n" for ch in decoded):
        raise ValueError(tr("err_unprintable") % text)
    return decoded


def hexdump_lines(offset: int, data: bytes):
    """offset から始まる data を 16バイト/行 のHEXダンプ行リストにする。"""
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hexpart = " ".join("%02X" % b for b in chunk)
        hexpart = hexpart.ljust(16 * 3 - 1)
        asciipart = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in chunk)
        lines.append("%08X  %s  |%s|" % (offset + i, hexpart, asciipart))
    return lines


class NewlineFilter:
    """受信テキスト表示用の改行変換(チャンク分割されたCRLFにも対応)。

    mode は言語非依存コード: "raw" / "cr_to_lf" / "strip_cr"
    """

    def __init__(self):
        self.mode = "raw"
        self._pending_cr = False

    def reset(self):
        self._pending_cr = False

    def feed(self, text: str) -> str:
        if self.mode == "raw":
            return text
        if self._pending_cr:
            text = "\r" + text
            self._pending_cr = False
        if text.endswith("\r"):
            self._pending_cr = True
            text = text[:-1]
        if self.mode == "cr_to_lf":
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        elif self.mode == "strip_cr":
            text = text.replace("\r", "")
        return text

    def convert_all(self, text: str) -> str:
        """バッファ全体の再デコード用(ステートレス変換)。"""
        if self.mode == "cr_to_lf":
            return text.replace("\r\n", "\n").replace("\r", "\n")
        if self.mode == "strip_cr":
            return text.replace("\r", "")
        return text


# ------------------------------------------------------- 定型文編集ダイアログ ----

class MacroDialog(tk.Toplevel):
    """定型文の追加・編集用ダイアログ。"""

    def __init__(self, master, title_key="dlg_macro_edit", macro=None,
                 encoding="utf-8"):
        super().__init__(master)
        self.title(tr(title_key))
        self.resizable(True, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        self.encoding = encoding
        macro = macro or {"name": "", "mode": "ascii", "data": "", "ending": True}
        self._prev_mode = macro["mode"]

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text=tr("d_name")).grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value=macro["name"])
        ttk.Entry(frm, textvariable=self.name_var, width=32)\
            .grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(frm, text=tr("d_mode")).grid(row=1, column=0, sticky="w")
        self.mode_var = tk.StringVar(value=macro["mode"])
        mf = ttk.Frame(frm)
        mf.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(mf, text="ASCII", variable=self.mode_var,
                        value="ascii", command=self._mode_changed)\
            .pack(side="left")
        ttk.Radiobutton(mf, text="HEX", variable=self.mode_var,
                        value="hex", command=self._mode_changed)\
            .pack(side="left", padx=(8, 0))

        ttk.Label(frm, text=tr("d_data")).grid(row=2, column=0, sticky="nw", pady=(4, 0))
        self.data_text = tk.Text(frm, width=46, height=4, font=MONO_FONT)
        self.data_text.grid(row=2, column=1, sticky="ew", pady=(4, 0))
        self.data_text.insert("1.0", macro["data"])

        self.ending_var = tk.BooleanVar(value=macro.get("ending", True))
        ttk.Checkbutton(frm, text=tr("d_ending"),
                        variable=self.ending_var)\
            .grid(row=3, column=1, sticky="w", pady=(4, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text=tr("d_cancel"), command=self.destroy).pack(side="left")

        self.bind("<Escape>", lambda e: self.destroy())
        self.data_text.focus_set()

    def _mode_changed(self):
        """形式の切替時にデータ欄を ASCII↔HEX 相互変換する。

        変換できない場合はデータを変更せず、ラジオを元の形式に戻す。
        """
        new_mode = self.mode_var.get()
        if new_mode == self._prev_mode:
            return
        data = self.data_text.get("1.0", "end-1c")
        if not data:
            self._prev_mode = new_mode
            return
        try:
            if new_mode == "hex":
                converted = ascii_to_hex_str(data, self.encoding)
            else:
                converted = hex_str_to_ascii(data, self.encoding)
        except (ValueError, UnicodeEncodeError, LookupError) as e:
            key = ("warn_to_hex_failed" if new_mode == "hex"
                   else "warn_to_ascii_failed")
            messagebox.showwarning(tr("warn_convert_title"), tr(key) + str(e),
                                   parent=self)
            self.mode_var.set(self._prev_mode)
            return
        self.data_text.delete("1.0", "end")
        self.data_text.insert("1.0", converted)
        self._prev_mode = new_mode

    def _ok(self):
        name = self.name_var.get().strip()
        data = self.data_text.get("1.0", "end-1c")
        if not name:
            messagebox.showwarning(tr("err_input_title"), tr("err_name_required"),
                                   parent=self)
            return
        if self.mode_var.get() == "hex":
            try:
                parse_hex(data)
            except ValueError as e:
                messagebox.showerror(tr("err_hex_title"), str(e), parent=self)
                return
        self.result = {"name": name, "mode": self.mode_var.get(),
                       "data": data, "ending": self.ending_var.get()}
        self.destroy()


# -------------------------------------------------------------- ポートタブ ----

class PortTab(ttk.Frame):
    """1つのシリアルポートに対応するタブ。"""

    def __init__(self, notebook: ttk.Notebook, app):
        super().__init__(notebook)
        self.notebook = notebook
        self.app = app

        self.ser = None                       # serial.Serial
        self.reader_thread = None
        self.alive = False
        self.rx_queue = queue.Queue()

        self.rx_raw = bytearray()             # 受信生データ全保持
        self.tx_raw = bytearray()             # 送信生データ全保持
        self.session_log = []                 # (datetime, "RX"/"TX", bytes)
        self.rawlog_fp = None                 # 連続RAWログ用ファイル

        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.nl_filter = NewlineFilter()

        # HEXビュー描画状態
        self._hex_offset = 0                  # 完成行として描画済みのバイト数
        self._hex_pending = bytearray()       # 未完成行のバイト

        self._build_ui()
        self.refresh_ports()
        self.after(50, self._poll_rx)

    # ---------------------------------------------------------------- UI ----

    def _build_ui(self):
        # ---- 接続バー ----
        bar1 = ttk.Frame(self, padding=(6, 4))
        bar1.pack(fill="x")

        T(ttk.Label(bar1), "port").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cmb = ttk.Combobox(bar1, textvariable=self.port_var, width=22)
        self.port_cmb.pack(side="left", padx=(2, 2))
        T(ttk.Button(bar1, width=7, command=self.refresh_ports),
          "refresh").pack(side="left", padx=(0, 8))

        ttk.Label(bar1, text="Baud:").pack(side="left")
        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(bar1, textvariable=self.baud_var, values=BAUDRATES,
                     width=8).pack(side="left", padx=(2, 8))

        ttk.Label(bar1, text="Data:").pack(side="left")
        self.bits_var = tk.StringVar(value="8")
        ttk.Combobox(bar1, textvariable=self.bits_var, values=list(BYTESIZES),
                     width=3, state="readonly").pack(side="left", padx=(2, 8))

        ttk.Label(bar1, text="Parity:").pack(side="left")
        self.parity_var = tk.StringVar(value="None")
        ttk.Combobox(bar1, textvariable=self.parity_var, values=list(PARITIES),
                     width=5, state="readonly").pack(side="left", padx=(2, 8))

        ttk.Label(bar1, text="Stop:").pack(side="left")
        self.stop_var = tk.StringVar(value="1")
        ttk.Combobox(bar1, textvariable=self.stop_var, values=list(STOPBITS),
                     width=4, state="readonly").pack(side="left", padx=(2, 8))

        self.conn_btn = ttk.Button(bar1, width=10,
                                   command=self.toggle_connection)
        self.conn_btn.pack(side="left", padx=(4, 8))

        T(ttk.Button(bar1, command=self.close_tab), "close_tab").pack(side="right")

        # ---- 設定バー ----
        bar2 = ttk.Frame(self, padding=(6, 0))
        bar2.pack(fill="x")

        T(ttk.Label(bar2), "encoding").pack(side="left")
        self.enc_var = tk.StringVar(value="utf-8")
        enc_cmb = ttk.Combobox(bar2, textvariable=self.enc_var, values=ENCODINGS,
                               width=10, state="readonly")
        enc_cmb.pack(side="left", padx=(2, 8))
        enc_cmb.bind("<<ComboboxSelected>>", lambda e: self._change_encoding())

        # 送信改行 / 受信改行: 内部コードを保持し、表示文字列は言語切替で再生成する
        T(ttk.Label(bar2), "tx_eol").pack(side="left")
        self.tx_eol_code = "lf"
        self.tx_eol_var = tk.StringVar()
        self.tx_eol_combo = ttk.Combobox(bar2, textvariable=self.tx_eol_var,
                                         width=11, state="readonly")
        self.tx_eol_combo.pack(side="left", padx=(2, 8))
        self.tx_eol_combo.bind(
            "<<ComboboxSelected>>",
            lambda e: setattr(self, "tx_eol_code",
                              TX_EOL_CODES[self.tx_eol_combo.current()]))

        T(ttk.Label(bar2), "rx_nl").pack(side="left")
        self.rx_nl_var = tk.StringVar()
        self.rx_nl_combo = ttk.Combobox(bar2, textvariable=self.rx_nl_var,
                                        width=10, state="readonly")
        self.rx_nl_combo.pack(side="left", padx=(2, 8))
        self.rx_nl_combo.bind("<<ComboboxSelected>>",
                              lambda e: self._change_rx_newline())
        self._retranslate_combos()

        self.hexview_var = tk.BooleanVar(value=False)
        T(ttk.Checkbutton(bar2, variable=self.hexview_var,
                          command=self._toggle_hexview),
          "hexview").pack(side="left", padx=(0, 8))

        self.echo_var = tk.BooleanVar(value=False)
        T(ttk.Checkbutton(bar2, variable=self.echo_var),
          "local_echo").pack(side="left", padx=(0, 8))

        self.autoscroll_var = tk.BooleanVar(value=True)
        T(ttk.Checkbutton(bar2, variable=self.autoscroll_var),
          "autoscroll").pack(side="left", padx=(0, 8))

        T(ttk.Button(bar2, command=self.clear_views),
          "clear_view").pack(side="left", padx=(0, 8))

        # 保存メニュー
        save_mb = T(ttk.Menubutton(bar2), "save_menu")
        save_menu = tk.Menu(save_mb, tearoff=False)
        save_menu.add_command(command=lambda: self.save_data("rx", "bin"))
        save_menu.add_command(command=lambda: self.save_data("rx", "txt"))
        save_menu.add_separator()
        save_menu.add_command(command=lambda: self.save_data("tx", "bin"))
        save_menu.add_command(command=lambda: self.save_data("tx", "txt"))
        save_menu.add_separator()
        save_menu.add_command(command=self.save_session_log)
        save_menu.add_separator()
        self.rawlog_var = tk.BooleanVar(value=False)
        save_menu.add_checkbutton(variable=self.rawlog_var,
                                  command=self._toggle_rawlog)
        save_mb["menu"] = save_menu

        def relabel_save_menu():
            for index, key in ((0, "save_rx_bin"), (1, "save_rx_txt"),
                               (3, "save_tx_bin"), (4, "save_tx_txt"),
                               (6, "save_log"), (8, "rawlog")):
                save_menu.entryconfigure(index, label=tr(key))
        relabel_save_menu()
        on_language_change(relabel_save_menu)
        save_mb.pack(side="left")

        # ---- メイン領域: 左=送受信 / 右=定型文 ----
        hpane = ttk.PanedWindow(self, orient="horizontal")
        hpane.pack(fill="both", expand=True, padx=6, pady=4)

        left = ttk.Frame(hpane)
        hpane.add(left, weight=4)

        vpane = ttk.PanedWindow(left, orient="vertical")
        vpane.pack(fill="both", expand=True)

        # 受信エリア (ASCII | HEX)
        rx_frame = T(ttk.LabelFrame(vpane, padding=2), "rx_frame")
        vpane.add(rx_frame, weight=4)

        self.rx_pane = ttk.PanedWindow(rx_frame, orient="horizontal")
        self.rx_pane.pack(fill="both", expand=True)

        ascii_fr = ttk.Frame(self.rx_pane)
        self.rx_pane.add(ascii_fr, weight=3)
        self.rx_text = self._make_text(ascii_fr)

        self.hex_fr = ttk.Frame(self.rx_pane)      # HEXビュー(初期非表示)
        self.hex_text = self._make_text(self.hex_fr)

        # 送信エリア
        tx_frame = T(ttk.LabelFrame(vpane, padding=2), "tx_frame")
        vpane.add(tx_frame, weight=1)

        tx_top = ttk.Frame(tx_frame)
        tx_top.pack(fill="x")
        self.tx_mode_var = tk.StringVar(value="ascii")
        ttk.Radiobutton(tx_top, text="ASCII", variable=self.tx_mode_var,
                        value="ascii").pack(side="left")
        T(ttk.Radiobutton(tx_top, variable=self.tx_mode_var, value="hex"),
          "tx_hex_radio").pack(side="left", padx=(8, 0))
        T(ttk.Label(tx_top), "tx_hint").pack(side="left")
        T(ttk.Button(tx_top, width=10, command=self.send_from_entry),
          "send").pack(side="right")

        self.tx_text = tk.Text(tx_frame, height=3, font=MONO_FONT,
                               undo=True, wrap="char")
        self.tx_text.pack(fill="both", expand=True, pady=(2, 0))
        self.tx_text.bind("<Control-Return>",
                          lambda e: (self.send_from_entry(), "break")[1])

        # 定型文エリア
        macro_frame = T(ttk.LabelFrame(hpane, padding=2), "macro_frame")
        hpane.add(macro_frame, weight=2)

        cols = ("mode", "data")
        self.macro_tree = ttk.Treeview(macro_frame, columns=cols, height=8)

        def relabel_macro_headings():
            self.macro_tree.heading("#0", text=tr("m_name"))
            self.macro_tree.heading("mode", text=tr("m_mode"))
            self.macro_tree.heading("data", text=tr("m_data"))
        relabel_macro_headings()
        on_language_change(relabel_macro_headings)

        self.macro_tree.column("#0", width=110)
        self.macro_tree.column("mode", width=50, anchor="center")
        self.macro_tree.column("data", width=160)
        self.macro_tree.pack(fill="both", expand=True)
        self.macro_tree.bind("<Double-1>", lambda e: self.send_macro())

        mb = ttk.Frame(macro_frame)
        mb.pack(fill="x", pady=(2, 0))
        for key, cmd in (("send", self.send_macro),
                         ("m_add", self.add_macro),
                         ("m_edit", self.edit_macro),
                         ("m_delete", self.delete_macro),
                         ("m_load", self.load_macros),
                         ("m_save", self.save_macros)):
            T(ttk.Button(mb, width=7, command=cmd), key).pack(side="left", padx=1)

        self.macros = []      # [{name, mode, data, ending}, ...]

        # ---- ステータスバー ----
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, anchor="w",
                  relief="sunken", padding=(6, 2)).pack(fill="x", side="bottom")

        # 言語切替時に動的テキスト (接続ボタン・タブ名・ステータス) を更新
        self._retranslate_dynamic()
        on_language_change(self._retranslate)

    def _retranslate_combos(self):
        """送信改行/受信改行コンボの選択肢と現在値を現在言語で再生成する。"""
        self.tx_eol_combo["values"] = [tr("eol_" + c) for c in TX_EOL_CODES]
        self.tx_eol_var.set(tr("eol_" + self.tx_eol_code))
        self.rx_nl_combo["values"] = [tr("rxnl_" + c) for c in RX_NEWLINE_CODES]
        self.rx_nl_var.set(tr("rxnl_" + self.nl_filter.mode))

    def _retranslate_dynamic(self):
        connected = bool(self.ser and self.ser.is_open)
        self.conn_btn.config(text=tr("disconnect" if connected else "connect"))
        if not connected:
            try:
                self.notebook.tab(self, text=tr("not_connected"))
            except tk.TclError:
                pass        # まだ notebook に追加されていない
        self._update_status()

    def _retranslate(self):
        self._retranslate_combos()
        self._retranslate_dynamic()

    def _make_text(self, parent):
        fr = ttk.Frame(parent)
        fr.pack(fill="both", expand=True)
        txt = tk.Text(fr, font=MONO_FONT, wrap="char", state="disabled",
                      background="#1e1e1e", foreground="#d4d4d4",
                      insertbackground="#d4d4d4")
        ys = ttk.Scrollbar(fr, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=ys.set)
        txt.tag_configure("tx", foreground="#6fc36f")     # ローカルエコー用
        txt.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        return txt

    # ----------------------------------------------------------- ポート ----

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cmb["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def toggle_connection(self):
        if self.ser and self.ser.is_open:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning(tr("mb_connect_title"), tr("mb_select_port"),
                                   parent=self)
            return
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=int(self.baud_var.get()),
                bytesize=BYTESIZES[self.bits_var.get()],
                parity=PARITIES[self.parity_var.get()],
                stopbits=STOPBITS[self.stop_var.get()],
                timeout=0.1,
            )
        except (serial.SerialException, ValueError, OSError) as e:
            messagebox.showerror(tr("mb_conn_err_title"), str(e), parent=self)
            self.ser = None
            return
        self.alive = True
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()
        self.conn_btn.config(text=tr("disconnect"))
        self.notebook.tab(self, text=port)
        self._update_status()

    def disconnect(self):
        self.alive = False
        if self.reader_thread:
            self.reader_thread.join(timeout=1.0)
            self.reader_thread = None
        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None
        self.conn_btn.config(text=tr("connect"))
        self._update_status()

    def close_tab(self):
        if self.ser and self.ser.is_open:
            if not messagebox.askokcancel(
                    tr("mb_confirm_title"), tr("mb_close_confirm"),
                    parent=self):
                return
        self.disconnect()
        self._toggle_rawlog_off()
        self.app.remove_tab(self)

    def _reader(self):
        """受信スレッド: シリアルから読み出してキューへ。"""
        while self.alive and self.ser:
            try:
                n = self.ser.in_waiting
                data = self.ser.read(n if n else 1)
            except (serial.SerialException, OSError):
                self.rx_queue.put(None)         # 切断シグナル
                break
            if data:
                self.rx_queue.put(bytes(data))

    def _poll_rx(self):
        """UIスレッド: 受信キューを処理。"""
        disconnected = False
        try:
            while True:
                data = self.rx_queue.get_nowait()
                if data is None:
                    disconnected = True
                    break
                self._handle_rx(data)
        except queue.Empty:
            pass
        if disconnected:
            self.disconnect()
            messagebox.showwarning(tr("mb_disconnect_title"),
                                   tr("mb_conn_lost"), parent=self)
        self.after(50, self._poll_rx)

    # ----------------------------------------------------------- 受信処理 ----

    def _handle_rx(self, data: bytes):
        self.rx_raw.extend(data)
        self.session_log.append((datetime.now(), "RX", data))
        if self.rawlog_fp:
            try:
                self.rawlog_fp.write(data)
                self.rawlog_fp.flush()
            except OSError:
                pass

        # ASCIIビュー (インクリメンタルデコード + 改行フィルタ)
        text = self.decoder.decode(data)
        text = self.nl_filter.feed(text)
        if text:
            self._append_text(self.rx_text, text)

        # HEXビュー
        if self.hexview_var.get():
            self._append_hex(data)
        self._update_status()

    def _append_text(self, widget, text, tag=None):
        widget.config(state="normal")
        if tag:
            widget.insert("end", text, tag)
        else:
            widget.insert("end", text)
        widget.config(state="disabled")
        if self.autoscroll_var.get():
            widget.see("end")

    def _append_hex(self, data: bytes):
        """HEXダンプを差分描画(未完成行は毎回描き直す)。"""
        self._hex_pending.extend(data)
        full_len = len(self._hex_pending) // 16 * 16
        full, rest = self._hex_pending[:full_len], self._hex_pending[full_len:]

        self.hex_text.config(state="normal")
        # 前回の未完成行を削除
        try:
            self.hex_text.delete("partial", "end-1c")
        except tk.TclError:
            pass
        if full:
            for line in hexdump_lines(self._hex_offset, bytes(full)):
                self.hex_text.insert("end", line + "\n")
            self._hex_offset += full_len
            self._hex_pending = bytearray(rest)
        # 未完成行を partial マーク付きで描画
        self.hex_text.mark_set("partial", "end-1c")
        self.hex_text.mark_gravity("partial", "left")
        if self._hex_pending:
            line = hexdump_lines(self._hex_offset, bytes(self._hex_pending))[0]
            self.hex_text.insert("end", line)
        self.hex_text.config(state="disabled")
        if self.autoscroll_var.get():
            self.hex_text.see("end")

    def _rebuild_hexview(self):
        """rx_raw 全体からHEXビューを再構築。"""
        self.hex_text.config(state="normal")
        self.hex_text.delete("1.0", "end")
        self.hex_text.config(state="disabled")
        self._hex_offset = 0
        self._hex_pending = bytearray()
        if self.rx_raw:
            self._append_hex(bytes(self.rx_raw))
            # _append_hex は pending に積み直すので空にしてオフセット調整
            # (上の呼び出しで全データが描画済み)

    def _toggle_hexview(self):
        if self.hexview_var.get():
            self.rx_pane.add(self.hex_fr, weight=2)
            self._rebuild_hexview()
        else:
            self.rx_pane.forget(self.hex_fr)

    def _change_encoding(self):
        """エンコード変更時: 受信バッファ全体を再デコードして表示し直す。"""
        enc = self.enc_var.get()
        try:
            self.decoder = codecs.getincrementaldecoder(enc)(errors="replace")
        except LookupError:
            messagebox.showerror(tr("mb_enc_title"),
                                 tr("mb_enc_unsupported") + enc, parent=self)
            return
        self.nl_filter.reset()
        text = self.rx_raw.decode(enc, errors="replace")
        text = self.nl_filter.convert_all(text)
        self.rx_text.config(state="normal")
        self.rx_text.delete("1.0", "end")
        self.rx_text.insert("end", text)
        self.rx_text.config(state="disabled")
        if self.autoscroll_var.get():
            self.rx_text.see("end")

    def _change_rx_newline(self):
        self.nl_filter.mode = RX_NEWLINE_CODES[self.rx_nl_combo.current()]
        self._change_encoding()      # 表示を作り直す

    def clear_views(self):
        for w in (self.rx_text, self.hex_text):
            w.config(state="normal")
            w.delete("1.0", "end")
            w.config(state="disabled")
        self._hex_offset = 0
        self._hex_pending = bytearray()
        # 表示のみクリア。保存用バッファも消す場合は確認
        if self.rx_raw or self.tx_raw:
            if messagebox.askyesno(tr("mb_clear_title"),
                                   tr("mb_clear_buffers"),
                                   parent=self):
                self.rx_raw = bytearray()
                self.tx_raw = bytearray()
                self.session_log = []
        self._update_status()

    # ----------------------------------------------------------- 送信処理 ----

    def _send_bytes(self, payload: bytes):
        if not (self.ser and self.ser.is_open):
            messagebox.showwarning(tr("mb_send_title"), tr("mb_port_not_open"),
                                   parent=self)
            return False
        try:
            self.ser.write(payload)
        except (serial.SerialException, OSError) as e:
            messagebox.showerror(tr("mb_send_err_title"), str(e), parent=self)
            return False
        self.tx_raw.extend(payload)
        self.session_log.append((datetime.now(), "TX", payload))
        if self.echo_var.get():
            try:
                shown = payload.decode(self.enc_var.get(), errors="replace")
            except LookupError:
                shown = repr(payload)
            self._append_text(self.rx_text, shown, tag="tx")
            if self.hexview_var.get():
                self._append_text(
                    self.hex_text,
                    "\nTX> " + " ".join("%02X" % b for b in payload) + "\n",
                    tag="tx")
        self._update_status()
        return True

    def _build_payload(self, mode, data, append_ending=True):
        if mode == "hex":
            return parse_hex(data)
        payload = data.encode(self.enc_var.get(), errors="strict")
        if append_ending:
            payload += TX_EOL_BYTES[self.tx_eol_code]
        return payload

    def send_from_entry(self):
        data = self.tx_text.get("1.0", "end-1c")
        mode = self.tx_mode_var.get()
        if not data:
            return
        try:
            payload = self._build_payload(mode, data)
        except (ValueError, UnicodeEncodeError, LookupError) as e:
            messagebox.showerror(tr("mb_tx_data_err_title"), str(e), parent=self)
            return
        if self._send_bytes(payload):
            self.tx_text.delete("1.0", "end")

    # ------------------------------------------------------------- 定型文 ----

    def _selected_macro_index(self):
        sel = self.macro_tree.selection()
        if not sel:
            return None
        return self.macro_tree.index(sel[0])

    def _refresh_macro_tree(self):
        self.macro_tree.delete(*self.macro_tree.get_children())
        for m in self.macros:
            preview = m["data"].replace("\n", "⏎")
            if len(preview) > 40:
                preview = preview[:40] + "…"
            self.macro_tree.insert("", "end", text=m["name"],
                                   values=(m["mode"].upper(), preview))

    def add_macro(self):
        dlg = MacroDialog(self, "dlg_macro_add", encoding=self.enc_var.get())
        self.wait_window(dlg)
        if dlg.result:
            self.macros.append(dlg.result)
            self._refresh_macro_tree()

    def edit_macro(self):
        idx = self._selected_macro_index()
        if idx is None:
            return
        dlg = MacroDialog(self, "dlg_macro_edit", self.macros[idx],
                          encoding=self.enc_var.get())
        self.wait_window(dlg)
        if dlg.result:
            self.macros[idx] = dlg.result
            self._refresh_macro_tree()

    def delete_macro(self):
        idx = self._selected_macro_index()
        if idx is None:
            return
        del self.macros[idx]
        self._refresh_macro_tree()

    def send_macro(self):
        idx = self._selected_macro_index()
        if idx is None:
            return
        m = self.macros[idx]
        try:
            payload = self._build_payload(m["mode"], m["data"],
                                          append_ending=m.get("ending", True))
        except (ValueError, UnicodeEncodeError, LookupError) as e:
            messagebox.showerror(tr("mb_macro_err_title"), str(e), parent=self)
            return
        self._send_bytes(payload)

    def save_macros(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".json",
            filetypes=[(tr("ft_json"), "*.json"), (tr("ft_all"), "*.*")],
            initialfile="macros.json")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.macros, f, ensure_ascii=False, indent=2)

    def load_macros(self):
        path = filedialog.askopenfilename(
            parent=self, filetypes=[(tr("ft_json"), "*.json"),
                                    (tr("ft_all"), "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                macros = json.load(f)
            assert isinstance(macros, list)
        except Exception as e:
            messagebox.showerror(tr("mb_load_err_title"), str(e), parent=self)
            return
        self.macros = macros
        self._refresh_macro_tree()

    # --------------------------------------------------------------- 保存 ----

    def save_data(self, direction, fmt):
        buf = self.rx_raw if direction == "rx" else self.tx_raw
        if not buf:
            messagebox.showinfo(tr("mb_save_title"), tr("mb_no_data"),
                                parent=self)
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "bin":
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".bin",
                filetypes=[(tr("ft_bin"), "*.bin"), (tr("ft_all"), "*.*")],
                initialfile="%s_%s.bin" % (direction, stamp))
            if not path:
                return
            with open(path, "wb") as f:
                f.write(buf)
        else:
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".txt",
                filetypes=[(tr("ft_txt"), "*.txt"), (tr("ft_all"), "*.*")],
                initialfile="%s_%s.txt" % (direction, stamp))
            if not path:
                return
            text = buf.decode(self.enc_var.get(), errors="replace")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        self.status_var.set(tr("st_saved") + path)

    def save_session_log(self):
        if not self.session_log:
            messagebox.showinfo(tr("mb_save_title"), tr("mb_no_log"),
                                parent=self)
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".log",
            filetypes=[(tr("ft_log"), "*.log"), (tr("ft_all"), "*.*")],
            initialfile="session_%s.log" % stamp)
        if not path:
            return
        enc = self.enc_var.get()
        with open(path, "w", encoding="utf-8") as f:
            for ts, d, data in self.session_log:
                hexs = " ".join("%02X" % b for b in data)
                asc = data.decode(enc, errors="replace")\
                          .replace("\r", "\\r").replace("\n", "\\n")
                f.write("%s  %s  [%s]  %s\n"
                        % (ts.strftime("%H:%M:%S.%f")[:-3], d, hexs, asc))
        self.status_var.set("保存しました: " + path)

    def _toggle_rawlog(self):
        if self.rawlog_var.get():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".bin",
                filetypes=[(tr("ft_bin"), "*.bin"), (tr("ft_all"), "*.*")],
                initialfile="rxlog_%s.bin" % stamp)
            if not path:
                self.rawlog_var.set(False)
                return
            try:
                self.rawlog_fp = open(path, "ab")
            except OSError as e:
                messagebox.showerror(tr("mb_log_title"), str(e), parent=self)
                self.rawlog_var.set(False)
        else:
            self._toggle_rawlog_off()

    def _toggle_rawlog_off(self):
        if self.rawlog_fp:
            try:
                self.rawlog_fp.close()
            except OSError:
                pass
            self.rawlog_fp = None
        self.rawlog_var.set(False)

    # --------------------------------------------------------------- 状態 ----

    def _update_status(self):
        if self.ser and self.ser.is_open:
            s = tr("st_open_fmt") % (self.ser.port, self.ser.baudrate)
        else:
            s = tr("not_connected")
        self.status_var.set("%s | RX: %d bytes  TX: %d bytes"
                            % (s, len(self.rx_raw), len(self.tx_raw)))


# ------------------------------------------------------------ アプリ本体 ----

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Serial Binary/ASCII Terminal")
        self.geometry("1100x680")
        self.minsize(820, 480)

        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(fill="x")
        T(ttk.Button(bar, command=self.add_tab), "add_tab").pack(side="left")
        T(ttk.Label(bar), "tab_hint").pack(side="left")

        # 言語切替 (右端)。各言語名はその言語で表記するため翻訳しない
        self._lang_names = ["日本語", "English"]
        self.lang_var = tk.StringVar(
            value=self._lang_names[LANGUAGES.index(get_language())])
        lang_cmb = ttk.Combobox(bar, textvariable=self.lang_var,
                                values=self._lang_names, width=8,
                                state="readonly")
        lang_cmb.pack(side="right")
        lang_cmb.bind("<<ComboboxSelected>>",
                      lambda e: self.switch_language(
                          LANGUAGES[lang_cmb.current()]))
        T(ttk.Label(bar), "lang_label").pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.add_tab()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def switch_language(self, lang: str):
        if lang == get_language():
            return
        set_language(lang)
        settings = load_settings()
        settings["language"] = lang
        save_settings(settings)
        self.lang_var.set(self._lang_names[LANGUAGES.index(lang)])
        retranslate_all()

    def add_tab(self):
        tab = PortTab(self.notebook, self)
        self.notebook.add(tab, text=tr("not_connected"))
        self.notebook.select(tab)

    def remove_tab(self, tab):
        self.notebook.forget(tab)
        tab.destroy()
        if not self.notebook.tabs():
            self.add_tab()

    def on_close(self):
        for tab_id in self.notebook.tabs():
            tab = self.nametowidget(tab_id)
            if isinstance(tab, PortTab):
                tab.disconnect()
                tab._toggle_rawlog_off()
        self.destroy()


def main():
    lang = load_settings().get("language")
    if lang not in LANGUAGES:
        lang = detect_default_language()
    set_language(lang)
    App().mainloop()


if __name__ == "__main__":
    main()
