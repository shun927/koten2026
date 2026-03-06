# Unity プロジェクト

## ファイル構成

```
unity_project/
  README.md           ← このファイル
  HandTrackingApp/
    Assets/
      scripts/
        HandReceiver.cs         ← OSC受信・点群表示スクリプト
        HandPointsGenerator.cs  ← エディタメニューから点群GameObject生成
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
- Unity メニュー **koten2026 > Create Hand Points** で `LeftHand` / `RightHand` を自動生成（Scale: 0.05、Transparent マテリアル付き）
  - `HandReceiver` の `Left/Right Points` と `Left/Right Renderers` も自動登録される

### 3. OSC 受信アドレス一覧

| アドレス | 型 | 値の数 | 内容 |
|---|---|---|---|
| `/box/hand/left/lm3d/0` ～ `/62` | float | 各1（計63ch） | 左手21点 (x0,y0,z0,...,x20,y20,z20) |
| `/box/hand/right/lm3d/0` ～ `/62` | float | 各1（計63ch） | 右手21点 |
| `/box/hand/left/valid` | int | 1 | 左手検出フラグ (0/1) |
| `/box/hand/right/valid` | int | 1 | 右手検出フラグ (0/1) |

### 4. 座標系
- `x, y`：箱正面の正規化座標（左上=0,0 / 右下=1,1）
- `y` は Unity 座標系に合わせて `1f - y` で反転して使う
- `z`：疑似深度（演出用、ノイズ多め）

詳細は `docs/development_workflow.md` §3.3 参照。
