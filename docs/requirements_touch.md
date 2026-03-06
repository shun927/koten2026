# TouchDesigner 実装要件（統合ハブ）

このドキュメントは、TouchDesigner を「統合ハブ」として使い、送信PCから受け取った指先座標を作品用の box 座標に変換して UnityPC / soundPC へ配信するための要件・実装仕様です。

## 1. 役割
- 入力: PC → touch（UDP / JSON）
- 処理: 左右割り当て、平滑化、範囲制限、ロスト処理、box座標化（0..1）
- 出力: touch → Unity / sound（OSC / UDP）

## 2. 受信（PC→touch）
- 受信ポート: `5005`（UDP DAT）

### 2.1 推奨：Box平面（ArUco）モード
- メッセージ仕様: `docs/requirements_message_format_box_plane.md`（`v=2 kind=box_plane`）
- 利用フィールド（主要）:
  - `t_ms`, `seq`, `aruco.ok`, `aruco.stale`, `aruco.age_ms`
  - `hands[].valid`, `hands[].lm_box`, `hands[].lm_box3`, `hands[].z_like`, `hands[].lm_img`

### 2.2 旧仕様（参考）：指先相対3Dモード
既存資産との互換のために残します。新規はBox平面モードを推奨。
- メッセージ仕様: `docs/archive/requirements_message_format.md`（`v=1`、旧仕様・参考）
- 利用フィールド:
  - `t_ms`, `seq`, `valid`, `tip_img`, `tip_norm`

## 3. 左右判定（X位置ベース）
作品の正面と左右穴が固定である前提で、左右は「手首のX位置」で決める。

### 3.1 Box平面（推奨）
`hands[].lm_box` があるときは、手首（landmark 0）の `x` で左右を固定する。
- 2件来た場合:
  - `wrist_x` が小さい方 → `left`
  - `wrist_x` が大きい方 → `right`
- 1件だけ来た場合:
  - `wrist_x < 0.5` → `left`
  - それ以外 → `right`

`aruco.ok=false` の場合は `hands[].lm_img`（画像正規化座標）の手首 `x` にフォールバックしてよい。

補足：`hand`（Left/Right）は参考値として保持し、最終判定には使わない（遮蔽で入れ替わることがある）。

### 3.2 旧仕様（tip_img）
2件来た場合:
- `tip_img.x` が小さい方 → `left`
- `tip_img.x` が大きい方 → `right`

1件だけ来た場合:
- `tip_img.x < 0.5` → `left`
- それ以外 → `right`

## 4. 作品座標への変換（box座標）
### 4.1 Box平面（推奨）
- 入力は `hands[].lm_box3`（`x,y,z_like`）を使用（ArUco + 疑似深度）
- Unityで手CGを動かす用途なら、まずは次の2点から始めるのが簡単:
  - 手首: landmark `0`
  - 人差し指先: landmark `8`

拡張（手全体）:
- 21点すべてをUnityへ送って、Unity側でボーン/IKへ落とす

### 4.2 旧仕様（tip_norm）
- 入力は `tip_norm (x,y,z)` を使用
- touch内で軸ごとに `scale` / `offset` / `clamp(0..1)` を適用して `box_x, box_y, box_z` を生成
- まずは `0..1` の正規化で統一（箱サイズが決まったら最後に `W/H/D` を掛ける）

## 5. 平滑化（推奨）
- left / right の各チャンネルごとに EMA を適用
- 初期値: `alpha = 0.75`
- 目安:
  - 反応重視: `0.6`
  - 安定重視: `0.85`
- `z_like` は `x,y` よりノイズが出やすいので、`z` だけ強めの平滑化を推奨

## 6. ロスト処理（推奨）
- `valid=false` またはメッセージ途絶が `150ms` 超でロスト開始
- ロスト中:
  - 「最後の値ホールド」
  - `300ms` で `valid=0` に遷移
- 復帰時:
  - `100ms` 程度でフェードイン（値ジャンプ抑制）

Box平面モード補足（ArUco一時隠れ）：
- `aruco.ok=false` の間は `lm_box` が無い（またはホールド）ので、以下のどちらかを推奨
  - `aruco.stale=true` の間は値を採用（`age_ms` が小さい間だけ）
  - `aruco.ok=false` が一定時間続いたら `valid=0` 扱いにしてフェードアウト

## 7. OSC出力（固定）
UnityPC / soundPC が別PCでも扱いやすいように、左右2chを固定で送る前提。

### 7.1 最小（指先だけ：互換重視）
旧仕様と同じ形で出せるようにし、疑似3Dでは `z=z_like` を送る。
- 左穴: `/box/finger/left` に `x y z valid`（float,float,float,int）
- 右穴: `/box/finger/right` に `x y z valid`（float,float,float,int）

### 7.2 推奨（手の21点：Unityで手CGを動かす）
TD の OSC Out CHOP は1チャンネル=1値のため、63個の独立チャンネルとして送る。
- 左手: `/box/hand/left/lm3d/0` ～ `/box/hand/left/lm3d/62`（各 float 1値、計63ch）
- 右手: `/box/hand/right/lm3d/0` ～ `/box/hand/right/lm3d/62`（同上）
- 順序: x0,y0,z0, x1,y1,z1, ..., x20,y20,z20（x,yは0..1箱平面、zは疑似深度）
- `valid` は別アドレスで送る（int）
  - `/box/hand/left/valid`
  - `/box/hand/right/valid`

任意（デバッグ）：
- 平面推定の状態（箱平面モードのとき）
  - `/box/aruco/ok`（int 0/1）
  - `/box/aruco/stale`（int 0/1）
  - `/box/aruco/age_ms`（int）

必要なら追加:
- デバッグ用に `seq`（int）, `t_ms`（int）を別アドレスで送る

### 7.3 OSC Out の宛先IP
- **同一PC（Unity/soundを自分のPCで動かす場合）**: `127.0.0.1` を宛先にする（ファイアウォール不要）
- **別PC（3台運用）**: Unity/sound PCの固定IPを宛先にする
  - 例：Unity/sound PCが `192.168.10.3` の場合、TouchDesignerのOSC Outは `192.168.10.3` 宛て
  - Unity/sound PC側のファイアウォールでOSC受信ポートを許可すること（`docs/requirements_network_pc_direct.md` §4.3 参照）

## 8. 監視項目（本番時）
- 受信FPS（目標15以上）
- `seq` 欠損率
- left/right の `valid` 継続率
- ロスト発生回数（1分あたり）

## 9. ノード構成例
### ネットワーク受信
1. `udp_in`（UDP In DAT）
2. `json_parse`（Text DAT / DAT ExecuteでJSONパース）
3. `route_hands`（Script DAT）
4. left/right 用 CHOP へ値を反映（`lm3d[63]` + `valid`）

### 座標処理（left/right 共通）
1. `*_in`（CHOP: `lm3d[63]`, `valid`）
2. `*_limit`（x,yは0..1 clamp、zは別レンジ clamp）
3. `*_math`（必要に応じて scale/offset）
4. `*_filter`（Filter CHOP: EMA相当）
5. `*_logic`（Logic CHOP: validのしきい値処理）

### ロスト処理
1. `timeout_timer`（Timer CHOP または Script CHOP）
2. `hold_fade`（Lag CHOP / Filter CHOP）

### OSC送信
1. `osc_out_unity`（OSC Out CHOP）
2. `osc_out_sound`（OSC Out CHOP）

### デバッグ（推奨）
1. `monitor_fps`（Info CHOP）
2. `monitor_seq`（Script DAT/CHOP）
3. `trail_left_right`（Trail CHOP）
4. `text_status`（Text TOP）
