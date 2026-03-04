# 단계 2: Virtual CAN 구성 및 더미 데이터 검증

## 1. Virtual CAN 설정

```bash
./scripts/virtual_can_setup.sh
```

인터페이스 지정 가능:

```bash
./scripts/virtual_can_setup.sh vcan0
```

## 2. 더미 데이터 송신

```bash
python3 scripts/send_dummy_can.py vcan0
```

옵션:

- `-i`, `--interval`: 송신 간격(초), 기본 0.1

```bash
python3 scripts/send_dummy_can.py vcan0 -i 0.5
```

종료: `Ctrl+C`

## 3. 수신 확인

다른 터미널에서:

```bash
# can-utils 설치된 경우
candump vcan0
```

또는 단위 테스트로 vcan0 연결 검증:

```bash
python3 -m pytest tests/test_virtual_can.py -v
```

## 4. 트러블슈팅

| 증상 | 조치 |
|------|------|
| `Module vcan not found` | `sudo apt-get install linux-modules-extra-$(uname -r)` |
| `vcan0: No such device` | `./scripts/virtual_can_setup.sh` 실행 |
| `Permission denied` | `chmod +x scripts/virtual_can_setup.sh` |
| `Operation not permitted` | sudo로 스크립트 실행 |
| `python-can` ImportError | `pip install -r requirements.txt` |
