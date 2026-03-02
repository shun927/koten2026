# pc_sender（PC + RealSense D435i → UDP送信）

このフォルダは、PCの **Intel RealSense D435i（推奨）** のColor映像から MediaPipe Hand Landmarker で手を推定し、箱の疑似3D（x,yは箱平面0..1、zは単眼の疑似深度）として両手21点をUDP(JSON)でTouchDesignerへ送信します。
（OpenCVのWebカメラ入力も `--source opencv` で利用可能）

## 作品システム（案）
- 送信PC（台下）：RealSense D435i入力＋手推論（箱疑似3D: 両手21点）を生成してTouchDesigner PCへ送信
- TouchDesigner：受信した座標を統合・正規化・平滑化して、Unityとsoundへ配信
- Unity：ビジュアル
- sound：音
- Blender：オブジェクト制作（Unityへ取り込み）

通信（推奨）
- 送信PC → touch：UDP（JSON。`docs/requirements_message_format_box_plane.md` の形式）
- touch → Unity / sound：OSC（UDP）

安定化の要点（重要）
- 座標処理の正本はtouchに寄せる（送信PCは「箱疑似3Dランドマーク＋`seq`＋`t_ms`」を送る）
- ロスト時挙動をtouchで統一（例：`aruco.ok=false` が一定時間続いたらホールド→フェード→無効）
- OSCの仕様（アドレス/引数順）を先に固定して、Unityとsoundで同じ前提にする
 - 例: `/box/finger/left` と `/box/finger/right` に `x y z valid` を送る

## Box体験の前提（おすすめ）
- カメラは「箱の正面中心」から正面向き（箱の正面平面にできるだけ垂直）に固定（ArUco平面推定が安定）
- 穴は左右側面。手が重ならないように離す/仕切りを入れると安定
- 座標はまず `0..1` の正規化で統一（箱サイズは後から掛け算で対応）
- 両手を使うなら送信側は `max_hands=2`、touch側でX位置ベースで左右を決める

## 体験の流れ（案）
1. 体験者がboxの側面穴から指（人差し指をさした状態）を差し入れる
2. box正面のカメラが箱の正面平面（ArUco）と手を撮影
3. 送信PCが手ランドマークを推定し、箱平面（0..1）へ写像してtouchへUDP送信
4. touchが左右割り当て/平滑化/ロスト処理を行い、UnityPCとsoundPCへOSC配信
5. Unityが映像を更新、soundが音を更新

## TouchDesigner実装手順（集約先）
touch側の要件、左右判定、フィルタ、ロスト、OSC出力、ノード構成例はすべて次を参照:
- `docs/requirements_touch.md`

## 動作確認環境（目安）
- Python：`3.12`（64bit推奨。`3.11` でも動くことが多い）
- 主要パッケージ：`mediapipe==0.10.32` / `opencv-contrib-python==4.10.0.84` / `numpy==1.26.4`
- `uv` のバージョン確認：`uv self version`（`uv version` は `pyproject.toml` が無いとエラー）

## セットアップ（Windows / PowerShell想定）
### venv（標準）
```powershell
cd pc_sender
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\pip install -r requirements.txt
```

### uv（使いたい人向け）
```powershell
cd pc_sender
uv self version
uv python install 3.12
uv venv --python 3.12
uv pip install -r requirements.txt
```

補足：
- `uv python install 3.12` は未インストールなら入れます（既にあるなら省略可）。
- 実行は `.venv` を使います（例：`.\.venv\Scripts\python ...`）。

## モデル配置
MediaPipe Tasksの `hand_landmarker.task` を入手して、`pc_sender/models/hand_landmarker.task` に置きます（リポジトリには含めません）。

## 設定
```powershell
Copy-Item .\config\endpoint.example.json .\config\endpoint.json
```
`config/endpoint.json` の `host`（TouchDesignerのIP）と `port` を環境に合わせて変更します。

## 実行（Box平面：推奨）
```powershell
.\.venv\Scripts\python .\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\config\endpoint.json --model .\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3
```

固定値でそのまま使うコマンド集：
- `docs/runbook_d435i_commands.md`

### RealSense（D435iなど）をカメラ入力に使う
Webカメラ（OpenCV）ではなく RealSense のColor映像を入力にしたい場合は `--source realsense` を使います。

例（D435i、serial指定あり）：
```powershell
.\.venv\Scripts\python .\app\pc_hand_box_sender.py --source realsense --rs-serial 925622071620 --rs-fps 30 --config .\config\endpoint.json --model .\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3
```

補足：
- RealSenseを複数台挿す場合だけ、`--rs-serial` を指定してください（取り違え防止）。
- `--preview` はデバッグ用です（ウィンドウを出します）。
- `--backend` は `auto / dshow / msmf / any` が選べます。
- `--aruco-corner-ids` は箱の正面四隅（TL,TR,BR,BL）のIDを指定します。
- 疑似深度は `--z-like-*` オプション（scale/offset/clamp/smoothing）で調整できます。

## Box平面のデバッグ（おすすめ）
ArUcoが見えているか／箱平面（0..1）へ写像できているかを確認する場合：
```powershell
.\.venv\Scripts\python .\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3
```

### RealSense（D435iなど）でのデバッグ表示
```powershell
.\.venv\Scripts\python .\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3
```

## RealSense（D435iなど）動作確認（スモークテスト）
まず RealSense（D435i想定）自体が使えるか（Color/Depthが出るか）を確認したい場合：

前提：
- Intel RealSense SDK 2.0（librealsense）をインストール
- Pythonで `pyrealsense2` が import できる

```powershell
.\run_realsense_smoke_test.ps1
```

補足：
- `depth_center_m=0.000` が時々出るのは、そのピクセルのDepthが無効(0)になるためです（反射/角度/距離など）。
- `--center-window 5`（既定）で中心周辺の中央値（`depth_med_m`）も出しているので、目安はそちらを使うのがおすすめです。

## Box平面（ArUcoで座標安定化 → TouchDesigner/Unityへ送信）
箱の正面四隅にArUcoを貼っておくと、画像座標を「箱の正面平面（0..1）」へ安定してマップできます。zは単眼推定の疑似深度を使います。

注意：ArUcoは `opencv-contrib-python` が必要です。既に `opencv-python` を入れている場合は入れ替えてください。

実行例（四隅ID=TL,TR,BR,BL が `0,1,2,3` の場合）：
```powershell
.\.venv\Scripts\python .\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\config\endpoint.json --model .\models\hand_landmarker.task --width 1280 --height 720 --preview --aruco-corner-ids 0,1,2,3
```

補足：
- マーカーが一瞬隠れる場合に備えて、送信側は直近の平面推定を短時間だけ再利用できます（既定 `--aruco-hold-ms 300`）。
- TouchDesignerを統合ハブにする場合は、`config/endpoint.json` の `host` を TouchDesigner PC のIPにします（受信UDPポートは touch 側で `5005`）。

### 画面が黒い / 映らないとき
- RealSense Viewer で Color が映るか確認（映らない場合はSDK/接続を先に解決）
- USB3ポートへ直挿し（ハブ回避）。Viewer上でUSBが `3.x` になっているか確認
- `--rs-serial` を指定して、意図したD435iを固定して起動
- ほかのアプリ（Zoom/Teams/ブラウザ等）でカメラを掴んでいないか確認
- OpenCVカメラに切り替えて切り分ける場合（フォールバック）：
```powershell
.\.venv\Scripts\python .\app\pc_hand_box_debug_viewer.py --source opencv --camera 0 --flip --backend msmf --model .\models\hand_landmarker.task --aruco-corner-ids 0,1,2,3
.\.venv\Scripts\python .\app\pc_hand_box_debug_viewer.py --source opencv --camera 0 --flip --backend any --model .\models\hand_landmarker.task --aruco-corner-ids 0,1,2,3
```
