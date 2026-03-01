# TouchDesigner 実装要件（統合ハブ）

このドキュメントは、TouchDesigner を「統合ハブ」として使い、送信PCから受け取った指先座標を作品用の box 座標に変換して UnityPC / soundPC へ配信するための要件・実装仕様です。

## 1. 役割
- 入力: PC → touch（UDP / JSON）
- 処理: 左右割り当て、平滑化、範囲制限、ロスト処理、box座標化（0..1）
- 出力: touch → Unity / sound（OSC / UDP）

## 2. 受信（PC→touch）
- 受信ポート: `5005`（UDP DAT）
- メッセージ仕様: `docs/requirements_message_format.md`
- 利用フィールド:
  - `t_ms`, `seq`, `valid`, `tip_img`, `tip_norm`
- 送信仕様:
  - 「検出した手ごとに1メッセージ」が来る（両手なら最大2件）
  - `hand_index` は同フレーム内の並び番号（0/1）。識別の正本ではない

## 3. 左右判定（X位置ベース）
作品の正面と左右穴が固定である前提で、左右は `tip_img.x` で決める。

- 2件来た場合:
  - `tip_img.x` が小さい方 → `left`
  - `tip_img.x` が大きい方 → `right`
- 1件だけ来た場合:
  - `tip_img.x < 0.5` → `left`
  - それ以外 → `right`
- `hand`（Left/Right）は参考値として保持し、最終判定には使わない

## 4. 作品座標への変換（box座標）
- 入力は `tip_norm (x,y,z)` を使用
- touch内で軸ごとに `scale` / `offset` / `clamp(0..1)` を適用して `box_x, box_y, box_z` を生成
- まずは `0..1` の正規化で統一（箱サイズが決まったら最後に `W/H/D` を掛ける）

## 5. 平滑化（推奨）
- left / right の各チャンネルごとに EMA を適用
- 初期値: `alpha = 0.75`
- 目安:
  - 反応重視: `0.6`
  - 安定重視: `0.85`

## 6. ロスト処理（推奨）
- `valid=false` またはメッセージ途絶が `150ms` 超でロスト開始
- ロスト中:
  - 「最後の値ホールド」
  - `300ms` で `valid=0` に遷移
- 復帰時:
  - `100ms` 程度でフェードイン（値ジャンプ抑制）

## 7. OSC出力（固定）
UnityPC / soundPC が別PCでも扱いやすいように、左右2chを固定で送る前提。

- 左穴: `/box/finger/left` に `x y z valid`（float,float,float,int）
- 右穴: `/box/finger/right` に `x y z valid`（float,float,float,int）

必要なら追加:
- デバッグ用に `seq`（int）, `t_ms`（int）を別アドレスで送る

### 7.1 2台運用（有線直結）の注意
直結で固定IP運用する場合は、OSC Out の宛先IPを「受信するPCの固定IP」に設定する。
例：自分のPCが `192.168.10.2` の場合、TouchDesignerのOSC Outは `192.168.10.2` 宛て。

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
4. left/right 用 CHOP へ値を反映（x,y,z,valid）

### 座標処理（left/right 共通）
1. `*_in`（CHOP: x,y,z,valid）
2. `*_math`（Math CHOP: scale/offset）
3. `*_limit`（Limit CHOP: 0..1 clamp）
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
