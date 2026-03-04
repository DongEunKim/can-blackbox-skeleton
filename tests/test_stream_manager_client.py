"""
StreamManager 클라이언트 팩토리 단위 테스트
"""

from pathlib import Path

import pytest

from src.stream_manager_client import create_stream_manager_client


def test_create_mock_client(tmp_path: Path) -> None:
    """use_mock=true 시 StreamManagerMock 반환, S3 구조로 upload_file 동작"""
    config = {
        "use_mock": True,
        "stream_name": "TestStream",
        "s3_bucket": "test-bucket",
        "s3_prefix": "logs/",
    }
    client = create_stream_manager_client(config, mock_output_dir=tmp_path)
    f = tmp_path / "in" / "test.blf"
    f.parent.mkdir()
    f.write_bytes(b"data")
    result = client.upload_file(f)
    client.close()
    assert result is True
    blfs = list((tmp_path / "test-bucket" / "logs").rglob("test.blf"))
    assert len(blfs) == 1
    assert blfs[0].read_bytes() == b"data"


def test_create_real_client_requires_s3_bucket() -> None:
    """use_mock=false, s3_bucket 비어있으면 ValueError"""
    config = {
        "use_mock": False,
        "stream_name": "TestStream",
        "status_stream_name": "StatusStream",
        "s3_bucket": "",
        "s3_prefix": "can-logs/",
    }
    with pytest.raises(ValueError, match="s3_bucket"):
        create_stream_manager_client(config)


def test_create_real_client_use_mock_true_raises() -> None:
    """StreamManagerReal은 use_mock=false 일 때만 사용 (직접 생성 시)"""
    from src.stream_manager_real import StreamManagerReal

    config = {
        "use_mock": True,
        "stream_name": "S",
        "status_stream_name": "Status",
        "s3_bucket": "bucket",
        "s3_prefix": "p/",
    }
    with pytest.raises(ValueError, match="use_mock=false"):
        StreamManagerReal(config)
