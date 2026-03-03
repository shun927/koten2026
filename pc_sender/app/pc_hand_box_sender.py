r"""
pc_hand_box_sender.py

箱の正面(1枚の平面)を正面カメラで撮影し、ArUcoで箱の平面を推定して、
MediaPipe Hand Landmarker の21ランドマークを「箱疑似3D(x,yは箱平面0..1、zは疑似深度)」としてUDP(JSON)で送信します。

想定用途：
- Unityで「箱を正面から見たCG映像」を描画し、左右の手CGを疑似3Dで動かす

起動例(PowerShell / pc_sender 直下で実行）：
  ..\.\.venv\Scripts\python .\app\pc_hand_box_sender.py `
  --source realsense --rs-fps 30 `
  --config .\config\endpoint.json `
  --model .\models\hand_landmarker.task `
  --width 1280 --height 720 --preview --print-fps `
  --aruco-dict DICT_4X4_50 `
  --aruco-corner-ids 0,1,2,3


注意(ArUcoの依存):
- ArUcoは OpenCV の contrib モジュール(cv2.aruco)が必要です。
- `opencv-python` では `cv2.aruco` が無いことが多いので、`opencv-contrib-python` に入れ替えます。

入れ替え例（このプロジェクトの venv を使う想定）：
  # まず入っている方を消す(どちらかが入っていればOK)
  .\\.venv\\Scripts\\pip uninstall -y opencv-python opencv-contrib-python
  # requirements.txt に合わせて入れる
  .\\.venv\\Scripts\\pip install opencv-contrib-python==4.10.0.84

ArUco ID の用意（例）：
- `DICT_4X4_50` を使い、箱の正面四隅に 4枚貼ります
- ID は TL,TR,BR,BL の順で `--aruco-corner-ids` に渡します
  例：左上=0, 右上=1, 右下=2, 左下=3 → `--aruco-corner-ids 0,1,2,3`

実運用のコツ：
- `--preview` を付けて、四隅マーカーが常に検出される(aruco_ok=true)配置/照明にする
- 両手の割り当ては `hand`(Left/Right)だけに頼らず、入口位置（例：手首 lm_box[0].x)で固定すると安定
"""

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


class _RsCapture:
    def __init__(self, *, serial: str, width: int, height: int, fps: int):
        try:
            import pyrealsense2 as rs  # type: ignore

            self._rs = rs
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                "pyrealsense2 import failed. Install Intel RealSense SDK 2.0 and `pip install pyrealsense2`."
            ) from e

        self.serial = serial
        self._pipeline = self._rs.pipeline()
        config = self._rs.config()
        if serial:
            config.enable_device(serial)
        config.enable_stream(self._rs.stream.color, int(width), int(height), self._rs.format.bgr8, int(fps))
        self._profile = self._pipeline.start(config)

    def read(self):
        try:
            frames = self._pipeline.wait_for_frames(timeout_ms=5000)
            color = frames.get_color_frame()
            if not color:
                return False, None
            frame_bgr = np.asanyarray(color.get_data())
            return True, frame_bgr
        except Exception:  # noqa: BLE001
            return False, None

    def release(self) -> None:
        try:
            self._pipeline.stop()
        except Exception:  # noqa: BLE001
            pass


def _now_ms() -> int:
    return int(time.time() * 1000)


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


def _open_capture(args):
    if args.source == "realsense":
        cap = _RsCapture(serial=str(args.rs_serial or ""), width=int(args.width), height=int(args.height), fps=int(args.rs_fps))
        cam_meta = {"kind": "realsense", "serial": str(args.rs_serial or ""), "index": -1, "api": -1}
        opened_api = -1
        return cap, opened_api, cam_meta

    cap, opened_api = _open_camera(int(args.camera), str(args.backend))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(args.width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(args.height))
    cam_meta = {"kind": "opencv", "index": int(args.camera), "api": int(opened_api)}
    return cap, opened_api, cam_meta


def _hand_label(handedness_entry) -> tuple[str, float]:
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


def _parse_int_list(s: str) -> list[int]:
    out: list[int] = []
    for part in s.split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out


def _aruco_dict(name: str):
    if not hasattr(cv2, "aruco"):
        raise RuntimeError("cv2.aruco not found. Install opencv-contrib-python.")
    aruco = cv2.aruco
    if not hasattr(aruco, name):
        raise ValueError(f"Unknown ArUco dictionary: {name}")
    return aruco.getPredefinedDictionary(getattr(aruco, name))


def _detect_aruco(gray: np.ndarray, dictionary, detector_params):
    aruco = cv2.aruco
    # OpenCV 4.7+ has ArucoDetector; older uses detectMarkers.
    if hasattr(aruco, "ArucoDetector"):
        detector = aruco.ArucoDetector(dictionary, detector_params)
        corners, ids, rejected = detector.detectMarkers(gray)
        return corners, ids, rejected
    corners, ids, rejected = aruco.detectMarkers(gray, dictionary, parameters=detector_params)
    return corners, ids, rejected


def _marker_centers(corners, ids) -> dict[int, tuple[float, float]]:
    centers: dict[int, tuple[float, float]] = {}
    if ids is None:
        return centers
    for i, mid in enumerate(ids.flatten().tolist()):
        c = np.asarray(corners[i], dtype=np.float32).reshape(-1, 2)
        xy = c.mean(axis=0)
        centers[int(mid)] = (float(xy[0]), float(xy[1]))
    return centers


def _homography_from_aruco_centers(
    centers_px: dict[int, tuple[float, float]],
    corner_ids: list[int],
) -> np.ndarray | None:
    """
    corner_ids order: TL, TR, BR, BL (image when looking at the box from the front).
    Returns H that maps image pixel -> box normalized (0..1, 0..1).
    """
    needed = [cid for cid in corner_ids if cid not in centers_px]
    if needed:
        return None

    src = np.array([centers_px[cid] for cid in corner_ids], dtype=np.float32)
    dst = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)
    h, _ = cv2.findHomography(src, dst, method=0)
    if h is None:
        return None
    return h.astype(np.float32)


def _warp_points(pts_px: np.ndarray, h_img_to_box: np.ndarray) -> np.ndarray:
    pts = np.asarray(pts_px, dtype=np.float32).reshape(-1, 1, 2)
    out = cv2.perspectiveTransform(pts, h_img_to_box).reshape(-1, 2)
    return out.astype(np.float32)


def _ema(prev: np.ndarray | None, cur: np.ndarray, alpha: float) -> np.ndarray:
    a = float(alpha)
    if prev is None or a >= 0.999:
        return cur.astype(np.float32, copy=False)
    if a <= 0.001:
        return prev.astype(np.float32, copy=False)
    return (a * cur + (1.0 - a) * prev).astype(np.float32)


def _safe_norm(v: np.ndarray) -> float:
    return float(np.linalg.norm(v))


def _compute_z_like(hand_landmarks, hand_world_landmarks) -> np.ndarray:
    """
    Compute pseudo depth per landmark as a relative, scale-normalized value.
    Positive z_like means "toward camera" by default.
    """
    if hand_world_landmarks:
        w = np.array([[lm.x, lm.y, lm.z] for lm in hand_world_landmarks], dtype=np.float32)  # (21,3)
        wrist_z = float(w[0, 2])
        scale = _safe_norm(w[5] - w[17])
        if scale < 1e-6:
            scale = 1.0
        z_like = -(w[:, 2] - wrist_z) / scale
        return z_like.astype(np.float32)

    # Fallback: image-landmark z with 2D hand-size normalization.
    p = np.array([[lm.x, lm.y, lm.z] for lm in hand_landmarks], dtype=np.float32)  # (21,3)
    wrist_z = float(p[0, 2])
    scale2d = _safe_norm(p[5, :2] - p[17, :2])
    if scale2d < 1e-6:
        scale2d = 1.0
    z_like = -(p[:, 2] - wrist_z) / scale2d
    return z_like.astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to endpoint.json")
    parser.add_argument("--model", type=str, required=True, help="Path to hand_landmarker.task")
    parser.add_argument(
        "--source",
        type=str,
        default="realsense",
        choices=["opencv", "realsense"],
        help="Frame source. Use `realsense` to capture from Intel RealSense (D435i etc.).",
    )
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index (used when --source opencv)")
    parser.add_argument(
        "--backend",
        type=str,
        default="auto",
        choices=["auto", "dshow", "msmf", "any"],
        help="OpenCV capture backend (Windows). If black screen, try msmf/dshow.",
    )
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--rs-serial", type=str, default="", help="RealSense device serial (recommended)")
    parser.add_argument("--rs-fps", type=int, default=30, help="RealSense color FPS")
    parser.add_argument("--max-hands", type=int, default=2)
    parser.add_argument("--preview", action="store_true", help="Show debug preview window")
    parser.add_argument("--print-fps", action="store_true")
    parser.add_argument(
        "--aruco-dict",
        type=str,
        default="DICT_4X4_50",
        help="ArUco dictionary name (e.g. DICT_4X4_50, DICT_5X5_100).",
    )
    parser.add_argument(
        "--aruco-corner-ids",
        type=str,
        default="0,1,2,3",
        help="ArUco ids for box corners in order TL,TR,BR,BL.",
    )
    parser.add_argument(
        "--aruco-hold-ms",
        type=int,
        default=300,
        help="Reuse last valid ArUco plane for this duration (ms) when markers are temporarily occluded.",
    )
    parser.add_argument(
        "--smooth-alpha",
        type=float,
        default=0.35,
        help="EMA smoothing for box landmarks (0..1). 1 disables smoothing.",
    )
    parser.add_argument(
        "--z-smooth-alpha",
        type=float,
        default=0.35,
        help="EMA smoothing for pseudo depth z_like (0..1). 1 disables smoothing.",
    )
    parser.add_argument(
        "--z-like-scale",
        type=float,
        default=1.0,
        help="Scale multiplier applied to z_like.",
    )
    parser.add_argument(
        "--z-like-offset",
        type=float,
        default=0.0,
        help="Offset added to z_like after scaling.",
    )
    parser.add_argument(
        "--z-like-min",
        type=float,
        default=-1.0,
        help="Lower clamp for z_like.",
    )
    parser.add_argument(
        "--z-like-max",
        type=float,
        default=1.0,
        help="Upper clamp for z_like.",
    )
    args = parser.parse_args()

    endpoint = _read_endpoint(Path(args.config))
    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    corner_ids = _parse_int_list(args.aruco_corner_ids)
    if len(corner_ids) != 4:
        raise ValueError("--aruco-corner-ids must have 4 comma-separated ints (TL,TR,BR,BL)")

    cap, opened_api, cam_meta = _open_capture(args)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    landmarker = _build_landmarker(model_path, num_hands=args.max_hands)

    dictionary = _aruco_dict(args.aruco_dict)
    detector_params = cv2.aruco.DetectorParameters()

    seq = 0
    last_stats_t = time.time()
    frames = 0

    # Smoothing state per hand "key"
    smoothed: dict[str, np.ndarray] = {}
    smoothed_z: dict[str, np.ndarray] = {}
    last_h_img_to_box: np.ndarray | None = None
    last_h_t_ms: int | None = None

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                time.sleep(0.03)
                continue

            h_img, w_img = frame_bgr.shape[:2]

            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            corners, ids, _rej = _detect_aruco(gray, dictionary, detector_params)
            centers_px = _marker_centers(corners, ids)
            h_img_to_box = _homography_from_aruco_centers(centers_px, corner_ids)

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = _to_mp_image(frame_rgb)
            t_ms = _now_ms()
            result = landmarker.detect_for_video(mp_image, t_ms)

            aruco_ok = h_img_to_box is not None
            aruco_stale = False
            aruco_age_ms = 0
            if not aruco_ok and last_h_img_to_box is not None and last_h_t_ms is not None:
                age = int(t_ms - last_h_t_ms)
                if age <= int(args.aruco_hold_ms):
                    h_img_to_box = last_h_img_to_box
                    aruco_ok = True
                    aruco_stale = True
                    aruco_age_ms = age

            if h_img_to_box is not None and not aruco_stale:
                last_h_img_to_box = h_img_to_box
                last_h_t_ms = int(t_ms)

            hands_out: list[dict] = []
            handedness_list = result.handedness or []
            hand_landmarks_list = result.hand_landmarks or []

            for hand_index, hand_landmarks in enumerate(hand_landmarks_list):
                label, conf = _hand_label(handedness_list[hand_index] if hand_index < len(handedness_list) else [])

                lm_img_px = np.array([[lm.x * w_img, lm.y * h_img] for lm in hand_landmarks], dtype=np.float32)
                key = label if label != "Unknown" else f"hand{hand_index}"

                z_raw = _compute_z_like(
                    hand_landmarks,
                    result.hand_world_landmarks[hand_index]
                    if result.hand_world_landmarks and hand_index < len(result.hand_world_landmarks)
                    else None,
                )
                z_adj = np.clip(
                    z_raw * float(args.z_like_scale) + float(args.z_like_offset),
                    float(args.z_like_min),
                    float(args.z_like_max),
                ).astype(np.float32)
                z_prev = smoothed_z.get(key)
                z_like = _ema(z_prev, z_adj, alpha=args.z_smooth_alpha)
                smoothed_z[key] = z_like

                lm_box = None
                if h_img_to_box is not None:
                    lm_box = _warp_points(lm_img_px, h_img_to_box)
                    prev = smoothed.get(key)
                    lm_box = _ema(prev, lm_box, alpha=args.smooth_alpha)
                    smoothed[key] = lm_box

                lm_box3 = None
                if lm_box is not None:
                    lm_box3 = np.concatenate([lm_box, z_like.reshape(-1, 1)], axis=1)

                hands_out.append(
                    {
                        "hand_index": int(hand_index),
                        "hand": label,
                        "conf": float(conf),
                        # Always include 2D image coords (normalized) for fallback assignment.
                        "lm_img": [[float(lm.x), float(lm.y)] for lm in hand_landmarks],
                        # When ArUco is visible: normalized box plane coords (0..1).
                        "lm_box": None if lm_box is None else [[float(x), float(y)] for x, y in lm_box.tolist()],
                        # Pseudo 3D in box coordinates (x,y from lm_box, z from z_like).
                        "lm_box3": None
                        if lm_box3 is None
                        else [[float(x), float(y), float(z)] for x, y, z in lm_box3.tolist()],
                        # z_like is always available (even when ArUco is temporarily unavailable).
                        "z_like": [float(z) for z in z_like.tolist()],
                        "valid": True,
                    }
                )

            payload = {
                "v": 2,
                "kind": "box_plane",
                "t_ms": int(t_ms),
                "seq": int(seq),
                "src": endpoint.src,
                "cam": cam_meta,
                "frame": {"w": int(w_img), "h": int(h_img)},
                "aruco": {
                    "dict": args.aruco_dict,
                    "corner_ids": corner_ids,
                    "detected_ids": [] if ids is None else [int(x) for x in ids.flatten().tolist()],
                    "ok": bool(aruco_ok),
                    "stale": bool(aruco_stale),
                    "age_ms": int(aruco_age_ms),
                    "hold_ms": int(args.aruco_hold_ms),
                },
                "z_like": {
                    "scale": float(args.z_like_scale),
                    "offset": float(args.z_like_offset),
                    "min": float(args.z_like_min),
                    "max": float(args.z_like_max),
                    "smooth_alpha": float(args.z_smooth_alpha),
                },
                "hands": hands_out,
            }
            _send_udp(sock, endpoint, payload)

            if args.preview:
                vis = frame_bgr.copy()
                if ids is not None and hasattr(cv2.aruco, "drawDetectedMarkers"):
                    cv2.aruco.drawDetectedMarkers(vis, corners, ids)

                if h_img_to_box is not None:
                    # draw box corners (marker centers)
                    # Note: when reusing a stale homography (aruco_stale=true),
                    # current-frame marker centers may be missing.
                    for cid in corner_ids:
                        if cid not in centers_px:
                            continue
                        cx, cy = centers_px[cid]
                        cv2.circle(vis, (int(cx), int(cy)), 6, (0, 255, 0), -1)

                cv2.putText(
                    vis,
                    f"seq={seq} hands={len(hand_landmarks_list)} aruco_ok={aruco_ok} stale={aruco_stale} src={cam_meta.get('kind')} api={opened_api}",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("pc_hand_box_sender (ESC to quit)", vis)
                if cv2.waitKey(1) & 0xFF == 27:
                    break

            seq += 1
            frames += 1
            if args.print_fps:
                now = time.time()
                if now - last_stats_t >= 2.0:
                    fps = frames / (now - last_stats_t)
                    print(f"fps={fps:.1f} seq={seq} aruco_ok={h_img_to_box is not None} hands={len(hand_landmarks_list)}")
                    last_stats_t = now
                    frames = 0

    finally:
        cap.release()
        cv2.destroyAllWindows()
        sock.close()
        landmarker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
