# pc_sender（PC + RealSense D435i → UDP送信）

このフォルダは、PCの **Intel RealSense D435i（推奨）** のColor映像から MediaPipe Hand Landmarker で手を推定し、箱の疑似3D（x,yは箱平面0..1、zは単眼の疑似深度）として両手21点をUDP(JSON)でTouchDesignerへ送信します。
（OpenCVのWebカメラ入力も `--source opencv` で利用可能）

## 実行（Box平面：推奨）
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3
```

固定値でそのまま使うコマンド集：
- `docs/runbook.md`（「送信PC：D435iコマンド（固定値）」）

### RealSense（D435iなど）をカメラ入力に使う
Webカメラ（OpenCV）ではなく RealSense のColor映像を入力にしたい場合は `--source realsense` を使います。

補足：
- RealSenseを複数台挿す場合だけ、`--rs-serial` を指定してください（取り違え防止）。
- `--preview` はデバッグ用です（ウィンドウを出します）。
- `--backend` は `auto / dshow / msmf / any` が選べます。
- `--aruco-corner-ids` は箱の正面四隅（TL,TR,BR,BL）のIDを指定します。
- 疑似深度は `--z-like-*` オプション（scale/offset/clamp/smoothing）で調整できます。

## Box平面のデバッグ
ArUcoが見えているか／箱平面（0..1）へ写像できているかを確認する場合：
```powershell
python .\pc_sender\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3
```

## RealSense（D435iなど）動作確認（スモークテスト）
まず RealSense（D435i想定）自体が使えるか（Color/Depthが出るか）を確認したい場合：

前提：
- Intel RealSense SDK 2.0（librealsense）をインストール
- Pythonで `pyrealsense2` が import できる

```powershell
.\pc_sender\run_realsense_smoke_test.ps1
```

補足：
- `depth_center_m=0.000` が時々出るのは、そのピクセルのDepthが無効(0)になるためです（反射/角度/距離など）。
- `--center-window 5`（既定）で中心周辺の中央値（`depth_med_m`）も出しているので、目安はそちらを使うのがおすすめです。

## Box平面（ArUcoで座標安定化 → TouchDesigner/Unityへ送信）
箱の正面四隅にArUcoを貼っておくと、画像座標を「箱の正面平面（0..1）」へ安定してマップできます。zは単眼推定の疑似深度を使います。

注意：ArUcoは `opencv-contrib-python` が必要です。既に `opencv-python` を入れている場合は入れ替えてください。

実行例（四隅ID=TL,TR,BR,BL が `0,1,2,3` の場合）：
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --aruco-corner-ids 0,1,2,3
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
python .\pc_sender\app\pc_hand_box_debug_viewer.py --source opencv --camera 0 --flip --backend msmf --model .\pc_sender\models\hand_landmarker.task --aruco-corner-ids 0,1,2,3
python .\pc_sender\app\pc_hand_box_debug_viewer.py --source opencv --camera 0 --flip --backend any --model .\pc_sender\models\hand_landmarker.task --aruco-corner-ids 0,1,2,3
```
