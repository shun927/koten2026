# PC2台を有線で直結する要件（会場向け）

このドキュメントは「台の下PC（作品専用）と、自分のPC（TouchDesigner + Unity + sound）を有線LANで直結」して運用するためのネットワーク要件です。
3台運用に拡張する場合は `docs/considerations.md` の「2台運用 / 3台運用の検討」を参照してください。

## 0. 前提（おすすめ役割分担）
このリポジトリでは、以下の分担をおすすめとします（2台運用）：

- 台の下PC（作品専用）：
  - Webカメラ
  - `pc_sender`（推論→UDP/JSONでTouchDesigner PCへ送信）
- 自分のPC（統合）：
  - TouchDesigner（UDP受信→座標処理→OSC送信）
  - Unity / sound（OSC受信。作品出力側）

## 1. 直結の基本（IP固定）
直結はDHCPが無いことが多いので、両PCの「有線LAN(イーサネット)」に固定IPを設定します。

おすすめ例：
- 台の下PC（作品専用）：`192.168.10.1` / `255.255.255.0`
- 自分のPC（TouchDesigner）：`192.168.10.2` / `255.255.255.0`

注意：
- デフォルトゲートウェイ、DNSは空でOK（インターネット不要の直結運用）
- ケーブルは通常のLANケーブルでOK（多くのPCはAuto MDI-Xで直結可）

## 2. 疎通確認（必須）
片方向だけでなく両方向を確認します。

台の下PC → 自分のPC：
```powershell
ping 192.168.10.2
```

自分のPC → 台の下PC：
```powershell
ping 192.168.10.1
```

補足：
- Windowsはping応答(ICMP)をブロックすることがあります。pingが通らなくても、UDP/OSC受信できていれば致命ではありません。

## 3. ポート設計（このリポジトリの前提）
### 3.1 PC送信 → touch（UDP/JSON）
- 宛先：自分のPC（TouchDesigner）
- ポート：`5005`

`pc_sender/config/endpoint.json` は、TouchDesigner PC（例：`192.168.10.2`）に送る：
- `host`: `192.168.10.2`
- `port`: `5005`

### 3.2 touch → Unity / sound（OSC/UDP）
2台運用の標準では Unity/sound は自分のPCで動かすため、OSC送信先はローカルを推奨します。
- 宛先（推奨）：`127.0.0.1`（同一PC内）

補足：
- 3台運用時は Unity/sound PC の固定IPを宛先にします。

送信アドレス仕様：
- `/box/finger/left` に `x y z valid`
- `/box/finger/right` に `x y z valid`
（詳細は `docs/requirements_touch.md`）

## 4. Windowsファイアウォール（重要）
受信する側のPCで、UDPの受信を許可します。

- 自分のPC（TouchDesigner）：UDP `5005` を許可（`pc_sender` の受信）
- 自分のPC（Unity/sound）：Unity/soundが使うOSC受信ポートを許可（TouchDesignerからの受信）
- 3台運用時は Unity/sound PC 側でOSC受信ポートを許可
