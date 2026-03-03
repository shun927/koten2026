import argparse
import time
from pathlib import Path

import cv2
import numpy as np

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision


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
        opened_api = -1
        cam_label = f"realsense(serial={args.rs_serial})" if args.rs_serial else "realsense"
        return cap, opened_api, cam_label

    cap, opened_api = _open_camera(int(args.camera), str(args.backend))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(args.width))
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(args.height))
    cam_label = f"opencv(index={args.camera})"
    return cap, opened_api, cam_label


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


def _draw_landmarks_on_image(frame_bgr: np.ndarray, hand_landmarks_list) -> None:
    h, w = frame_bgr.shape[:2]
    for hand_landmarks in hand_landmarks_list:
        pts = np.array([[lm.x * w, lm.y * h] for lm in hand_landmarks], dtype=np.float32)
        for (x, y) in pts:
            cv2.circle(frame_bgr, (int(x), int(y)), 2, (0, 255, 0), -1)
        tip = pts[8]
        cv2.circle(frame_bgr, (int(tip[0]), int(tip[1])), 6, (0, 0, 255), 2)


def _draw_landmarks_on_plane(plane_bgr: np.ndarray, lm_box: np.ndarray, color: tuple[int, int, int]) -> None:
    h, w = plane_bgr.shape[:2]
    pts = lm_box.copy()
    pts[:, 0] *= w
    pts[:, 1] *= h
    for (x, y) in pts:
        cv2.circle(plane_bgr, (int(x), int(y)), 2, color, -1)
    tip = pts[8]
    cv2.circle(plane_bgr, (int(tip[0]), int(tip[1])), 6, (0, 0, 255), 2)


def main() -> int:
    parser = argparse.ArgumentParser()
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
    parser.add_argument(
        "--rs-serial",
        type=str,
        default="",
        help="RealSense device serial (optional; use only when multiple devices are connected)",
    )
    parser.add_argument("--rs-fps", type=int, default=30, help="RealSense color FPS")
    parser.add_argument("--max-hands", type=int, default=2)
    parser.add_argument("--flip", action="store_true", help="Mirror horizontally for easy checking")
    parser.add_argument("--viewer-size", type=int, default=720, help="Box plane canvas size (square)")
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
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    corner_ids = _parse_int_list(args.aruco_corner_ids)
    if len(corner_ids) != 4:
        raise ValueError("--aruco-corner-ids must have 4 comma-separated ints (TL,TR,BR,BL)")

    cap, opened_api, cam_label = _open_capture(args)

    landmarker = _build_landmarker(model_path, num_hands=args.max_hands)
    dictionary = _aruco_dict(args.aruco_dict)
    detector_params = cv2.aruco.DetectorParameters()

    last_h_img_to_box: np.ndarray | None = None
    last_h_t_ms: int | None = None

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                time.sleep(0.03)
                continue

            if args.flip:
                frame_bgr = cv2.flip(frame_bgr, 1)

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

            vis = frame_bgr.copy()
            if ids is not None and hasattr(cv2.aruco, "drawDetectedMarkers"):
                cv2.aruco.drawDetectedMarkers(vis, corners, ids)

            _draw_landmarks_on_image(vis, result.hand_landmarks or [])

            plane = np.zeros((args.viewer_size, args.viewer_size, 3), dtype=np.uint8)
            plane[:] = (18, 18, 18)

            # draw border
            cv2.rectangle(plane, (0, 0), (plane.shape[1] - 1, plane.shape[0] - 1), (80, 80, 80), 1)

            hand_landmarks_list = result.hand_landmarks or []
            if aruco_ok and h_img_to_box is not None:
                for hand_index, hand_landmarks in enumerate(hand_landmarks_list):
                    lm_img_px = np.array([[lm.x * w_img, lm.y * h_img] for lm in hand_landmarks], dtype=np.float32)
                    lm_box = _warp_points(lm_img_px, h_img_to_box)
                    # clip for display
                    lm_box = np.clip(lm_box, -0.2, 1.2)
                    color = (200, 200, 200) if hand_index == 0 else (120, 200, 255)
                    _draw_landmarks_on_plane(plane, lm_box, color=color)
            else:
                cv2.putText(
                    plane,
                    "aruco.ok=false (no lm_box)",
                    (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )

            cv2.putText(
                vis,
                f"{cam_label} api={opened_api} aruco_ok={aruco_ok} stale={aruco_stale} age_ms={aruco_age_ms}",
                (10, 24),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )

            cv2.imshow("pc_hand_box_debug_camera (ESC to quit)", vis)
            cv2.imshow("pc_hand_box_debug_plane (ESC to quit)", plane)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        landmarker.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
