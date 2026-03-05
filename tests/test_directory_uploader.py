"""
DirectoryUploader 단위 테스트
"""

from pathlib import Path

import pytest

from src.directory_uploader import DirectoryUploader, MockUploadClient


def test_directory_uploader_scan_and_upload(tmp_path: Path) -> None:
    """스캔 시 안정 파일 업로드"""
    watch_dir = tmp_path / "logs"
    watch_dir.mkdir()
    out_dir = tmp_path / "out"

    mock = MockUploadClient(
        config={"s3_bucket": "b", "s3_prefix": "p/"},
        mock_output_dir=out_dir,
    )

    du = DirectoryUploader(
        watch_dir=watch_dir,
        client=mock,
        max_total_mb=10,
        poll_interval=1,
        min_stable_polls=2,
    )

    f = watch_dir / "CBB_2025-03-04T120000_#001.blf"
    f.write_bytes(b"data" * 100)

    for _ in range(3):
        du._scan()
        du._trim_storage()

    mock.close()
    du.close()

    blfs = list((out_dir / "b" / "p").rglob("*.blf"))
    assert len(blfs) >= 1
    assert not f.exists()


def test_directory_uploader_trim_storage(tmp_path: Path) -> None:
    """_trim_storage 호출"""
    watch_dir = tmp_path / "logs"
    watch_dir.mkdir()

    mock = MockUploadClient(config={})
    du = DirectoryUploader(
        watch_dir=watch_dir,
        client=mock,
        max_total_mb=0.0001,
        poll_interval=1,
    )

    (watch_dir / "a.blf").write_bytes(b"x" * 500)
    deleted = du._trim_storage()
    du.close()
    mock.close()

    assert deleted >= 1
