# 開発の進め方（おすすめ手順）

目的：原因切り分けを簡単にし、現場で安定稼働する構成に寄せていく。

推奨：Unity側は「点群表示」→「手リグ」→「演出」の順で進める。

本番当日のチェック（現場用）は次に集約：
- `docs/runbook.md`

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
- 固定値コマンド集（本番用）：`docs/runbook.md`（「送信PC：D435iコマンド（固定値）」）

## 1. 計測フェーズ（送信PCのみ）→OK
目的：ArUco平面推定と手検出を安定させる（物理配置が9割）。

- 起動（デバッグ表示）：`pc_sender/app/pc_hand_box_debug_viewer.py`
- 合格の目安：
  - `aruco_ok=true` が常時に近い
  - `stale` が出ても短時間（例：数百ms）で戻る

メモ：
- マーカーは大きく、**白フチを確保**、照明は均一
- 黒フェルト、黒布、艶消し塗装など

## 2. 通信フェーズ（送信PC → TouchDesigner）→OK
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

## 3. OSCフェーズ（TouchDesigner → Unity）→OK
目的：Unity側は受信と可視化だけ先に完成させる（手リグはまだ）。TouchDesigner → Unity に 21点×3値=63 float値が届く → 全部点として表示するだけつまり通信のテスト。

参照：
- OSC出力仕様（アドレス・引数順）：`docs/requirements_touch.md` §7
- Unity側の受信仕様：`docs/requirements_unity.md` §2.1
- OSC受信ポート（仮）：`9000`（チームで確定後に更新）

### 3.1 前提（OSCアドレスとデータ形式を先に固定する）

推奨アドレス（`docs/requirements_touch.md` §7.2 より）：

| アドレス | 型 | 内容 |
|---|---|---|
| `/box/hand/left/lm3d/0` ~ `/62` | float×63ch | 左手21点（各1値。x0,y0,z0,...,x20,y20,z20） |
| `/box/hand/right/lm3d/0` ~ `/62` | float×63ch | 右手21点（同上） |
| `/box/hand/left/valid` | int (0/1) | 左手検出フラグ |
| `/box/hand/right/valid` | int (0/1) | 右手検出フラグ |

> **実装上の注意**：TD の OSC Out CHOP は1チャンネル=1 OSCメッセージ（1値）で送るため、63floatsを1メッセージで送ることが**できない**。`td_project/callbacks/script2_callbacks.py` では63個の独立チャンネル（各1サンプル）として出力している。Unity 側の `HandReceiver.cs` はこれを受信してバッファに蓄積し、`Update()` でまとめて適用する。

デバッグ用（任意）：
- `/box/aruco/ok`（int 0/1）
- `/box/aruco/stale`（int 0/1）
- `/box/aruco/age_ms`（int）

座標系：
- `x, y`：箱の正面平面の正規化座標（左上=(0,0), 右下=(1,1)）
- `z`：疑似深度（単眼推定、演出用。`z_like`）

### 3.2 TouchDesigner側：ノード構成と OSC Out の設定

上流に「JSONを受信してCHOPチャンネルを作る」ノードが必要。
全体の流れは次のとおり：

```
udpin1（UDP In DAT, port 5005）
    ↓ callbacks（udpin1_callbacks）で onReceive → parent().store()
script2（Script CHOP）← script2_callbacks の cook() で parent().fetch() → appendChan
    ↓
oscout1（OSC Out CHOP）→ Unity へ
```

> **注意**：途中に Script DAT を挟む必要はない。`udpin1_callbacks` の `onReceive` で直接 `parent().store()` し、`script2_callbacks` の `cook()` で `parent().fetch()` する。

#### ステップ1：UDP In DAT を追加
- **UDP In DAT**（`udpin1`）をネットワークに配置
- パラメータ：
  - `Network Port` = `5005`、`Active` = `On`
  - **`Row/Callback Format` = `One Per Message`**（デフォルトの `One Per Line` のままだとバイトが溜まって警告が出る）
- 送信PCが動いていれば DAT にJSONが流れてくる（右クリック → View で確認）

合格の目安：
- DATのテキストに `{"v":2,"kind":"box_plane",...}` が表示され更新され続ける

#### ステップ2：udpin1_callbacks に onReceive を記述

`udpin1` を選択 → パラメータ右上の Python アイコン → `udpin1_callbacks` を開き、以下のファイルの内容をコピーして貼り付ける：

→ `td_project/callbacks/udpin1_callbacks.py`

#### ステップ3：Script CHOP（script2）と script2_callbacks を追加

- **Script CHOP**（`script2`）をネットワークに配置（`udpin1` との入力接続は不要）
- `script2` を選択 → `script2_callbacks` を開き、以下のファイルの内容をコピーして貼り付ける：

→ `td_project/callbacks/script2_callbacks.py`

> **チャンネル名の `/` について**：TD の OSC Out CHOP はチャンネル名の前に `/` を自動で付加する。`appendChan` の引数に `/` を付けると `//box/...` になるので **付けない**。

生成されるチャンネル（`script2` に表示されること）：

| チャンネル名（TDでの表示） | OSCアドレス（送出） | 値の数 |
|---|---|---|
| `box/aruco/ok` | `/box/aruco/ok` | 1 |
| `box/aruco/stale` | `/box/aruco/stale` | 1 |
| `box/hand/left/valid` | `/box/hand/left/valid` | 1 |
| `box/hand/left/lm3d/0` ~ `box/hand/left/lm3d/62` | `/box/hand/left/lm3d/0` ~ `/62` | 各1（計63ch） |
| `box/hand/right/valid` | `/box/hand/right/valid` | 1 |
| `box/hand/right/lm3d/0` ~ `box/hand/right/lm3d/62` | `/box/hand/right/lm3d/0` ~ `/62` | 各1（計63ch） |

> **なぜ 63 個別チャンネルか？**：TD の OSC Out CHOP は「1チャンネル＝1 OSC メッセージ（1値）」で送出する。1チャンネルに63サンプルを入れても現在のタイムスライスの1値しか送られないため、63個の独立チャンネル（各1サンプル）にしている。

補足：`aruco.ok=false` のときは `lm_box3` が null になるので、Script 側で前フレームの値を保持（ホールド）する処理を入れると安定する（詳細は `docs/requirements_touch.md` §6）。

#### ステップ4：OSC Out CHOP を接続・設定
- **OSC Out CHOP**（`oscout1`）を `script2` の下流に接続
- パラメータ設定：
  - `Network Address`：UnityPCと同じPCなら `localhost`、別PCなら固定IP（例：`192.168.10.3`）
  - `Network Port`：`9000`（仮。Unity側と合わせる）
  - `Numeric Format`：`Float (32 bit)`
  - `Data Format`：`Time Slice`
  - `Cook Every Frame`：`On`

#### 合格の目安
- `oscout1` がクックしている（緑枠、警告なし）
- 手を動かしたとき `script2` の `box/hand/left/lm3d` チャンネルの値が変化している
- Unity 側でパケットが届いている（次のステップ §3.3 で確認）

TDプロジェクトファイルの保管先：`td_project/` フォルダ参照。

### 3.3 Unity側：OSC受信の実装（最小）

#### ステップ1：uOSC のインストール

1. Unity メニュー → **Window → Package Manager**
2. 左上の **＋** → **Add package from git URL...**
3. 以下を入力して Add：
   ```
   https://github.com/hecomi/uOSC.git#upm
   ```
4. インポート完了後、`uOSC` が Packages に表示されることを確認

#### ステップ2：シーンに OscServer を配置

1. Hierarchy で空の GameObject を作成 → 名前を `OscManager` にする
2. Inspector → **Add Component → uOSC → uOsc Server**
3. `OscServer` のパラメータ：
   - `Port`：`9000`
   - その他はデフォルトのまま

> **別PCで運用する場合**：Windows ファイアウォールで UDP `9000` の受信を許可する（`docs/requirements_network_pc_direct.md` §4.3 参照）。同一PCなら不要。

#### ステップ3：受信スクリプトの作成

以下のファイルを Unity プロジェクトの Assets フォルダにコピーして `OscManager` にアタッチする：

→ `unity_project/HandTrackingApp/Assets/scripts/HandReceiver.cs`

#### ステップ4：点群 GameObject の作成

1. Unity メニュー **koten2026 > Create Hand Points** を実行すると `LeftHand` / `RightHand` が自動生成される（Scale: 0.05、Transparent マテリアル付き）。手動で作る場合は Sphere × 21（Scale: 0.05程度）
2. 同様に `RightHand` を作成
3. `HandReceiver` の `Left Points` 配列に `LeftHand` の子21個をドラッグ、`Right Points` に `RightHand` の子21個をドラッグ
4. `Left Renderers` / `Right Renderers` にも同じ Sphere の `MeshRenderer` を登録
5. Sphere のマテリアルを Transparent（URP なら `Surface Type = Transparent`）に設定

> Sphere でなく `GL.LINES` や `LineRenderer` で骨格を引いても良い。まずは点だけで動作確認する。

#### ステップ5：動作確認

1. Unity Play ボタンを押す
2. TouchDesigner の送信が動いている状態で、手をカメラに向ける
3. Hierarchy の `LeftHand` 下の Sphere が動けば受信成功
4. Console にエラーが出る場合：
   - `uOSC.OscServer が見つからない` → `OscManager` に `OscServer` コンポーネントがアタッチされているか確認
   - 受信できない → `oscout1` の `Network Address` が Unity PC の IP（同一PCなら `127.0.0.1`）になっているか確認

#### ランドマーク対応（主要インデックス）

| インデックス | 部位 |
|---|---|
| 0 | 手首 |
| 4 | 親指先端 |
| 8 | 人差し指先端 |
| 12 | 中指先端 |
| 16 | 薬指先端 |
| 20 | 小指先端 |

全21点の定義は [MediaPipe Hand Landmarks](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker) 参照。

#### 補足：z（z_like）の扱い

- `z_like` は単眼推定による疑似深度でノイズが多い
- 点群表示では `* 0.1f` 程度にスケールを抑えて演出用として使う
- 関節角の計算には使わない（x,y のみ使用）
- Unity 側でも EMA 平滑化推奨：`smoothZ = Mathf.Lerp(smoothZ, rawZ, 0.4f)`

### 3.4 合格の目安

| 確認項目 | 合格条件 |
|---|---|
| TouchDesigner でOSCが送信されている | `OSC Out CHOP` がクックしており値が変化している |
| Unity でランドマーク点群が動く | 手を動かすと点群が追従する |
| valid=0 でフェードアウトする | 手を隠したとき点群がフェードして消える |
| 左右が入れ替わらない | 左穴の手が常に左の点群に出る |
| `aruco.ok=false` でもクラッシュしない | 点群がホールド→フェードで安定する |

## 4. リグ・演出フェーズ（Unity）
目的：点群で安定した後に、手モデルへ落とす。ここでその 63 float値のうち、どの点をどう使うかを決める（2点 or 21点）。

OSC仕様の変更は不要（`lm3d` の63値はそのまま）。Unity側でどの点を使うかだけ変える。

### 4.1 ステップ1：2点（手首＋人差し指先）→ 指さし手CG回転
実装コスト：低〜中（1〜2日）

```
手首     = lm3d[index=0]  → CG の位置
人差し指先 = lm3d[index=8]  → 方向ベクトルの終点
方向     = lm[8].pos - lm[0].pos → LookAt でこの向きに回転
```

できること：
- 手を左右・上下に傾けると CG も同じ向きに回転する（**体験の核心が成立する**）
- 手全体を移動すると CG も追従する
- `z_like`（index=0 の z）で前後移動も表現できる（精度は演出レベル）

できないこと：指の曲げ伸ばし・親指の開閉（21点が必要）

#### Blenderでのモデル作成ポイント（👉用）

ポーズ（形状）：
- **人差し指を伸ばし、他の指を曲げた「指さし」ポーズで静止した状態**で作る（ボーン不要）
- ポーズはモデルに焼き込む（ステップ1ではアニメーション・リグは不要）

原点（ピボット）の位置 ── 最重要：
- **手首の位置に原点を置く**（`lm3d[0]` の座標をそのまま position に使うため）
- Blender で `Object > Set Origin > Origin to ...` で調整、またはモデルを手首が原点に来るよう移動して `Apply All Transforms`

向き ── LookRotation が正しく効くための条件：
- **人差し指が伸びている方向 = Blender の -Y 方向**（Unity に持ち込むと +Z 方向 = forward になる）
- 手の甲が上（Blender の +Z 方向 = Unity の +Y 方向）
- ずれていると `LookRotation` したときにモデルが横や後ろを向く → Blender 側で直すか Unity で `localRotation` オフセットを加える

エクスポート前に必ずやること：
- `Ctrl+A` → **Apply All Transforms**（Scale/Rotation を適用してから FBX/glTF 出力）

#### Unityでの実装例

```csharp
Vector3 wristPos   = points[0].localPosition;   // lm3d index 0
Vector3 tipPos     = points[8].localPosition;   // lm3d index 8
Vector3 dir        = (tipPos - wristPos).normalized;
handModel.position = wristPos;
handModel.rotation = Quaternion.LookRotation(dir, Vector3.up);
```

合格の目安：
- 手を上下左右に傾けると hand CG が追従して回転する
- 手を隠すと valid=0 でフェードアウトする

### 4.2 ステップ2（任意）：21点 → 指のボーン駆動
実装コスト：高（数日〜1週間）

体験上「指を曲げる/開く」演出が必要になった段階で着手する。

進め方：
- 各指 3点（MCP→PIP→DIP→TIP）から2ベクトルを作り、関節角を計算してボーン回転に落とす
- まず人差し指（index 5→6→7→8）1本だけ動かして感触を確認
- 安定したら全指（5本）へ展開
- IK / LookAt / ボーン直接回転のどれを使うかはモデル構造に依存

注意：
- `z_like` はノイズが出やすいため、関節角の計算には `x,y` だけ使う方が安定しやすい
- `z_like` は演出用（前後ふわっとした動き）に強め平滑化・レンジ制限して使う（計測用途にしない）

## 5. 運用テスト（本番想定）
目的：再現性のある「チェックリスト」で最後に潰し込む。

- 起動手順を固定（コマンド、ポート、IP、OS設定）
- 監視項目（例）：FPS、`seq` 欠損、`aruco_ok/stale`、valid率、左右入れ替わり回数
