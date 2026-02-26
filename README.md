# koten2026

このリポジトリは、Raspberry Pi 4 + Camera Module V2 で「人差し指先端の相対3D」を推定し、PCへUDP送信するための実装を含みます。

## まずやること（全体の流れ）
1. PC↔Piを有線直結して固定IPを設定（インターネット不要）
2. Raspberry Pi OSを入れてSSH有効化
3. `pi_project/` をPiにコピー
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
- Raspberry Pi 4 Model B 8GB
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

固定IP例：
- PC（有線LAN側）：`192.168.10.1/24`
- Pi（eth0）：`192.168.10.2/24`
- Piの送信先：`192.168.10.1:5005`

Windows（PC）側の設定（GUI）目安：
1. 設定 → ネットワークとインターネット → イーサネット
2. IP割り当てを「手動」
3. IPv4：IP=`192.168.10.1`、サブネット=`255.255.255.0`
4. デフォルトゲートウェイ/DNSは空でOK（直結だけなら不要）

疎通確認：
- PC→Pi：`ping 192.168.10.2`
- Pi→PC：`ping 192.168.10.1`

## Raspberry Pi OS セットアップ（初めて向け）
1. Raspberry Pi ImagerでRaspberry Pi OS 64-bitをmicroSDに書き込み
2. Imagerの設定（歯車）で以下を推奨
   - ホスト名（例：`koten-pi`）
   - ユーザー名/パスワード設定
   - SSH有効化
3. 初回起動後、PiをLANでPCに直結

Piに入る（例）：
```bash
ssh pi@192.168.10.2
```

## Piへプロジェクトをコピー
PC（PowerShell）で実行（PiのIPは `192.168.10.2` の想定）：
```powershell
ssh pi@192.168.10.2 "mkdir -p /home/pi/koten2026"
scp -r .\pi_project\* pi@192.168.10.2:/home/pi/koten2026/
```

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
cd /home/pi/koten2026
uv venv
uv pip install -r requirements.txt
```

## `hand_landmarker.task` を置く
`hand_landmarker.task` はPiの `/home/pi/koten2026/` 直下に置きます（`app/` と同じ階層）。

PC→Piコピー例（PowerShell）：
```powershell
scp .\hand_landmarker.task pi@192.168.10.2:/home/pi/koten2026/
```
Pi側確認：
```bash
ls -lh /home/pi/koten2026/hand_landmarker.task
```

## 実行（動作確認）
1. PC側（受信）
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005
```

2. Pi側（送信）
Piで `endpoint.json` を作成してから起動します：
```bash
cd /home/pi/koten2026
cp config/endpoint.example.json config/endpoint.json
python3 app/pi_hand_sender.py --config config/endpoint.json --model ./hand_landmarker.task --print-fps
```

## つまづきポイント（よくある）
- 受信できない：WindowsファイアウォールでUDP `5005` を許可（受信側PC）
- カメラが映らない：`libcamera-hello` が動くか確認（Pi）
- `mediapipe` が入らない：Pi OS/Pythonの組み合わせ依存があるので `docs/requirements_raspberrypi.md` を参照
