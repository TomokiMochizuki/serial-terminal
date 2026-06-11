# Serial Binary/ASCII Terminal

クロスプラットフォーム (Windows / WSL / Ubuntu / macOS) 対応の
シリアルポート バイナリ・ASCII 送受信エディタです。

Python + tkinter + pyserial による単一ファイル実装で、
Windows 向けには PyInstaller でビルドした単体 `.exe` を配布しています。

## 機能

- ASCII送信欄と受信ビューを分離し、受信バイナリ(HEXダンプ)ビューを選択的に表示
- 1ポート = 1タブ。複数のCOMポートを1アプリで同時に操作可能
- 定型文送信 (ASCII / HEX どちらの形式でも登録可、JSONで保存・読込)
- 送信改行 (なし / LF / CR / CRLF) と受信改行の表示方法 (そのまま / CR→LF変換 / CR削除) を設定可能
- ボーレート・データビット・パリティ・ストップビット変更
- 送受信データの保存
  - 受信: バイナリ (.bin) / テキスト (選択エンコードでデコード) を選択可
  - 送信: バイナリ / テキスト
  - タイムスタンプ・方向・HEX・ASCII併記の送受信ログ
  - 受信RAWデータのファイル逐次追記 (連続ログ)
- 文字エンコード選択 (UTF-8 / Shift_JIS / EUC-JP / ASCII / Latin-1 / UTF-16 LE/BE)。
  切替時は受信バッファ全体を再デコードして表示し直します
- UI言語切替 (日本語 / English)。即時反映され、選択は設定ファイルに保存。
  初回起動時はOSの言語設定に追従
- 定型文ダイアログで形式 (ASCII/HEX) を切り替えると、入力済みデータを自動変換
  (例: `abc` → `61 62 63`)
- ローカルエコー、自動スクロール

## ダウンロード (ビルド済みバイナリ)

[Releases](../../releases) ページから取得してください。

| OS | ファイル |
|---|---|
| Windows | `SerialTerminal.exe` (単体で動作、インストール不要) |
| macOS | `SerialTerminal-macos.zip` (.app) |
| Linux | `SerialTerminal` (実行ビット付与: `chmod +x SerialTerminal`) |

> **注意 (Windows):** PyInstaller の onefile 形式はまれにウイルス対策ソフトが
> 誤検知することがあります。その場合はソースから実行するか、自分でビルドしてください。

## ソースから実行

### uv (推奨)

[uv](https://docs.astral.sh/uv/) があれば、リポジトリを clone して 1 コマンドで起動できます
(Python 本体も依存ライブラリも自動で揃います)。

```bash
uv run serial-terminal
```

ターミナルで `serial-terminal` と打つだけで起動したい場合は、ツールとしてインストールします。

```bash
uv tool install .
serial-terminal
```

> ソース更新後にツール版へ反映するには `uv tool install --force .` を再実行してください。
> アンインストールは `uv tool uninstall serial-terminal`。

### pip

```bash
pip install pyserial
python serial_terminal.py
```

### プラットフォーム別の補足

| 環境 | 補足 |
|---|---|
| Windows | Python 3.9+ (tkinter同梱)。ポートは `COM3` 等 |
| Ubuntu / WSL | `sudo apt install python3-tk` が必要 (uv / pip 共通)。日本語表示には `fonts-noto-cjk` も推奨。シリアル権限: `sudo usermod -aG dialout $USER` (要再ログイン) |
| WSL2 | WSLg (Windows 11) でGUI表示可。USBシリアルは [usbipd-win](https://github.com/dorssel/usbipd-win) で `usbipd attach --wsl` するとWSL側に `/dev/ttyUSB*` として見える |
| macOS | ポート名は `/dev/cu.usbserial-*` 系。tkが古い場合は `brew install python-tk` |

## 自分でexeをビルドする (Windows)

uv の場合:

```powershell
uv run --group build pyinstaller --onefile --windowed --name SerialTerminal serial_terminal.py
# → dist\SerialTerminal.exe
```

pip の場合:

```powershell
pip install pyserial pyinstaller
pyinstaller --onefile --windowed --name SerialTerminal serial_terminal.py
# → dist\SerialTerminal.exe
```

## リリース手順 (メンテナ向け)

GitHub Actions により、バージョンタグをpushすると
Windows / macOS / Linux のバイナリが自動ビルドされ Releases に添付されます。

```bash
git tag v0.1.0
git push origin v0.1.0
```

手動ビルドは Actions タブ → Build → Run workflow からも実行できます
(この場合は Artifacts としてダウンロード可能)。

## ライセンス

[MIT License](LICENSE)
