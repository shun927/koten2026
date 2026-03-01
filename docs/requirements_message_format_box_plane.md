# 座標送信 メッセージ仕様（送信PC→TouchDesigner/Unity / UDP / Box平面2D + 両手）

この仕様は、箱の正面を正面から撮影した単眼カメラ映像に対して
ArUcoで箱の正面平面を推定し、手ランドマーク（21点）を「箱平面（0..1）」へ写像して送るための仕様です。

用途（想定）：
- Unityで「箱を正面から見たCG映像」を描画する
- 手は箱の左右から入る（両手同時）
- 奥行きは一旦使わない（箱の正面平面上の2Dとして扱う）

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
  "cam": { "index": 0, "api": 1400 },
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
  "hands": [
    {
      "hand_index": 0,
      "hand": "Left",
      "conf": 0.98,
      "lm_img": [[0.5,0.5], "... 21 points ..."],
      "lm_box": [[0.2,0.6], "... 21 points ..."],
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

## 3. 座標系（重要）
- `lm_img` は MediaPipeの正規化画像座標（左上=(0,0), 右下=(1,1)）
- `lm_box` は箱の正面平面の正規化座標（左上=(0,0), 右下=(1,1)）
  - ArUco四隅IDは「正面から見たときの」TL,TR,BR,BL の順で与える

## 4. 受信側（Unity）要件
- `seq` が最新のものだけ採用（遅延パケットは破棄）
- `aruco.ok=false` のときは、前回の値を短時間ホールド→失効できる設計にする
- 両手の割り当ては `hand`（Left/Right）だけに依存せず、入口の左右（例：手首0番の `lm_box.x` が 0.5 未満/以上）で固定すると安定
