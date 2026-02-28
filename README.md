# koten2026

このリポジトリは、Raspberry Pi 4 + Camera Module V2 で「人差し指先端の相対3D」を推定し、PCへUDP送信するための実装を含みます。

## 作品システム（案）
- Raspberry Pi：カメラ入力＋手推論（人差し指先端の相対3D）を生成してPCへ送信
- TouchDesigner：受信した座標を統合・正規化・平滑化して、Unityとsoundへ配信
- Unity：ビジュアル
- sound：音
- Blender：オブジェクト制作（Unityへ取り込み）

通信（推奨）
- Pi → touch：UDP（JSON。`docs/requirements_message_format.md` の形式）
- touch → Unity / sound：OSC（UDP）

安定化の要点（重要）
- 座標処理の正本はtouchに寄せる（Piは「生の相対3D＋`valid`＋`seq`＋`t_ms`」を送るだけ）
- ロスト時挙動をtouchで統一（例：`valid=false` が一定時間続いたらホールド→フェード→無効）
- OSCの仕様（アドレス/引数順）を先に固定して、Unityとsoundで同じ前提にする
 - 例: `/box/finger/left` と `/box/finger/right` に `x y z valid` を送る

## Box体験の前提（おすすめ）
- カメラは「箱の上面中央から下向き」に固定（遮蔽が減って追跡が安定）
- 穴は側面でもOK。ただし指先が見える姿勢に誘導するガイドがあると良い
- 座標はまず `0..1` の正規化で統一（箱サイズは後から掛け算で対応）
- 両手を使うならPiは `max_hands=2`、touch側でX位置ベースで左右を決める

## 体験の流れ（案）
1. 体験者がboxの側面穴から指（人差し指をさした状態）を差し入れる
2. box上面のカメラが指先を撮影
3. Raspberry Piが手のランドマークを推定し、指先の相対3DをtouchへUDP送信
4. touchが「作品用のbox座標」に変換し、UnityPCとsoundPCへOSC配信
5. Unityが映像を更新、soundが音を更新

## TouchDesigner実装手順（集約先）
touch側の要件、左右判定、フィルタ、ロスト、OSC出力、ノード構成例はすべて次を参照:
- `docs/requirements_touch.md`

## ラズパイ実装手順（集約先）
ラズパイのセットアップ、インストール、ネットワーク直結、起動確認はすべて次を参照：
- `docs/requirements_raspberrypi.md`

## ファイル構造
```text
koten2026/
  README.md
  .gitignore
  docs/
    requirements_raspberrypi.md
    requirements_message_format.md
  pi_project/
    README.md
    pyproject.toml
    requirements.txt
    config/
      endpoint.example.json
    app/
      pi_hand_sender.py
    systemd/
      koten2026.service
  pc_receiver/
    udp_receiver.py
```

## 用意するもの（ハード）
- Raspberry Pi 4 Model B 4GB
- Raspberry Pi カメラモジュール V2
- microSD（Raspberry Pi OS用）
- PC（Windows想定）
- LANケーブル（PC↔Pi直結）

## 用意するもの（ファイル）
- `hand_landmarker.task`（MediaPipe Tasks公式配布のHand Landmarkerモデルを入手して配置）
- `pi_project/config/endpoint.json`（`endpoint.example.json` をコピーして作る）

注意：`hand_landmarker.task` はリポジトリに含めず、各自でダウンロードして配置する運用です（`.gitignore` 済み）。
