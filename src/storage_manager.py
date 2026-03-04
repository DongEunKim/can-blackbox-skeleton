"""
저장소 관리자 - 용량 초과 시 오래된 파일 삭제
"""

from pathlib import Path
from typing import List, Tuple

BLF_SUFFIX = ".blf"


def get_total_size_mb(target_dir: Path) -> float:
    """
    대상 폴더 내 BLF 파일 총 용량(MB).

    Args:
        target_dir: 대상 폴더

    Returns:
        총 용량(MB)
    """
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
    """
    용량 초과 시 오래된 파일부터 삭제.

    Args:
        target_dir: 대상 폴더
        max_total_mb: 최대 총 용량(MB)
        suffix: 대상 파일 확장자

    Returns:
        삭제한 파일 수
    """
    if not target_dir.exists() or max_total_mb <= 0:
        return 0

    files: List[Tuple[Path, int, float]] = []
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

    # mtime 오름차순 (오래된 것 먼저)
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
