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

## 3. OSCフェーズ（TouchDesigner → Unity）
目的：Unity側は受信と可視化だけ先に完成させる（手リグはまだ）。TouchDesigner → Unity に 63 floats 届く → 全部点として表示するだけつまり通信のテスト。

参照：
- OSC出力仕様（アドレス・引数順）：`docs/requirements_touch.md` §7
- Unity側の受信仕様：`docs/requirements_unity.md` §2.1
- OSC受信ポート（仮）：`9000`（チームで確定後に更新）

### 3.1 前提（OSCアドレスとデータ形式を先に固定する）

推奨アドレス（`docs/requirements_touch.md` §7.2 より）：

| アドレス | 型 | 内容 |
|---|---|---|
| `/box/hand/left/lm3d` | 63 floats | 左手21点 (x0,y0,z0,...,x20,y20,z20) |
| `/box/hand/right/lm3d` | 63 floats | 右手21点（同上） |
| `/box/hand/left/valid` | int (0/1) | 左手検出フラグ |
| `/box/hand/right/valid` | int (0/1) | 右手検出フラグ |

デバッグ用（任意）：
- `/box/aruco/ok`（int 0/1）
- `/box/aruco/stale`（int 0/1）
- `/box/aruco/age_ms`（int）

座標系：
- `x, y`：箱の正面平面の正規化座標（左上=(0,0), 右下=(1,1)）
- `z`：疑似深度（単眼推定、演出用。`z_like`）

### 3.2 TouchDesigner側：OSC Out の設定

1. **OSC Out CHOP** を追加
   - 宛先IP：UnityPCと同じPCなら `127.0.0.1`、別PCなら固定IP（例：`192.168.10.3`）
   - 宛先ポート：`9000`（仮。Unity側と合わせる）
2. `/box/hand/left/lm3d` に 63 floats を1メッセージで送る（右手も同様）
3. `/box/hand/left/valid` に int (0/1) を送る
4. デバッグ用に `/box/aruco/ok` も送ると Unity 側の切り分けが楽

合格の目安（TouchDesigner）：
- `OSC Out CHOP` がクックしている
- 手を動かしたとき `/box/hand/left/lm3d` の値が変化している

### 3.3 Unity側：OSC受信の実装（最小）

#### OSCライブラリの選択
Unity で OSC を受けるには外部ライブラリが必要。候補：
- **uOSC**（推奨）：Package Manager から導入可。メインスレッドへの橋渡しが容易
- **OscJack**：軽量。`AddressHandler` でアドレスごとにコールバックを登録する方式

#### 受信ポートの設定
- OSCサーバーの受信ポートを `9000`（仮）に設定
- **別PCで運用する場合**は WindowsファイアウォールでUDP `9000` を許可（`docs/requirements_network_pc_direct.md` §4.3 参照）
- 同一PCなら `127.0.0.1` で受けるためファイアウォール不要

#### 63 floats → 21点への分解

```csharp
// 例（uOSC想定）
void OnDataReceived(string address, OscMessage message)
{
    if (address == "/box/hand/left/lm3d")
    {
        // 63 floats → 21点 (x, y, z) に分解
        // 注意: uOSC の values は object[] で float が double で届くことがある
        //       (float)(double) とキャストするのが安全
        for (int i = 0; i < 21; i++)
        {
            float x = (float)(double)message.values[i * 3];
            float y = (float)(double)message.values[i * 3 + 1];
            float z = (float)(double)message.values[i * 3 + 2];
            // x,y は 0..1 の箱平面座標
            // y は箱座標系で下方向が+なので Unity の座標系に合わせて反転
            points[i].localPosition = new Vector3(x, 1f - y, z);
        }
    }
    if (address == "/box/hand/left/valid")
    {
        bool valid = (int)message.values[0] == 1;
        SetHandVisible(valid);
    }
}
```

ランドマーク対応（主要インデックス）：
- `0`：手首
- `8`：人差し指先端
- `4`：親指先端
- `12`：中指先端
- 全21点の定義は MediaPipe Hand Landmarks 参照

ポイント：
- `z`（`z_like`）はノイズが出やすいので Unity 側でも EMA 平滑化推奨（alpha: 0.5 程度から調整）
- `x,y` も平滑化する場合、TouchDesigner 側と二重にかかるので alpha を弱めに（0.2〜0.4）

#### valid=0 のフェードアウト
- `valid=0` になったら Material の alpha をランプで下げてフェードアウト
- EMA や Lerp を挟むと自然な消え方になる（突然消えない）
- 受信が途切れた場合に備えて、Unity 側でも「最終受信から N ms 経ったら valid=0 扱い」にするとより安全

### 3.4 合格の目安

| 確認項目 | 合格条件 |
|---|---|
| TouchDesigner でOSCが送信されている | `OSC Out CHOP` がクックしており値が変化している |
| Unity でランドマーク点群が動く | 手を動かすと点群が追従する |
| valid=0 でフェードアウトする | 手を隠したとき点群がフェードして消える |
| 左右が入れ替わらない | 左穴の手が常に左の点群に出る |
| `aruco.ok=false` でもクラッシュしない | 点群がホールド→フェードで安定する |

## 4. リグ・演出フェーズ（Unity）
目的：点群で安定した後に、手モデルへ落とす。ここでその 63 floats のうち、どの点をどう使うかを決める（2点 or 21点）。

OSC仕様の変更は不要（`lm3d` 63 floats はそのまま）。Unity側でどの点を使うかだけ変える。

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
