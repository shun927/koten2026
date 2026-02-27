# koten2026

このリポジトリは、Raspberry Pi 4 + Camera Module V2 で「人差し指先端の相対3D」を推定し、PCへUDP送信するための実装を含みます。

## まずやること（全体の流れ）
1. PC↔Piを有線直結して固定IPを設定（インターネット不要）
2. Raspberry Pi OSを入れてSSH有効化
3. 初回起動後、PiをPCに有線直結（LANケーブル。Wi‑Fiではない）して `pi_project/` をPiにコピー
4. Piで `uv` と依存をインストール（`picamera2` はaptで入れる）
5. `hand_landmarker.task` をPiのプロジェクト直下に置く
6. PCで受信、Piで送信を起動して動作確認

## ファイル構造
```text
koten2026/
  README.md
  .gitignore
  docs/
    requirements_raspberrypi.md
    requirements_message_format.md
  pi_project/
    README.md
    pyproject.toml
    requirements.txt
    config/
      endpoint.example.json
    app/
      pi_hand_sender.py
    systemd/
      koten2026.service
  pc_receiver/
    udp_receiver.py
```

## 用意するもの（ハード）
- Raspberry Pi 4 Model B 4GB
- Raspberry Pi カメラモジュール V2
- microSD（Raspberry Pi OS用）
- PC（Windows想定）
- LANケーブル（PC↔Pi直結）

## 用意するもの（ファイル）
- `hand_landmarker.task`（MediaPipe Tasks公式配布のHand Landmarkerモデルを入手して配置）
- `pi_project/config/endpoint.json`（`endpoint.example.json` をコピーして作る）

注意：`hand_landmarker.task` はリポジトリに含めず、各自でダウンロードして配置する運用です（`.gitignore` 済み）。

## ネットワーク（会場向け：PC↔Pi 直結）
会場Wi‑Fiが不安定でも動く構成です（この通信はローカルのみで完結）。

やりたいこと（結論）：
- PCとPiをLANケーブルで直結して、同じネットワーク（同じサブネット）に固定IPを付ける
- その固定IP宛に、PiからPCへUDPで座標を送る

固定IP例（このまま使ってOK）：
- PC（有線LAN側）：`192.168.10.1/24`
- Pi（eth0）：`192.168.10.2/24`
- Piの送信先：`192.168.10.1:5005`

Windows（PC）側の設定（GUI）目安：
1. 設定 → ネットワークとインターネット → イーサネット
2. IP割り当てを「手動」
3. IPv4：IP=`192.168.10.1`、サブネット=`255.255.255.0`
4. デフォルトゲートウェイ/DNSは空でOK（直結だけなら不要）

Raspberry Pi（Pi）側の設定（NetworkManager想定）：
1. 有線NIC名を確認（`eth0` など）
```bash
ip -br link
ip -br a
```
2. いま有効な接続（CONNECTION名）を確認
```bash
nmcli -t -f NAME,DEVICE,TYPE con show --active
```
3. 有線の接続名（例：`Wired connection 1`）に固定IPを設定して有効化
```bash
sudo nmcli con mod "<CONNECTION_NAME>" ipv4.addresses 192.168.10.2/24 ipv4.method manual
sudo nmcli con up "<CONNECTION_NAME>"
ip -br a
```

疎通確認：
- PC→Pi：`ping 192.168.10.2`
- Pi→PC：`ping 192.168.10.1`

## Raspberry Pi OS セットアップ（初めて向け）
1. Raspberry Pi ImagerでRaspberry Pi OS 64-bitをmicroSDに書き込み
2. Imagerの設定（歯車）で以下を推奨
   - ホスト名（例：`pi4-01`。自分で設定した名前）
   - ユーザー名/パスワード設定（例：ユーザー名を `sk` にしたなら `ssh sk@...`）
   - SSH有効化
3. 初回起動後、PiをLANケーブルでPCに直結（Wi‑Fiではない）

ディスプレイが必要か？
- なくてもOK：Imagerで `SSH` とユーザー名/パスワードを設定しておけばヘッドレスで進められます
- うまくSSHできない場合：最初だけモニタ/キーボードでログインしてネット設定を確認すると早いです

Piに入る（例）：
```bash
# 直結用の固定IP設定が終わったあと（おすすめ）
ssh <USER>@192.168.10.2

# 直結IPをまだ設定していない場合は、同じWi‑Fi/LAN上でホスト名でも入れることがあります
# ssh <USER>@pi4-01
```

## Piへプロジェクトをコピー
PC（PowerShell）で実行（PiのIPは `192.168.10.2` の想定）：
```powershell
ssh <USER>@192.168.10.2 "mkdir -p /home/<USER>/koten2026"
scp -r .\pi_project\* <USER>@192.168.10.2:/home/<USER>/koten2026/
```
scp -r .\pi_project\* sk@pi4-01:/home/sk/koten2026/ はPC → Piへコピー

## Pi側：依存インストール（Camera Module V2 向け）
Pi（SSHで入った端末）で実行：

1. OS更新
```bash
sudo apt update
sudo apt -y upgrade
```

2. カメラ関連（Picamera2 / libcamera）
```bash
sudo apt -y install libcamera-apps python3-picamera2
libcamera-hello
```

3. `uv` を入れる（推奨）
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version
```

4. Python依存（MediaPipe/OpenCV）
```bash
cd /home/<USER>/koten2026
uv python install 3.11
uv venv --python 3.11
uv pip install -r requirements.txt
```

## `hand_landmarker.task` を置く
`hand_landmarker.task` はPiの `/home/<USER>/koten2026/` 直下に置きます（`app/` と同じ階層）。

PC→Piコピー例（PowerShell）：
```powershell
scp .\hand_landmarker.task <USER>@192.168.10.2:/home/<USER>/koten2026/
```
Pi側確認：
```bash
ls -lh /home/<USER>/koten2026/hand_landmarker.task
```

## 実行（動作確認）
1. PC側（受信）
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005
```

2. Pi側（送信）
Piで `endpoint.json` を作成してから起動します：
```bash
cd /home/<USER>/koten2026
cp config/endpoint.example.json config/endpoint.json
python3 app/pi_hand_sender.py --config config/endpoint.json --model ./hand_landmarker.task --print-fps
```

## つまづきポイント（よくある）
- 受信できない：WindowsファイアウォールでUDP `5005` を許可（受信側PC）
- カメラが映らない：`libcamera-hello` が動くか確認（Pi）
- `mediapipe` が入らない：Pi OS/Pythonの組み合わせ依存があるので `docs/requirements_raspberrypi.md` を参照
