"""
디렉터리 업로더 - 폴더 스캔 + S3 업로드 + status 처리 + 저장소 정리 통합
aws-greengrass-labs-s3-file-uploader DirectoryUploader 스타일 단일 파일
"""

from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Set

from src.config_loader import (
    get_logging_config,
    get_storage_config,
    get_stream_manager_config,
    get_watcher_config,
    load_config,
)

BLF_SUFFIX = ".blf"


# ---------------------------------------------------------------------------
# 스캔 로직 (file_watcher에서 인라인)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 저장소 로직 (storage_manager에서 인라인)
# ---------------------------------------------------------------------------


def get_total_size_mb(target_dir: Path) -> float:
    """대상 폴더 내 BLF 파일 총 용량(MB)."""
    if not target_dir.exists():
        return 0.0

    total = 0
    for entry in target_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() == BLF_SUFFIX:
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def trim_storage(
    target_dir: Path,
    max_total_mb: float,
    *,
    suffix: str = BLF_SUFFIX,
) -> int:
    """용량 초과 시 오래된 파일부터 삭제. 삭제한 파일 수 반환."""
    if not target_dir.exists() or max_total_mb <= 0:
        return 0

    files: list[tuple[Path, int, float]] = []
    for entry in target_dir.iterdir():
        if entry.is_file() and entry.suffix.lower() == suffix:
            try:
                st = entry.stat()
                if st.st_size > 0:
                    files.append((entry, st.st_size, st.st_mtime))
            except OSError:
                pass

    total_bytes = sum(s for _, s, _ in files)
    max_bytes = int(max_total_mb * 1024 * 1024)
    if total_bytes <= max_bytes:
        return 0

    files.sort(key=lambda x: x[2])

    deleted = 0
    for path, size, _ in files:
        if total_bytes <= max_bytes:
            break
        try:
            path.unlink()
            total_bytes -= size
            deleted += 1
        except OSError:
            pass

    return deleted


# ---------------------------------------------------------------------------
# 모킹 업로드 클라이언트 (stream_manager_mock에서 인라인)
# ---------------------------------------------------------------------------


class MockUploadClient:
    """
    Stream Manager 모킹.
    실제 S3 구조(bucket/prefix/날짜/파일)와 동일한 로컬 경로에 저장.
    """

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        *,
        mock_output_dir: Optional[Path] = None,
    ) -> None:
        config = config or {}
        self._s3_bucket = (config.get("s3_bucket") or "").strip() or "mock-bucket"
        self._s3_prefix = (config.get("s3_prefix") or "can-logs/").rstrip("/") + "/"

        self._output_dir = (
            Path(mock_output_dir) if mock_output_dir else Path("mock_uploads")
        )
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._closed = False

    def _resolve_key(self, filename: str) -> Path:
        now = datetime.now()
        date_part = now.strftime("%Y/%m/%d")
        key = f"{self._s3_prefix}{date_part}/{filename}"
        return Path(key)

    def upload_file(
        self,
        path: Path,
        *,
        delete_on_success: bool = True,
    ) -> bool:
        """파일을 S3 구조와 동일한 로컬 경로에 복사."""
        if self._closed:
            raise RuntimeError("MockUploadClient already closed")

        try:
            data = path.read_bytes()
        except OSError:
            return False

        key_path = self._resolve_key(path.name)
        out_path = self._output_dir / self._s3_bucket / key_path
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
        except OSError:
            return False

        if delete_on_success:
            try:
                path.unlink()
            except OSError:
                pass

        return True

    def close(self) -> None:
        self._closed = True


# ---------------------------------------------------------------------------
# 실제 Stream Manager 클라이언트 (stream_manager_real에서 인라인)
# ---------------------------------------------------------------------------


def _create_real_upload_client(config: dict[str, Any]) -> Any:
    """실제 Greengrass Stream Manager 클라이언트 생성."""
    if config.get("use_mock", True):
        raise ValueError(
            "실제 StreamManager는 use_mock=false 일 때만 사용합니다."
        )
    bucket = config.get("s3_bucket", "").strip()
    if not bucket:
        raise ValueError("s3_bucket이 비어있으면 안 됩니다. config.ini를 확인하세요.")

    try:
        from stream_manager import StreamManagerClient
        from stream_manager.data import (
            ExportDefinition,
            MessageStreamDefinition,
            Persistence,
            ReadMessagesOptions,
            S3ExportTaskDefinition,
            S3ExportTaskExecutorConfig,
            Status,
            StatusConfig,
            StatusLevel,
            StatusMessage,
            StrategyOnFull,
        )
        from stream_manager.exceptions import StreamManagerException
        from stream_manager.util import Util
    except ImportError as e:
        raise RuntimeError(
            "실제 StreamManager 사용 시 Greengrass Stream Manager SDK 필요. "
            "테스트/개발은 config.ini에서 use_mock=true 로 설정"
        ) from e

    stream_name = config["stream_name"]
    status_stream_name = config["status_stream_name"]
    s3_prefix = (config.get("s3_prefix") or "can-logs/").rstrip("/") + "/"

    client = StreamManagerClient()
    existing = set(client.list_streams())

    if status_stream_name not in existing:
        client.create_message_stream(
            MessageStreamDefinition(
                name=status_stream_name,
                max_size=1048576,
                strategy_on_full=StrategyOnFull.OverwriteOldestData,
                persistence=Persistence.Memory,
            )
        )

    if stream_name not in existing:
        client.create_message_stream(
            MessageStreamDefinition(
                name=stream_name,
                max_size=268435456,
                strategy_on_full=StrategyOnFull.OverwriteOldestData,
                persistence=Persistence.File,
                export_definition=ExportDefinition(
                    s3_task_executor=[
                        S3ExportTaskExecutorConfig(
                            identifier="can-blackbox-s3",
                            size_threshold_for_multipart_upload_bytes=5242880,
                            priority=1,
                            disabled=False,
                            status_config=StatusConfig(
                                status_stream_name=status_stream_name,
                                status_level=StatusLevel.INFO,
                            ),
                        )
                    ]
                ),
            )
        )

    def upload_file(path: Path, *, delete_on_success: bool = True) -> bool:
        abs_path = path.resolve()
        if not abs_path.exists():
            return False

        input_url = f"file://{abs_path}"
        s3_key = f"{s3_prefix}!{{timestamp:yyyy/MM/dd}}/{path.name}"

        task = S3ExportTaskDefinition(
            input_url=input_url,
            bucket=bucket,
            key=s3_key,
            user_metadata={"source": "can-blackbox"},
        )
        task_bytes = Util.validate_and_serialize_to_json_bytes(task)

        try:
            client.append_message(stream_name=stream_name, data=task_bytes)
        except (StreamManagerException, ConnectionError, TimeoutError) as e:
            print(f"[업로드 실패] 태스크 전달 오류 {path}: {e}")
            return False

        max_wait_sec = 300
        poll_interval_sec = 2
        start = time.monotonic()

        while (time.monotonic() - start) < max_wait_sec:
            try:
                messages = client.read_messages(
                    status_stream_name,
                    ReadMessagesOptions(
                        min_message_count=1,
                        max_message_count=10,
                        read_timeout_millis=3000,
                    ),
                )
            except (StreamManagerException, ConnectionError, TimeoutError):
                time.sleep(poll_interval_sec)
                continue

            for msg in messages:
                try:
                    status_msg = Util.deserialize_json_bytes_to_obj(
                        msg.payload, StatusMessage
                    )
                except Exception:
                    continue

                ctx = status_msg.status_context
                if not ctx or not ctx.s3_export_task_definition:
                    continue
                if ctx.s3_export_task_definition.input_url != input_url:
                    continue

                if status_msg.status == Status.Success:
                    if delete_on_success:
                        try:
                            path.unlink()
                        except OSError as e:
                            print(f"[경고] 업로드 성공했으나 삭제 실패 {path}: {e}")
                    return True
                if status_msg.status in (Status.Failure, Status.Canceled):
                    print(
                        f"[업로드 실패] {path}: {status_msg.status.name} - "
                        f"{status_msg.message or '알 수 없음'}"
                    )
                    return False

            time.sleep(poll_interval_sec)

        print(f"[업로드 실패] {path}: status stream 응답 시간 초과 ({max_wait_sec}s)")
        return False

    def close() -> None:
        client.close()

    class RealUploadClient:
        upload_file = staticmethod(upload_file)
        close = staticmethod(close)

    return RealUploadClient()


def create_upload_client(
    config: dict[str, Any],
    *,
    mock_output_dir: Optional[Path] = None,
) -> Any:
    """
    설정에 따라 모킹 또는 실제 업로드 클라이언트 생성.
    upload_file(path, delete_on_success=True), close() 메서드 제공.
    """
    if config.get("use_mock", True):
        return MockUploadClient(config=config, mock_output_dir=mock_output_dir)
    return _create_real_upload_client(config)


# ---------------------------------------------------------------------------
# DirectoryUploader
# ---------------------------------------------------------------------------


class DirectoryUploader:
    """
    폴더 스캔 + S3 업로드 + status 처리 + 저장소 정리 통합.
    """

    def __init__(
        self,
        watch_dir: Path,
        client: Any,
        *,
        max_total_mb: float = 500,
        poll_interval: int = 5,
        min_stable_polls: int = 2,
    ) -> None:
        """
        Args:
            watch_dir: 감시 대상 디렉터리
            client: upload_file(path), close() 메서드 제공
            max_total_mb: 최대 총 용량(MB)
            poll_interval: 폴링 주기(초)
            min_stable_polls: 크기 안정 판별 최소 연속 횟수
        """
        self._watch_dir = Path(watch_dir)
        self._client = client
        self._max_total_mb = max_total_mb
        self._poll_interval = poll_interval
        self._min_stable_polls = min_stable_polls

        self._known: Set[Path] = set()
        self._stable: dict = {}
        self._failed: Set[Path] = set()
        self._closed = False

    def _on_new_file(self, path: Path) -> None:
        if self._closed:
            return

        success = self._client.upload_file(path)
        if success:
            print(f"[업로드 완료] {path.name}")
            if path in self._failed:
                self._failed.discard(path)
        else:
            self._failed.add(path)
            self._known.discard(path)

    def _scan(self) -> None:
        if not self._watch_dir.exists():
            return

        for path in self._failed:
            self._known.discard(path)
        self._failed.clear()

        _scan_new_files(
            self._watch_dir,
            self._known,
            self._stable,
            self._min_stable_polls,
            self._on_new_file,
        )

    def _trim_storage(self) -> int:
        return trim_storage(self._watch_dir, self._max_total_mb)

    def _check_directory_access(self) -> bool:
        if not self._watch_dir.exists():
            return False
        try:
            return os.access(
                self._watch_dir, os.R_OK | os.W_OK | os.X_OK
            )
        except OSError:
            return False

    def run(self) -> int:
        """메인 루프. 스캔 → trim → sleep 반복. SIGINT 시 정상 종료."""
        if self._closed:
            return 1

        _running = True

        def _signal_handler(signum: int, frame: object) -> None:
            nonlocal _running
            _running = False

        signal.signal(signal.SIGINT, _signal_handler)

        self._watch_dir.mkdir(parents=True, exist_ok=True)

        while not self._check_directory_access():
            print(
                f"[경고] {self._watch_dir} 권한(rwx) 부족. 60초 후 재시도..."
            )
            time.sleep(60)

        print(f"폴더 감시 시작: {self._watch_dir} (폴링: {self._poll_interval}초)")
        print("종료: Ctrl+C")

        while _running:
            try:
                self._scan()
                deleted = self._trim_storage()
                if deleted > 0:
                    print(f"[용량 정리] {deleted}개 파일 삭제")
            except Exception as e:
                print(f"[오류] 스캔/정리 중 예외: {e}")
            if _running:
                time.sleep(self._poll_interval)

        print("종료됨")
        return 0

    def close(self) -> None:
        if not self._closed:
            self._client.close()
            self._closed = True


# ---------------------------------------------------------------------------
# 메인 진입점 (uploader 통합)
# ---------------------------------------------------------------------------


def main(config_path: Optional[Path] = None) -> int:
    """
    업로더 메인 루프. config 로드 → DirectoryUploader 실행.
    예외 시 60초 대기 후 재시작.
    """
    restart_interval_sec = 60

    while True:
        du = None
        try:
            config = load_config(config_path)
            log_cfg = get_logging_config(config)
            sm_cfg = get_stream_manager_config(config)
            storage_cfg = get_storage_config(config)
            watcher_cfg = get_watcher_config(config)

            mock_output_dir = Path(log_cfg["output_dir"]).parent / "mock_uploads"

            client = create_upload_client(
                sm_cfg,
                mock_output_dir=mock_output_dir,
            )

            du = DirectoryUploader(
                watch_dir=Path(log_cfg["output_dir"]),
                client=client,
                max_total_mb=storage_cfg["max_total_mb"],
                poll_interval=watcher_cfg["poll_interval"],
            )
            exit_code = du.run()
            if exit_code == 0:
                return 0
        except ValueError as e:
            print(f"설정 오류: {e}")
            return 1
        except FileNotFoundError as e:
            print(f"설정 파일 오류: {e}")
            return 1
        except RuntimeError as e:
            print(f"StreamManager 클라이언트 생성 실패: {e}")
            return 1
        except Exception:
            print("예외 발생, 60초 후 재시작...")
            import traceback

            traceback.print_exc()
        finally:
            if du is not None:
                du.close()
        time.sleep(restart_interval_sec)


if __name__ == "__main__":
    sys.exit(main())
