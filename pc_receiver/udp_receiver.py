import argparse
import json
import socket
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    sock.settimeout(1.0)

    last_seq = None
    print(f"Listening UDP {args.bind}:{args.port}")

    while True:
        try:
            data, addr = sock.recvfrom(65535)
        except TimeoutError:
            continue
        except socket.timeout:
            continue

        try:
            msg = json.loads(data.decode("utf-8", errors="replace"))
        except Exception:
            print(f"[{time.time():.3f}] {addr} <non-json> {data[:120]!r}")
            continue

        seq = msg.get("seq")
        if isinstance(seq, int) and isinstance(last_seq, int) and seq != last_seq + 1:
            print(f"seq jump: {last_seq} -> {seq} (from {addr[0]}:{addr[1]})")
        last_seq = seq if isinstance(seq, int) else last_seq

        if args.pretty:
            print(json.dumps(msg, ensure_ascii=False, indent=2))
        else:
            print(msg)


if __name__ == "__main__":
    raise SystemExit(main())

