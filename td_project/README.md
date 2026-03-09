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
    Network Address: 127.0.0.1
    Network Port: 9000
    Numeric Format: Float (32 bit)
    Data Format: Time Slice
    Cook Every Frame: On
```

---

## OSCアドレス一覧

| OSCアドレス | 型 | 値の数 | 内容 |
|---|---|---|---|
| `/box/hand/left/wrist` | float,int | 4 | 左手首 (`x y z valid`) |
| `/box/hand/left/index_tip` | float,int | 4 | 左人差し指先 (`x y z valid`) |
| `/box/hand/right/wrist` | float,int | 4 | 右手首 (`x y z valid`) |
| `/box/hand/right/index_tip` | float,int | 4 | 右人差し指先 (`x y z valid`) |
| `/box/finger/left` | float,int | 4 | 互換用の左人差し指先 (`x y z valid`) |
| `/box/finger/right` | float,int | 4 | 互換用の右人差し指先 (`x y z valid`) |
| `/box/aruco/ok` | int | 1 | ArUco検出フラグ (0/1) |
| `/box/aruco/stale` | int | 1 | ArUcoステール中フラグ (0/1) |

---

## 起動手順

1. 送信PCで `pc_hand_box_sender.py` を起動（port 5005 へ送信）
2. TouchDesigner を開き `koten2026.toe` をロード
3. `udpin1` に JSON が流れていることを確認（View で行数が増える）
4. `script2` に `wrist` / `index_tip` / `finger` / `aruco` のチャンネルが表示されていることを確認
5. `oscout1` が緑枠でクックしていることを確認

詳細は `docs/development_workflow.md` §3.2 参照。
