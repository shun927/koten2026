import argparse
import json
import socket
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int
    src: str


def _now_ms() -> int:
    return int(time.time() * 1000)


def _norm3(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def _read_endpoint(path: Path) -> Endpoint:
    data = json.loads(path.read_text(encoding="utf-8"))
    host = str(data.get("host", "127.0.0.1"))
    port = int(data.get("port", 5005))
    src = str(data.get("src", "pc"))
    return Endpoint(host=host, port=port, src=src)


def _build_landmarker(model_path: Path, num_hands: int) -> mp_vision.HandLandmarker:
    base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
    options = mp_vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=num_hands,
    )
    return mp_vision.HandLandmarker.create_from_options(options)


def _to_mp_image(frame_rgb):
    if hasattr(mp, "Image") and hasattr(mp, "ImageFormat"):
        return mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
    if hasattr(mp_vision, "MpImage") and hasattr(mp_vision, "ImageFormat"):
        return mp_vision.MpImage(image_format=mp_vision.ImageFormat.SRGB, data=frame_rgb)
    raise RuntimeError("No MediaPipe Image type found (mp.Image / mp_vision.MpImage)")


def _open_camera(camera_index: int, backend: str):
    backend_map = {
        "auto": [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY],
        "dshow": [cv2.CAP_DSHOW],
        "msmf": [cv2.CAP_MSMF],
        "any": [cv2.CAP_ANY],
    }
    if backend not in backend_map:
        raise ValueError(f"Unknown backend: {backend}")

    last_cap = None
    last_err = None
    for api in backend_map[backend]:
        try:
            cap = cv2.VideoCapture(camera_index, api)
            if cap.isOpened():
                return cap, api
            last_cap = cap
        except Exception as e:
            last_err = e

    if last_cap is not None:
        last_cap.release()
    if last_err is not None:
        raise RuntimeError(f"Failed to open camera {camera_index} (backend={backend}): {last_err}")
    raise RuntimeError(f"Failed to open camera {camera_index} (backend={backend})")


def _hand_label(handedness_entry) -> tuple[str, float]:
    # handedness_entry: list[Category]
    if not handedness_entry:
        return ("Unknown", 0.0)
    top = handedness_entry[0]
    name = getattr(top, "category_name", None) or getattr(top, "display_name", None) or "Unknown"
    score = float(getattr(top, "score", 0.0) or 0.0)
    if name not in ("Left", "Right"):
        name = "Unknown"
    return (name, score)


def _send_udp(sock: socket.socket, endpoint: Endpoint, payload: dict) -> None:
    msg = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sock.sendto(msg, (endpoint.host, endpoint.port))


def _empty_payload(endpoint: Endpoint, seq: int, t_ms: int) -> dict:
    return {
        "v": 1,
        "t_ms": t_ms,
        "seq": seq,
        "src": endpoint.src,
        "hand_index": -1,
        "hand": "Unknown",
        "conf": 0.0,
        "tip_img": [0.0, 0.0],
        "tip_rel": [0.0, 0.0, 0.0],
        "tip_norm": [0.0, 0.0, 0.0],
        "scale": 0.0,
        "valid": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to endpoint.json")
    parser.add_argument("--model", type=str, required=True, help="Path to hand_landmarker.task")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument(
        "--backend",
        type=str,
        default="auto",
        choices=["auto", "dshow", "msmf", "any"],
        help="OpenCV capture backend (Windows). If black screen, try msmf/any.",
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--max-hands", type=int, default=2)
    parser.add_argument("--preview", action="store_true", help="Show camera preview window")
    parser.add_argument("--print-fps", action="store_true")
    parser.add_argument(
        "--stats-interval-sec",
        type=float,
        default=2.0,
        help="Stats print interval in seconds (used with --print-fps).",
    )
    parser.add_argument(
        "--reconnect-sec",
        type=float,
        default=2.0,
        help="Try camera reopen if read failures continue for this duration.",
    )
    parser.add_argument(
        "--heartbeat-ms",
        type=int,
        default=250,
        help="Send valid=false heartbeat when camera frames are unavailable.",
    )
    args = parser.parse_args()

    endpoint = _read_endpoint(Path(args.config))
    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    cap, opened_api = _open_camera(args.camera, args.backend)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    landmarker = _build_landmarker(model_path, num_hands=args.max_hands)

    seq = 0
    last_stats_t = time.time()
    frames = 0
    sent_packets = 0
    valid_packets = 0
    read_failures = 0
    reconnects = 0
    camera_down_since = None
    last_heartbeat_ms = 0

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                read_failures += 1
                now = time.time()
                if camera_down_since is None:
                    camera_down_since = now

                t_ms = _now_ms()
                if t_ms - last_heartbeat_ms >= args.heartbeat_ms:
                    _send_udp(sock, endpoint, _empty_payload(endpoint, seq, t_ms))
                    seq += 1
                    sent_packets += 1
                    last_heartbeat_ms = t_ms

                if now - camera_down_since >= args.reconnect_sec:
                    cap.release()
                    cap, opened_api = _open_camera(args.camera, args.backend)
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
                    camera_down_since = None
                    reconnects += 1

                time.sleep(0.03)
                continue
            camera_down_since = None

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = _to_mp_image(frame_rgb)
            t_ms = _now_ms()
            result = landmarker.detect_for_video(mp_image, t_ms)

            num_detected = len(result.hand_landmarks or [])
            if num_detected == 0:
                _send_udp(sock, endpoint, _empty_payload(endpoint, seq, t_ms))
                sent_packets += 1
            else:
                for hand_index in range(num_detected):
                    hand_landmarks = result.hand_landmarks[hand_index]
                    handedness = result.handedness[hand_index] if result.handedness else []
                    hand_label, conf = _hand_label(handedness)

                    # 2D (normalized 0..1) landmarks (x,y)
                    tip2d = hand_landmarks[8]
                    tip_img = [float(tip2d.x), float(tip2d.y)]

                    tip_rel = np.zeros(3, dtype=np.float32)
                    tip_norm = np.zeros(3, dtype=np.float32)
                    scale = 0.0

                    if result.hand_world_landmarks and hand_index < len(result.hand_world_landmarks):
                        w = result.hand_world_landmarks[hand_index]
                        tip_w = np.array([w[8].x, w[8].y, w[8].z], dtype=np.float32)
                        wrist_w = np.array([w[0].x, w[0].y, w[0].z], dtype=np.float32)
                        mcp5_w = np.array([w[5].x, w[5].y, w[5].z], dtype=np.float32)
                        mcp17_w = np.array([w[17].x, w[17].y, w[17].z], dtype=np.float32)
                        tip_rel = tip_w - wrist_w
                        scale = _norm3(mcp5_w - mcp17_w)
                        if scale >= 1e-6:
                            tip_norm = tip_rel / scale

                    payload = {
                        "v": 1,
                        "t_ms": t_ms,
                        "seq": seq,
                        "src": endpoint.src,
                        "hand_index": hand_index,
                        "hand": hand_label,
                        "conf": conf,
                        "tip_img": tip_img,
                        "tip_rel": [float(tip_rel[0]), float(tip_rel[1]), float(tip_rel[2])],
                        "tip_norm": [float(tip_norm[0]), float(tip_norm[1]), float(tip_norm[2])],
                        "scale": float(scale),
                        "valid": True,
                    }
                    _send_udp(sock, endpoint, payload)
                    sent_packets += 1
                    valid_packets += 1

            seq += 1
            frames += 1

            if args.preview:
                cv2.putText(
                    frame_bgr,
                    f"seq={seq} hands={num_detected} cam={args.camera} api={opened_api} -> {endpoint.host}:{endpoint.port}",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("pc_hand_sender", frame_bgr)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            if args.print_fps:
                now = time.time()
                elapsed = now - last_stats_t
                if elapsed >= args.stats_interval_sec:
                    fps = frames / elapsed if elapsed > 0 else 0.0
                    valid_rate = (valid_packets / sent_packets) if sent_packets else 0.0
                    print(
                        f"fps={fps:.1f} hands={num_detected} seq={seq} "
                        f"sent={sent_packets} valid_rate={valid_rate:.2f} "
                        f"read_fail={read_failures} reconnects={reconnects}"
                    )
                    last_stats_t = now
                    frames = 0
                    sent_packets = 0
                    valid_packets = 0
                    read_failures = 0

    finally:
        cap.release()
        cv2.destroyAllWindows()
        sock.close()
        landmarker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
