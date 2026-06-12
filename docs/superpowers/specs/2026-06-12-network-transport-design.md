# ネットワーク接続 (TCP/UDP) 対応 設計ドキュメント

日付: 2026-06-12
ステータス: 承認済み (案A: Transport抽象化)

## 目的

シリアルポート専用の本ターミナルを、TCPクライアント / TCPサーバ / UDP でも
使えるようにする。送受信表示・HEXビュー・定型文・ログ保存・改行処理・
エンコーディング・i18n などの既存機能は全接続種別で共通に動作させる。

## 要件

- 接続形態: TCPクライアント、TCPサーバ、UDP の3形態すべてに対応する
- UI: 各タブのツールバー先頭に接続種別コンボを置き、タブ内で切り替える。
  種別に応じてパラメータ欄が切り替わる
- TCPサーバ: 同時接続は1クライアントのみ。接続中の新規接続は即拒否。
  クライアント切断後は自動で再待ち受けに戻る
- UDP: 送信宛先 (host:port) とローカル受信ポートを個別に指定する。
  受信は送信元を問わず受け付ける (コネクションレス)

## アーキテクチャ

### Transport抽象化

共通インターフェース `Transport` を定義し、`PortTab.ser` (serial.Serial) を
`PortTab.transport` に置き換える。

```
Transport (基底クラス)
  open()                 接続/待受/ソケット作成。失敗時は TransportError
  close()                後始末。多重呼び出し安全
  read(timeout) -> bytes 受信データ。タイムアウト時は b""、切断時は
                         TransportError (受信スレッドから呼ばれる)
  write(data: bytes)     送信。失敗時は TransportError
  is_open -> bool        接続状態
  description -> str     タブ名/ステータス用の表示文字列
```

実装クラス:

| クラス | 実体 | 備考 |
|---|---|---|
| `SerialTransport` | serial.Serial | 既存ロジックの移設。in_waiting + read |
| `TcpClientTransport` | socket.create_connection | 接続タイムアウト5秒 |
| `TcpServerTransport` | bind + listen(1) + accept | 1クライアント。接続中の新規接続は accept 後即 close。切断後は再待ち受け |
| `UdpTransport` | SO_REUSEADDR + bind(受信ポート) | write は宛先へ sendto、read は recvfrom (送信元不問) |

例外は `TransportError` (基底 Exception) に統一し、UI層では
serial.SerialException と同列に捕捉する。

### 受信スレッドとの接続

既存の `_reader` ループは「読めたら rx_queue に put、切断検知で
rx_queue.put(None)」という構造。Transport の read() が
タイムアウト時 b"" / 切断時 TransportError を返すことで、この構造を
ほぼ変えずに全種別へ流用する。

TCPサーバの「待受 → 接続 → 切断 → 再待受」の状態遷移は
TcpServerTransport 内部 (read() の中で accept を回す) に閉じ込め、
受信スレッド・UI層からは単一の read() に見えるようにする。
接続相手の変化はステータス表示用コールバック
(`on_status_change(description)`) で UI スレッドへ通知する
(tkinter の after 経由)。

## UI

ツールバー先頭に接続種別コンボを追加。種別ごとにパラメータ欄を切替:

| 種別 | パラメータ欄 |
|---|---|
| シリアル | ポート、ボーレート、ビット、パリティ、ストップ (現状どおり) |
| TCPクライアント | Host、Port |
| TCPサーバ | 待受Port (bindアドレスは 0.0.0.0 固定) |
| UDP | 宛先Host、宛先Port、受信Port |

- パラメータ欄の切替は frame の差し替え (grid/pack forget) で行う
- 接続中は種別コンボを無効化する
- タブ名表記: `COM3` / `192.168.0.10:5000` / `:5000(待受)` または
  `:5000←相手addr` / `UDP:5000`
- 種別名・ラベルは i18n 辞書 (ja/en) に追加する

## 設定の保存

既存の設定JSON (現在は language のみ保持) に、最後に接続へ成功した
ネットワークパラメータを全タブ共通の既定値として追加保存し、
新規タブの初期値に使う:

- `conn_type`: "serial" | "tcp_client" | "tcp_server" | "udp"
- `tcp_host`, `tcp_port`, `tcp_server_port`,
  `udp_host`, `udp_port`, `udp_local_port`

シリアルパラメータは現状どおり保存しない (既存挙動を変えない)。

## エラー処理

- ポート番号は 1〜65535 の整数で入力検証。不正時は接続前に警告
- 接続失敗 (拒否・タイムアウト・bind失敗) は既存の接続エラーダイアログを流用
- 送信時に未接続 (TCPサーバ待受中など) なら既存の「ポート未接続」警告
- TCP切断は rx_queue.put(None) → 既存の切断処理 (サーバは内部で再待受)

## テスト

- Transport層: GUI不要の単体テスト。localhost実ソケットで
  TcpClient↔TcpServer のループバック、UDPの送受信、切断検知、
  接続中の二重接続拒否を検証
- UI層: GUIテスト (DISPLAY必須) で種別切替によるパラメータ欄の切替、
  接続中のコンボ無効化を検証
- 既存テスト (i18n、改行、変換) は無変更でパスすること

## 変えないこと

送受信表示、HEXビュー、定型文、ログ保存 (RAWログ含む)、改行処理、
エンコーディング、言語切替の各機能・構造には手を入れない。
