"""
StreamManager 모킹 단위 테스트
"""

from pathlib import Path

import pytest

from src.stream_manager_mock import StreamManagerMock


def test_upload_file_success(tmp_path: Path) -> None:
    """upload_file 성공 시 S3 구조(bucket/prefix/날짜/파일명)로 복사 후 원본 삭제"""
    config = {"s3_bucket": "test-bucket", "s3_prefix": "logs/"}
    f = tmp_path / "test.blf"
    f.write_bytes(b"blf content")

    mock = StreamManagerMock(config=config, mock_output_dir=tmp_path / "out")
    result = mock.upload_file(f)
    mock.close()

    assert result is True
    assert not f.exists()
    # mock_output_dir / bucket / prefix / yyyy/MM/dd / filename
    blfs = list((tmp_path / "out" / "test-bucket" / "logs").rglob("test.blf"))
    assert len(blfs) == 1
    assert blfs[0].read_bytes() == b"blf content"


def test_upload_file_delete_false(tmp_path: Path) -> None:
    """delete_on_success=False 시 원본 유지"""
    config = {"s3_bucket": "b", "s3_prefix": "p/"}
    f = tmp_path / "keep.blf"
    f.write_bytes(b"data")

    mock = StreamManagerMock(config=config, mock_output_dir=tmp_path / "out")
    result = mock.upload_file(f, delete_on_success=False)
    mock.close()

    assert result is True
    assert f.exists()
    blfs = list((tmp_path / "out" / "b" / "p").rglob("keep.blf"))
    assert len(blfs) == 1
    assert blfs[0].read_bytes() == b"data"


def test_upload_file_read_error(tmp_path: Path) -> None:
    """존재하지 않는 파일 업로드 시 False"""
    mock = StreamManagerMock(config={}, mock_output_dir=tmp_path)
    result = mock.upload_file(Path("/nonexistent/file.blf"))
    mock.close()
    assert result is False


def test_upload_file_after_close_raises(tmp_path: Path) -> None:
    """close 후 upload_file 시 RuntimeError"""
    mock = StreamManagerMock(config={}, mock_output_dir=tmp_path)
    mock.close()
    f = tmp_path / "x.blf"
    f.write_bytes(b"x")
    with pytest.raises(RuntimeError, match="already closed"):
        mock.upload_file(f)


def test_mock_uses_s3_like_structure(tmp_path: Path) -> None:
    """모킹 출력이 실제 S3 구조와 동일 (bucket/prefix/날짜/파일)"""
    config = {"s3_bucket": "my-bucket", "s3_prefix": "can-logs/"}
    f = tmp_path / "CBB_2025-03-04T120000_#001.blf"
    f.write_bytes(b"blf data")

    mock = StreamManagerMock(config=config, mock_output_dir=tmp_path)
    mock.upload_file(f)
    mock.close()

    base = tmp_path / "my-bucket" / "can-logs"
    assert base.exists()
    # 날짜 폴더 (yyyy/MM/dd) 하위에 파일
    blfs = list(base.rglob("*.blf"))
    assert len(blfs) == 1
    assert blfs[0].name == "CBB_2025-03-04T120000_#001.blf"


def test_default_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """config 비어있으면 mock-bucket, can-logs/ 기본값"""
    monkeypatch.chdir(tmp_path)
    f = tmp_path / "a.blf"
    f.write_bytes(b"a")
    mock = StreamManagerMock(config={})
    mock.upload_file(f)
    mock.close()
    base = tmp_path / "mock_uploads" / "mock-bucket" / "can-logs"
    blfs = list(base.rglob("a.blf"))
    assert len(blfs) == 1
    assert blfs[0].read_bytes() == b"a"
