# Raspberry Pi 実装要件（相対3D・座標送信）

このドキュメントは「Raspberry Piで手を推論し、人差し指先端の相対3DをPCへ送る」ための設計要件です。

## 1. 前提
- 単一カメラのため、Z（奥行き）は推定の相対値であり、絶対距離（mm）精度は狙わない
- 送信する座標仕様は `docs/requirements_message_format.md` に従う

## 2. 推奨アーキテクチャ
**Piで推論（Python）→ UDPでPCへ座標送信**

理由：
- UDPは最新優先で遅延が溜まりにくい
- Piは有線LAN運用がしやすい

## 3. ハード要件
- Raspberry Pi 4 Model B 推奨
- カメラ：Pi Camera / USBカメラのいずれか
- 冷却（推奨）：ヒートシンク/ファン（発熱によるクロック低下を避ける）
- ネットワーク：有線LAN推奨（Wi‑Fiは混雑で遅延/ドロップ増の可能性）

### 3.1 採用予定ハード
- Raspberry Pi 4 Model B 8GB
- Raspberry Pi カメラモジュール V2

## 4. ソフト要件
- OS：Raspberry Pi OS 64bit 推奨
- Python環境：
  - カメラ入力（OpenCV等）
  - MediaPipe系（HandLandmarker相当）で推論できること
- 常設運用：
  - `systemd` による自動起動・自動再起動（推奨）

## 5. 性能要件（重要）
- 目標：15〜30FPS（モデル・解像度で調整）
- 最低：15FPS（未満だと追従が破綻しやすい）

調整要件：
- カメラ解像度は必要最小限（例：640x480〜）
- 推論入力のリサイズ/間引きでCPU負荷を抑える
- 温度/クロック/CPU使用率を監視できること（運用で重要）

## 6. 推論・座標の要件
- 送信対象ランドマーク：
  - `8`（index_finger_tip）
  - 相対化/スケール用に `0, 5, 17` を使用
- 相対3D：
  - `tip_rel = tip_world - wrist_world`
  - `tip_norm = tip_rel / scale`（`scale = ||mcp5 - mcp17||`）
- ロスト時：
  - `valid=false` を送る（PC側で失効/無視できる）

## 7. 運用要件
- プロセス監視：異常終了時に自動再起動
- ログ：
  - FPS、温度、ドロップ率（`seq` 欠損）、検出率（`valid` 率）
- カメラ初期化失敗：一定時間待ってリトライ

## 8. 受け入れ基準（チェック項目）
- 30秒連続稼働でプロセスが落ちない
- 目標FPSを満たす（少なくとも 15FPS）
- 有線LANで `seq` 欠損率が低い（例：< 0.5%）
- ロスト→復帰で座標が暴れない（失効/平滑化が効く）

## 9. Raspberry Pi セットアップ手順（推奨）

### 9.1 OSセットアップ
- Raspberry Pi OS 64-bit（Bookworm系）を推奨
- 初回起動時に設定：
  - `SSH` を有効化（後でPCから操作できるように）
  - 有線LAN推奨（Wi‑Fiでも可）
  - 文字コード/タイムゾーン設定

更新：
```bash
sudo apt update
sudo apt -y upgrade
sudo reboot
```

### 9.2 カメラ設定

#### Pi Camera（推奨）
Pi Cameraを使う場合：
```bash
sudo apt -y install libcamera-apps
libcamera-hello
```

#### USBカメラ
```bash
v4l2-ctl --list-devices
```
（`v4l2-ctl` がなければ `sudo apt -y install v4l-utils`）

### 9.3 Python環境（venv推奨）
```bash
sudo apt -y install python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

### 9.4 依存パッケージ（OpenCV系）
OpenCVのpip導入でコケる場合があるので、先に依存を入れておく：
```bash
sudo apt -y install \
  libatlas-base-dev libjpeg-dev libpng-dev libtiff-dev \
  libavcodec-dev libavformat-dev libswscale-dev
```

## 10. インストール要件（推論ライブラリ）

このセクションは **Raspberry Pi上で** 実施します。

### 10.1 Python環境は `uv` 推奨（インストール含む）
`uv` は venv と依存導入をまとめて管理しやすいので推奨します。

`uv` インストール例（Pi上）：
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
その後、シェルを開き直すか、`PATH` が通っていることを確認：
```bash
uv --version
```

### 10.2 venv作成（uv）
プロジェクトディレクトリ（例：`/home/pi/koten2026`）で実行：
```bash
cd /home/pi/koten2026
uv venv
```

### 10.3 MediaPipeの導入（第一候補）
要件：
- PiのOS/アーキテクチャによって `mediapipe` が `uv pip`/`pip` で入らない場合があります。
- 入らない場合は、要件として「OS/Pythonバージョンを合わせる」か「代替実装（TFLite直叩き等）」を検討します。

導入（通ればOK）：
```bash
cd /home/pi/koten2026
uv pip install mediapipe
```

### 10.4 OpenCVの導入
基本はヘッドレス推奨（GUI不要なら軽い）：
```bash
cd /home/pi/koten2026
uv pip install opencv-python-headless
```
画面表示（imshow等）が必要なら：
```bash
cd /home/pi/koten2026
uv pip install opencv-python
```

## 11. モデルファイル配置
`hand_landmarker.task`（MediaPipe TasksのHand Landmarkerモデル）を用意して、Piのプロジェクト直下に配置します。

注意：
- このリポジトリにモデルファイルが入っていない場合があります（サイズ/配布都合）。その場合は別途入手して配置します。

### 11.1 どこに置けばいい？
Pi上のプロジェクトディレクトリ直下に置くのが分かりやすいです。

例：
- Pi側プロジェクト：`/home/pi/koten2026`
- モデル配置先：`/home/pi/koten2026/hand_landmarker.task`

### 11.2 どうやってPiに持っていく？
PCからPiにコピーします（PCで実行）。

例（PC→Piにコピー）：
```bash
scp hand_landmarker.task pi@<PI_IP>:/home/pi/koten2026/
```

### 11.3 参照のしかた（実装時の要件）
- 実装では「相対パス `./hand_landmarker.task`」または「絶対パス `/home/pi/koten2026/hand_landmarker.task`」で参照する
- ファイルが存在することをPi側で確認：
```bash
ls -lh /home/pi/koten2026/hand_landmarker.task
```

### 11.4 Pi Camera Module V2（Picamera2）について
Camera Module V2は `libcamera` 系で扱うのが基本です。

要件：
- Pi側で `libcamera-hello` が動くこと
- Pythonからは `picamera2` を使うのが安定（OpenCVの `VideoCapture(0)` だけで読めない環境がある）

インストール（Pi上）：
```bash
sudo apt -y install libcamera-apps python3-picamera2
libcamera-hello
```

実装側の想定：
- `pi_project/app/pi_hand_sender.py` は `camera.device` に `picamera2` を指定できる

## 12. ネットワーク設定（UDP）
- 送信先（PC）のIPアドレスと受信ポートを決める
- PiからPCのIPへUDP送信できること
- PiのIP確認：
```bash
hostname -I
```

### 12.1 送信先のデフォルト（記録）
- 送信先PC IP：`192.168.1.100`（例）
- 送信先PC UDPポート：`5005`（例）

### 12.2 会場向け：PC↔Pi を有線で直結する構成（推奨）
会場Wi‑Fiが不安定/使えない場合でも動くように、PCとPiをLANケーブルで直結してUDP送信します（インターネット不要）。

#### 直結の要件
- PCとPiを **LANケーブルで直結**
- 直結用に、PCとPiに **固定IP** を設定（同一サブネット）
- 送信先IPは **直結側PCのIP** を使う（Wi‑Fi側のIPではない）

#### 固定IP例（そのまま使ってOK）
- PC（有線側）：`192.168.10.1/24`
- Raspberry Pi（eth0）：`192.168.10.2/24`
- 送信先PC IP（Piから見る宛先）：`192.168.10.1`
- 送信先PC UDPポート：`5005`

#### PC（Windows想定）の設定メモ
- 「イーサネット」アダプタに `192.168.10.1` / サブネット `255.255.255.0` を設定
- デフォルトゲートウェイ/DNSは未設定でOK（直結通信のみなら不要）
- ファイアウォールでUDP受信ポート（例：5005）を許可

#### Raspberry Pi側の設定メモ（例：NetworkManager）
IPを固定にする（例：`192.168.10.2/24`）。
環境によって設定方法が異なるため、採用しているネットワーク管理（NetworkManager / dhcpcd）に合わせて手順化する。

## 13. 常設運用（systemd推奨）
要件（例）：
- 自動起動
- 異常終了時の自動再起動
- 標準出力/エラーをログとして残す

（具体的なunitファイルは、実装スクリプト名とパスが確定した段階で作成する）
