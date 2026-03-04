"""
StreamManager 클라이언트 팩토리
설정에 따라 모킹 또는 실제 Greengrass StreamManager 반환
"""

from pathlib import Path
from typing import Optional, Protocol

from src.stream_manager_mock import StreamManagerMock


class StreamManagerClientProtocol(Protocol):
    """StreamManager 클라이언트 공통 인터페이스"""

    def upload_file(
        self,
        path: Path,
        *,
        delete_on_success: bool = True,
    ) -> bool:
        """
        파일 업로드.
        모킹: mock_uploads에 복사 후 삭제.
        실제: S3ExportTaskDefinition 전달 → status Success 확인 후 삭제.

        Returns:
            성공 시 True, 실패 시 False
        """
        ...

    def close(self) -> None:
        """클라이언트 종료"""
        ...


def create_stream_manager_client(
    config: dict,
    *,
    mock_output_dir: Optional[Path] = None,
) -> StreamManagerClientProtocol:
    """
    설정에 따라 StreamManager 클라이언트 생성.

    Args:
        config: get_stream_manager_config() 반환값
        mock_output_dir: use_mock 시 저장 경로 (None이면 ./mock_uploads)

    Returns:
        upload_file(), close() 메서드 제공 클라이언트

    Raises:
        RuntimeError: use_mock=false 이나 실제 클라이언트 생성 실패
    """
    if config.get("use_mock", True):
        return StreamManagerMock(config=config, mock_output_dir=mock_output_dir)

    return _create_real_client(config)


def _create_real_client(config: dict) -> StreamManagerClientProtocol:
    """
    실제 Greengrass StreamManager 클라이언트 생성.
    Greengrass 환경 배포 시 구현.
    """
    try:
        from src.stream_manager_real import StreamManagerReal

        return StreamManagerReal(config)
    except (ImportError, NotImplementedError) as e:
        raise RuntimeError(
            "실제 StreamManager 사용 시 stream_manager_real 구현 및 "
            "Greengrass Stream Manager SDK 필요. "
            "테스트/개발은 config.ini에서 use_mock=true 로 설정"
        ) from e
