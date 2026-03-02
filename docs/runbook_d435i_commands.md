# D435i 本番用コマンド集（固定値）

目的：当日の起動を迷わないように、実運用で使うコマンドを固定してまとめる。

前提（このファイルの固定値）:
- model: `pc_sender/models/hand_landmarker.task`
- sender config: `pc_sender/config/endpoint.json`
- 実行場所: リポジトリルート `koten2026/`
- `python` が venv を指すこと（プロンプトに `(koten2026)` が出ている状態が目安）

## 0. 事前確認（1回だけ）
```powershell
Test-Path .\pc_sender\models\hand_landmarker.task
Test-Path .\pc_sender\config\endpoint.json
```

## 1. D435i疎通確認（推奨）
```powershell
.\pc_sender\run_realsense_smoke_test.ps1
```

## 2. ArUco/手検出確認（送信PC）
```powershell
python .\pc_sender\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3
```

## 3. UDP送信開始（送信PC）
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3
```

## 4. UDP受信確認（touch側PC, 任意）
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty
```

## 5. トラブル時の最短切り分け
1. ViewerでColorが映るか（USBが `3.x` か）
2. `pc_realsense_smoke_test.py` が動くか
3. `pc_hand_box_debug_viewer.py` で `aruco_ok` が安定するか
4. `pc_hand_box_sender.py` の `seq` が増え続けるか

## 6. D435i以外を使う場合
- RealSenseを複数台挿す場合:
  - `--rs-serial <SERIAL>` を追加して対象機を固定する

## 7. `python` が見つからない/venvじゃない場合
環境によって venv のフォルダ名が `.venv` ではないことがあるため、その場合は venv の `python.exe` をフルパスで指定して実行する。
