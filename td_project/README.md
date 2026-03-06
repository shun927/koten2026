# TouchDesigner プロジェクト

## ファイル構成

```
td_project/
  README.md           ← このファイル
  koten2026.toe       ← TDプロジェクトファイル（TDで保存したもの）
  callbacks/
    udpin1_callbacks.py   ← udpin1_callbacks の内容（バックアップ）
    script2_callbacks.py  ← script2_callbacks の内容（バックアップ）
```

> `.toe` ファイルはバイナリなので git diff が効かない。
> コールバックの Python コードは `callbacks/` フォルダにテキストとして保管しておく。

---

## ノード構成

```
udpin1（UDP In DAT）
    port: 5005
    Row/Callback Format: One Per Message
    ↓
udpin1_callbacks（callbacks/udpin1_callbacks.py）
    onReceive → parent().store('hand_data', data)
script2（Script CHOP）
    ↑ script2_callbacks（callbacks/script2_callbacks.py）
    cook() → parent().fetch('hand_data') → appendChan
    ↓
oscout1（OSC Out CHOP）
    Network Address: localhost（同一PC）or Unity PCのIP
    Network Port: 9000
    Numeric Format: Float (32 bit)
    Data Format: Time Slice
    Cook Every Frame: On
```

---

## OSCアドレス一覧

| OSCアドレス | 型 | 値の数 | 内容 |
|---|---|---|---|
| `/box/hand/left/lm3d/0` ～ `/62` | float | 各1（計63ch） | 左手21点 (x0,y0,z0,...,x20,y20,z20) |
| `/box/hand/right/lm3d/0` ～ `/62` | float | 各1（計63ch） | 右手21点（同上） |
| `/box/hand/left/valid` | int | 1 | 左手検出フラグ (0/1) |
| `/box/hand/right/valid` | int | 1 | 右手検出フラグ (0/1) |
| `/box/aruco/ok` | int | 1 | ArUco検出フラグ (0/1) |
| `/box/aruco/stale` | int | 1 | ArUcoステール中フラグ (0/1) |

> **なぜ個別チャンネルか**：TD の OSC Out CHOP は1チャンネル=1 OSCメッセージ（1値）で送出するため、`script2_callbacks.py` で63個の独立チャンネルを生成している。

---

## 起動手順

1. 送信PCで `pc_hand_box_sender.py` を起動（port 5005 へ送信）
2. TouchDesigner を開き `koten2026.toe` をロード
3. `udpin1` に JSON が流れていることを確認（View で行数が増える）
4. `script2` に 132チャンネル（aruco×2 + left/right の valid×2 + lm3d×63×2）が表示されていることを確認
5. `oscout1` が緑枠でクックしていることを確認

詳細は `docs/development_workflow.md` §3.2 参照。
