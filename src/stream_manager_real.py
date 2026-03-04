"""
실제 Greengrass Stream Manager 클라이언트
S3ExportTaskDefinition으로 로컬 파일 업로드, status stream으로 완료 확인 후 삭제
use_mock=false 일 때만 사용
"""

import time
from pathlib import Path
from typing import Any

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


class StreamManagerReal:
    """
    실제 Greengrass Stream Manager 래퍼.
    S3 업로드: S3ExportTaskDefinition append → status stream Success 대기 → 로컬 삭제
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """
        Args:
            config: get_stream_manager_config() 반환값.
                    use_mock=false, s3_bucket, s3_prefix, stream_name, status_stream_name 필요
        """
        if config.get("use_mock", True):
            raise ValueError(
                "StreamManagerReal은 use_mock=false 일 때만 사용합니다. "
                "config.ini에서 use_mock=true 이면 StreamManagerMock이 사용됩니다."
            )
        bucket = config.get("s3_bucket", "").strip()
        if not bucket:
            raise ValueError(
                "실제 StreamManager 사용 시 s3_bucket이 비어있으면 안 됩니다. config.ini를 확인하세요."
            )

        self._config = config
        self._stream_name = config["stream_name"]
        self._status_stream_name = config["status_stream_name"]
        self._s3_bucket = bucket
        self._s3_prefix = (config.get("s3_prefix") or "can-logs/").rstrip("/") + "/"
        self._client = StreamManagerClient()
        self._closed = False

        self._ensure_streams()

    def _ensure_streams(self) -> None:
        """status 스트림과 export 스트림이 없으면 생성"""
        existing = set(self._client.list_streams())

        if self._status_stream_name not in existing:
            self._client.create_message_stream(
                MessageStreamDefinition(
                    name=self._status_stream_name,
                    max_size=1048576,  # 1MB
                    strategy_on_full=StrategyOnFull.OverwriteOldestData,
                    persistence=Persistence.Memory,
                )
            )

        if self._stream_name not in existing:
            self._client.create_message_stream(
                MessageStreamDefinition(
                    name=self._stream_name,
                    max_size=268435456,  # 256MB
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
                                    status_stream_name=self._status_stream_name,
                                    status_level=StatusLevel.INFO,
                                ),
                            )
                        ]
                    ),
                )
            )

    def upload_file(
        self,
        path: Path,
        *,
        delete_on_success: bool = True,
    ) -> bool:
        """
        로컬 파일을 S3로 업로드. Stream Manager가 업로드 완료 후 status stream에 알림.
        Success 확인 시에만 delete_on_success면 로컬 파일 삭제.

        Args:
            path: 업로드할 로컬 파일 경로
            delete_on_success: 업로드 성공 시 로컬 파일 삭제 여부

        Returns:
            성공 시 True, 실패 시 False
        """
        if self._closed:
            raise RuntimeError("StreamManagerReal already closed")

        abs_path = path.resolve()
        if not abs_path.exists():
            return False

        input_url = str(abs_path)
        # Stream Manager가 업로드 시 !{timestamp:...} 플레이스홀더 해석
        s3_key = f"{self._s3_prefix}!{{timestamp:yyyy/MM/dd}}/{path.name}"

        task = S3ExportTaskDefinition(
            input_url=input_url,
            bucket=self._s3_bucket,
            key=s3_key,
            user_metadata={"source": "can-blackbox"},
        )
        task_bytes = Util.validate_and_serialize_to_json_bytes(task)

        try:
            self._client.append_message(
                stream_name=self._stream_name,
                data=task_bytes,
            )
        except (StreamManagerException, ConnectionError, TimeoutError) as e:
            print(f"[업로드 실패] 태스크 전달 오류 {path}: {e}")
            return False

        # status stream에서 Success/Failure/Canceled 대기
        if not self._wait_for_status(input_url, delete_on_success, path):
            return False

        return True

    def _wait_for_status(
        self,
        input_url: str,
        delete_on_success: bool,
        path: Path,
    ) -> bool:
        """status stream에서 해당 input_url의 업로드 완료 대기"""
        max_wait_sec = 300  # 5분
        poll_interval_sec = 2
        start = time.monotonic()

        while (time.monotonic() - start) < max_wait_sec:
            try:
                messages = self._client.read_messages(
                    self._status_stream_name,
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
                        f"[업로드 실패] {path}: {status_msg.status.name} - {status_msg.message or '알 수 없음'}"
                    )
                    return False

            time.sleep(poll_interval_sec)

        print(f"[업로드 실패] {path}: status stream 응답 시간 초과 ({max_wait_sec}s)")
        return False

    def close(self) -> None:
        """클라이언트 종료"""
        if not self._closed:
            self._client.close()
            self._closed = True
