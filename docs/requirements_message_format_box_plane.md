# 座標送信 メッセージ仕様（送信PC→TouchDesigner/Unity / UDP / Box疑似3D + 両手）

この仕様は、箱の正面を正面から撮影したカメラ映像（推奨：RealSense D435i のColor）に対して
ArUcoで箱の正面平面を推定し、手ランドマーク（21点）を「箱平面（0..1）+ 疑似深度z_like」へ写像して送るための仕様です。

用途（想定）：
- Unityで「箱を正面から見たCG映像」を描画する
- 手は箱の左右から入る（両手同時）
- 単眼でも奥行き演出を加えたい（疑似3D）

送信実装：
- `pc_sender/app/pc_hand_box_sender.py`

## 1. 送信レート
- 目標 30FPS（最低 15FPS 以上）
- `seq` は送信ごとにインクリメント

## 2. JSON（1パケット=1JSON）
例（1メッセージ）：
```json
{
  "v": 2,
  "kind": "box_plane",
  "t_ms": 1700000000000,
  "seq": 12345,
  "src": "pc",
  "cam": { "kind": "realsense", "serial": "XXXXXXXXXXXX", "index": -1, "api": -1 },
  "frame": { "w": 1280, "h": 720 },
  "aruco": {
    "dict": "DICT_4X4_50",
    "corner_ids": [0,1,2,3],
    "detected_ids": [0,1,2,3],
    "ok": true,
    "stale": false,
    "age_ms": 0,
    "hold_ms": 300
  },
  "z_like": {
    "scale": 1.0,
    "offset": 0.0,
    "min": -1.0,
    "max": 1.0,
    "smooth_alpha": 0.35
  },
  "hands": [
    {
      "hand_index": 0,
      "hand": "Left",
      "conf": 0.98,
      "lm_img": [[0.5,0.5], "... 21 points ..."],
      "lm_box": [[0.2,0.6], "... 21 points ..."],
      "lm_box3": [[0.2,0.6,0.1], "... 21 points ..."],
      "z_like": [0.1, "... 21 values ..."],
      "valid": true
    }
  ]
}
```

### フィールド要件
- `v`: スキーマバージョン（整数）。本仕様は `2`。
- `kind`: `"box_plane"` 固定。
- `t_ms`: 送信元UNIX epoch ms
- `seq`: 連番（ドロップ/遅延検出用）
- `src`: 送信元ID
- `cam`: 入力カメラ情報（デバッグ用）
  - `kind`: `"realsense"` または `"opencv"`
  - `serial`: RealSenseのシリアル（RealSense使用時、任意）
  - `index`: OpenCVカメラインデックス（RealSense使用時は `-1`）
  - `api`: OpenCVのAPI（RealSense使用時は `-1`）
- `frame`: 入力フレームのピクセルサイズ
- `aruco.ok`:
  - `true`: 箱平面が推定できた（`hands[].lm_box` が埋まる）
  - `false`: 箱平面が推定できない（`hands[].lm_box` は `null`）
- `aruco.stale`:
  - `true`: マーカーが一時的に隠れたため、直近の平面推定を「短時間だけ」再利用している
- `aruco.age_ms`: `stale=true` のとき、その平面が何ms前のものか
- `aruco.hold_ms`: 送信側が平面を再利用する最大時間（ms）
- `hands`: 検出された手の配列（0..N）
- `hands[].lm_img`: 画像座標（正規化0..1）の21点（常に送る）
- `hands[].lm_box`: 箱平面座標（0..1）の21点（`aruco.ok=true` のときのみ送る）
- `hands[].z_like`: 疑似深度（21値）。単眼推定のため演出用途として扱う
- `hands[].lm_box3`: 疑似3D座標（21点の `[x,y,z_like]`）。`aruco.ok=true` のときのみ送る
- `z_like`: 送信側の疑似深度パラメータ（scale/offset/clamp/smoothing）

## 3. 座標系（重要）
- `lm_img` は MediaPipeの正規化画像座標（左上=(0,0), 右下=(1,1)）
- `lm_box` は箱の正面平面の正規化座標（左上=(0,0), 右下=(1,1)）
  - ArUco四隅IDは「正面から見たときの」TL,TR,BR,BL の順で与える
- `z_like` は手首基準の相対深度を正規化した疑似値（絶対距離mmではない）

## 4. 受信側（Unity）要件
- `seq` が最新のものだけ採用（遅延パケットは破棄）
- `aruco.ok=false` のときは、前回の値を短時間ホールド→失効できる設計にする
- 両手の割り当ては `hand`（Left/Right）だけに依存せず、入口の左右（例：手首0番の `lm_box.x` が 0.5 未満/以上）で固定すると安定
- `z_like` はノイズが出やすいため、受信側でも追加の平滑化と範囲制限を推奨
