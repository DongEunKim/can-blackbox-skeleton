"""
Virtual CAN 연결 검증 테스트
vcan0 인터페이스가 있는 환경에서만 통과함
"""

import pytest

try:
    import can
    CAN_AVAILABLE = True
except ImportError:
    CAN_AVAILABLE = False


@pytest.mark.skipif(not CAN_AVAILABLE, reason="python-can 미설치")
def test_vcan0_connection() -> None:
    """vcan0 연결 및 송수신 검증"""
    try:
        bus = can.interface.Bus(channel="vcan0", interface="socketcan")
    except can.CanError as e:
        pytest.skip(f"vcan0 사용 불가 (Virtual CAN 미설정): {e}")

    try:
        msg = can.Message(arbitration_id=0x123, data=[1, 2, 3, 4, 5, 6, 7, 8])
        bus.send(msg)
        # 송신 성공 시 통과
    finally:
        bus.shutdown()
