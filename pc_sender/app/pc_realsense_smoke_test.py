r"""
pc_realsense_smoke_test.py

RealSense (recommended: D435i) smoke test:
- Enumerate devices
- Start Color+Depth streams
- Align depth to color
- Show preview (optional) and print center depth distance

Examples (PowerShell, from pc_sender/):
  .\.venv\Scripts\python .\app\pc_realsense_smoke_test.py --preview
  .\.venv\Scripts\python .\app\pc_realsense_smoke_test.py --serial <D435I_SERIAL> --width 640 --height 480 --fps 30 --preview
  .\.venv\Scripts\python .\app\pc_realsense_smoke_test.py --duration-sec 10 --no-preview

Notes:
- Requires Intel RealSense SDK 2.0 / librealsense and Python package `pyrealsense2`.
- USB3 is recommended for stable FPS.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any


def _import_rs():
    try:
        import pyrealsense2 as rs  # type: ignore

        return rs
    except Exception as e:  # noqa: BLE001
        msg = (
            "Failed to import pyrealsense2.\n"
            "- Install Intel RealSense SDK 2.0 (librealsense)\n"
            "- Install Python package: pip install pyrealsense2\n"
            f"Error: {e}\n"
        )
        raise RuntimeError(msg) from e


def _try_import_cv2_numpy():
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        return cv2, np
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            "Preview requires opencv-python and numpy.\n"
            "Install: pip install opencv-python numpy\n"
            f"Error: {e}\n"
        ) from e


def _try_import_numpy_only():
    try:
        import numpy as np  # type: ignore

        return np
    except Exception:
        return None


def _center_depth_stats(
    depth,
    depth_scale: float,
    cx: int,
    cy: int,
    window: int,
    max_depth_m: float,
):
    """
    Returns:
      (center_m, median_m, valid_ratio)
    - center_m: depth.get_distance(cx, cy) (meters)
    - median_m: median in NxN window ignoring invalid/0 and out-of-range
    - valid_ratio: fraction of valid samples used for median
    """
    # After applying librealsense filters, the returned object can be a generic `frame`
    # without `get_distance`. Fall back to raw depth value * scale in that case.
    if hasattr(depth, "get_distance"):
        center_m = float(depth.get_distance(int(cx), int(cy)))
    else:
        np = _try_import_numpy_only()
        if np is not None:
            raw = np.asanyarray(depth.get_data())  # uint16
            center_m = float(raw[int(cy), int(cx)]) * float(depth_scale)
        else:
            center_m = 0.0
    # Treat invalid / out-of-range as NaN to avoid misleading huge values like 65.535m (uint16=65535).
    if not (0.0 < float(center_m) < float(max_depth_m)):
        center_m = float("nan")

    w = int(window)
    if w <= 1:
        return center_m, center_m, 1.0 if center_m == center_m else 0.0
    if w % 2 == 0:
        w += 1

    np = _try_import_numpy_only()
    if np is not None:
        raw = np.asanyarray(depth.get_data())  # uint16
        h, ww = raw.shape[:2]
        r = w // 2
        x0 = max(0, int(cx) - r)
        x1 = min(ww, int(cx) + r + 1)
        y0 = max(0, int(cy) - r)
        y1 = min(h, int(cy) + r + 1)
        patch = raw[y0:y1, x0:x1].astype("float32") * float(depth_scale)
        valid = (patch > 0.0) & (patch < float(max_depth_m))
        vals = patch[valid]
        if vals.size == 0:
            return center_m, float("nan"), 0.0
        median_m = float(np.median(vals))
        valid_ratio = float(vals.size) / float(patch.size)
        return center_m, median_m, valid_ratio

    # Fallback without numpy: sample via get_distance (slower but robust).
    r = w // 2
    samples = []
    total = 0
    valid_n = 0
    for yy in range(int(cy) - r, int(cy) + r + 1):
        if yy < 0:
            continue
        for xx in range(int(cx) - r, int(cx) + r + 1):
            if xx < 0:
                continue
            total += 1
            d = float(depth.get_distance(int(xx), int(yy)))
            if 0.0 < d < float(max_depth_m):
                samples.append(d)
                valid_n += 1

    if not samples:
        return center_m, float("nan"), 0.0
    samples.sort()
    median_m = samples[len(samples) // 2]
    valid_ratio = float(valid_n) / float(max(total, 1))
    return center_m, float(median_m), valid_ratio


def _build_depth_filters(rs, args) -> list[Any]:
    filters: list[Any] = []
    if bool(args.decimate):
        filters.append(rs.decimation_filter())
    if bool(args.spatial):
        filters.append(rs.spatial_filter())
    if bool(args.temporal):
        filters.append(rs.temporal_filter())
    if bool(args.hole_filling):
        filters.append(rs.hole_filling_filter())
    return filters


def _apply_depth_filters(depth_frame, filters: list[Any]):
    out = depth_frame
    for f in filters:
        out = f.process(out)
    # Cast back to depth frame so callers can use depth APIs (get_distance, etc.).
    if hasattr(out, "as_depth_frame"):
        try:
            out = out.as_depth_frame()
        except Exception:  # noqa: BLE001
            pass
    return out


def _list_devices(rs) -> list[dict]:
    ctx = rs.context()
    out: list[dict] = []
    for dev in ctx.devices:
        info = {}
        for k in (
            rs.camera_info.name,
            rs.camera_info.serial_number,
            rs.camera_info.firmware_version,
            rs.camera_info.usb_type_descriptor,
        ):
            try:
                info[str(k)] = dev.get_info(k)
            except Exception:  # noqa: BLE001
                pass
        out.append(info)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="RealSense (D435i recommended) smoke test")
    parser.add_argument("--serial", type=str, default="", help="Use specific device serial number")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--depth-scale", type=float, default=0.0, help="Override depth scale (meters per unit)")
    parser.add_argument("--preview", action="store_true", help="Show OpenCV preview windows")
    parser.add_argument("--no-preview", action="store_true", help="Disable preview even if OpenCV is available")
    parser.add_argument("--print-every", type=int, default=15, help="Print center depth every N frames")
    parser.add_argument(
        "--center-window",
        type=int,
        default=5,
        help="Compute median depth in NxN window around center (odd number recommended).",
    )
    parser.add_argument(
        "--max-depth-m",
        type=float,
        default=2.0,
        help="Ignore depth samples >= this value when computing median.",
    )
    parser.add_argument("--decimate", action="store_true", help="Apply depth decimation filter")
    parser.add_argument("--spatial", action="store_true", help="Apply depth spatial smoothing filter")
    parser.add_argument("--temporal", action="store_true", help="Apply depth temporal smoothing filter")
    parser.add_argument("--hole-filling", action="store_true", help="Apply depth hole filling filter")
    parser.add_argument("--duration-sec", type=float, default=0.0, help="Stop after N seconds (0 = run until ESC/Ctrl+C)")
    args = parser.parse_args()

    rs = _import_rs()
    devices = _list_devices(rs)
    if not devices:
        print("No RealSense devices found. Check USB connection and driver/SDK install.", file=sys.stderr)
        return 2

    print("RealSense devices:")
    for i, info in enumerate(devices):
        name = info.get(str(rs.camera_info.name), "Unknown")
        serial = info.get(str(rs.camera_info.serial_number), "Unknown")
        fw = info.get(str(rs.camera_info.firmware_version), "Unknown")
        usb = info.get(str(rs.camera_info.usb_type_descriptor), "Unknown")
        print(f"  [{i}] name={name} serial={serial} fw={fw} usb={usb}")

    want_preview = bool(args.preview) and not bool(args.no_preview)
    cv2 = np = None
    if want_preview:
        cv2, np = _try_import_cv2_numpy()

    pipeline = rs.pipeline()
    config = rs.config()
    if args.serial:
        config.enable_device(args.serial)
    config.enable_stream(rs.stream.color, args.width, args.height, rs.format.bgr8, args.fps)
    config.enable_stream(rs.stream.depth, args.width, args.height, rs.format.z16, args.fps)

    print("Starting pipeline...")
    profile = pipeline.start(config)

    try:
        depth_sensor = profile.get_device().first_depth_sensor()
        depth_scale = float(args.depth_scale) if args.depth_scale > 0 else float(depth_sensor.get_depth_scale())
        try:
            name = profile.get_device().get_info(rs.camera_info.name)
            serial = profile.get_device().get_info(rs.camera_info.serial_number)
        except Exception:  # noqa: BLE001
            name = "Unknown"
            serial = "Unknown"

        print(f"Device: {name} serial={serial}")
        print(f"Depth scale: {depth_scale} (meters per unit)")
        print("Running... (ESC to quit if preview enabled, Ctrl+C to quit)")

        align = rs.align(rs.stream.color)
        depth_filters = _build_depth_filters(rs, args)
        if depth_filters:
            enabled = []
            if args.decimate:
                enabled.append("decimate")
            if args.spatial:
                enabled.append("spatial")
            if args.temporal:
                enabled.append("temporal")
            if args.hole_filling:
                enabled.append("hole_filling")
            print(f"Depth filters: {', '.join(enabled)}")
        frame_i = 0
        t0 = time.time()

        while True:
            if args.duration_sec > 0 and (time.time() - t0) >= float(args.duration_sec):
                break

            frames = pipeline.wait_for_frames(timeout_ms=5000)
            frames = align.process(frames)
            color = frames.get_color_frame()
            depth = frames.get_depth_frame()
            if not color or not depth:
                continue
            if depth_filters:
                depth = _apply_depth_filters(depth, depth_filters)

            # Center depth distance (meters). Use distance API, which respects device scale.
            w = int(color.get_width())
            h = int(color.get_height())
            cx = w // 2
            cy = h // 2
            d_center_m, d_med_m, valid_ratio = _center_depth_stats(
                depth=depth,
                depth_scale=depth_scale,
                cx=cx,
                cy=cy,
                window=int(args.center_window),
                max_depth_m=float(args.max_depth_m),
            )

            if args.print_every > 0 and (frame_i % int(args.print_every) == 0):
                vr = int(round(valid_ratio * 100))
                print(
                    f"frame={frame_i} size={w}x{h} "
                    f"depth_center_m={d_center_m:.3f} depth_med_m={d_med_m:.3f} valid={vr}%"
                )

            if want_preview and cv2 is not None and np is not None:
                color_bgr = np.asanyarray(color.get_data())
                depth_raw = np.asanyarray(depth.get_data())  # uint16

                # Convert to meters for display (avoid division by zero).
                depth_m = depth_raw.astype("float32") * depth_scale
                depth_vis = cv2.convertScaleAbs(depth_m, alpha=255.0 / 2.0)  # 0..~2m mapped to 0..255
                depth_vis = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)

                cv2.circle(color_bgr, (cx, cy), 6, (0, 0, 255), 2)
                vr = int(round(valid_ratio * 100))
                cv2.putText(
                    color_bgr,
                    f"center={d_center_m:.3f}m med={d_med_m:.3f}m valid={vr}%",
                    (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 0),
                    2,
                )

                stacked = np.hstack([color_bgr, depth_vis])
                cv2.imshow("RealSense Color | Depth (aligned)", stacked)
                if (cv2.waitKey(1) & 0xFF) == 27:
                    break

            frame_i += 1

    except KeyboardInterrupt:
        pass
    finally:
        pipeline.stop()
        if want_preview and cv2 is not None:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
