# Unity プロジェクト

## ファイル構成

```
unity_project/
  README.md           ← このファイル
  HandTrackingApp/
    Assets/
      scripts/
        HandReceiver.cs         ← OSC受信・2点表示スクリプト
        HandPointsGenerator.cs  ← エディタメニューから2点GameObject生成
```

---

## セットアップ手順

### 1. uOSC インストール
- Window → Package Manager → ＋ → Add package from git URL
- `https://github.com/hecomi/uOSC.git#upm`

### 2. シーン構成
- 空の GameObject `OscManager` を作成
  - `OscServer` コンポーネントを追加（Port: 9000）
  - `HandReceiver.cs` をアタッチ
- Unity メニュー **koten2026 > Create Hand Points** で `LeftHand` / `RightHand` の `wrist` と `index_tip` を自動生成
  - `HandReceiver` の参照と `Left/Right Renderers` も自動登録される

### 3. OSC 受信アドレス一覧

| アドレス | 型 | 値の数 | 内容 |
|---|---|---|---|
| `/box/hand/left/wrist` | float,int | 4 | 左手首 (`x y z valid`) |
| `/box/hand/left/index_tip` | float,int | 4 | 左人差し指先 (`x y z valid`) |
| `/box/hand/right/wrist` | float,int | 4 | 右手首 (`x y z valid`) |
| `/box/hand/right/index_tip` | float,int | 4 | 右人差し指先 (`x y z valid`) |

### 4. 座標系
- `x, y`：箱正面の正規化座標（左上=0,0 / 右下=1,1）
- `y` は Unity 座標系に合わせて `1f - y` で反転して使う
- `z`：疑似深度（演出用、ノイズ多め）

詳細は `docs/development_workflow.md` §3.3 参照。
