"""
StreamManager 모킹 - Greengrass 미설치 환경용
실제 Stream Manager와 동일한 S3 구조(bucket/prefix/날짜/파일명)로 로컬에 저장.
개발 단계와 실제 환경 동작이 혼동되지 않도록 동일 규칙 적용.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class StreamManagerMock:
    """
    Stream Manager 모킹.
    실제와 동일하게 s3_bucket, s3_prefix, 날짜 경로 구조 사용.
    출력: mock_output_dir / bucket / prefix / yyyy/MM/dd / filename
    """

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        *,
        mock_output_dir: Optional[Path] = None,
    ) -> None:
        """
        Args:
            config: get_stream_manager_config() 반환값.
                    s3_bucket, s3_prefix 사용 (비어있으면 기본값)
            mock_output_dir: 모킹 시 루트 저장 경로. None이면 ./mock_uploads
        """
        config = config or {}
        self._s3_bucket = (config.get("s3_bucket") or "").strip() or "mock-bucket"
        self._s3_prefix = (config.get("s3_prefix") or "can-logs/").rstrip("/") + "/"

        self._output_dir = (
            Path(mock_output_dir) if mock_output_dir else Path("mock_uploads")
        )
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._closed = False

    def _resolve_key(self, filename: str) -> Path:
        """실제 S3 키 구조와 동일: prefix + yyyy/MM/dd + filename"""
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
        """
        파일을 S3 구조와 동일한 로컬 경로에 복사.
        실제: s3://bucket/can-logs/yyyy/MM/dd/file.blf
        모킹: mock_output_dir/bucket/can-logs/yyyy/MM/dd/file.blf

        Args:
            path: 업로드할 파일 경로
            delete_on_success: 성공 시 로컬 파일 삭제 여부

        Returns:
            성공 시 True, 실패 시 False
        """
        if self._closed:
            raise RuntimeError("StreamManagerMock already closed")

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
        """클라이언트 종료"""
        self._closed = True
