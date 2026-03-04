"""
저장소 관리자 단위 테스트
"""

import os
from pathlib import Path

import pytest

from src.storage_manager import get_total_size_mb, trim_storage


def test_get_total_size_mb_empty(tmp_path: Path) -> None:
    """빈 폴더는 0"""
    assert get_total_size_mb(tmp_path) == 0.0


def test_get_total_size_mb(tmp_path: Path) -> None:
    """BLF 파일 용량 합계"""
    (tmp_path / "a.blf").write_bytes(b"x" * 1024)
    (tmp_path / "b.blf").write_bytes(b"y" * 2048)
    (tmp_path / "c.txt").write_bytes(b"z" * 1024)
    assert abs(get_total_size_mb(tmp_path) - 3 / 1024) < 0.001


def test_trim_storage_no_trim(tmp_path: Path) -> None:
    """용량 초과 없으면 삭제 없음"""
    (tmp_path / "a.blf").write_bytes(b"x" * 100)
    deleted = trim_storage(tmp_path, 1.0)
    assert deleted == 0
    assert (tmp_path / "a.blf").exists()


def test_trim_storage_deletes_oldest(tmp_path: Path) -> None:
    """용량 초과 시 오래된 파일 삭제"""
    old_p = tmp_path / "old.blf"
    new_p = tmp_path / "new.blf"
    old_p.write_bytes(b"a" * 500)
    new_p.write_bytes(b"b" * 500)
    os.utime(old_p, (1000, 1000))
    os.utime(new_p, (2000, 2000))
    # max 0.0005MB ≈ 524B, 현재 1000B -> 초과
    deleted = trim_storage(tmp_path, 0.0005)
    assert deleted >= 1
    assert not (tmp_path / "old.blf").exists()


def test_trim_storage_ignores_zero_byte(tmp_path: Path) -> None:
    """0바이트 파일은 삭제 후보에서 제외"""
    (tmp_path / "empty.blf").touch()
    (tmp_path / "data.blf").write_bytes(b"x" * 200)
    # max 0.0001MB ≈ 105B, 현재 200B -> 초과. empty는 0바이트라 후보 제외
    deleted = trim_storage(tmp_path, 0.0001)
    assert deleted == 1
    assert not (tmp_path / "data.blf").exists()
    assert (tmp_path / "empty.blf").exists()
