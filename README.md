# koten2026（設計メモ）

このリポジトリは、Raspberry Pi 4 + Camera Module V2 で「人差し指先端の相対3D」を推定し、PCへUDP送信するための設計メモです（現状は設計のみ）。

## ファイル構造（予定）
```text
koten2026/
  README.md
  .gitignore
  hand_landmarker.task
  docs/
    requirements_raspberrypi.md
    requirements_message_format.md
  pi_project/                    # Piへ配置する一式（実装開始時に追加）
    app/pi_hand_sender.py        # Pi側：推論→UDP送信
    systemd/koten2026.service    # Pi常駐
  pc_receiver/                   # PC側：UDP受信（必要なら）
    udp_receiver.py
```

