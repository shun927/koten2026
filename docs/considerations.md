# 検討事項メモ（本番運用）

このファイルは、現行構成（2台直結・PC送信）で本番前に確認する検討事項をまとめたものです。

## 0. 作品内容（体験設計）
- 体験者が「指を入れる行為」と、映像・音の変化が直感的につながるか
- 左右の穴で役割差を作るか（同効果 or 別効果）
- 指の位置変化を「何に対応させるか」（映像の移動/変形、音色/音量/空間）
- 反応の速さと安定のバランス（気持ちよさ優先か、静けさ優先か）
- 未検出時の演出（急停止ではなく、保持・フェード・余韻のどれにするか）

## 1. 構成と責務
- 送信PC（台下）：`pc_sender` + カメラ入力
- TouchDesigner PC（操作PC）：UDP受信、座標処理、OSC送信
- Unity/sound：必要に応じて送信PCまたは別PCで受信

## 1.x. 2台運用 / 3台運用の検討（構成選定）
本番の安定性を優先し、まずは2台運用で成立するかを確認し、負荷や運用要件で必要なら3台運用へ拡張する。

### A) 2台運用（最小構成）
- 台下PC（作品専用）：`pc_sender` + RealSense D435i（Python処理のみ）
- 自分PC（統合）：TouchDesigner（UDP受信→座標処理→OSC送信） + Unity + sound（OSC受信）

通信：
- 台下PC → 自分PC：UDP/JSON `5005`
- 自分PC内：touch → Unity/sound（可能なら `127.0.0.1` 宛てOSC）

メリット：
- 配線/ネットワークが最小（トラブル箇所が少ない）
- Unity/sound宛OSCがローカルで安定（遅延/ロスが最小）
- 切り分けが簡単（台下はPythonだけ）

デメリット/注意：
- 自分PCに負荷が集中（TouchDesigner + Unity + sound）
- GPU/音周りの負荷でフレーム落ちした場合、原因切り分けが必要

向いている条件：
- 自分PCに十分なGPU/CPU余力がある
- 構成を増やしたくない（本番の事故要因を減らす）

### B) 3台運用（負荷分散構成）
- 台下PC（作品専用）：`pc_sender` + RealSense D435i（Python処理のみ）
- 自分PC（TouchDesigner）：TouchDesigner（統合ハブ）
- Unity/sound PC（出力）：Unity + sound（OSC受信、演出出力）

通信：
- 台下PC → TouchDesigner PC：UDP/JSON `5005`
- TouchDesigner PC → Unity/sound PC：OSC/UDP（Unity/sound側の受信ポートを固定して許可）

ネットワーク要件：
- 3台は「PCをハブ化（ブリッジ/ICS）」より、スイッチ（ハブ）で同一LAN推奨
- 固定IP例：
  - 台下PC：`192.168.10.1/24`
  - TouchDesigner PC：`192.168.10.2/24`
  - Unity/sound PC：`192.168.10.3/24`

メリット：
- 役割分離で負荷を分散（映像/音の安定性が上がりやすい）
- Unity/sound側の調整・再起動がTouchDesignerと独立

デメリット/注意：
- 機材・配線・設定（IP/ポート/Firewall）が増えて事故要因が増える
- OSC経路がネットワーク越しになるため、疎通確認と本番前チェックが必須

向いている条件：
- 自分PCが既に重く、2台だとフレームが安定しない
- Unity側のGPU負荷が高い、または音のI/Oを別PCに寄せたい

### 選定の判断基準（先に決める）
- まず2台で成立するなら2台（シンプルさ＝本番安定）
- 2台でフレーム落ち/音切れ/操作遅延が出るなら3台へ
- どちらでも、ポート番号とOSCアドレスは固定（`docs/requirements_touch.md` 準拠）
- 本番前チェックに「UDP受信（`5005`）」「OSC受信（Unity/sound側）」を必ず含める

## 2. ネットワーク
- 2台直結は固定IPで統一（例：`192.168.10.1` / `192.168.10.2`）
- TouchDesigner受信ポート `5005/UDP` の許可
- OSC受信側ポートの許可
- 開演前に `ping` と実UDP受信で疎通確認

## 3. 送信安定化
- カメラ未取得時の自動再接続（実装済み）
- `valid=false` 心拍メッセージ送信でロスト判定を明確化
- FPS、`valid`率、`seq` の監視ログを確認

## 4. リスクと対策
- 黒画面: RealSense ViewerでColor確認、USB3直挿し、`--rs-serial`固定で起動
- カメラ占有: Zoom/Teams/ブラウザを終了
- 長時間運用: 自動起動設定（タスクスケジューラ）と再起動手順を用意
- 誤操作: 本番時はTouchDesigner PC以外で開発作業しない

## 5. 依存管理
- Pythonは `3.12`（64bit）を基準
- `requirements.txt` は実績バージョンへ固定
- 本番前にクリーンなvenvで再インストール確認

## 6. 開演前チェックリスト
1. モデル配置 `pc_sender/models/hand_landmarker.task`
2. `endpoint.json` のIP/ポート確認
3. カメラプレビュー確認（`pc_sender/app/pc_hand_box_debug_viewer.py`）
4. UDP受信確認（`pc_receiver/udp_receiver.py`）
5. TouchDesigner左右判定/ロスト挙動確認
6. Unity/soundのOSC受信確認
