# Pi Project (Runtime)

This folder is the Raspberry Pi runtime project. Copy it to the Pi and run the sender.

## Layout
- `app/pi_hand_sender.py`: Pi sender (MediaPipe → UDP JSON)
- `config/endpoint.example.json`: example config
- `systemd/koten2026.service`: systemd unit template

## Required Files
- `hand_landmarker.task` in the project root (same level as `app/`)

## Quick Start (Pi)
```bash
cd /home/pi/koten2026
python3 app/pi_hand_sender.py --config config/endpoint.json --model ./hand_landmarker.task
```

## Config
Copy `config/endpoint.example.json` to `config/endpoint.json` and edit:
```json
{
  "dest_ip": "192.168.10.1",
  "dest_port": 5005,
  "camera": { "device": "picamera2", "width": 640, "height": 480, "fps": 30 },
  "model_path": "./hand_landmarker.task",
  "alpha": 0.75
}
```
