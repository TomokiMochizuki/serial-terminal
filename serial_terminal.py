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
import queue
import threading
from datetime import datetime

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

LINE_ENDINGS = {            # 送信時に付加する改行
    "なし":          b"",
    "LF (\\n)":      b"\n",
    "CR (\\r)":      b"\r",
    "CRLF (\\r\\n)": b"\r\n",
}

RX_NEWLINE_MODES = ["そのまま", "CR→LF変換", "CR削除"]   # 受信表示時の改行の扱い

PARITIES  = {"None": serial.PARITY_NONE,
             "Even": serial.PARITY_EVEN,
             "Odd":  serial.PARITY_ODD}
STOPBITS  = {"1": serial.STOPBITS_ONE,
             "1.5": serial.STOPBITS_ONE_POINT_FIVE,
             "2": serial.STOPBITS_TWO}
BYTESIZES = {"8": serial.EIGHTBITS, "7": serial.SEVENBITS,
             "6": serial.SIXBITS,  "5": serial.FIVEBITS}

MONO_FONT = ("Consolas", 10) if tk.TkVersion else ("Courier", 10)


# ----------------------------------------------------------- ユーティリティ ----

def parse_hex(text: str) -> bytes:
    """'AA BB 0d,0x0A' のような文字列を bytes に変換する。"""
    cleaned = (text.replace("0x", " ").replace("0X", " ")
                   .replace(",", " ").replace(";", " "))
    cleaned = "".join(cleaned.split())
    if not cleaned:
        return b""
    if len(cleaned) % 2 != 0:
        raise ValueError("HEX文字列の桁数が奇数です: %r" % text)
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        raise ValueError("HEXとして解釈できない文字が含まれています: %r" % text)


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
    """受信テキスト表示用の改行変換(チャンク分割されたCRLFにも対応)。"""

    def __init__(self):
        self.mode = "そのまま"
        self._pending_cr = False

    def reset(self):
        self._pending_cr = False

    def feed(self, text: str) -> str:
        if self.mode == "そのまま":
            return text
        if self._pending_cr:
            text = "\r" + text
            self._pending_cr = False
        if text.endswith("\r"):
            self._pending_cr = True
            text = text[:-1]
        if self.mode == "CR→LF変換":
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        elif self.mode == "CR削除":
            text = text.replace("\r", "")
        return text

    def convert_all(self, text: str) -> str:
        """バッファ全体の再デコード用(ステートレス変換)。"""
        if self.mode == "CR→LF変換":
            return text.replace("\r\n", "\n").replace("\r", "\n")
        if self.mode == "CR削除":
            return text.replace("\r", "")
        return text


# ------------------------------------------------------- 定型文編集ダイアログ ----

class MacroDialog(tk.Toplevel):
    """定型文の追加・編集用ダイアログ。"""

    def __init__(self, master, title="定型文の編集", macro=None):
        super().__init__(master)
        self.title(title)
        self.resizable(True, False)
        self.transient(master)
        self.grab_set()
        self.result = None
        macro = macro or {"name": "", "mode": "ascii", "data": "", "ending": True}

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="名前:").grid(row=0, column=0, sticky="w")
        self.name_var = tk.StringVar(value=macro["name"])
        ttk.Entry(frm, textvariable=self.name_var, width=32)\
            .grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(frm, text="形式:").grid(row=1, column=0, sticky="w")
        self.mode_var = tk.StringVar(value=macro["mode"])
        mf = ttk.Frame(frm)
        mf.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(mf, text="ASCII", variable=self.mode_var,
                        value="ascii").pack(side="left")
        ttk.Radiobutton(mf, text="HEX", variable=self.mode_var,
                        value="hex").pack(side="left", padx=(8, 0))

        ttk.Label(frm, text="データ:").grid(row=2, column=0, sticky="nw", pady=(4, 0))
        self.data_text = tk.Text(frm, width=46, height=4, font=MONO_FONT)
        self.data_text.grid(row=2, column=1, sticky="ew", pady=(4, 0))
        self.data_text.insert("1.0", macro["data"])

        self.ending_var = tk.BooleanVar(value=macro.get("ending", True))
        ttk.Checkbutton(frm, text="送信時に改行設定を付加する (ASCIIのみ有効)",
                        variable=self.ending_var)\
            .grid(row=3, column=1, sticky="w", pady=(4, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=4, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="OK", command=self._ok).pack(side="left", padx=4)
        ttk.Button(btns, text="キャンセル", command=self.destroy).pack(side="left")

        self.bind("<Escape>", lambda e: self.destroy())
        self.data_text.focus_set()

    def _ok(self):
        name = self.name_var.get().strip()
        data = self.data_text.get("1.0", "end-1c")
        if not name:
            messagebox.showwarning("入力エラー", "名前を入力してください。", parent=self)
            return
        if self.mode_var.get() == "hex":
            try:
                parse_hex(data)
            except ValueError as e:
                messagebox.showerror("HEXエラー", str(e), parent=self)
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

        ttk.Label(bar1, text="ポート:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cmb = ttk.Combobox(bar1, textvariable=self.port_var, width=22)
        self.port_cmb.pack(side="left", padx=(2, 2))
        ttk.Button(bar1, text="更新", width=5,
                   command=self.refresh_ports).pack(side="left", padx=(0, 8))

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

        self.conn_btn = ttk.Button(bar1, text="接続", width=8,
                                   command=self.toggle_connection)
        self.conn_btn.pack(side="left", padx=(4, 8))

        ttk.Button(bar1, text="タブを閉じる", command=self.close_tab)\
            .pack(side="right")

        # ---- 設定バー ----
        bar2 = ttk.Frame(self, padding=(6, 0))
        bar2.pack(fill="x")

        ttk.Label(bar2, text="エンコード:").pack(side="left")
        self.enc_var = tk.StringVar(value="utf-8")
        enc_cmb = ttk.Combobox(bar2, textvariable=self.enc_var, values=ENCODINGS,
                               width=10, state="readonly")
        enc_cmb.pack(side="left", padx=(2, 8))
        enc_cmb.bind("<<ComboboxSelected>>", lambda e: self._change_encoding())

        ttk.Label(bar2, text="送信改行:").pack(side="left")
        self.tx_eol_var = tk.StringVar(value="LF (\\n)")
        ttk.Combobox(bar2, textvariable=self.tx_eol_var,
                     values=list(LINE_ENDINGS), width=11, state="readonly")\
            .pack(side="left", padx=(2, 8))

        ttk.Label(bar2, text="受信改行:").pack(side="left")
        self.rx_nl_var = tk.StringVar(value="そのまま")
        rxnl = ttk.Combobox(bar2, textvariable=self.rx_nl_var,
                            values=RX_NEWLINE_MODES, width=10, state="readonly")
        rxnl.pack(side="left", padx=(2, 8))
        rxnl.bind("<<ComboboxSelected>>", lambda e: self._change_rx_newline())

        self.hexview_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text="バイナリ(HEX)ビュー", variable=self.hexview_var,
                        command=self._toggle_hexview).pack(side="left", padx=(0, 8))

        self.echo_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text="ローカルエコー",
                        variable=self.echo_var).pack(side="left", padx=(0, 8))

        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar2, text="自動スクロール",
                        variable=self.autoscroll_var).pack(side="left", padx=(0, 8))

        ttk.Button(bar2, text="表示クリア", command=self.clear_views)\
            .pack(side="left", padx=(0, 8))

        # 保存メニュー
        save_mb = ttk.Menubutton(bar2, text="保存 ▾")
        save_menu = tk.Menu(save_mb, tearoff=False)
        save_menu.add_command(label="受信データをバイナリ保存 (.bin)",
                              command=lambda: self.save_data("rx", "bin"))
        save_menu.add_command(label="受信データをテキスト保存 (現在のエンコード)",
                              command=lambda: self.save_data("rx", "txt"))
        save_menu.add_separator()
        save_menu.add_command(label="送信データをバイナリ保存 (.bin)",
                              command=lambda: self.save_data("tx", "bin"))
        save_menu.add_command(label="送信データをテキスト保存",
                              command=lambda: self.save_data("tx", "txt"))
        save_menu.add_separator()
        save_menu.add_command(label="送受信ログ保存 (時刻+方向+HEX+ASCII)",
                              command=self.save_session_log)
        save_menu.add_separator()
        self.rawlog_var = tk.BooleanVar(value=False)
        save_menu.add_checkbutton(label="受信RAWを連続ログ (ファイルへ逐次追記)",
                                  variable=self.rawlog_var,
                                  command=self._toggle_rawlog)
        save_mb["menu"] = save_menu
        save_mb.pack(side="left")

        # ---- メイン領域: 左=送受信 / 右=定型文 ----
        hpane = ttk.PanedWindow(self, orient="horizontal")
        hpane.pack(fill="both", expand=True, padx=6, pady=4)

        left = ttk.Frame(hpane)
        hpane.add(left, weight=4)

        vpane = ttk.PanedWindow(left, orient="vertical")
        vpane.pack(fill="both", expand=True)

        # 受信エリア (ASCII | HEX)
        rx_frame = ttk.LabelFrame(vpane, text="受信", padding=2)
        vpane.add(rx_frame, weight=4)

        self.rx_pane = ttk.PanedWindow(rx_frame, orient="horizontal")
        self.rx_pane.pack(fill="both", expand=True)

        ascii_fr = ttk.Frame(self.rx_pane)
        self.rx_pane.add(ascii_fr, weight=3)
        self.rx_text = self._make_text(ascii_fr)

        self.hex_fr = ttk.Frame(self.rx_pane)      # HEXビュー(初期非表示)
        self.hex_text = self._make_text(self.hex_fr)

        # 送信エリア
        tx_frame = ttk.LabelFrame(vpane, text="送信", padding=2)
        vpane.add(tx_frame, weight=1)

        tx_top = ttk.Frame(tx_frame)
        tx_top.pack(fill="x")
        self.tx_mode_var = tk.StringVar(value="ascii")
        ttk.Radiobutton(tx_top, text="ASCII", variable=self.tx_mode_var,
                        value="ascii").pack(side="left")
        ttk.Radiobutton(tx_top, text="HEX (例: AA BB 0D 0A)",
                        variable=self.tx_mode_var, value="hex")\
            .pack(side="left", padx=(8, 0))
        ttk.Label(tx_top, text="  Ctrl+Enterで送信").pack(side="left")
        ttk.Button(tx_top, text="送信", width=10,
                   command=self.send_from_entry).pack(side="right")

        self.tx_text = tk.Text(tx_frame, height=3, font=MONO_FONT,
                               undo=True, wrap="char")
        self.tx_text.pack(fill="both", expand=True, pady=(2, 0))
        self.tx_text.bind("<Control-Return>",
                          lambda e: (self.send_from_entry(), "break")[1])

        # 定型文エリア
        macro_frame = ttk.LabelFrame(hpane, text="定型文 (ダブルクリックで送信)",
                                     padding=2)
        hpane.add(macro_frame, weight=2)

        cols = ("mode", "data")
        self.macro_tree = ttk.Treeview(macro_frame, columns=cols, height=8)
        self.macro_tree.heading("#0", text="名前")
        self.macro_tree.heading("mode", text="形式")
        self.macro_tree.heading("data", text="データ")
        self.macro_tree.column("#0", width=110)
        self.macro_tree.column("mode", width=50, anchor="center")
        self.macro_tree.column("data", width=160)
        self.macro_tree.pack(fill="both", expand=True)
        self.macro_tree.bind("<Double-1>", lambda e: self.send_macro())

        mb = ttk.Frame(macro_frame)
        mb.pack(fill="x", pady=(2, 0))
        for text, cmd in (("送信", self.send_macro),
                          ("追加", self.add_macro),
                          ("編集", self.edit_macro),
                          ("削除", self.delete_macro),
                          ("読込", self.load_macros),
                          ("保存", self.save_macros)):
            ttk.Button(mb, text=text, width=5, command=cmd)\
                .pack(side="left", padx=1)

        self.macros = []      # [{name, mode, data, ending}, ...]

        # ---- ステータスバー ----
        self.status_var = tk.StringVar(value="未接続")
        ttk.Label(self, textvariable=self.status_var, anchor="w",
                  relief="sunken", padding=(6, 2)).pack(fill="x", side="bottom")

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
            messagebox.showwarning("接続", "ポートを選択してください。", parent=self)
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
            messagebox.showerror("接続エラー", str(e), parent=self)
            self.ser = None
            return
        self.alive = True
        self.reader_thread = threading.Thread(target=self._reader, daemon=True)
        self.reader_thread.start()
        self.conn_btn.config(text="切断")
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
        self.conn_btn.config(text="接続")
        self._update_status()

    def close_tab(self):
        if self.ser and self.ser.is_open:
            if not messagebox.askokcancel(
                    "確認", "ポートが開いています。切断してタブを閉じますか?",
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
            messagebox.showwarning("切断",
                                   "ポートとの接続が失われました。", parent=self)
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
            messagebox.showerror("エンコード", "未対応のエンコードです: " + enc,
                                 parent=self)
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
        self.nl_filter.mode = self.rx_nl_var.get()
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
            if messagebox.askyesno("クリア",
                                   "保存用の送受信バッファも消去しますか?",
                                   parent=self):
                self.rx_raw = bytearray()
                self.tx_raw = bytearray()
                self.session_log = []
        self._update_status()

    # ----------------------------------------------------------- 送信処理 ----

    def _send_bytes(self, payload: bytes):
        if not (self.ser and self.ser.is_open):
            messagebox.showwarning("送信", "ポートが開いていません。", parent=self)
            return False
        try:
            self.ser.write(payload)
        except (serial.SerialException, OSError) as e:
            messagebox.showerror("送信エラー", str(e), parent=self)
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
            payload += LINE_ENDINGS[self.tx_eol_var.get()]
        return payload

    def send_from_entry(self):
        data = self.tx_text.get("1.0", "end-1c")
        mode = self.tx_mode_var.get()
        if not data:
            return
        try:
            payload = self._build_payload(mode, data)
        except (ValueError, UnicodeEncodeError, LookupError) as e:
            messagebox.showerror("送信データエラー", str(e), parent=self)
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
        dlg = MacroDialog(self, "定型文の追加")
        self.wait_window(dlg)
        if dlg.result:
            self.macros.append(dlg.result)
            self._refresh_macro_tree()

    def edit_macro(self):
        idx = self._selected_macro_index()
        if idx is None:
            return
        dlg = MacroDialog(self, "定型文の編集", self.macros[idx])
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
            messagebox.showerror("定型文エラー", str(e), parent=self)
            return
        self._send_bytes(payload)

    def save_macros(self):
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("すべて", "*.*")],
            initialfile="macros.json")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.macros, f, ensure_ascii=False, indent=2)

    def load_macros(self):
        path = filedialog.askopenfilename(
            parent=self, filetypes=[("JSON", "*.json"), ("すべて", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                macros = json.load(f)
            assert isinstance(macros, list)
        except Exception as e:
            messagebox.showerror("読込エラー", str(e), parent=self)
            return
        self.macros = macros
        self._refresh_macro_tree()

    # --------------------------------------------------------------- 保存 ----

    def save_data(self, direction, fmt):
        buf = self.rx_raw if direction == "rx" else self.tx_raw
        if not buf:
            messagebox.showinfo("保存", "保存するデータがありません。", parent=self)
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "bin":
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".bin",
                filetypes=[("バイナリ", "*.bin"), ("すべて", "*.*")],
                initialfile="%s_%s.bin" % (direction, stamp))
            if not path:
                return
            with open(path, "wb") as f:
                f.write(buf)
        else:
            path = filedialog.asksaveasfilename(
                parent=self, defaultextension=".txt",
                filetypes=[("テキスト", "*.txt"), ("すべて", "*.*")],
                initialfile="%s_%s.txt" % (direction, stamp))
            if not path:
                return
            text = buf.decode(self.enc_var.get(), errors="replace")
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(text)
        self.status_var.set("保存しました: " + path)

    def save_session_log(self):
        if not self.session_log:
            messagebox.showinfo("保存", "ログがありません。", parent=self)
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            parent=self, defaultextension=".log",
            filetypes=[("ログ", "*.log"), ("すべて", "*.*")],
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
                filetypes=[("バイナリ", "*.bin"), ("すべて", "*.*")],
                initialfile="rxlog_%s.bin" % stamp)
            if not path:
                self.rawlog_var.set(False)
                return
            try:
                self.rawlog_fp = open(path, "ab")
            except OSError as e:
                messagebox.showerror("ログ", str(e), parent=self)
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
            s = "%s @ %s bps  接続中" % (self.ser.port, self.ser.baudrate)
        else:
            s = "未接続"
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
        ttk.Button(bar, text="＋ ポートタブを追加", command=self.add_tab)\
            .pack(side="left")
        ttk.Label(bar, text="  各タブが1つのCOMポートに対応します").pack(side="left")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)

        self.add_tab()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def add_tab(self):
        tab = PortTab(self.notebook, self)
        self.notebook.add(tab, text="未接続")
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
    App().mainloop()


if __name__ == "__main__":
    main()
