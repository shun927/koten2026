# PC3台を有線LAN + Thunderboltネットワークで運用する要件（会場向け）

このドキュメントは「画像処理PC」「TD / Unity PC」「音PC」の3台を、画像処理系は有線LAN、音系は Thunderbolt ネットワーク（IP over Thunderbolt）で運用するためのネットワーク要件です。

## 0. 前提（おすすめ役割分担）
このリポジトリでは、以下の3台運用を前提とします：

- 画像処理PC（台の下・作品専用）：
  - Intel RealSense D435i（推奨）
  - `pc_sender`（推論→UDP/JSONでTD / Unity PCへ送信）
- TD / Unity PC（統合）：
  - TouchDesigner（UDP受信→座標処理→OSC送信）
  - Unity（ローカルOSC受信。作品映像出力側）
- 音PC：
  - sound アプリ / パッチ（OSC受信。作品音響出力側）

## 1. ネットワークの基本（IP固定）→ok
DHCPに依存しないよう、利用する各インターフェースに固定IPを設定します。

### 1.1 画像処理系（有線LAN）
画像処理PC と TD / Unity PC は、有線LAN(イーサネット)で接続します。

おすすめ例：
- 画像処理PC：`192.168.10.1` / `255.255.255.0`
- TD / Unity PC：`192.168.10.2` / `255.255.255.0`

注意：
- デフォルトゲートウェイ、DNSは空でOK（インターネット不要の直結運用）
- 画像処理PC と TD / Unity PC は、直結でもスイッチ（ハブ）経由でもよい
- ケーブルは通常のLANケーブルでOK

### 1.2 音系（Thunderbolt ネットワーク）
TD / Unity PC と 音PC は、Thunderbolt ネットワーク（IP over Thunderbolt）で接続します。

おすすめ例：
- TD / Unity PC の Thunderbolt 側：`192.168.20.1` / `255.255.255.0`
- 音PC の Thunderbolt 側：`192.168.20.2` / `255.255.255.0`

注意：
- **有線LAN側と Thunderbolt 側で同じIP帯を使わない**
- TD / Unity PC は2つのネットワークIFを持つ前提になる
  - LAN側：画像処理PCからのUDP/JSON受信
  - Thunderbolt側：音PCへのOSC/UDP送信

## 2. 疎通確認（必須）→ok
片方向だけでなく両方向を確認します。

画像処理PC → TD / Unity PC：
```powershell
ping 192.168.10.2
```

TD / Unity PC → 画像処理PC：
```powershell
ping 192.168.10.1
```

TD / Unity PC（Thunderbolt側）→ 音PC：
```powershell
ping 192.168.20.2
```

補足：
- Windowsはping応答(ICMP)をブロックすることがあります。pingが通らなくても、UDP/OSC受信できていれば致命ではありません。

## 3. ポート設計（このリポジトリの前提）
### 3.1 PC送信 → touch（UDP/JSON）
- 宛先：TD / Unity PC（TouchDesigner）
- ポート：`5005`

`pc_sender/config/endpoint.json` は、TD / Unity PC（例：`192.168.10.2`）に送る：
- `host`: `192.168.10.2`
- `port`: `5005`

### 3.2 touch → Unity / sound（OSC/UDP）
3台運用では Unity はTDと同一PC、sound は別PCを前提にします。
- Unity宛先（推奨）：`127.0.0.1`（同一PC内）
- Unity受信ポート：`9000`（固定）
- sound宛先：音PCの Thunderbolt 側IP（例：`192.168.20.2`）
- sound受信ポート：`9000`（固定）

補足：
- TouchDesigner では `osc_out_unity` と `osc_out_sound` を分けて設定することを推奨
- `osc_out_sound` は、TD / Unity PC の Thunderbolt 側インターフェースから音PCへ出る想定

送信アドレス仕様：
- `/box/hand/left/wrist` に `x y z valid`
- `/box/hand/left/index_tip` に `x y z valid`
- `/box/hand/right/wrist` に `x y z valid`
- `/box/hand/right/index_tip` に `x y z valid`
（詳細は `docs/requirements_touch.md`）

## 4. Windowsファイアウォール（重要）→ok
受信する側のPCで、UDPの受信を許可します。

- 自分のPC（TouchDesigner）：UDP `5005` を許可（`pc_sender` の受信）
- TD / Unity PC（Unity）：同一PC受信なら通常は追加設定不要
- 音PC（sound）：soundが使うOSC受信ポートを許可（TouchDesignerからの受信）

### 4.1 まず確認（推奨：Private(受信側)にする）
直結LAN（イーサネット）のネットワークプロファイルが `Public` のままだと、意図しない共有/受信を避けるために厳しめに運用したくなることが多いです。

管理者PowerShellで確認：
```powershell
Get-NetConnectionProfile
```
- 直結LANの `NetworkCategory` は `Private` 推奨
- 会場Wi-Fi等が `Public` のままでも、後述ルールを `Private` のみにすれば影響を抑えられます

### 4.2 TouchDesigner PC（受信側）で UDP 5005 を許可する
`pc_sender` → TouchDesigner の受信（UDP/JSON `5005`）を通すための受信ルールを作ります。
推奨は「Privateのみ」かつ「直結サブネット（または送信元PC）に限定」です。

管理者PowerShell（直結サブネットに限定する例）：
```powershell
New-NetFirewallRule `
  -DisplayName "koten2026 Allow UDP 5005 from 192.168.10.0/24" `
  -Direction Inbound -Action Allow -Enabled True `
  -Protocol UDP -LocalPort 5005 `
  -Profile Private `
  -RemoteAddress 192.168.10.0/24
```

送信元を「画像処理PCだけ」に絞るなら（例：送信元が `192.168.10.1`）：
```powershell
New-NetFirewallRule `
  -DisplayName "koten2026 Allow UDP 5005 from 192.168.10.1" `
  -Direction Inbound -Action Allow -Enabled True `
  -Protocol UDP -LocalPort 5005 `
  -Profile Private `
  -RemoteAddress 192.168.10.1
```

作成したルールの確認：
```powershell
Get-NetFirewallRule -DisplayName "koten2026 Allow UDP 5005 from 192.168.10.0/24" | Format-List
```

### 4.3 音PC の OSC 受信ポートを許可する
TouchDesigner → sound は OSC/UDP なので、**音PC側で「実際に待ち受けるポート番号」を固定して**許可します。
Unity を TD / Unity PC の同一PCで受ける場合は通常不要です。

管理者PowerShell：
```powershell
$oscPort = 9000
New-NetFirewallRule `
  -DisplayName "koten2026 Allow OSC UDP $oscPort from 192.168.20.0/24" `
  -Direction Inbound -Action Allow -Enabled True `
  -Protocol UDP -LocalPort $oscPort `
  -Profile Private `
  -RemoteAddress 192.168.20.0/24
```

送信元を TD / Unity PC の Thunderbolt 側IPだけに絞るなら（例：`192.168.20.1`）：
```powershell
New-NetFirewallRule `
  -DisplayName "koten2026 Allow OSC UDP $oscPort from 192.168.20.1" `
  -Direction Inbound -Action Allow -Enabled True `
  -Protocol UDP -LocalPort $oscPort `
  -Profile Private `
  -RemoteAddress 192.168.20.1
```

### 4.4 完了チェック（FW確認として一番確実）
Windowsファイアウォールの「許可できているか」は、実際に **受信側で待ち受け**て **送信側から投げて届くか** で確認するのが確実です。

受信側（TouchDesigner PC）で `pc_receiver` を起動（全IFで待ち受け）：
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty
```

送信側（画像処理PC）で `pc_sender` を起動して JSON が流れてくることを確認します。
受信できない場合は、まず以下を疑います：
- 受信側のファイアウォールルール（UDP 5005）が無い/無効/プロファイル不一致（`Private` になっていない等）
- 送信先IP（`pc_sender/config/endpoint.json` の `host`）が受信側PCを指していない
- 物理接続（ケーブル/アダプタ）やIP固定（`192.168.10.x/24`）が崩れている

## 4.5 Thunderbolt 併用時の設定まとめ
- `pc_sender/config/endpoint.json` の `host` は TD / Unity PC の **LAN側IP**（例：`192.168.10.2`）にする
- TouchDesigner の `osc_out_unity` は `127.0.0.1` にする
- TouchDesigner の `osc_out_unity` の `Network Port` は `9000` にする
- TouchDesigner の `osc_out_sound` は 音PC の **Thunderbolt側IP**（例：`192.168.20.2`）にする
- TouchDesigner の `osc_out_sound` の `Network Port` は `9000` にする
- LAN側と Thunderbolt側で同じサブネットを使わない

## 5. 台の下PCをSSHで操作したい　→ok
直結運用ではDNSが無いことが多いため、SSH接続先はホスト名ではなく固定IPで指定します。

例（自分のPC → 台の下PC）：
```powershell
ssh <USER>@192.168.10.1
```

### 5.1 台の下PCがWindowsの場合（OpenSSH Server）
台の下PC側で OpenSSH Server を有効化して `sshd` を起動します（管理者PowerShell）。
```powershell
# OpenSSH Server のインストール（未導入なら）
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# sshd を自動起動＋起動
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
```

ファイアウォール（台の下PC側）：
- TCP `22`（SSH）を許可（できれば「直結LANだけ」に限定）

#### Windows（台の下PC）でTCP 22を許可する方法
推奨は PowerShell でルールを作る方法です（管理者PowerShell）。

1) まずネットワークプロファイルを確認（Public だと開けたくないことが多い）
```powershell
Get-NetConnectionProfile
```
- 直結LANの `NetworkCategory` は `Private` 推奨（会場のWi-Fi等が `Public` のままでも、後述のルールを `Private` のみにすれば影響を抑えられます）

2) 受信ルール作成（Privateのみ・直結サブネットに限定）
```powershell
New-NetFirewallRule `
  -DisplayName "Allow SSH (TCP 22) from 192.168.10.0/24" `
  -Direction Inbound -Action Allow -Enabled True `
  -Protocol TCP -LocalPort 22 `
  -Profile Private `
  -RemoteAddress 192.168.10.0/24
```
- 「自分のPCだけ」に絞るなら `-RemoteAddress 192.168.10.2` にします

3) ルール確認
```powershell
Get-NetFirewallRule -DisplayName "Allow SSH (TCP 22) from 192.168.10.0/24" | Format-List
```

4) 接続確認（自分のPC側）
```powershell
Test-NetConnection 192.168.10.1 -Port 22
```

補足：
- 初回はパスワード認証になりがちです。可能なら鍵認証（`ssh-keygen` → `authorized_keys`）を推奨します。
- GUI操作が必要ならSSHではなくRDP（リモートデスクトップ）も検討してください。
