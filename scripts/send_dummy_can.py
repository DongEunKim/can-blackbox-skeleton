#!/usr/bin/env python3
"""
더미 CAN 메시지 송신 스크립트
Virtual CAN(vcan0) 테스트용
종료: Ctrl+C
"""

import argparse
import random
import signal
import sys
import time
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import can
except ImportError:
    print("python-can이 필요합니다: pip install python-can")
    sys.exit(1)


def main() -> int:
    """더미 CAN 메시지를 주기적으로 송신한다."""
    parser = argparse.ArgumentParser(description="더미 CAN 메시지 송신")
    parser.add_argument(
        "interface",
        nargs="?",
        default="vcan0",
        help="CAN 인터페이스 (기본: vcan0)",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=0.05,
        help="송신 간격(초) (기본: 0.05)",
    )
    args = parser.parse_args()

    try:
        bus = can.interface.Bus(channel=args.interface, interface="socketcan")
    except can.CanError as e:
        print(f"CAN 인터페이스 연결 실패: {e}")
        print(f"Virtual CAN 설정: ./scripts/virtual_can_setup.sh {args.interface}")
        return 1

    running = True

    def signal_handler(signum: int, frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    print(f"{args.interface}로 더미 CAN 송신 시작 (간격: {args.interval}s, Ctrl+C 종료)")

    try:
        msg_id = 0x100
        while running:
            data = bytes([random.randint(0, 255) for _ in range(8)])
            msg = can.Message(arbitration_id=msg_id, data=data, is_extended_id=False)
            bus.send(msg)
            msg_id = (msg_id + 1) % 0x800
            time.sleep(args.interval)
    except can.CanError as e:
        print(f"송신 오류: {e}")
        return 1
    finally:
        bus.shutdown()

    print("종료됨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
