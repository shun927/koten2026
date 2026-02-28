from __future__ import annotations

import argparse
import json
import math
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __sub__(self, other: "Vec3") -> "Vec3":
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __truediv__(self, s: float) -> "Vec3":
        return Vec3(self.x / s, self.y / s, self.z / s)

    def to_list(self) -> list[float]:
        return [float(self.x), float(self.y), float(self.z)]


def _norm(v: Vec3) -> float:
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


def _load_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pi: MediaPipe hand → UDP JSON (relative 3D).")
    parser.add_argument("--config", help="Path to config JSON")
    parser.add_argument("--dest-ip", help="Destination PC IP")
    parser.add_argument("--dest-port", type=int, help="Destination UDP port")
    parser.add_argument(
        "--camera",
        help="Camera device: OpenCV index (e.g. 0) or 'picamera2' for Pi Camera Module",
    )
    parser.add_argument("--width", type=int, help="Capture width")
    parser.add_argument("--height", type=int, help="Capture height")
    parser.add_argument("--fps", type=int, help="Capture FPS")
    parser.add_argument("--model", help="Path to hand_landmarker.task")
    parser.add_argument("--max-hands", type=int, help="Max hands")
    parser.add_argument("--alpha", type=float, help="EMA alpha (0 disables)")
    parser.add_argument("--print-fps", action="store_true", help="Print sender FPS")
    return parser.parse_args()


class _FrameSource:
    def read_rgb(self) -> Any | None:
        raise NotImplementedError

    def close(self) -> None:
        return


class _OpenCvSource(_FrameSource):
    def __init__(self, camera_index: int, width: int, height: int, fps: int) -> None:
        import cv2  # type: ignore

        self._cv2 = cv2
        self._cap = cv2.VideoCapture(camera_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Camera open failed: index={camera_index}")

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS, fps)

    def read_rgb(self) -> Any | None:
        ok, frame_bgr = self._cap.read()
        if not ok:
            return None
        return self._cv2.cvtColor(frame_bgr, self._cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        self._cap.release()


class _Picamera2Source(_FrameSource):
    def __init__(self, width: int, height: int, fps: int) -> None:
        # Prefer the native Pi camera path. This requires Raspberry Pi OS + libcamera.
        from picamera2 import Picamera2  # type: ignore

        self._cam = Picamera2()
        config = self._cam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self._cam.configure(config)
        try:
            # Best-effort FPS control; depends on camera/driver.
            self._cam.set_controls({"FrameRate": fps})
        except Exception:
            pass
        self._cam.start()

    def read_rgb(self) -> Any | None:
        # Returns an RGB numpy array (H, W, 3).
        return self._cam.capture_array()

    def close(self) -> None:
        try:
            self._cam.stop()
        finally:
            self._cam.close()


def main() -> int:
    args = _parse_args()
    cfg = _load_json(args.config)

    dest_ip = args.dest_ip or cfg.get("dest_ip") or "192.168.10.1"
    dest_port = int(args.dest_port or cfg.get("dest_port") or 5005)
    camera_cfg = cfg.get("camera") or {}
    camera_device = args.camera if args.camera is not None else camera_cfg.get("device", 0)
    width = int(args.width or camera_cfg.get("width") or 640)
    height = int(args.height or camera_cfg.get("height") or 480)
    fps = int(args.fps or camera_cfg.get("fps") or 30)
    model_path = args.model or cfg.get("model_path") or "./hand_landmarker.task"
    max_hands = int(args.max_hands or cfg.get("max_hands") or 1)
    alpha = float(args.alpha if args.alpha is not None else cfg.get("alpha", 0.0))

    import mediapipe as mp  # type: ignore
    from mediapipe.tasks.python import BaseOptions  # type: ignore
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions  # type: ignore
    from mediapipe.tasks.python.vision import RunningMode  # type: ignore

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = (dest_ip, dest_port)

    if isinstance(camera_device, str) and camera_device.lower() in {"picamera2", "picam", "pi"}:
        source: _FrameSource = _Picamera2Source(width=width, height=height, fps=fps)
    else:
        camera_index = int(camera_device)
        source = _OpenCvSource(camera_index=camera_index, width=width, height=height, fps=fps)

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.VIDEO,
        num_hands=max_hands,
    )

    seq = 0
    ema_by_hand_index: dict[int, Vec3] = {}
    frames = 0
    last_fps_print = time.time()

    with HandLandmarker.create_from_options(options) as landmarker:
        try:
            while True:
                frame_rgb = source.read_rgb()
                if frame_rgb is None:
                    continue

            frames += 1
            now = time.time()
            if args.print_fps and now - last_fps_print >= 2.0:
                fps_now = frames / (now - last_fps_print)
                print(f"FPS~ {fps_now:.1f}")
                frames = 0
                last_fps_print = now

            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            # Use monotonic time for MediaPipe timestamps to avoid issues if wall clock jumps.
            t_mp_ms = int(time.monotonic() * 1000)
            t_ms = int(now * 1000)

            result = landmarker.detect_for_video(mp_image, t_mp_ms)

            world = getattr(result, "hand_world_landmarks", None) or []
            image_landmarks = getattr(result, "hand_landmarks", None) or []
            handedness = getattr(result, "handedness", None) or []

            # Send one message per detected hand (up to max_hands).
            send_count = min(len(world), max_hands)
            for hand_index in range(send_count):
                msg = {
                    "v": 1,
                    "t_ms": t_ms,
                    "seq": seq,
                    "src": "pi",
                    "hand_index": hand_index,
                    "hand": "Unknown",
                    "conf": 0.0,
                    "tip_img": [0.0, 0.0],
                    "tip_rel": [0.0, 0.0, 0.0],
                    "tip_norm": [0.0, 0.0, 0.0],
                    "scale": 0.0,
                    "valid": False,
                }
                seq += 1

                hw = world[hand_index]
                wrist = Vec3(hw[0].x, hw[0].y, hw[0].z)
                tip = Vec3(hw[8].x, hw[8].y, hw[8].z)
                mcp5 = Vec3(hw[5].x, hw[5].y, hw[5].z)
                mcp17 = Vec3(hw[17].x, hw[17].y, hw[17].z)

                tip_rel = tip - wrist
                scale = _norm(mcp5 - mcp17)
                if scale > 1e-6:
                    tip_norm = tip_rel / scale
                    if alpha and 0.0 < alpha < 1.0:
                        prev = ema_by_hand_index.get(hand_index)
                        if prev is None:
                            ema_by_hand_index[hand_index] = tip_norm
                        else:
                            a = alpha
                            ema_by_hand_index[hand_index] = Vec3(
                                a * prev.x + (1.0 - a) * tip_norm.x,
                                a * prev.y + (1.0 - a) * tip_norm.y,
                                a * prev.z + (1.0 - a) * tip_norm.z,
                            )
                        tip_norm_out = ema_by_hand_index[hand_index]
                    else:
                        tip_norm_out = tip_norm

                    msg["tip_rel"] = tip_rel.to_list()
                    msg["tip_norm"] = tip_norm_out.to_list()
                    msg["scale"] = float(scale)
                    msg["valid"] = True

                # Normalized image-space tip position (0..1). Useful for left/right assignment in TouchDesigner.
                if hand_index < len(image_landmarks):
                    hl = image_landmarks[hand_index]
                    msg["tip_img"] = [float(hl[8].x), float(hl[8].y)]

                if hand_index < len(handedness) and len(handedness[hand_index]) > 0:
                    label = getattr(handedness[hand_index][0], "category_name", None)
                    if isinstance(label, str) and label:
                        msg["hand"] = label
                    score = getattr(handedness[hand_index][0], "score", None)
                    if isinstance(score, (int, float)):
                        msg["conf"] = float(score)

                sock.sendto(json.dumps(msg, ensure_ascii=False).encode("utf-8"), dest)

            # If no hands detected, still send a heartbeat message so the receiver can time out cleanly.
            if send_count == 0:
                msg = {
                    "v": 1,
                    "t_ms": t_ms,
                    "seq": seq,
                    "src": "pi",
                    "hand_index": -1,
                    "hand": "Unknown",
                    "conf": 0.0,
                    "tip_img": [0.0, 0.0],
                    "tip_rel": [0.0, 0.0, 0.0],
                    "tip_norm": [0.0, 0.0, 0.0],
                    "scale": 0.0,
                    "valid": False,
                }
                seq += 1
                sock.sendto(json.dumps(msg, ensure_ascii=False).encode("utf-8"), dest)

        finally:
            source.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
