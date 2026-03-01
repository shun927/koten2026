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
- Raspberry Pi 4 Model B 4GB
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
- Raspberry Pi OS 64-bit（Bookworm系）
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
sudo apt -y install rpicam-apps
rpicam-hello
```

補足：
- `rpicam-hello` はデフォルトだと短時間で終了します
- ずっと表示して確認したい場合は `-t 0` を付ける：
```bash
rpicam-hello -t 0
```
- 箱内運用に近い低負荷の確認例：
```bash
rpicam-hello -t 0 --width 640 --height 480 --framerate 30
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
uv python install 3.11
uv venv --python 3.11
```

### 10.3 MediaPipeの導入（第一候補）
要件：
- Piの環境では `mediapipe` のwheel都合で **Python 3.13 だと入りません**（`cp313` が無い）。
- そのため、まず `uv python install 3.11` などで **Python 3.11/3.12** を使う前提にします。
- さらに、aarch64（Pi）向けwheelがあるバージョンに合わせる必要があるため、`mediapipe==0.10.21` を第一候補にします。
- 入らない場合は、要件として「OS/Pythonバージョンを合わせる」か「代替実装（TFLite直叩き等）」を検討します。

導入（通ればOK）：
```bash
cd /home/pi/koten2026
uv pip install mediapipe==0.10.21
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

例：
- Pi側プロジェクト：`/home/pi/koten2026`
- モデル配置先：`/home/pi/koten2026/hand_landmarker.task`

### 11.1 どうやってPiに持っていく？
PCからPiにコピーします（PCで実行）。

例（PC→Piにコピー）：
```bash
scp hand_landmarker.task pi@<PI_IP>:/home/pi/koten2026/
```

### 11.2 参照のしかた（実装時の要件）
- 実装では「相対パス `./hand_landmarker.task`」または「絶対パス `/home/pi/koten2026/hand_landmarker.task`」で参照する
- ファイルが存在することをPi側で確認：
```bash
ls -lh /home/pi/koten2026/hand_landmarker.task
```

### 11.3 Pi Camera Module V2（Picamera2）について
Camera Module V2は `libcamera` 系で扱うのが基本です。

要件：
- Pi側で `rpicam-hello`（旧: `libcamera-hello`）が動くこと
- Pythonからは `picamera2` を使うのが安定（OpenCVの `VideoCapture(0)` だけで読めない環境がある）

インストール（Pi上）：
```bash
sudo apt -y install rpicam-apps python3-picamera2
rpicam-hello
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
- 送信先PC IP：`192.168.10.1`（直結構成の例）
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

## 14. SSH接続の実運用メモ
### 14.1 初回セットアップ（Imager）
- Raspberry Pi ImagerでRaspberry Pi OS 64-bitを書き込み
- 詳細設定（歯車）で以下を設定：
  - ホスト名（例：`pi4-01`）
  - ユーザー名/パスワード（例：`sk`）
  - `SSH` 有効化

### 14.2 接続例
- 直結固定IP後：`ssh <USER>@192.168.10.2`
- 同一LANで名前解決できる場合：`ssh <USER>@pi4-01`

### 14.3 よくある失敗
- `Could not resolve hostname`：ホスト名解決できていない。IP直指定で接続する
- `Permission denied`：ユーザー名が違う可能性が高い（Imager設定のユーザー名を使う）

### 14.4 VS Code（Remote-SSH）でPi上を直接編集（推奨）
この方式は「PCからPiへコピー（`scp`）して反映」を繰り返すのではなく、**Pi上の `/home/<USER>/koten2026` を直接開いて編集**します。

#### 前提
- PC：Windows + VS Code
- Pi：SSH有効、直結固定IP（例：`192.168.10.2`）またはホスト名（例：`pi4-01`）
- Pi側プロジェクト配置先：`/home/<USER>/koten2026`

#### VS Code セットアップ
- 拡張：`Remote - SSH`（`ms-vscode-remote.remote-ssh`）をインストール

#### 接続
VS Codeで：
- `Ctrl+Shift+P` → `Remote-SSH: Connect to Host...`
- 接続先：`<USER>@192.168.10.2`（または `<USER>@pi4-01`）

初回はホストキー確認が出るので、意図したPiなら `yes`。
接続できると VS Code 左下に `SSH: ...` が表示されます。

#### フォルダを開く
- `Ctrl+Shift+P` → `Remote-SSH: Open Folder...` → `/home/<USER>/koten2026`
- フォルダが無い場合（Pi側ターミナルで）：
```bash
mkdir -p ~/koten2026
```

#### Remote-SSH での実行（このタイプの実行方法）
VS Code のターミナルが **Pi上** になっていることを確認（`pwd` が `/home/<USER>/...`）。

Pi側（Remote-SSHターミナル）：
```bash
cd /home/<USER>/koten2026
cp -n config/endpoint.example.json config/endpoint.json
./.venv/bin/python app/pi_hand_sender.py --config config/endpoint.json --model ./hand_landmarker.task --print-fps
```

PC側受信（PC上の別ターミナル）：
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005
```

#### systemd運用している場合の反映
コード/設定を編集したら（Pi側で）：
```bash
sudo systemctl restart koten2026
```
unitファイルを触った場合は：
```bash
sudo systemctl daemon-reload
sudo systemctl restart koten2026
```
状態確認：
```bash
systemctl status koten2026 --no-pager
journalctl -u koten2026 -f
```

## 15. Piへのプロジェクト配置（初回 / PCで実行）
Remote-SSH で編集する場合でも、最初にPiの `/home/<USER>/koten2026` にプロジェクトを配置する必要があります（初回のみ）。
PowerShell例（`<USER>` はPiのユーザー名）：
```powershell
ssh <USER>@192.168.10.2 "mkdir -p /home/<USER>/koten2026"
scp -r .\pi_project\* <USER>@192.168.10.2:/home/<USER>/koten2026/
```

## 16. 依存インストール手順（Piで実行）
### 16.1 OS更新
```bash
sudo apt update
sudo apt -y upgrade
```

### 16.2 カメラ関連
```bash
sudo apt -y install rpicam-apps python3-picamera2
rpicam-hello
```

### 16.3 `uv` 導入
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env
uv --version
```

### 16.4 Python依存
```bash
cd /home/<USER>/koten2026
uv python install 3.11
uv venv --python 3.11
uv pip install -r requirements.txt
```

## 17. モデル配置と起動確認
### 17.1 モデル配置（初回 / PCで実行）
```powershell
scp .\hand_landmarker.task <USER>@192.168.10.2:/home/<USER>/koten2026/
```

### 17.2 モデル存在確認（Piで実行）
```bash
ls -lh /home/<USER>/koten2026/hand_landmarker.task
```

### 17.3 実行（PC受信 + Pi送信）
PC：
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005
```

Pi：
```bash
cd /home/<USER>/koten2026
cp config/endpoint.example.json config/endpoint.json
.venv/bin/python app/pi_hand_sender.py --config config/endpoint.json --model ./hand_landmarker.task --print-fps
```

## 18. トラブルシュート
- 受信できない：WindowsファイアウォールでUDP `5005` を許可
- Remote-SSHで編集したのに反映されない：VS Code 左下が `SSH: ...` になっているか、開いているパスが `/home/<USER>/koten2026` か確認
- 接続先が意図したPiか不安：Pi側ターミナルで `hostname` と `ip a show eth0` を確認
- `ping` が片方向に通らない：WindowsはICMP（ping）応答をブロックする設定がある。UDP疎通（受信ログ）が本命
- カメラが映らない：`rpicam-hello`（旧: `libcamera-hello`）が動くか確認
- `mediapipe` が入らない：Python 3.11/3.12のvenvで再実行
