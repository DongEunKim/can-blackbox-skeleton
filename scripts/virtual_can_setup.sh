#!/bin/bash
# Virtual CAN 설정
# Linux에서 테스트용 vcan0 인터페이스 구성
# 더미 데이터는 scripts/send_dummy_can.py 사용

set -e

VCAN=${1:-vcan0}

echo "Virtual CAN ($VCAN) 설정 중..."

# 모듈 로드 (실패 시 linux-modules-extra 설치 안내)
if ! sudo modprobe vcan 2>/dev/null; then
    echo "vcan 모듈을 찾을 수 없습니다."
    echo "설치: sudo apt-get install linux-modules-extra-\$(uname -r)"
    exit 1
fi
sudo modprobe can_raw 2>/dev/null || true

# vcan0 생성 (이미 있으면 삭제 후 재생성하여 깨끗한 상태로)
if ip link show "$VCAN" &>/dev/null; then
    echo "기존 $VCAN 삭제 후 재생성"
    sudo ip link set down "$VCAN"
    sudo ip link delete "$VCAN"
fi
sudo ip link add dev "$VCAN" type vcan
sudo ip link set up "$VCAN"

echo "Virtual CAN $VCAN 설정 완료"
ip link show "$VCAN"
echo ""
echo "더미 데이터 송신: python3 scripts/send_dummy_can.py $VCAN"
