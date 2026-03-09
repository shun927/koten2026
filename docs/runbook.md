# Runbook（本番当日 / 現場運用）

目的：会場で「どこが詰まっているか」を最短で切り分け、起動と復旧を迷わないようにする。

- **まずは最短ルート**で起動したい → [現場チェック（最短）](#現場チェック最短) を上から順に
- **コマンドをコピペ**したい → [送信PC：D435iコマンド（固定値）](#送信pcd435iコマンド固定値) へ
- **ネットワーク/FWの手順**が必要 → `docs/requirements_network_pc_direct.md`
- **touchの仕様/OSCアドレス**を確認したい → `docs/requirements_touch.md`

---

## 想定構成（前提）

**本番前提（3台運用）**
- 画像処理PC（台下・作品専用）：RealSense D435i → `pc_sender`（UDP/JSON `5005`）
- TD / Unity PC（操作PC）：TouchDesigner（UDP受信→処理→OSC送信） + Unity（同一PCでOSC受信）
- 音PC：sound（OSC受信）

固定IP例：
- LAN側
  - 画像処理PC：`192.168.10.1/24`
  - TD / Unity PC：`192.168.10.2/24`
- Thunderbolt側
  - TD / Unity PC：`192.168.20.1/24`
  - 音PC：`192.168.20.2/24`

---

<a id="現場チェック最短"></a>
## 現場チェック（最短）: 画像処理PC → TD / Unity PC（Touch）→ 音PC

このセクションは「当日、上から順に潰す」ためのチェックリストです。  
各ステップに **目的 / 合格条件 / 失敗したら** を書いています。

### 0) 今日の起動ルール（最重要）

- **起動順序（推奨）**
  1. 受信PC：UDP受信の確認（TouchDesignerを開く前）
  2. 送信PC：D435iの疎通 → 送信開始（`seq`が増える）
  3. 受信PC：TouchDesigner（OSCが出ているか）
  4. 受信PC：Unity（ローカルOSCを受けて動くか）
  5. 音PC：sound（OSCを受けて動くか）
- **切り分け方針**
  - 「touchやUnityが悪い」より前に、**まず `pc_receiver/udp_receiver.py` でUDPが来ているか**を必ず確認する（FW/宛先ミスを最短で炙り出す）

### 1) 物理（ケーブル/USB）

目的：カメラ問題とネットワーク問題を「配線」で潰す。

- D435iは **USB3直挿し**（ハブ回避）
- 画像処理PC ↔ TD / Unity PC は **有線LAN**
- TD / Unity PC ↔ 音PC は **Thunderbolt ケーブル**

合格条件：
- RealSense ViewerでColorが映る / USBが `3.x` 表示
- Thunderbolt ネットワークが両PCで認識されている

失敗したら（最優先で疑う）：
- USB2になっている（ケーブル/ポート/ハブが原因になりやすい）
- 他アプリがカメラを掴んでいる（Zoom/Teams/ブラウザ等を閉じる）

### 2) ネットワーク（固定IP）

目的：UDPが「届かない」を最初に潰す。

前提（おすすめ例。詳細は `docs/requirements_network_pc_direct.md`）：
- LAN側
  - 画像処理PC：`192.168.10.1/24`
  - TD / Unity PC：`192.168.10.2/24`
- Thunderbolt側
  - TD / Unity PC：`192.168.20.1/24`
  - 音PC：`192.168.20.2/24`

受信PCで確認（管理者PowerShell推奨）：
```powershell
Get-NetConnectionProfile
```
合格条件：
- LAN側 / Thunderbolt側の `NetworkCategory` がどちらも `Private`（推奨）

疎通（任意。pingはブロックされることもある）：
```powershell
ping 192.168.10.1
ping 192.168.10.2
ping 192.168.20.2
```

失敗したら：
- LAN側IP固定が崩れている（`192.168.10.x/24` になっているか）
- Thunderbolt側IP固定が崩れている（`192.168.20.x/24` になっているか）
- 物理接続（LANケーブル / Thunderbolt ケーブル / アダプタ）が不安定

### 3) Windowsファイアウォール（受信側：最重要）

目的：受信PCで **UDP 5005** を確実に受けられるようにする。

- 手順は `docs/requirements_network_pc_direct.md` の「4. Windowsファイアウォール（重要）」に集約
- 迷ったら「受信PCで `udp_receiver.py` を起動して届くか」で判定する（机上確認より確実）

### 4) `endpoint.json`（送信先IP）

目的：送信先の宛先ミスを潰す。

送信PCで確認：`pc_sender/config/endpoint.json` の `host` が **TD / Unity PC のLAN側IP** になっていること。  
例：`192.168.10.2`

合格条件：
- `udp_receiver.py` にJSONが届く（次のステップ）

### 5) Python/venv（送信PC・受信PC）

目的：`python` が venv を指している状態にそろえる（当日トラブルの最大要因を潰す）。

リポジトリルート `koten2026/` で（両PCとも必要なら）：
```powershell
cd C:\project\team_project\koten2026
.\.venv\Scripts\Activate.ps1
python -c "import sys; print(sys.executable)"
python --version
```
合格条件：
- `sys.executable` が `.venv` 配下を指す

失敗したら：
- venvが無い/壊れている → READMEの「セットアップ（Windows / PowerShell）」に従って作り直す
- 端末が別のフォルダにいる → 必ずリポジトリルートから実行する

### 6) 送信PC：D435i最短切り分け（カメラ → 推論 → ArUco）

目的：送信側だけで「カメラが出ない / 推論が動かない / ArUcoが出ない」を切り分ける。

#### 6.1 RealSense Viewer（最初にやる）
合格条件：
- Colorが映る（USB `3.x`）

#### 6.2 スモークテスト（Color/Depth）
合格条件：
- 例外で落ちず、プレビューが出て depth 値が更新される

```powershell
.\pc_sender\run_realsense_smoke_test.ps1
```
補足：このスクリプトは venv の `python.exe` を自動で探して実行します（`.venv` が壊れていなければ当日強い）。

#### 6.3 ArUco/手検出（プレビュー）
合格条件：
- カメラプレビューが出る
- マーカーが見えている間は `aruco_ok=true` が安定（多少 `stale=true` は許容）

```powershell
python .\pc_sender\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3
```
失敗したら（典型）：
- `cv2.aruco not found` → `opencv-contrib-python` が入っていない（`pc_sender/README.md` の注意参照）
- `Model not found` → `pc_sender\models\hand_landmarker.task` が無い
- `pyrealsense2 import failed` → RealSense SDK/pyrealsense2 が入っていない

### 7) 送信PC：UDP送信開始（本番コマンド）

目的：`seq` が増え続ける状態にして、受信側の切り分けへ渡す。

合格条件：
- 送信側コンソールで `fps=... seq=...` が出続ける（`--print-fps`）

```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3
```
補足：
- `--rs-serial` は **複数台のRealSenseを挿す場合だけ** 追加（取り違え防止）
- 当日用に固定値でまとめた版： [送信PC：D435iコマンド（固定値）](#送信pcd435iコマンド固定値)

<a id="udp-recv-check"></a>
### 8) 受信PC：UDP受信の確認（TouchDesignerを開く前）

目的：TouchDesignerの前に「そもそもUDPが届いているか」を確定する。

```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty
```
合格条件：
- `seq` が増え続ける（止まらない）
- `seq jump` が常発しない（少しは許容。常発ならネットワーク/負荷を疑う）
- `aruco.ok=true` が（マーカーが見えている限り）安定

補足：
- `hands: []` でも「通信」自体の確認はできる（まずは届くことが最優先）

失敗したら（届かない）：
1. `endpoint.json` の `host` が受信PCを指しているか
2. 受信PCのFW（UDP 5005）が許可されているか（プロファイル `Private` の一致含む）
3. IP固定/ケーブルの物理

### 9) TouchDesigner：作品側の確認

目的：touch内の処理（左右割り当て/ロスト/OSC）が想定通りか確認する。

合格条件（例）：
- `seq` 欠損（`seq jump`）が常発しない
- ロスト時の挙動（ホールド→フェード→無効）が想定通り
- 左右割り当てが入れ替わらない（`docs/requirements_touch.md` のX位置ベースの方針）

### 10) Unity / sound：OSC受信

目的：最終出力が動くことを確認する。

- Unity は TD / Unity PC 上で `127.0.0.1` 受信になっていることを確認する
- sound は音PC側で **受信ポートを固定**し、TouchDesigner の `osc_out_sound` 宛先が `192.168.20.2` になっていることを確認する
- sound は音PC側で、Thunderbolt 側ネットワークに対してファイアウォール受信許可する（`docs/requirements_network_pc_direct.md` 参照）

---

## 最短トラブルシュート（止まっている場所の特定）

1. 送信PC：RealSense Viewer / `run_realsense_smoke_test.ps1` が通るか（カメラ問題）
2. 送信PC：`pc_hand_box_debug_viewer.py` で `aruco_ok` / 手の点が出るか（計測/依存問題）
3. 受信PC：`udp_receiver.py` で `seq` が増えるか（ネットワーク/FW/宛先問題）
4. TouchDesigner内でOSCが出ているか（touch側問題）
5. UnityがローカルOSCを受けるか（TD / Unity PC内の設定問題）
6. 音PCのsoundがOSCを受けるか（受信ポート/FW/宛先問題）

---

## 当日メモ（よくある詰まり）

### A) `cv2.aruco` が無い（ArUcoが動かない）
症状例：`cv2.aruco not found. Install opencv-contrib-python.`

原因：`opencv-python` だと ArUco（contrib）が入っていないことがある。

対処（venv有効化済みで）：
```powershell
python -m pip uninstall -y opencv-python opencv-contrib-python
python -m pip install opencv-contrib-python==4.10.0.84
```

### B) `pyrealsense2 import failed`
原因：RealSense SDK（librealsense）/ Python側の `pyrealsense2` が入っていない、または環境が崩れている。

対処：
- まず RealSense Viewer で映る状態を作る（SDK/ドライバ側を先に直す）
- その上で venv を正しく使えているか（`python -c "import pyrealsense2"`）を確認

### C) `Model not found: pc_sender/models/hand_landmarker.task`
原因：モデルファイルが無い/場所が違う。

対処：
```powershell
Test-Path .\pc_sender\models\hand_landmarker.task
```
無ければ各自で取得して配置する（README参照）。

### D) `seq jump` が常発する / FPSが落ちる
まず疑う：
- 受信PC側の負荷（Touch + Unity を同時起動しているため）
- LAN側またはThunderbolt側の接続が不安定
- ネットワークがWi-Fiになっている（LAN / Thunderbolt に戻す）

緊急回避（送信側負荷を下げる例）：
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 15 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 640 --height 480 --preview --print-fps --aruco-corner-ids 0,1,2,3
```

---

## ログを残す（現場で助かる）

原因究明用に「いつ・どのPCで・どの段階で」落ちたかを残す。

例：UDP受信ログ（受信PC）
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty | Tee-Object -FilePath .\udp_5005_log.txt
```

例：送信ログ（送信PC）
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --print-fps --aruco-corner-ids 0,1,2,3 | Tee-Object -FilePath .\sender_log.txt
```

---

## 終了手順（撤収 / 再起動のとき）

目的：次の起動で「どこから復旧すればいいか」を分かりやすくする。

**推奨の止め順**
1. Unity / sound を停止（受信ポートを掴んでいる場合がある）
2. TouchDesigner を停止（OSC/UDP出力を止める）
3. 受信PCの `udp_receiver.py` を停止（`Ctrl+C`）
4. 送信PCの `pc_hand_box_sender.py` / `pc_hand_box_debug_viewer.py` を停止（ウィンドウで `ESC`）
5. 最後に RealSense Viewer を閉じる（開きっぱなしだとカメラ占有になることがある）

**再起動で迷ったら**
- 「まずUDPが届いてるか」を復旧の基準にする → [受信PC：UDP受信の確認](#udp-recv-check)

---

<a id="送信pcd435iコマンド固定値"></a>
## 送信PC：D435iコマンド（固定値）

目的：当日の起動を迷わないように、実運用で使うコマンドを「固定値」でまとめる。

前提（このセクションの固定値）:
- model: `pc_sender/models/hand_landmarker.task`
- sender config: `pc_sender/config/endpoint.json`
- 実行場所: リポジトリルート `koten2026/`

### 0. 事前確認（1回だけ）
```powershell
cd C:\project\team_project\koten2026
.\.venv\Scripts\Activate.ps1
Test-Path .\pc_sender\models\hand_landmarker.task
Test-Path .\pc_sender\config\endpoint.json
python -c "import sys; print(sys.executable)"
```

### 1. D435i疎通確認（推奨）
```powershell
.\pc_sender\run_realsense_smoke_test.ps1
```

### 2. ArUco/手検出確認（送信PC）
```powershell
python .\pc_sender\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3
```

### 3. UDP送信開始（送信PC）

**推奨（平面ロックあり）**: 起動後マーカーが2秒間安定検出されたら平面を固定。以後マーカーを隠しても動き続ける。
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3 --aruco-lock-after-ms 2000
```

ロック出力例：起動後2秒ほどで `[aruco] plane locked after 2000 ms stable detection` と表示されたら完了。

フォールバック（ロックなし・従来の動作）：
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3
```

### 4. UDP受信確認（受信PC, 任意）
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty
```

### 5. トラブル時の最短切り分け（送信PC側）
1. RealSense ViewerでColorが映るか（USBが `3.x` か）
2. `.\pc_sender\run_realsense_smoke_test.ps1` が動くか
3. `pc_hand_box_debug_viewer.py` で `aruco_ok` が安定するか
4. `pc_hand_box_sender.py` の `fps/seq` が増え続けるか

### 6. D435i以外/複数台を使う場合
- RealSenseを複数台挿す場合だけ、`--rs-serial <SERIAL>` を追加して対象機を固定する

### 7. venvが使えない/`python` が見つからない場合
環境によって venv の場所や名前が異なることがあります。切り分けとして、venvの `python.exe` を明示して実行します。

例（リポジトリ直下の `.venv` を使う）：
```powershell
.\.venv\Scripts\python.exe .\pc_sender\app\pc_hand_box_sender.py --help
```
