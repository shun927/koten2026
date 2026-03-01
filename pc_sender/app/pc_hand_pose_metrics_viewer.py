# .\.venv\Scripts\python .\pc_sender\app\pc_hand_pose_metrics_viewer.py --model .\pc_sender\models\hand_landmarker.task --camera 0 --flip --backend msmf

import argparse
import json
import math
import time
from pathlib import Path

import cv2
import numpy as np

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision


def _now_ms() -> int:
    return int(time.time() * 1000)


def _build_landmarker(model_path: Path, num_hands: int) -> mp_vision.HandLandmarker:
    base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
    options = mp_vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_hands=num_hands,
    )
    return mp_vision.HandLandmarker.create_from_options(options)


# MediaPipe Hands landmark connections (21 landmarks).
HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (13, 17),
    (17, 18),
    (18, 19),
    (19, 20),
    (0, 17),
)


def _draw_hand(frame_bgr, hand_landmarks, color=(0, 255, 0)) -> None:
    h, w = frame_bgr.shape[:2]

    pts = []
    for lm in hand_landmarks:
        pts.append((int(lm.x * w), int(lm.y * h)))

    for a, b in HAND_CONNECTIONS:
        if 0 <= a < len(pts) and 0 <= b < len(pts):
            cv2.line(frame_bgr, pts[a], pts[b], color, 2)

    for (x, y) in pts:
        cv2.circle(frame_bgr, (x, y), 2, color, -1)


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


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(v))
    if n < 1e-8:
        return np.zeros_like(v)
    return v / n


def _angle_deg(v1: np.ndarray, v2: np.ndarray) -> float:
    a = _unit(v1)
    b = _unit(v2)
    d = float(np.clip(np.dot(a, b), -1.0, 1.0))
    return float(math.degrees(math.acos(d)))


def _joint_angle_deg(points_xyz: np.ndarray, prev_i: int, joint_i: int, next_i: int) -> float:
    p = points_xyz
    v1 = p[prev_i] - p[joint_i]
    v2 = p[next_i] - p[joint_i]
    return _angle_deg(v1, v2)


def _yaw_pitch_deg(dir_xyz: np.ndarray) -> tuple[float, float]:
    """
    Approximate angles from a 3D direction.
    - yaw: left/right around Y axis
    - pitch: up/down around X axis
    These are only indicative (camera/world axes are not calibrated).
    """
    d = _unit(dir_xyz)
    x, y, z = float(d[0]), float(d[1]), float(d[2])
    yaw = math.degrees(math.atan2(x, z if abs(z) > 1e-8 else 1e-8))
    pitch = math.degrees(math.atan2(-y, math.sqrt(x * x + z * z) + 1e-8))
    return float(yaw), float(pitch)


def _hand_metrics(hand_landmarks) -> dict:
    pts = np.array([[lm.x, lm.y, lm.z] for lm in hand_landmarks], dtype=np.float32)  # (21,3)

    wrist = pts[0]
    index_mcp, index_pip, index_dip, index_tip = pts[5], pts[6], pts[7], pts[8]
    middle_mcp, middle_tip = pts[9], pts[12]
    pinky_mcp = pts[17]

    palm_normal = _unit(np.cross(index_mcp - wrist, pinky_mcp - wrist))
    index_dir = _unit(index_tip - index_mcp)
    middle_dir = _unit(middle_tip - middle_mcp)

    index_mcp_angle = _joint_angle_deg(pts, 0, 5, 6)
    index_pip_angle = _joint_angle_deg(pts, 5, 6, 7)
    index_dip_angle = _joint_angle_deg(pts, 6, 7, 8)

    yaw, pitch = _yaw_pitch_deg(index_dir)

    return {
        "index_dir_xyz": [float(x) for x in index_dir.tolist()],
        "middle_dir_xyz": [float(x) for x in middle_dir.tolist()],
        "palm_normal_xyz": [float(x) for x in palm_normal.tolist()],
        "index_angles_deg": {
            "mcp": float(index_mcp_angle),
            "pip": float(index_pip_angle),
            "dip": float(index_dip_angle),
        },
        "index_yaw_pitch_deg": {"yaw": float(yaw), "pitch": float(pitch)},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True, help="Path to hand_landmarker.task")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument(
        "--backend",
        type=str,
        default="auto",
        choices=["auto", "dshow", "msmf", "any"],
        help="OpenCV capture backend (Windows). If black screen, try msmf/dshow.",
    )
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--max-hands", type=int, default=2)
    parser.add_argument("--flip", action="store_true", help="Mirror horizontally for easy checking")
    parser.add_argument("--print-fps", action="store_true")
    parser.add_argument("--print-json", action="store_true", help="Print per-frame metrics as JSON Lines")
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    cap, opened_api = _open_camera(args.camera, args.backend)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    landmarker = _build_landmarker(model_path, num_hands=args.max_hands)

    last_fps_t = time.time()
    frames = 0

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                placeholder = np.zeros((args.height, args.width, 3), dtype=np.uint8)
                cv2.putText(
                    placeholder,
                    "No frames from camera (check privacy / index / backend)",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )
                cv2.imshow("pc_hand_pose_metrics_viewer (ESC to quit)", placeholder)
                if cv2.waitKey(1) & 0xFF == 27:
                    break
                time.sleep(0.05)
                continue

            if args.flip:
                frame_bgr = cv2.flip(frame_bgr, 1)

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = _to_mp_image(frame_rgb)
            t_ms = _now_ms()
            result = landmarker.detect_for_video(mp_image, t_ms)

            hand_landmarks_list = result.hand_landmarks or []
            handedness_list = result.handedness or []

            metrics_out = []

            for hand_index, hand_landmarks in enumerate(hand_landmarks_list):
                _draw_hand(frame_bgr, hand_landmarks)

                m = _hand_metrics(hand_landmarks)
                metrics_out.append(m)

                label = "Unknown"
                score = 0.0
                if hand_index < len(handedness_list) and handedness_list[hand_index]:
                    top = handedness_list[hand_index][0]
                    label = getattr(top, "category_name", None) or getattr(top, "display_name", None) or "Unknown"
                    score = float(getattr(top, "score", 0.0) or 0.0)

                # Highlight index_finger_tip (8)
                tip = hand_landmarks[8]
                h, w = frame_bgr.shape[:2]
                cx, cy = int(tip.x * w), int(tip.y * h)
                cv2.circle(frame_bgr, (cx, cy), 8, (0, 0, 255), 2)

                y0 = 10 + 110 * hand_index
                cv2.putText(
                    frame_bgr,
                    f"{hand_index}:{label} {score:.2f}",
                    (10, y0 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                )

                a = m["index_angles_deg"]
                yp = m["index_yaw_pitch_deg"]
                n = m["palm_normal_xyz"]
                cv2.putText(
                    frame_bgr,
                    f"index angles (deg) mcp={a['mcp']:.0f} pip={a['pip']:.0f} dip={a['dip']:.0f}",
                    (10, y0 + 45),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2,
                )
                cv2.putText(
                    frame_bgr,
                    f"index yaw/pitch (deg) yaw={yp['yaw']:.0f} pitch={yp['pitch']:.0f}",
                    (10, y0 + 70),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2,
                )
                cv2.putText(
                    frame_bgr,
                    f"palm normal xyz=({n[0]:+.2f},{n[1]:+.2f},{n[2]:+.2f})",
                    (10, y0 + 95),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    2,
                )

            if args.print_json:
                out = {"t_ms": t_ms, "hands": metrics_out}
                print(json.dumps(out, ensure_ascii=False))

            cv2.putText(
                frame_bgr,
                f"cam={args.camera} api={opened_api} size={frame_bgr.shape[1]}x{frame_bgr.shape[0]} hands={len(hand_landmarks_list)}",
                (10, frame_bgr.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2,
            )
            cv2.imshow("pc_hand_pose_metrics_viewer (ESC to quit)", frame_bgr)
            if cv2.waitKey(1) & 0xFF == 27:
                break

            frames += 1
            if args.print_fps:
                now = time.time()
                if now - last_fps_t >= 1.0:
                    fps = frames / (now - last_fps_t)
                    print(f"fps={fps:.1f} hands={len(hand_landmarks_list)}")
                    last_fps_t = now
                    frames = 0

    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

