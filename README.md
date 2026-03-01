# koten2026

このリポジトリは、PC + Webカメラで「人差し指先端の相対3D」を推定し、TouchDesignerへUDP送信するための実装を含みます。

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
- カメラは「箱の上面中央から下向き」に固定（遮蔽が減って追跡が安定）
- 穴は側面でもOK。ただし指先が見える姿勢に誘導するガイドがあると良い
- 座標はまず `0..1` の正規化で統一（箱サイズは後から掛け算で対応）
- 両手を使うなら送信側は `max_hands=2`、touch側でX位置ベースで左右を決める

## 体験の流れ（案）
1. 体験者がboxの側面穴から指（人差し指をさした状態）を差し入れる
2. box上面のカメラが指先を撮影
3. PCが手のランドマークを推定し、指先の相対3DをtouchへUDP送信
4. touchが「作品用のbox座標」に変換し、UnityPCとsoundPCへOSC配信
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
    requirements_raspberrypi.md
    requirements_message_format.md
    requirements_touch.md
  pc_sender/
    README.md
    requirements.txt
    config/
      endpoint.example.json
    app/
      pc_hand_sender.py
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
