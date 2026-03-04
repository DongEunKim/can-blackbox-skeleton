"""
폴더 감시 - 저장 폴더의 신규 파일 감지 (표준 라이브러리 폴링)
0바이트 파일 제외, 크기 안정 시점에 콜백 호출
"""

import signal
import sys
import time
from pathlib import Path
from typing import Callable, Optional, Set

from src.config_loader import (
    get_logging_config,
    get_watcher_config,
    load_config,
)

# BLF 파일 확장자
BLF_SUFFIX = ".blf"


def _scan_new_files(
    watch_dir: Path,
    known: Set[Path],
    stable: dict,
    min_stable_polls: int,
    on_new_file: Callable[[Path], None],
) -> None:
    """
    폴더 스캔 후 신규/안정된 파일 처리.
    - 0바이트 파일 제외
    - 크기가 min_stable_polls 회 연속 동일한 파일만 콜백 호출 (쓰기 완료 추정)
    """
    if not watch_dir.exists():
        return

    for entry in watch_dir.iterdir():
        if not entry.is_file() or entry.suffix.lower() != BLF_SUFFIX:
            continue

        try:
            size = entry.stat().st_size
        except OSError:
            continue

        if size == 0:
            continue

        path = entry.resolve()
        if path not in known:
            known.add(path)
            stable[path] = (size, 1)
            continue

        if path in stable:
            last_size, count = stable[path]
            if size == last_size:
                count += 1
                stable[path] = (size, count)
                if count >= min_stable_polls:
                    del stable[path]
                    on_new_file(path)
            else:
                stable[path] = (size, 1)


def run_file_watcher(
    config_path: Optional[Path] = None,
    on_new_file: Optional[Callable[[Path], None]] = None,
    after_scan: Optional[Callable[[], None]] = None,
) -> int:
    """
    폴더 감시 메인 루프 (폴링).

    Args:
        config_path: 설정 파일 경로
        on_new_file: 신규 안정된 파일 감지 시 호출할 콜백 (path 전달).
                     None이면 감지만 로그 출력
        after_scan: 매 스캔 후 호출할 콜백 (용량 정리 등)

    Returns:
        종료 코드 (0: 정상)
    """
    config = load_config(config_path)
    log_cfg = get_logging_config(config)
    watcher_cfg = get_watcher_config(config)

    watch_dir = Path(log_cfg["output_dir"])
    poll_interval = watcher_cfg["poll_interval"]
    min_stable_polls = 2

    watch_dir.mkdir(parents=True, exist_ok=True)

    def default_callback(path: Path) -> None:
        print(f"[감지] {path.name}")

    callback = on_new_file if on_new_file is not None else default_callback

    known: Set[Path] = set()
    stable: dict = {}

    # 초기 스캔: 기존 파일은 known에만 등록 (콜백 X)
    _scan_new_files(watch_dir, known, stable, min_stable_polls, lambda _: None)

    running = True

    def signal_handler(signum: int, frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, signal_handler)

    print(f"폴더 감시 시작: {watch_dir} (폴링: {poll_interval}초)")
    print("종료: Ctrl+C")

    while running:
        _scan_new_files(
            watch_dir, known, stable, min_stable_polls, callback
        )
        if after_scan is not None:
            after_scan()
        time.sleep(poll_interval)

    print("종료됨")
    return 0


def main() -> int:
    """CLI 진입점"""
    return run_file_watcher()


if __name__ == "__main__":
    sys.exit(main())
