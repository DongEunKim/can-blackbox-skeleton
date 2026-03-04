# 단계 3: CAN → BLF 로깅 검증

## 실행

```bash
# Virtual CAN + 더미 송신 (터미널 1)
./scripts/virtual_can_setup.sh
python3 scripts/send_dummy_can.py vcan0

# CAN 로거 실행 (터미널 2)
python3 -m src.can_logger
```

config.ini의 `[logging]` output_dir에 BLF 파일이 생성된다.

## 단위 테스트

```bash
python3 -m pytest tests/test_can_logger.py -v
```

## 설정

### [can]
| 항목 | 설명 |
|------|------|
| interface | 쉼표 구분 다중 지원 (예: vcan0,vcan1,can0) |

### [logging]
| 항목 | 설명 | 기본값 |
|------|------|--------|
| output_dir | BLF 저장 경로 | ./logs |
| log_prefix | 파일명 prefix | CBB_ |
| rotation_max_mb | 로테이션 용량(MB) | 10 |
| max_logging_minutes | 최대 로깅 시간(분), 0=무제한 | 30 |

## 출력 파일

- 단일 파일 멀티채널: `{prefix}{YYYY-MM-DDTHHMMSS}_#N.blf`
- 예: `CBB_2026-03-05T000724_#000.blf` (기본), `CBB_2026-03-05T001002_#001.blf` (로테이션)
- 채널 매핑: 1=첫 번째, 2=두 번째, ... (config.ini interface 순서)
