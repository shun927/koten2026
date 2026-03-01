# pc_sender（PC + Webカメラ → UDP送信）

このフォルダは、PCのWebカメラ映像から MediaPipe Hand Landmarker で手を推定し、指先（人差し指先端）の相対3DをUDP(JSON)でTouchDesignerへ送信します。

## 作品システム（案）
- 送信PC（台下）：Webカメラ入力＋手推論（人差し指先端の相対3D）を生成してTouchDesigner PCへ送信
- TouchDesigner：受信した座標を統合・正規化・平滑化して、Unityとsoundへ配信
- Unity：ビジュアル
- sound：音
- Blender：オブジェクト制作（Unityへ取り込み）

通信（推奨）
- 送信PC → touch：UDP（JSON。`docs/requirements_message_format.md` の形式）
- touch → Unity / sound：OSC（UDP）

安定化の要点（重要）
- 座標処理の正本はtouchに寄せる（送信PCは「生の相対3D＋`valid`＋`seq`＋`t_ms`」を送る）
- ロスト時挙動をtouchで統一（例：`valid=false` が一定時間続いたらホールド→フェード→無効）
- OSCの仕様（アドレス/引数順）を先に固定して、Unityとsoundで同じ前提にする
 - 例: `/box/finger/left` と `/box/finger/right` に `x y z valid` を送る

## Box体験の前提（おすすめ）
- カメラは「箱の上面中央から下向き」に固定（遮蔽が減って追跡が安定）
- 穴は側面でもOK。ただし指先が見える姿勢に誘導するガイドがあると良い
- 座標はまず `0..1` の正規化で統一（箱サイズは後から掛け算で対応）
- 両手を使うなら送信側は `max_hands=2`、touch側でX位置ベースで左右を決める

## 体験の流れ（案）
1. 体験者がboxの側面穴から指（人差し指をさした状態）を差し入れる
2. box上面のカメラが指先を撮影
3. 送信PCが手のランドマークを推定し、指先の相対3DをtouchへUDP送信
4. touchが「作品用のbox座標」に変換し、UnityPCとsoundPCへOSC配信
5. Unityが映像を更新、soundが音を更新

## TouchDesigner実装手順（集約先）
touch側の要件、左右判定、フィルタ、ロスト、OSC出力、ノード構成例はすべて次を参照:
- `docs/requirements_touch.md`

## 動作確認環境（目安）
- Python：`3.12`（64bit推奨。`3.11` でも動くことが多い）
- 主要パッケージ：`mediapipe==0.10.32` / `opencv-python==4.10.0.84` / `numpy==1.26.4`
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

## 実行
```powershell
.\.venv\Scripts\python .\app\pc_hand_sender.py --config .\config\endpoint.json --model .\models\hand_landmarker.task --camera 0 --preview --print-fps
```

補足：
- `--camera` は `0` が一般的ですが、環境によって `1` などに変えてください。
- `--preview` はデバッグ用です（ウィンドウを出します）。
- `--backend` は `auto / dshow / msmf / any` が選べます。
- `--reconnect-sec` はカメラ未取得時の再接続までの秒数です（既定 `2.0`）。
- `--heartbeat-ms` はカメラ未取得中に `valid=false` を送る間隔です（既定 `250`）。
- `--stats-interval-sec` は `--print-fps` 時の統計ログ間隔です（既定 `2.0`）。

## 映像デバッグ（おすすめ）
認識できているかを映像にランドマーク表示して確認する場合：
```powershell
.\.venv\Scripts\python .\app\pc_hand_debug_viewer.py --model .\models\hand_landmarker.task --camera 0 --flip
```

### 画面が黒い / 映らないとき
- `--camera 1` など、カメラインデックスを変えて試す
- ほかのアプリ（Zoom/Teams/ブラウザ等）でカメラを掴んでいないか確認
- Windows「カメラのプライバシー設定」でデスクトップアプリのカメラ利用が許可されているか確認
- OpenCVのバックエンドを変える（黒画面対策）：
```powershell
.\.venv\Scripts\python .\app\pc_hand_debug_viewer.py --model .\models\hand_landmarker.task --camera 0 --flip --backend msmf
.\.venv\Scripts\python .\app\pc_hand_debug_viewer.py --model .\models\hand_landmarker.task --camera 0 --flip --backend any
```
