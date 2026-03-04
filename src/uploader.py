"""
업로더 - StreamManager를 통해 파일을 S3로 전달
파일 전송 성공 시 로컬 파일 삭제 (use_mock=false: status Success 확인 후 삭제)
"""

import sys
from pathlib import Path
from typing import Optional

from src.config_loader import (
    get_logging_config,
    get_storage_config,
    get_stream_manager_config,
    load_config,
)
from src.storage_manager import trim_storage
from src.stream_manager_client import create_stream_manager_client


def run_uploader(config_path: Optional[Path] = None) -> int:
    """
    폴더 감시 + 업로드 메인 루프.
    file_watcher와 연동하여 신규 BLF 파일 전송 후 삭제.

    Returns:
        종료 코드 (0: 정상)
    """
    from src.file_watcher import run_file_watcher

    config = load_config(config_path)
    log_cfg = get_logging_config(config)
    sm_cfg = get_stream_manager_config(config)
    storage_cfg = get_storage_config(config)

    # 모킹 시 mock_uploads를 logs와 별도 경로에
    mock_output_dir = Path(log_cfg["output_dir"]).parent / "mock_uploads"

    try:
        client = create_stream_manager_client(
            sm_cfg,
            mock_output_dir=mock_output_dir,
        )
    except RuntimeError as e:
        print(f"StreamManager 클라이언트 생성 실패: {e}")
        return 1

    watch_dir = Path(log_cfg["output_dir"])
    max_total_mb = storage_cfg["max_total_mb"]

    def on_new_file(path: Path) -> None:
        if client.upload_file(path):
            print(f"[업로드 완료] {path.name}")

    def after_scan() -> None:
        deleted = trim_storage(watch_dir, max_total_mb)
        if deleted > 0:
            print(f"[용량 정리] {deleted}개 파일 삭제")

    try:
        return run_file_watcher(
            config_path=config_path,
            on_new_file=on_new_file,
            after_scan=after_scan,
        )
    finally:
        client.close()


def main() -> int:
    """CLI 진입점"""
    return run_uploader()


if __name__ == "__main__":
    sys.exit(main())
