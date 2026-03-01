# .\.venv\Scripts\python .\pc_sender\app\pc_hand_debug_viewer.py --model .\pc_sender\models\hand_landmarker.task --camera 0 --flip --backend msmf
# 自由に動く:　.\.venv\Scripts\python .\pc_sender\app\pc_hand_debug_viewer.py --model .\pc_sender\models\hand_landmarker.task --camera 0 --flip --backend msmf --center none
# 固定したいとき: .\.venv\Scripts\python .\pc_sender\app\pc_hand_debug_viewer.py --model .\pc_sender\models\hand_landmarker.task --camera 0 --flip --backend msmf --center wrist
import argparse
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
# We keep this local to avoid relying on `mediapipe.solutions`, which may not exist
# depending on the installed MediaPipe package build.
HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    # Palm
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


def _rot_yaw_pitch(points_xyz: np.ndarray, yaw_deg: float, pitch_deg: float) -> np.ndarray:
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)

    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    # Yaw around Y axis, then pitch around X axis.
    r_yaw = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float32)
    r_pitch = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]], dtype=np.float32)
    r = (r_pitch @ r_yaw).astype(np.float32)

    return (points_xyz @ r.T).astype(np.float32)


def _project_points(
    points_xyz: np.ndarray,
    canvas_w: int,
    canvas_h: int,
    focal_px: float,
    camera_dist: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Perspective project 3D points to 2D.
    Returns (pts_2d_int Nx2, valid_mask N).
    """
    p = np.asarray(points_xyz, dtype=np.float32)
    z = p[:, 2] + float(camera_dist)
    valid = z > 1e-3

    cx, cy = canvas_w * 0.5, canvas_h * 0.5
    x2 = cx + focal_px * (p[:, 0] / z)
    y2 = cy - focal_px * (p[:, 1] / z)
    pts2 = np.stack([x2, y2], axis=1)
    pts2i = np.round(pts2).astype(np.int32)
    return pts2i, valid


def _draw_axes(canvas_bgr: np.ndarray, yaw_deg: float, pitch_deg: float, focal_px: float, camera_dist: float) -> None:
    # Axes in local hand space (after rotation): X=red, Y=green, Z=blue.
    axis_len = 0.25
    axes = np.array(
        [
            [0.0, 0.0, 0.0],
            [axis_len, 0.0, 0.0],
            [0.0, axis_len, 0.0],
            [0.0, 0.0, axis_len],
        ],
        dtype=np.float32,
    )
    axes_r = _rot_yaw_pitch(axes, yaw_deg=yaw_deg, pitch_deg=pitch_deg)
    pts2i, valid = _project_points(
        axes_r, canvas_w=canvas_bgr.shape[1], canvas_h=canvas_bgr.shape[0], focal_px=focal_px, camera_dist=camera_dist
    )
    if not (valid[0] and valid[1] and valid[2] and valid[3]):
        return

    o = tuple(int(v) for v in pts2i[0])
    cv2.line(canvas_bgr, o, tuple(int(v) for v in pts2i[1]), (0, 0, 255), 2)  # X
    cv2.line(canvas_bgr, o, tuple(int(v) for v in pts2i[2]), (0, 255, 0), 2)  # Y
    cv2.line(canvas_bgr, o, tuple(int(v) for v in pts2i[3]), (255, 0, 0), 2)  # Z


def _landmarks_to_hand_xyz(hand_landmarks, center_mode: str) -> np.ndarray:
    """
    Convert MediaPipe hand landmarks to a 3D point cloud.
    - X/Y come from normalized image coords (centered at 0.5).
    - Z comes from landmark.z (rough depth). We invert sign so "toward camera" is +Z.

    center_mode:
      - "wrist": subtract wrist (landmark 0) so the hand stays at origin
      - "none": keep absolute (image-centered) position so the hand can translate
    """
    pts = np.array([[lm.x - 0.5, -(lm.y - 0.5), -lm.z] for lm in hand_landmarks], dtype=np.float32)  # (21,3)
    if center_mode == "wrist":
        pts -= pts[0:1]
    elif center_mode == "none":
        pass
    else:
        raise ValueError(f"Unknown center_mode: {center_mode}")
    return pts


def _ema_update(prev: np.ndarray | None, cur: np.ndarray, alpha: float) -> np.ndarray:
    """
    Exponential moving average.
    alpha: weight of current sample in [0,1]. 1.0 means no smoothing.
    """
    a = float(alpha)
    if prev is None or a >= 0.999:
        return cur.astype(np.float32, copy=False)
    if a <= 0.001:
        return prev.astype(np.float32, copy=False)
    return (a * cur + (1.0 - a) * prev).astype(np.float32)


def _draw_hand_3d(
    canvas_bgr: np.ndarray,
    hand_xyz: np.ndarray,
    yaw_deg: float,
    pitch_deg: float,
    focal_px: float,
    camera_dist: float,
    color=(200, 200, 200),
) -> None:
    pts_r = _rot_yaw_pitch(hand_xyz, yaw_deg=yaw_deg, pitch_deg=pitch_deg)
    pts2i, valid = _project_points(
        pts_r, canvas_w=canvas_bgr.shape[1], canvas_h=canvas_bgr.shape[0], focal_px=focal_px, camera_dist=camera_dist
    )

    for a, b in HAND_CONNECTIONS:
        if 0 <= a < len(pts2i) and 0 <= b < len(pts2i) and valid[a] and valid[b]:
            cv2.line(canvas_bgr, tuple(int(v) for v in pts2i[a]), tuple(int(v) for v in pts2i[b]), color, 2)

    for i, (x, y) in enumerate(pts2i):
        if not valid[i]:
            continue
        r = 5 if i == 8 else 3  # index fingertip highlighted
        c = (0, 0, 255) if i == 8 else color
        cv2.circle(canvas_bgr, (int(x), int(y)), r, c, -1)


def _to_mp_image(frame_rgb):
    # MediaPipe Tasks expects `mediapipe.Image` in recent versions.
    if hasattr(mp, "Image") and hasattr(mp, "ImageFormat"):
        return mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
    # Fallback for older builds (kept for safety).
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


def main() -> int:
    parser = argparse.ArgumentParser()
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
    parser.add_argument("--flip", action="store_true", help="Mirror horizontally for easy checking")
    parser.add_argument("--print-fps", action="store_true")
    parser.add_argument("--viewer-size", type=int, default=800, help="3D viewer canvas size (square)")
    parser.add_argument(
        "--center",
        type=str,
        default="none",
        choices=["none", "wrist"],
        help='3D centering mode. "none" allows translation; "wrist" locks wrist to origin.',
    )
    parser.add_argument(
        "--smooth-alpha",
        type=float,
        default=0.35,
        help="EMA smoothing (0..1). Lower is smoother, higher follows faster. 1 disables smoothing.",
    )
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
    yaw_deg = -20.0
    pitch_deg = 15.0
    camera_dist = 1.6

    # Per-hand smoothing state (keyed by handedness when available).
    smoothed_by_key: dict[str, np.ndarray] = {}

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                placeholder = np.zeros((args.viewer_size, args.viewer_size, 3), dtype=np.uint8)
                cv2.putText(
                    placeholder,
                    "No frames from camera (check privacy / index / backend)",
                    (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )
                cv2.imshow("pc_hand_debug_viewer_3d (ESC to quit)", placeholder)
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

            canvas = np.zeros((args.viewer_size, args.viewer_size, 3), dtype=np.uint8)
            canvas[:] = (18, 18, 18)
            focal_px = args.viewer_size * 0.9

            _draw_axes(canvas, yaw_deg=yaw_deg, pitch_deg=pitch_deg, focal_px=focal_px, camera_dist=camera_dist)

            handedness_list = result.handedness or []
            for hand_index, hand_landmarks in enumerate(hand_landmarks_list):
                label = "Unknown"
                score = 0.0
                if hand_index < len(handedness_list) and handedness_list[hand_index]:
                    top = handedness_list[hand_index][0]
                    label = getattr(top, "category_name", None) or getattr(top, "display_name", None) or "Unknown"
                    score = float(getattr(top, "score", 0.0) or 0.0)

                hand_xyz = _landmarks_to_hand_xyz(hand_landmarks, center_mode=args.center)
                key = label if label != "Unknown" else f"hand{hand_index}"
                prev = smoothed_by_key.get(key)
                hand_xyz_s = _ema_update(prev, hand_xyz, alpha=args.smooth_alpha)
                smoothed_by_key[key] = hand_xyz_s

                _draw_hand_3d(
                    canvas,
                    hand_xyz_s,
                    yaw_deg=yaw_deg,
                    pitch_deg=pitch_deg,
                    focal_px=focal_px,
                    camera_dist=camera_dist,
                    color=(200, 200, 200) if hand_index == 0 else (120, 200, 255),
                )

                cv2.putText(
                    canvas,
                    f"{hand_index}:{label} {score:.2f}",
                    (10, 30 + 24 * hand_index),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                )

            cv2.putText(
                canvas,
                f"cam={args.camera} api={opened_api} hands={len(hand_landmarks_list)}  center={args.center}  yaw/pitch={yaw_deg:.0f}/{pitch_deg:.0f}  dist={camera_dist:.2f}  smooth={args.smooth_alpha:.2f}",
                (10, canvas.shape[0] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (255, 255, 255),
                2,
            )
            cv2.imshow("pc_hand_debug_viewer_3d (ESC to quit)", canvas)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:  # ESC
                break
            if key in (ord("a"), ord("A")):
                yaw_deg -= 3.0
            elif key in (ord("d"), ord("D")):
                yaw_deg += 3.0
            elif key in (ord("w"), ord("W")):
                pitch_deg += 3.0
            elif key in (ord("s"), ord("S")):
                pitch_deg -= 3.0
            elif key in (ord("q"), ord("Q")):
                camera_dist = max(0.5, camera_dist - 0.05)
            elif key in (ord("e"), ord("E")):
                camera_dist = min(4.0, camera_dist + 0.05)
            elif key in (ord("r"), ord("R")):
                yaw_deg, pitch_deg, camera_dist = -20.0, 15.0, 1.6

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
