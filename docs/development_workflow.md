# 開発の進め方（おすすめ手順）

目的：原因切り分けを簡単にし、現場で安定稼働する構成に寄せていく。

推奨：Unity側は「点群表示」→「手リグ」→「演出」の順で進める。

## 0. ゴール（合格条件の例）
- `aruco_ok=true` が安定して維持できる（多少 `stale` が出ても復帰する）
- TouchDesignerで左右割り当てが入れ替わらない
- ロスト時の挙動（ホールド→フェード→無効）が一貫している
- Unityで受信値が途切れても破綻しない（validで制御）

## 0.5 D435i最短チェック（着手前）
目的：配線・SDK・カメラ取得の問題を先に潰す。

- Viewer確認：RealSense ViewerでColorが映ること、USBが `3.x` 表示であること
- スモークテスト：`pc_sender/run_realsense_smoke_test.ps1`（venvとパスを自動で解決）
- ArUco/手検出確認：`python pc_sender/app/pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model pc_sender/models/hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3`
- 送信確認：`python pc_sender/app/pc_hand_box_sender.py --source realsense --rs-fps 30 --config pc_sender/config/endpoint.json --model pc_sender/models/hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3`
- 固定値コマンド集（本番用）：`docs/runbook_d435i_commands.md`

## 1. 計測フェーズ（送信PCのみ）
目的：ArUco平面推定と手検出を安定させる（物理配置が9割）。

- 起動（デバッグ表示）：`pc_sender/app/pc_hand_box_debug_viewer.py`
- 合格の目安：
  - `aruco_ok=true` が常時に近い
  - `stale` が出ても短時間（例：数百ms）で戻る

メモ：
- マーカーは大きく、**白フチを確保**、照明は均一
- 黒フェルト、黒布、艶消し塗装など

## 2. 通信フェーズ（送信PC → TouchDesigner）
目的：UDP受信の安定化とロスト処理の骨格を固める。

- 受信側（TouchDesigner PC）の前提：
  - 固定IP/直結の前提は `docs/requirements_network_pc_direct.md` を参照
  - Windowsファイアウォールで UDP `5005` を許可（ネットワークプロファイル `Private` 推奨）
- 受信のスモークテスト（TouchDesigner PC 側で実行）：まずは TouchDesigner を開く前に `pc_receiver` で受信できるかを確認する
  - `python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty`
- 送信側（送信PC）の前提：
  - `pc_sender/config/endpoint.json` の `host` が TouchDesigner PC のIP（例：`192.168.10.2`）になっていること
  - 起動（送信）：`python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3`
- 合格の目安（受信側で確認）：
  - `seq` が増え続ける（途切れ/停止しない）
  - 大きな `seq jump` が常発しない（Wi-Fiではなく直結で改善しやすい）
  - `aruco.ok=false` や `hands: []` でも「通信」自体の確認はできる（まずは UDP 5005 が届くことが重要）

## 3. OSCフェーズ（TouchDesigner → Unity）
目的：Unity側は受信と可視化だけ先に完成させる（手リグはまだ）。

推奨の最小実装：
- `lm3d[63] + valid` を受け取り、箱平面上に「点群」を表示する
- valid=0 のときは点群をフェードアウトする

## 4. リグ・演出フェーズ（Unity）
目的：点群で安定した後に、手モデルへ落とす。

進め方：
- まず手首（0）と指先（8）だけで動きを出す
- 次に各指のボーンへ展開
- `z_like` は演出用として強め平滑化・レンジ制限して使う（計測用途にしない）

## 5. 運用テスト（本番想定）
目的：再現性のある「チェックリスト」で最後に潰し込む。

- 起動手順を固定（コマンド、ポート、IP、OS設定）
- 監視項目（例）：FPS、`seq` 欠損、`aruco_ok/stale`、valid率、左右入れ替わり回数
