from __future__ import annotations

import argparse
import json
import socket
import time
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PC: receive fingertip 3D messages over UDP (JSON).")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=5005, help="Bind port (default: 5005)")
    parser.add_argument("--max-bytes", type=int, default=65535, help="Max UDP packet size")
    parser.add_argument("--print-every", type=int, default=1, help="Print every N valid messages")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))

    last_seq: int | None = None
    count_valid = 0

    print(f"Listening UDP on {args.bind}:{args.port}")

    while True:
        data, addr = sock.recvfrom(args.max_bytes)
        now_ms = int(time.time() * 1000)

        try:
            msg: dict[str, Any] = json.loads(data.decode("utf-8"))
        except Exception:
            print(f"DROP decode_error from {addr} bytes={len(data)}")
            continue

        seq = msg.get("seq")
        valid = bool(msg.get("valid", False))
        t_ms = msg.get("t_ms")

        if isinstance(seq, int) and last_seq is not None and seq > last_seq + 1:
            print(f"MISS seq gap: last={last_seq} now={seq} (+{seq - last_seq - 1})")
        if isinstance(seq, int):
            last_seq = seq

        if not valid:
            continue

        count_valid += 1
        if args.print_every <= 1 or (count_valid % args.print_every == 0):
            latency_ms = None
            if isinstance(t_ms, int):
                latency_ms = now_ms - t_ms
            print(
                json.dumps(
                    {
                        "from": f"{addr[0]}:{addr[1]}",
                        "seq": seq,
                        "latency_ms": latency_ms,
                        "tip_norm": msg.get("tip_norm"),
                    },
                    ensure_ascii=False,
                )
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
