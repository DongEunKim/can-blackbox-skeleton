"""
CAN 로거 - CAN 버스 메시지를 BLF 형식으로 로깅
다중 CAN 버스 단일 파일 멀티채널 로깅, python-can SizedRotatingLogger 사용
CAN 인터페이스 끊김 시 재연결 복구 지원
"""

import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import can
from can.io.logger import SizedRotatingLogger

from src.config_loader import (
    get_can_config,
    get_logging_config,
    load_config,
)


def _make_channel_listener(
    logger: SizedRotatingLogger,
    channel: int,
) -> Callable[[can.Message], None]:
    """채널을 설정하여 로거에 전달하는 리스너 생성 (멀티채널 단일 파일용)"""

    def on_message(msg: can.Message) -> None:
        # BLF 다중 채널 구분을 위해 channel 속성 설정 (1-based)
        msg.channel = channel
        logger.on_message_received(msg)

    return on_message


def _setup_buses_and_notifiers(
    interfaces: List[str],
    logger: SizedRotatingLogger,
) -> Tuple[List[can.Bus], List[can.Notifier], Optional[str]]:
    """
    버스 및 Notifier 설정.
    실패 시 (buses, notifiers, error_msg) 반환.
    성공 시 error_msg는 None.
    """
    buses: List[can.Bus] = []
    notifiers: List[can.Notifier] = []

    for idx, iface in enumerate(interfaces):
        try:
            bus = can.interface.Bus(
                channel=iface,
                bustype="socketcan",
            )
        except can.CanError as e:
            for n in notifiers:
                n.stop()
            for b in buses:
                b.shutdown()
            return (buses, notifiers, f"CAN 버스 연결 실패 ({iface}): {e}")

        channel = idx + 1
        listener = _make_channel_listener(logger, channel)
        notifier = can.Notifier(bus, [listener])

        buses.append(bus)
        notifiers.append(notifier)

    return (buses, notifiers, None)


def _make_rotation_namer(prefix: str):
    """
    로테이션 파일명: {prefix}{YYYY-MM-DDTHHMMSS}_#N.blf
    - 기본: 세션 시작 시각 + #000
    - 로테이션: 해당 시각 + #001, #002, ...
    """

    def namer(default_name: str) -> str:
        path = Path(default_name)
        # 마지막 _YYYY-MM-DDTHHMMSS_#N 추출 (로테이션 시각 + 순번)
        m = re.search(r"_(\d{4}-\d{2}-\d{2}T\d{6})_#(\d+)\.[^.]+$", path.name)
        if m:
            ts, num = m.groups()
            return str(path.parent / f"{prefix}{ts}_#{num}.blf")
        return str(default_name)

    return namer


def _cleanup(
    notifiers: List[can.Notifier],
    logger: SizedRotatingLogger,
    buses: List[can.Bus],
) -> None:
    """리소스 정리"""
    for notifier in notifiers:
        try:
            notifier.stop()
        except Exception:
            pass
    try:
        logger.stop()
    except Exception:
        pass
    for bus in buses:
        try:
            bus.shutdown()
        except Exception:
            pass


def run_can_logger(config_path: Optional[Path] = None) -> int:
    """
    CAN 버스 로깅 메인 루프 실행.
    다중 인터페이스 동시 지원, 끊김 시 재연결 복구.

    Args:
        config_path: 설정 파일 경로

    Returns:
        종료 코드 (0: 정상, 1: 오류)
    """
    config = load_config(config_path)
    can_cfg = get_can_config(config)
    log_cfg = get_logging_config(config)

    interfaces = can_cfg["interfaces"]
    output_dir = Path(log_cfg["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    log_prefix = log_cfg["log_prefix"]
    max_bytes = int(log_cfg["rotation_max_mb"] * 1024 * 1024)
    max_logging_minutes = log_cfg["max_logging_minutes"]
    max_retries = can_cfg["reconnect_max_retries"]
    retry_interval = can_cfg["reconnect_interval_sec"]

    running = True

    def signal_handler(signum: int, frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    ifaces_str = ", ".join(interfaces)
    print(
        f"CAN 로깅 시작: {ifaces_str} -> {log_cfg['output_dir']} "
        f"(prefix: {log_prefix}, 로테이션: {log_cfg['rotation_max_mb']}MB"
        + (f", 최대 로깅: {max_logging_minutes}분" if max_logging_minutes > 0 else "")
        + (f", 재연결: 최대 {max_retries}회" if max_retries > 0 else "")
        + ")"
    )
    print("종료: Ctrl+C")

    retry_count = 0

    while running:
        start_timestamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
        base_filename = output_dir / f"{log_prefix}{start_timestamp}_#000.blf"
        logger = SizedRotatingLogger(
            base_filename=base_filename,
            max_bytes=max_bytes,
        )
        logger.namer = _make_rotation_namer(log_prefix)

        buses, notifiers, err = _setup_buses_and_notifiers(interfaces, logger)
        if err:
            print(err)
            _cleanup(notifiers, logger, buses)
            if max_retries > 0 and retry_count < max_retries:
                retry_count += 1
                backoff = retry_interval * (2 ** (retry_count - 1))
                print(f"재연결 시도 {retry_count}/{max_retries} ({backoff:.0f}초 후)")
                time.sleep(backoff)
                continue
            return 1

        retry_count = 0  # 성공 시 리셋
        start_time = time.time()
        session_ok = True

        try:
            while running:
                # Notifier 스레드에서 발생한 예외 검사
                for n in notifiers:
                    if getattr(n, "exception", None) is not None:
                        print(f"CAN 오류 감지: {n.exception}")
                        session_ok = False
                        break
                if not session_ok:
                    break

                if max_logging_minutes > 0:
                    elapsed = (time.time() - start_time) / 60
                    if elapsed >= max_logging_minutes:
                        print(
                            f"최대 로깅 시간({max_logging_minutes}분) 경과, "
                            "로깅 중단"
                        )
                        break

                time.sleep(1)
        finally:
            _cleanup(notifiers, logger, buses)

        if not session_ok:
            if max_retries == 0:
                return 1
            retry_count += 1
            if retry_count <= max_retries:
                backoff = retry_interval * (2 ** (retry_count - 1))
                print(
                    f"재연결 시도 {retry_count}/{max_retries} "
                    f"({backoff:.0f}초 후, 새 파일로 재시작)"
                )
                time.sleep(backoff)
            else:
                print("재연결 최대 횟수 초과")
                return 1

    print("종료됨")
    return 0


def main() -> int:
    """CLI 진입점"""
    return run_can_logger()


if __name__ == "__main__":
    sys.exit(main())
