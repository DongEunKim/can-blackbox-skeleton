"""
file_watcher 단위 테스트
"""

import time
from pathlib import Path

import pytest

from src.file_watcher import _scan_new_files


def test_scan_ignores_zero_byte_files(tmp_path: Path) -> None:
    """0바이트 파일은 콜백 호출하지 않음"""
    (tmp_path / "empty.blf").touch()
    called = []

    _scan_new_files(tmp_path, set(), {}, 1, called.append)
    _scan_new_files(tmp_path, set(), {}, 1, called.append)

    assert len(called) == 0


def test_scan_detects_new_file_when_stable(tmp_path: Path) -> None:
    """크기 안정 시 콜백 호출"""
    f = tmp_path / "test.blf"
    f.write_bytes(b"x" * 100)

    known = set()
    stable = {}
    called = []

    _scan_new_files(tmp_path, known, stable, 2, called.append)
    assert len(called) == 0
    assert len(known) == 1

    _scan_new_files(tmp_path, known, stable, 2, called.append)
    assert len(called) == 1
    assert called[0].name == "test.blf"


def test_scan_waits_for_stable_size(tmp_path: Path) -> None:
    """크기 변경 중에는 콜백 미호출"""
    f = tmp_path / "growing.blf"
    f.write_bytes(b"a")

    known = set()
    stable = {}
    called = []

    _scan_new_files(tmp_path, known, stable, 2, called.append)
    f.write_bytes(b"ab")  # 크기 변경
    _scan_new_files(tmp_path, known, stable, 2, called.append)
    assert len(called) == 0

    _scan_new_files(tmp_path, known, stable, 2, called.append)  # 크기 유지
    assert len(called) == 1


def test_scan_ignores_non_blf(tmp_path: Path) -> None:
    """.blf가 아닌 파일은 무시"""
    (tmp_path / "log.txt").write_bytes(b"data")
    (tmp_path / "other.asc").write_bytes(b"data")

    called = []
    _scan_new_files(tmp_path, set(), {}, 1, called.append)
    _scan_new_files(tmp_path, set(), {}, 1, called.append)

    assert len(called) == 0
