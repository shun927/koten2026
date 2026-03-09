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
手CGを動かすなら、2点（疑似3D）を受け取る。
- `/box/hand/left/wrist`: `x y z valid`
- `/box/hand/left/index_tip`: `x y z valid`
- `/box/hand/right/wrist`: `x y z valid`
- `/box/hand/right/index_tip`: `x y z valid`

互換/試作:
- `/box/finger/left`: `x y z valid`（`z` は疑似深度）
- `/box/finger/right`: `x y z valid`（`z` は疑似深度）

## 3. Unity側の要件（実装）

### 3.1 OSC受信（TouchDesigner経由）

**受信ポート**: `9000`（固定）
- 本番の3台構成では、Unity は TD / Unity PC と同一PCで動かし `127.0.0.1` で受ける
- Unity を別PCへ分離する構成に変える場合は、WindowsファイアウォールでUDP `9000` を許可する（`docs/requirements_network_pc_direct.md` §4.3 相当の考え方で設定）

**OSCライブラリ候補**:
- **uOSC**（推奨）：Package Manager から導入可。メインスレッドへの橋渡しが容易
- **OscJack**：軽量。`AddressHandler` でアドレスごとにコールバックを登録する方式

その他の要件:
- メインスレッドをブロックしない（別スレッド/非同期で受信）
- 受信が途切れた場合に備えて、ロスト/失効をUnity側でも持てると安全

参考（Unity直結のとき）:
- UDP(JSON)を受信し、最新 `seq` 以外は破棄（遅延で古い手が反映されるのを防ぐ）

### 3.2 左右の手の割り当て
**基本方針：TouchDesignerが正本**

TouchDesigner側でX位置ベースの左右判定を行い、`/box/hand/left/` と `/box/hand/right/` の別アドレスで送信する設計のため、**Unity側では左右の振り分けロジックは原則不要**。

万が一TouchDesignerを通さずUnityへ直結する場合のフォールバック：
- 入力が2点のとき、手首の `x` が `0.5` 未満を左、以上を右
- `hand`（Left/Right）は補助（遮蔽時に入れ替わる可能性がある）

補足：左右判定の詳細は `docs/requirements_touch.md` §3 を参照。

### 3.3 ロスト/失効
- 受信が途切れたら、最後の姿勢を短時間ホールド→フェードアウト→無効
- `t_ms` を使って「何ms受信がないか」で判定できるようにする

### 3.4 平滑化
- 入力点（手首 / 人差し指先）にEMAを掛ける
- 目安：`alpha=0.2〜0.5` から調整（滑らかさと遅延のトレードオフ）
- `z` はノイズが目立ちやすいので、`x,y` より強く平滑化する

### 3.5 ボーン駆動（指）
最低要件：
- 手首と人差し指先の2点から手モデルの位置と向きを作る
- 必要なら後から指ボーン駆動へ拡張する

## 4. カメラ/箱の要件（計測安定化）
- カメラは箱の正面中心に近く、箱の正面平面に対してできるだけ垂直
- 箱の正面四隅にArUcoを貼り、毎フレーム平面を推定する
- 箱内部は反射しない単色（黒/グレー）で、照明を均一にする
- 両手が重ならないように入口を離す/仕切りを設ける

## 5. 送信側（Python）メモ
- 箱平面送信：`pc_sender/app/pc_hand_box_sender.py`
- ArUco利用のため `opencv-contrib-python` が必要
