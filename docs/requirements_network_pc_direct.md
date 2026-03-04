# PC2台を有線で直結する要件（会場向け）

このドキュメントは「台の下PC（作品専用）と、自分のPC（TouchDesigner + Unity + sound）を有線LANで直結」して運用するためのネットワーク要件です。
3台運用に拡張する場合は `docs/considerations.md` の「2台運用 / 3台運用の検討」を参照してください。

## 0. 前提（おすすめ役割分担）
このリポジトリでは、以下の分担をおすすめとします（2台運用）：

- 台の下PC（作品専用）：
  - Intel RealSense D435i（推奨）
  - `pc_sender`（推論→UDP/JSONでTouchDesigner PCへ送信）
- 自分のPC（統合）：
  - TouchDesigner（UDP受信→座標処理→OSC送信）
  - Unity / sound（OSC受信。作品出力側）

## 1. 直結の基本（IP固定）→ok
直結はDHCPが無いことが多いので、両PCの「有線LAN(イーサネット)」に固定IPを設定します。

おすすめ例：
- 台の下PC（作品専用）：`192.168.10.1` / `255.255.255.0`
- 自分のPC（TouchDesigner）：`192.168.10.2` / `255.255.255.0`

注意：
- デフォルトゲートウェイ、DNSは空でOK（インターネット不要の直結運用）
- ケーブルは通常のLANケーブルでOK（多くのPCはAuto MDI-Xで直結可）

## 2. 疎通確認（必須）→ok
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
- 受信ポート（仮）：Unity `9000`（チームで確定後に更新）

補足：
- 3台運用時は Unity/sound PC の固定IPを宛先にします。

送信アドレス仕様：
- `/box/finger/left` に `x y z valid`
- `/box/finger/right` に `x y z valid`
（詳細は `docs/requirements_touch.md`）

## 4. Windowsファイアウォール（重要）→ok
受信する側のPCで、UDPの受信を許可します。

- 自分のPC（TouchDesigner）：UDP `5005` を許可（`pc_sender` の受信）
- 自分のPC（Unity/sound）：Unity/soundが使うOSC受信ポートを許可（TouchDesignerからの受信）
- 3台運用時は Unity/sound PC 側でOSC受信ポートを許可

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

送信元を「台の下PCだけ」に絞るなら（例：送信元が `192.168.10.1`）：
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

### 4.3 Unity / sound の OSC 受信ポートを許可する（同一PC / 別PC）
TouchDesigner → Unity/sound は OSC/UDP なので、**Unity/sound 側で「実際に待ち受けるポート番号」を固定して**許可します。
（ポート番号が未決なら、先に Unity/sound 側の設定で受信ポートを決めてください）

管理者PowerShell（例：受信ポートを変数で指定）：
```powershell
$oscPort = 9000  # <- Unity/sound の実ポートに合わせて変更
New-NetFirewallRule `
  -DisplayName "koten2026 Allow OSC UDP $oscPort from 192.168.10.0/24" `
  -Direction Inbound -Action Allow -Enabled True `
  -Protocol UDP -LocalPort $oscPort `
  -Profile Private `
  -RemoteAddress 192.168.10.0/24
```

### 4.4 完了チェック（FW確認として一番確実）
Windowsファイアウォールの「許可できているか」は、実際に **受信側で待ち受け**て **送信側から投げて届くか** で確認するのが確実です。

受信側（TouchDesigner PC）で `pc_receiver` を起動（全IFで待ち受け）：
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty
```

送信側（台の下PC）で `pc_sender` を起動して JSON が流れてくることを確認します。
受信できない場合は、まず以下を疑います：
- 受信側のファイアウォールルール（UDP 5005）が無い/無効/プロファイル不一致（`Private` になっていない等）
- 送信先IP（`pc_sender/config/endpoint.json` の `host`）が受信側PCを指していない
- 物理接続（ケーブル/アダプタ）やIP固定（`192.168.10.x/24`）が崩れている

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
