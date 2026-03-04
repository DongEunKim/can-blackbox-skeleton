# 단계 5: StreamManager 모킹

## 설정 (config.ini [stream_manager])

| 항목 | 설명 | 기본값 |
|------|------|--------|
| use_mock | true: 모킹, false: 실제 StreamManager | true |
| stream_name | 스트림 이름 | CanBlackboxStream |

## 팩토리 사용

```python
from src.config_loader import get_stream_manager_config, load_config
from src.stream_manager_client import create_stream_manager_client

config = load_config()
sm_cfg = get_stream_manager_config(config)
client = create_stream_manager_client(sm_cfg)
```

## API 호환

실제 `StreamManagerClient`와 동일한 인터페이스:

```python
append_message(stream_name: str, data: bytes) -> int
close() -> None
```

## 사용

```python
from pathlib import Path
from src.stream_manager_mock import StreamManagerMock

mock = StreamManagerMock(mock_output_dir=Path("./mock_uploads"))
seq = mock.append_message("CanBlackboxStream", file_bytes)
mock.close()
```

## 모킹 동작

- `append_message`: 데이터를 `{stream_name}_{seq:06d}.blf` 형식으로 로컬 저장
- 실제 환경에서는 StreamManager가 스트림에 추가 후 S3로 전송

## 단위 테스트

```bash
python3 -m pytest tests/test_stream_manager_mock.py -v
```
