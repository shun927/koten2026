from __future__ import annotations

import argparse
import json
import socketserver
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any


def _load_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pi: MediaPipe hand landmarks preview as MJPEG over HTTP."
    )
    parser.add_argument("--config", help="Path to config JSON (e.g. config/endpoint.json)")
    parser.add_argument("--model", help="Path to hand_landmarker.task")
    parser.add_argument("--bind", default="0.0.0.0", help="HTTP bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    parser.add_argument("--fps", type=int, help="Preview FPS cap (default: from config or 15)")
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
        from picamera2 import Picamera2  # type: ignore

        self._cam = Picamera2()
        config = self._cam.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self._cam.configure(config)
        try:
            self._cam.set_controls({"FrameRate": fps})
        except Exception:
            pass
        self._cam.start()

    def read_rgb(self) -> Any | None:
        return self._cam.capture_array()

    def close(self) -> None:
        try:
            self._cam.stop()
        finally:
            self._cam.close()


_HAND_CONNECTIONS: list[tuple[int, int]] = [
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
]


class _LatestJpeg:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jpeg: bytes | None = None
        self._t_ms: int = 0

    def set(self, jpeg: bytes) -> None:
        with self._lock:
            self._jpeg = jpeg
            self._t_ms = int(time.time() * 1000)

    def get(self) -> tuple[bytes | None, int]:
        with self._lock:
            return self._jpeg, self._t_ms


class _MjpegHandler(BaseHTTPRequestHandler):
    latest: _LatestJpeg

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/", "/mjpeg"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if self.path == "/":
            html = (
                "<html><head><meta charset='utf-8'></head><body>"
                "<h3>koten2026 MJPEG preview</h3>"
                "<img src='/mjpeg' />"
                "</body></html>"
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        boundary = "frame"
        self.send_response(HTTPStatus.OK)
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Type", f"multipart/x-mixed-replace; boundary={boundary}")
        self.end_headers()

        last_t_ms = 0
        try:
            while True:
                jpeg, t_ms = self.latest.get()
                if jpeg is None:
                    time.sleep(0.05)
                    continue
                if t_ms == last_t_ms:
                    time.sleep(0.02)
                    continue
                last_t_ms = t_ms

                self.wfile.write(f"--{boundary}\r\n".encode("ascii"))
                self.wfile.write(b"Content-Type: image/jpeg\r\n")
                self.wfile.write(f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii"))
                self.wfile.write(jpeg)
                self.wfile.write(b"\r\n")
        except BrokenPipeError:
            return
        except ConnectionResetError:
            return

    def log_message(self, fmt: str, *args: object) -> None:
        # Quiet HTTP logs (optional).
        return


def _run_capture_loop(latest: _LatestJpeg, cfg: dict[str, Any], model_path: str, fps_cap: int) -> None:
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    import mediapipe as mp  # type: ignore
    from mediapipe.tasks.python import BaseOptions  # type: ignore
    from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions  # type: ignore
    from mediapipe.tasks.python.vision import RunningMode  # type: ignore

    camera_cfg = cfg.get("camera") or {}
    camera_device = camera_cfg.get("device", "picamera2")
    width = int(camera_cfg.get("width") or 640)
    height = int(camera_cfg.get("height") or 480)
    fps = int(camera_cfg.get("fps") or fps_cap)
    max_hands = int(cfg.get("max_hands") or 2)
    min_det = float(cfg.get("min_hand_detection_confidence", 0.1))
    min_pres = float(cfg.get("min_hand_presence_confidence", 0.1))
    min_track = float(cfg.get("min_tracking_confidence", 0.1))

    if isinstance(camera_device, str) and camera_device.lower() in {"picamera2", "picam", "pi"}:
        source: _FrameSource = _Picamera2Source(width=width, height=height, fps=fps)
    else:
        source = _OpenCvSource(camera_index=int(camera_device), width=width, height=height, fps=fps)

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.VIDEO,
        num_hands=max_hands,
        min_hand_detection_confidence=min_det,
        min_hand_presence_confidence=min_pres,
        min_tracking_confidence=min_track,
    )

    frame_interval = 1.0 / max(1, fps_cap)
    next_t = time.time()

    with HandLandmarker.create_from_options(options) as landmarker:
        try:
            while True:
                frame_rgb = source.read_rgb()
                if frame_rgb is None:
                    continue
                frame_rgb = np.ascontiguousarray(frame_rgb)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)

                t_mp_ms = int(time.monotonic() * 1000)
                result = landmarker.detect_for_video(mp_image, t_mp_ms)
                hands = getattr(result, "hand_landmarks", None) or []

                # Draw on BGR for OpenCV encoding.
                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                for hand in hands:
                    pts: list[tuple[int, int]] = []
                    for lm in hand:
                        x = int(max(0.0, min(1.0, float(lm.x))) * (width - 1))
                        y = int(max(0.0, min(1.0, float(lm.y))) * (height - 1))
                        pts.append((x, y))
                        cv2.circle(frame_bgr, (x, y), 3, (0, 255, 0), -1)
                    for a, b in _HAND_CONNECTIONS:
                        if a < len(pts) and b < len(pts):
                            cv2.line(frame_bgr, pts[a], pts[b], (255, 0, 0), 2)

                cv2.putText(
                    frame_bgr,
                    f"hands={len(hands)}",
                    (10, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

                ok, jpg = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
                if ok:
                    latest.set(jpg.tobytes())

                now = time.time()
                if now < next_t:
                    time.sleep(max(0.0, next_t - now))
                next_t = max(next_t + frame_interval, time.time())
        finally:
            source.close()


def main() -> int:
    args = _parse_args()
    cfg = _load_json(args.config)
    model_path = args.model or cfg.get("model_path") or "./hand_landmarker.task"
    fps_cap = int(args.fps or cfg.get("preview_fps") or 15)

    latest = _LatestJpeg()

    capture_thread = threading.Thread(
        target=_run_capture_loop, args=(latest, cfg, model_path, fps_cap), daemon=True
    )
    capture_thread.start()

    handler = _MjpegHandler
    handler.latest = latest

    class _ThreadingHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True

    with _ThreadingHTTPServer((args.bind, args.port), handler) as httpd:
        print(f"Open in browser: http://{args.bind}:{args.port}/  (or use Pi IP)")
        print(f"Listening on {args.bind}:{args.port}  model={model_path}")
        httpd.serve_forever()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

