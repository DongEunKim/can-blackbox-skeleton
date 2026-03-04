# CAN Blackbox

CAN 버스 데이터를 BLF 파일로 로깅하고, AWS Greengrass StreamManager를 통해 S3로 전송하는 에지 디바이스용 솔루션입니다.

## 주요 기능

- CAN 버스 메시지를 BLF 형식으로 로깅
- 5분 단위 로그 파일 로테이션
- 저장 폴더 감시 및 StreamManager를 통한 S3 업로드
- 업로드 완료 후 로컬 파일 삭제
- 용량 초과 시 오래된 파일 우선 삭제

## 요구사항

- Python 3.9+
- Linux (CAN 인터페이스, Virtual CAN 테스트 지원)

## 설치

```bash
# 저장소 클론
git clone https://github.com/YOUR_USERNAME/can-blackbox.git
cd can-blackbox

# 가상환경 생성 및 활성화
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 설정 파일 준비
cp config.ini.example config.ini
# config.ini 수정
```

## 설정

`config.ini` 파일에서 다음 항목을 설정합니다.

- **CAN 인터페이스**: 실제 CAN(can0) 또는 테스트용 Virtual CAN(vcan0), 쉼표로 다중 지정
- **로그 저장 경로**: BLF 파일 저장 폴더
- **로테이션 용량**: MB 단위 (실수 가능, 예: 0.5)
- **재연결**: `reconnect_max_retries`, `reconnect_interval_sec` (끊김 시 지수 백오프 재시도)
- **StreamManager**: `use_mock` (true: 로컬 모킹, false: 실제 Greengrass, `stream_manager_real` 구현 필요)

## 사용법

```bash
# CAN 로거 실행 (터미널 1)
python3 -m src.can_logger

# 업로더 실행 (터미널 2) - 폴더 감시 + StreamManager 전송 + 삭제
python3 -m src.uploader

# 감시만 (업로드 없이)
python3 -m src.file_watcher
```

## 테스트

```bash
# Virtual CAN 설정 (Linux)
./scripts/virtual_can_setup.sh

# 더미 CAN 송신 (별도 터미널)
python3 scripts/send_dummy_can.py vcan0

# 단위 테스트 실행
python3 -m pytest tests/ -v
```

## 프로젝트 구조

```
can-blackbox/
├── config.ini.example   # 설정 템플릿
├── requirements.txt
├── src/                 # 소스 코드
├── tests/               # 단위 테스트
├── docs/                # 문서
└── scripts/             # 유틸리티 스크립트
```

## 미구현 / 추후 개발

- **stream_manager_real**: 실제 Greengrass StreamManager 연동. 배포 시 `stream_manager_real.py` 구현 필요.

## 추가 고려사항 (TODO)

- **버스별 개별 재연결**: 현재는 하나의 버스라도 오류 시 전체 재시작. 향후 버스별 독립 재연결 검토
- **Bus 상태 주기 점검**: `bus.state` 등으로 사전 감지 후 재연결 검토
- **SIGTERM 처리**: 서비스( systemd ) 실행 시 정상 종료를 위한 SIGTERM 핸들러 추가 검토

## 라이선스

MIT License
