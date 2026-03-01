# Unity要件（Box体験：手CG駆動 / 送信PC→Unity直結 or TouchDesigner経由）

このドキュメントは「箱の正面を正面から見たCG映像」に対して、箱の左右から入る両手の動きで手CGを動かすための要件まとめです。

## 1. 構成
- Python → TouchDesigner（UDP受信）
- TouchDesignerで左右判定・平滑化・ロスト・デバッグ可視化・OSC変換
- TouchDesigner → Unity（OSC等）

向くケース：
- 現場でフィルタ/閾値/ロスト挙動をノードで素早く調整したい
- Unity側を描画に集中させたい（入力の正規化を外に出す）

## 2. 入力仕様（Unityで受けるデータ）
奥行き無し（箱の正面平面）：
- 送信PC → touch は `docs/requirements_message_format_box_plane.md`（`v=2 kind=box_plane`）
- Unityは基本「touchが出すOSC」を受ける（要件は `docs/requirements_touch.md`）

フォールバック（touch側の方針）：
- ArUcoが不安定なときは、touch側で「短時間ホールド→失効」や `lm_img` へのフォールバックを実装する（詳細は `docs/requirements_touch.md`）

### 2.1 TouchDesigner → Unity（OSC）の推奨入力
手CGを動かすなら、21点（疑似3D）を受け取れるようにする。
- `/box/hand/left/lm3d`: 63 floats（x0,y0,z0,...,x20,y20,z20）
- `/box/hand/right/lm3d`: 63 floats（同上）
- `/box/hand/left/valid`: int（0/1）
- `/box/hand/right/valid`: int（0/1）

最小（互換/試作）:
- `/box/finger/left`: `x y z valid`（`z` は疑似深度）
- `/box/finger/right`: `x y z valid`（`z` は疑似深度）

## 3. Unity側の要件（実装）

### 3.1 OSC受信（TouchDesigner経由）
- メインスレッドをブロックしない（別スレッド/非同期で受信）
- 受信が途切れた場合に備えて、ロスト/失効をUnity側でも持てると安全

参考（Unity直結のとき）:
- UDP(JSON)を受信し、最新 `seq` 以外は破棄（遅延で古い手が反映されるのを防ぐ）

### 3.2 左右の手の割り当て（両手必須）
推奨（入口位置で固定）：
- 入力が21点（`lm3d`）のとき、手首（index 0）の `x` が `0.5` 未満を左、以上を右
- `hand`（Left/Right）は補助（遮蔽時に入れ替わる可能性がある）

### 3.3 ロスト/失効
- 受信が途切れたら、最後の姿勢を短時間ホールド→フェードアウト→無効
- `t_ms` を使って「何ms受信がないか」で判定できるようにする

### 3.4 平滑化
- 入力点（21点）にEMAを掛けるか、関節角にEMAを掛ける
- 目安：`alpha=0.2〜0.5` から調整（滑らかさと遅延のトレードオフ）
- `z` はノイズが目立ちやすいので、`x,y` より強く平滑化する

### 3.5 ボーン駆動（指）
最低要件：
- 指ごとに `MCP/PIP/DIP` のボーンがある（Genericリグ推奨）
- 21点から関節角を作る場合は、指の3点から角度を計算して回転に落とす

簡略（まず動かす）：
- 指先（TIP）だけを使って、簡易IK/LookAtで指方向を作る
- その後、関節角へ置き換える

## 4. カメラ/箱の要件（計測安定化）
- カメラは箱の正面中心に近く、箱の正面平面に対してできるだけ垂直
- 箱の正面四隅にArUcoを貼り、毎フレーム平面を推定する
- 箱内部は反射しない単色（黒/グレー）で、照明を均一にする
- 両手が重ならないように入口を離す/仕切りを設ける

## 5. 送信側（Python）メモ
- 箱平面送信：`pc_sender/app/pc_hand_box_sender.py`
- ArUco利用のため `opencv-contrib-python` が必要
