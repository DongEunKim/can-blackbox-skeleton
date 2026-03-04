"""
CAN 로거 단위 테스트
SizedRotatingLogger 기반
"""

from pathlib import Path

import pytest

try:
    import can
    from can.io.logger import SizedRotatingLogger
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False


@pytest.mark.skipif(not CAN_AVAILABLE, reason="python-can 미설치")
def test_sized_rotating_logger_creates_blf(tmp_path: Path) -> None:
    """SizedRotatingLogger가 BLF 파일 생성 및 메시지 기록"""
    base_filename = tmp_path / "can.blf"
    logger = SizedRotatingLogger(
        base_filename=base_filename,
        max_bytes=10 * 1024 * 1024,  # 10MB
    )

    msg = can.Message(arbitration_id=0x123, data=[1, 2, 3, 4, 5, 6, 7, 8])
    logger.on_message_received(msg)
    logger.on_message_received(msg)
    logger.stop()

    assert base_filename.exists()
    assert base_filename.stat().st_size > 0


@pytest.mark.skipif(not CAN_AVAILABLE, reason="python-can 미설치")
def test_sized_rotating_logger_written_blf_readable(tmp_path: Path) -> None:
    """기록된 BLF 파일을 BLFReader로 읽을 수 있음"""
    base_filename = tmp_path / "can.blf"
    logger = SizedRotatingLogger(
        base_filename=base_filename,
        max_bytes=10 * 1024 * 1024,
    )

    msg = can.Message(arbitration_id=0x456, data=[0xFF, 0x00])
    logger.on_message_received(msg)
    logger.stop()

    reader = can.BLFReader(base_filename)
    messages = list(reader)
    assert len(messages) == 1
    assert messages[0].arbitration_id == 0x456
    assert messages[0].data == bytes([0xFF, 0x00])
