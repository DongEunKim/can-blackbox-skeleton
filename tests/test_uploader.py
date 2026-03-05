"""
업로더 단위 테스트
"""

import os
from pathlib import Path

import pytest

from src.directory_uploader import MockUploadClient


def test_upload_file_success(tmp_path: Path) -> None:
    """업로드 성공 시 S3 구조로 저장 후 원본 삭제"""
    config = {"s3_bucket": "b", "s3_prefix": "p/"}
    f = tmp_path / "test.blf"
    f.write_bytes(b"blf data")

    mock = MockUploadClient(config=config, mock_output_dir=tmp_path / "out")
    result = mock.upload_file(f)
    mock.close()

    assert result is True
    assert not f.exists()
    blfs = list((tmp_path / "out" / "b" / "p").rglob("test.blf"))
    assert len(blfs) == 1
    assert blfs[0].read_bytes() == b"blf data"


def test_upload_file_delete_false(tmp_path: Path) -> None:
    """delete_on_success=False 시 원본 유지"""
    f = tmp_path / "keep.blf"
    f.write_bytes(b"data")

    mock = MockUploadClient(config={}, mock_output_dir=tmp_path / "out")
    result = mock.upload_file(f, delete_on_success=False)
    mock.close()

    assert result is True
    assert f.exists()
    assert f.read_bytes() == b"data"


def test_upload_file_read_error(tmp_path: Path) -> None:
    """읽기 실패 시 False"""
    mock = MockUploadClient(config={}, mock_output_dir=tmp_path)
    result = mock.upload_file(Path("/nonexistent/file.blf"))
    mock.close()
    assert result is False


def test_upload_file_write_error(tmp_path: Path) -> None:
    """쓰기 실패 시 False, 파일 미삭제 - 쓰기 불가 디렉터리"""
    f = tmp_path / "test.blf"
    f.write_bytes(b"data")
    out_dir = tmp_path / "out"
    mock = MockUploadClient(config={}, mock_output_dir=out_dir)
    os.chmod(out_dir, 0o444)
    try:
        result = mock.upload_file(f)
    finally:
        os.chmod(out_dir, 0o755)
    mock.close()
    assert result is False
    assert f.exists()
