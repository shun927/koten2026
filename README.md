# koten2026

このリポジトリは、PC + **Intel RealSense D435i** で手を推定し、作品側（TouchDesigner/Unity/sound）で使える座標をUDP/OSCで配信するための実装を含みます。

- 旧：人差し指先端の相対3D（`docs/archive/requirements_message_format.md`、旧仕様・参考）
- 推奨：箱の疑似3D（ArUcoでx,yを0..1へ写像 + 単眼疑似z。利用点は手首 + 人差し指先、`docs/requirements_message_format_box_plane.md`）

## 作品システム（案）
- 送信PC：RealSense D435i入力＋手推論（箱疑似3Dから手首 + 人差し指先を利用）を生成してtouchへ送信
- TD / Unity PC：TouchDesignerが受信した座標を統合・正規化・平滑化し、Unityとsoundへ配信
- Unity：ビジュアル
- 音PC：sound
- Blender：オブジェクト制作（Unityへ取り込み）

通信（推奨）
- 送信PC → touch：UDP（JSON。`docs/requirements_message_format_box_plane.md` の形式）
- touch → Unity：OSC（UDP, `127.0.0.1`）
- touch → sound：OSC（UDP, 音PCの Thunderbolt 側IP）

本番構成（推奨）
- 画像処理PC → TD / Unity PC：有線LAN
- TD / Unity PC → 音PC：Thunderbolt ネットワーク（IP over Thunderbolt）

安定化の要点（重要）
- 座標処理の正本はtouchに寄せる（送信側PCは「箱疑似3Dランドマーク＋`seq`＋`t_ms`」を送る）
- ロスト時挙動をtouchで統一（例：`aruco.ok=false` が続いたらホールド→フェード→無効）
- OSCの仕様（アドレス/引数順）を先に固定して、Unityとsoundで同じ前提にする
 - 推奨（2点）: `/box/hand/left/right/wrist` と `/box/hand/left/right/index_tip` に `x y z valid`
 - 互換: `/box/finger/left` と `/box/finger/right` に `x y z valid`
 - 受信ポート: Unity / sound とも `9000` 固定

## Box体験の前提（おすすめ）
- カメラは「箱の正面中心」から正面向き（箱の正面平面にできるだけ垂直）に固定（AruCo平面推定が安定）
- 穴は左右側面。手が重ならないように離す/仕切りを入れると安定
- 座標はまず `0..1` の正規化で統一（箱サイズは後から掛け算で対応）
- 両手を使うなら送信側は `max_hands=2`、touch側でX位置ベースで左右を決める
- box: 縦40㎝横50㎝高さ20㎝想定
- マーカー4cm以上
- **箱は本番中動かさない前提なので `--aruco-lock-after-ms 2000` を推奨**
  - 起動後にマーカーが2秒間安定検出されたタイミングで平面を固定し、以後マーカーを隠しても `aruco.ok=true` のまま動き続ける
  - ズレた場合は送信PCを再起動してマーカーを映し直すだけで再キャリブレーション完了

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
- 開発手順：`docs/development_workflow.md`

## 体験の流れ（案）
1. 体験者がboxの側面穴から指（人差し指をさした状態）を差し入れる
2. box正面のカメラが箱の正面平面（ArUco）と手を撮影
3. 送信PCが手ランドマークを推定し、箱平面（0..1）へ写像してtouchへUDP送信
4. touchが左右割り当て/平滑化/ロスト処理を行い、Unityと音PCへOSC配信
5. Unityが映像を更新、soundが音を更新

## TouchDesigner実装手順（集約先）
touch側の要件、左右判定、フィルタ、ロスト、OSC出力、ノード構成例はすべて次を参照:
- `docs/requirements_touch.md`
- `docs/considerations.md`（本番運用と作品内容の検討事項）

## 送信側（カメラ＋推論＋UDP）実装について
送信側コードは `pc_sender/` にあります（PC + RealSense D435i）。
`docs/archive/requirements_raspberrypi.md` は過去案（参考）として残しています。

## クイックスタート（PC送信 → touch受信）
0. 本番のネットワーク前提は `docs/requirements_network_pc_direct.md` を参照
1. TouchDesigner側の要件は `docs/requirements_touch.md` を参照
2. 送信PCで `pc_sender/README.md` の手順に従って起動（`venv` / `uv` どちらでもOK。`pc_sender/config/endpoint.json` の `host` は TD / Unity PC の LAN 側IP にする）
3. デバッグ受信する場合は次を実行（任意）:
   - `python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty`

本番当日のチェック（現場用）：
- `docs/runbook.md`

## コマンド表記（venvの統一）
このリポジトリでは、**リポジトリ直下の `.venv` を activate してから `python ...` を実行**する表記に統一します。

- `python ...`：いま有効なPython（通常は venv）で実行される（推奨）
- `.\.venv\Scripts\python ...`：activate せずに venv を明示できる（切り分け用途）

目安：PowerShellプロンプトに `(koten2026)` が出ていれば、`python` は venv を指しています。

## D435i最短チェック（推奨）
送信系に入る前に、次の順でD435iの疎通を確認します。

1. RealSense ViewerでColorが映ることを確認（USB表示が `3.x` であること）
2. スモークテストを実行してColor/Depthの取得確認
   - `.\pc_sender\run_realsense_smoke_test.ps1`
3. `pc_hand_box_debug_viewer.py` でArUcoと手検出を確認
   - `python .\pc_sender\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3`
4. `pc_hand_box_sender.py` でUDP送信を開始
   - `python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3`

固定値でそのまま使うコマンド集：
- `docs/runbook.md`（「送信PC：D435iコマンド（固定値）」）

注意：
- Windowsのファイアウォールで UDP `5005` を許可してください（手順は `docs/requirements_network_pc_direct.md`）。

## ファイル構造
```text
koten2026/
  README.md
  .gitignore
  ArUco_image/          # ArUcoマーカー画像（印刷用）
  docs/
    considerations.md
    development_workflow.md
    runbook.md
    requirements_network_pc_direct.md
    requirements_message_format_box_plane.md
    requirements_unity.md
    requirements_touch.md
    archive/
      requirements_raspberrypi.md
      requirements_message_format.md
  pc_sender/
    README.md
    requirements.txt
    run_realsense_smoke_test.ps1
    config/
      endpoint.example.json   # endpoint.json は .gitignore 済み
    app/
      pc_hand_box_sender.py
      pc_hand_box_debug_viewer.py
      pc_realsense_smoke_test.py
    models/
      hand_landmarker.task    # .gitignore 済み（各自ダウンロード）
  pc_receiver/
    udp_receiver.py
  td_project/
    README.md
    koten2026.toe             # TouchDesignerプロジェクト
    callbacks/
      udpin1_callbacks.py     # UDP In DAT の onReceive
      script2_callbacks.py    # Script CHOP の cook()
  unity_project/
    README.md
    HandTrackingApp/
      Assets/
        scripts/
          HandReceiver.cs         # OSC受信・2点適用
          HandPointsGenerator.cs  # メニューから2点GameObject生成
```

## 用意するもの（ハード）
- PC（Windows想定）
- Intel RealSense D435i（推奨。USB3）

## 用意するもの（ファイル）
- `pc_sender/models/hand_landmarker.task`（MediaPipe Tasks公式配布のHand Landmarkerモデルを入手して配置）
- `pc_sender/config/endpoint.json`（`endpoint.example.json` をコピーして作る）

```powershell
Copy-Item .\pc_sender\config\endpoint.example.json .\pc_sender\config\endpoint.json
```
`config/endpoint.json` の `host`（TD / Unity PC の LAN 側IP）と `port` を環境に合わせて変更します。

注意：`hand_landmarker.task` はリポジトリに含めず、各自でダウンロードして配置する運用です（`.gitignore` 済み）。

## 動作確認環境（目安）
- Python：`3.12`（64bit推奨。`3.11` でも動くことが多い）
- 主要パッケージ：`mediapipe==0.10.32` / `opencv-contrib-python==4.10.0.84` / `numpy==1.26.4`
- `uv` のバージョン確認：`uv self version`（`uv version` は `pyproject.toml` が無いとエラー）

## セットアップ（Windows / PowerShell想定）
### venv（標準：リポジトリ直下の `.venv` に統一）
```powershell
cd <REPO_ROOT>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r .\pc_sender\requirements.txt
```

### uv（使いたい人向け）
```powershell
cd <REPO_ROOT>
uv self version
uv python install 3.12
uv venv --python 3.12
uv pip install -r .\pc_sender\requirements.txt
```

補足：
- `uv python install 3.12` は未インストールなら入れます（既にあるなら省略可）。
- 実行はリポジトリ直下の `.venv` を使います（`.\.venv\Scripts\Activate.ps1` 済みの前提で `python ...`）。
