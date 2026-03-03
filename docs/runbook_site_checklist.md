# 現場チェック（1枚）: 送信PC → TouchDesigner → Unity/sound

目的：会場で「どこが詰まっているか」を最短で切り分け、起動を迷わないようにする。

前提：
- 2台直結のネットワーク要件は `docs/requirements_network_pc_direct.md` を参照
- TouchDesignerの実装要件は `docs/requirements_touch.md` を参照
- `python` が venv を指していること（PowerShellプロンプトに `(koten2026)` が出ている状態が目安）

---

## 0) 役割（2台運用の標準）
- 送信PC（台下）：RealSense D435i → `pc_sender`（UDP/JSON `5005`）
- 受信PC（操作PC）：TouchDesigner（UDP受信→座標処理→OSC送信） + Unity/sound（同一PCならOSCは `127.0.0.1` 推奨）

---

## 1) ネットワーク（直結）
受信側（TouchDesigner PC）で確認：
```powershell
Get-NetConnectionProfile
```
- 直結LAN（イーサネット）の `NetworkCategory` は `Private` 推奨

疎通（任意）：
```powershell
ping 192.168.10.1
ping 192.168.10.2
```

---

## 2) Windowsファイアウォール（受信側）
受信側（TouchDesigner PC）で、UDP `5005` の受信を許可する。
手順は `docs/requirements_network_pc_direct.md` の「4. Windowsファイアウォール（重要）」を参照。

---

## 3) `endpoint.json`（送信先IP）
送信PCで、`pc_sender/config/endpoint.json` の `host` が受信PC（TouchDesigner PC）のIPになっていることを確認。
（例：2台直結なら `192.168.10.2`）

---

## 4) 送信PC：D435iの最短切り分け
1) Viewerで Color が映る（USBが `3.x`）
2) スモークテスト（Color/Depth）
```powershell
.\pc_sender\run_realsense_smoke_test.ps1
```
3) ArUco/手検出（プレビュー）
```powershell
python .\pc_sender\app\pc_hand_box_debug_viewer.py --source realsense --rs-fps 30 --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --flip --aruco-corner-ids 0,1,2,3
```
4) UDP送信開始（`seq` が増え続ける）
```powershell
python .\pc_sender\app\pc_hand_box_sender.py --source realsense --rs-fps 30 --config .\pc_sender\config\endpoint.json --model .\pc_sender\models\hand_landmarker.task --width 1280 --height 720 --preview --print-fps --aruco-corner-ids 0,1,2,3
```

補足：
- `--rs-serial` は **複数台のRealSenseを挿す場合だけ**使う（取り違え防止）

---

## 5) 受信PC：UDP受信の確認（TouchDesignerを開く前）
受信PCで次を実行して、JSONが流れてくることを確認：
```powershell
python .\pc_receiver\udp_receiver.py --bind 0.0.0.0 --port 5005 --pretty
```

合格の目安：
- `seq` が増え続ける
- `aruco.ok=true` が安定（多少 `stale=true` は許容）
- `hands: []` でも「通信」自体の確認はできる（次段で手検出を詰める）

---

## 6) TouchDesigner：作品側の確認
- `seq` 欠損（`seq jump`）が常発しない
- ロスト時の挙動（ホールド→フェード→無効）が想定通り
- 左右割り当てが入れ替わらない

---

## 7) Unity/sound：OSC受信
- 同一PC運用なら、TouchDesignerのOSC送信先は `127.0.0.1` 推奨
- 別PC運用なら、Unity/sound 側で受信ポートを固定し、ファイアウォールで受信許可する

---

## 8) 最短トラブルシュート（どこで止まっているか）
1. 送信PC：Viewer/スモークテストが通るか（カメラ問題の切り分け）
2. `pc_hand_box_debug_viewer.py` で `aruco_ok` / `hands` が出るか（計測問題）
3. 受信PC：`udp_receiver.py` で `seq` が増えるか（ネットワーク/FW問題）
4. TouchDesigner内でロスト処理/OSCが出るか（touch問題）
5. Unity/soundがOSCを受けるか（受信ポート/FW/宛先問題）

