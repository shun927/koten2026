# koten2026

このリポジトリは、PC + Webカメラで手を推定し、作品側（TouchDesigner/Unity）で使える座標をUDPで配信するための実装を含みます。

- 旧：人差し指先端の相対3D（`docs/requirements_message_format.md`）
- 推奨：箱の正面平面（ArUcoで0..1へ写像、両手21点、`docs/requirements_message_format_box_plane.md`）

## 作品システム（案）
- PC：Webカメラ入力＋手推論（人差し指先端の相対3D）を生成してtouchへ送信
- TouchDesigner：受信した座標を統合・正規化・平滑化して、Unityとsoundへ配信
- Unity：ビジュアル
- sound：音
- Blender：オブジェクト制作（Unityへ取り込み）

通信（推奨）
- PC → touch：UDP（JSON。`docs/requirements_message_format.md` の形式）
- touch → Unity / sound：OSC（UDP）

安定化の要点（重要）
- 座標処理の正本はtouchに寄せる（送信側PCは「生の相対3D＋`valid`＋`seq`＋`t_ms`」を送るだけ）
- ロスト時挙動をtouchで統一（例：`valid=false` が一定時間続いたらホールド→フェード→無効）
- OSCの仕様（アドレス/引数順）を先に固定して、Unityとsoundで同じ前提にする
 - 例: `/box/finger/left` と `/box/finger/right` に `x y z valid` を送る

## Box体験の前提（おすすめ）
- カメラは「箱の正面中心」から正面向き（箱の正面平面にできるだけ垂直）に固定（AruCo平面推定が安定）
- 穴は左右側面。手が重ならないように離す/仕切りを入れると安定
- 座標はまず `0..1` の正規化で統一（箱サイズは後から掛け算で対応）
- 両手を使うなら送信側は `max_hands=2`、touch側でX位置ベースで左右を決める

## Unityでの運用（TouchDesignerを統合ハブにする）
映像が全部CGで、奥行き無し（箱の正面平面）なら、次の構成を推奨します。

- 推奨（現場調整が強い）
  - Python → TouchDesigner（受信/左右判定/平滑化/ロスト/デバッグ/OSC変換）→ Unity
- 代替（最短・シンプル）
  - Python → Unity 直結（UDP/JSON）

要件まとめ：
- Unity要件：`docs/requirements_unity.md`
- TouchDesigner要件：`docs/requirements_touch.md`
- メッセージ仕様（箱平面）：`docs/requirements_message_format_box_plane.md`

## 体験の流れ（案）
1. 体験者がboxの側面穴から指（人差し指をさした状態）を差し入れる
2. box正面のカメラが箱の正面平面（ArUco）と手を撮影
3. 送信PCが手ランドマークを推定し、箱平面（0..1）へ写像してtouchへUDP送信
4. touchが左右割り当て/平滑化/ロスト処理を行い、UnityPCとsoundPCへOSC配信
5. Unityが映像を更新、soundが音を更新

## TouchDesigner実装手順（集約先）
touch側の要件、左右判定、フィルタ、ロスト、OSC出力、ノード構成例はすべて次を参照:
- `docs/requirements_touch.md`
- `docs/considerations.md`（本番運用と作品内容の検討事項）

## 送信側（カメラ＋推論＋UDP）実装について
送信側コードは `pc_sender/` にあります（PC + Webカメラ）。
`docs/requirements_raspberrypi.md` は過去案（参考）として残しています。

## クイックスタート（PC送信 → touch受信）
0. 2台直結する場合は `docs/requirements_network_pc_direct.md` を参照（固定IP）
1. TouchDesigner側の要件は `docs/requirements_touch.md` を参照
2. 送信PCで `pc_sender/README.md` の手順に従って起動（`venv` / `uv` どちらでもOK。2台運用なら `pc_sender/config/endpoint.json` の `host` をTouchDesigner PCのIPにする）
3. デバッグ受信する場合は次を実行（任意）:
   - `python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty`

注意：
- Windowsのファイアウォールで UDP `5005` を許可してください（受信側PC / touch側PC）。

## ファイル構造
```text
koten2026/
  README.md
  .gitignore
  docs/
    considerations.md
    requirements_raspberrypi.md
    requirements_network_pc_direct.md
    requirements_message_format.md
    requirements_touch.md
  pc_sender/
    README.md
    requirements.txt
    config/
      endpoint.example.json
    app/
      pc_hand_sender.py
      pc_hand_debug_viewer.py
    models/
      hand_landmarker.task
  pc_receiver/
    udp_receiver.py
```

## 用意するもの（ハード）
- PC（Windows想定）
- Webカメラ（USB想定）
- カメラ固定具（箱の上面に固定できるもの）

## 用意するもの（ファイル）
- `pc_sender/models/hand_landmarker.task`（MediaPipe Tasks公式配布のHand Landmarkerモデルを入手して配置）
- `pc_sender/config/endpoint.json`（`endpoint.example.json` をコピーして作る）

注意：`hand_landmarker.task` はリポジトリに含めず、各自でダウンロードして配置する運用です（`.gitignore` 済み）。

## Python環境（推奨）
- Python `3.12`（64bit）
