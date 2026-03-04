# Stream Manager를 통한 S3 업로드 가이드

CAN Blackbox 업로더가 Greengrass Stream Manager를 사용해 BLF 로그를 S3로 업로드하는 방법을 정리한다.

---

## 1. Stream Manager S3 업로드 방식

### 1.1 다른 대상과의 차이

| 대상 | append_message에 넣는 데이터 |
|------|-----------------------------|
| IoT Analytics, Kinesis | raw bytes (blob) |
| **S3** | **S3ExportTaskDefinition JSON** (로컬 파일 경로 정보) |

S3의 경우 **파일 바이트를 직접 보내지 않는다**. 대신 다음 정보를 담은 `S3ExportTaskDefinition`을 JSON 직렬화하여 스트림에 추가한다.

- `input_url`: 업로드할 **로컬 파일의 절대 경로** (디스크 상 파일)
- `bucket`: S3 버킷 이름
- `key`: S3 오브젝트 키 (예: `can-logs/2025/03/04/CBB_xxx.blf`)
- `user_metadata`: (선택) 메타데이터

Stream Manager는 이 태스크를 받아 `input_url`이 가리키는 파일을 읽고 S3에 업로드한다.

### 1.2 Stream Manager가 하는 일 / 못 하는 일

| 역할 | 담당 |
|------|------|
| 로컬 파일을 읽어 S3로 업로드 | ✅ Stream Manager |
| 업로드 완료 여부 알림 (status stream) | ✅ Stream Manager |
| **업로드 완료 후 로컬 파일 삭제** | ❌ **업로더** |

Stream Manager는 업로드 성공/실패를 status stream으로 알려주기만 한다. 로컬 파일 삭제는 **업로더가 직접 처리**해야 한다.

---

## 2. 업로더 워크플로우

### 2.1 전체 흐름

```
[file_watcher] 신규 BLF 파일 감지
       │
       ▼
[uploader] S3ExportTaskDefinition 생성
       │   - input_url = 로컬 파일 절대 경로
       │   - bucket, key = config에서
       │
       ▼
[uploader] append_message(stream_name, JSON_bytes)로 태스크 전달
       │
       ▼
[Stream Manager] 파일 읽기 → S3 업로드 → status stream에 결과 기록
       │
       ▼
[uploader] status stream에서 Success 확인
       │
       ▼
[uploader] 로컬 파일 삭제 (delete_on_success)
```

### 2.2 핵심 사항

1. **파일을 먼저 디스크에 기록**  
   CAN 로거가 BLF를 저장한 후, 그 경로를 `input_url`로 넘긴다.

2. **태스크 메시지 형식**  
   `append_message`에는 파일 내용이 아니라 `S3ExportTaskDefinition` JSON bytes를 전달한다.

3. **업로드 완료 확인**  
   스트림 생성 시 `S3ExportTaskExecutorConfig.status_config`에 status stream을 연결하고, 업로더가 해당 스트림에서 `StatusMessage`를 읽어 `Status.Success`인지 확인한다.

4. **삭제는 업로더 책임**  
   `Status.Success`를 확인한 뒤에만 로컬 파일을 삭제한다. Stream Manager는 파일을 삭제하지 않는다.

---

## 3. Python 구현 예시 (stream_manager_real)

### 3.1 태스크 전달

```python
from stream_manager import StreamManagerClient
from stream_manager.data import S3ExportTaskDefinition
from stream_manager.util import Util

# input_url: 로컬 파일 절대 경로 (pathlib.Path → str)
# Stream Manager가 이 경로의 파일을 읽어 S3로 업로드
task = S3ExportTaskDefinition(
    input_url=str(path.resolve()),  # 절대 경로
    bucket=config["s3_bucket"],
    key=f"{config['s3_prefix']}{path.name}",
    user_metadata={"source": "can-blackbox"},
)
data = Util.validate_and_serialize_to_json_bytes(task)
seq = client.append_message(stream_name=stream_name, data=data)
```

### 3.2 Status Stream으로 완료 확인

```python
# 스트림 생성 시 status_config 설정 필요
# 업로드 완료 후 status stream에서 Success 메시지 수신 시에만 파일 삭제
from stream_manager import ReadMessagesOptions, Status, StatusMessage
from stream_manager.util import Util

# Status.Success → 파일 삭제
# Status.Failure / Status.Canceled → 삭제하지 않음 (재시도 또는 알람)
messages = client.read_messages(
    status_stream_name,
    ReadMessagesOptions(min_message_count=1, read_timeout_millis=5000)
)
for msg in messages:
    status_msg = Util.deserialize_json_bytes_to_obj(msg.payload, StatusMessage)
    if status_msg.status == Status.Success:
        # 이 시점에서 로컬 파일 삭제
        path.unlink()
        break
    elif status_msg.status in (Status.Failure, Status.Canceled):
        # 업로드 실패 - 파일 유지
        break
```

---

## 4. 현재 코드와의 차이 (구현 시 반영 필요)

### 4.1 모킹 vs 실제

| 항목 | 모킹 (StreamManagerMock) | 실제 (StreamManagerReal) |
|------|--------------------------|---------------------------|
| append_message 인자 | `data` = 파일 바이트 | `data` = S3ExportTaskDefinition JSON |
| filename | 사용 (모킹 출력 파일명) | 사용 안 함 (key에 path.name 사용) |
| 업로드 완료 판단 | append 성공 시 즉시 | status stream Success 확인 후 |
| 파일 삭제 시점 | append 성공 직후 | status Success 확인 후 |

### 4.2 프로토콜/인터페이스

실제 Stream Manager용으로는 `append_message` 시그니처가 다음처럼 바뀔 수 있다.

- `data`: `S3ExportTaskDefinition` 직렬화 바이트 (파일 바이트 아님)
- `filename`: S3 `key` 생성 시에만 사용 (예: prefix + filename)
- 반환: sequence number (status stream 매칭에 사용 가능)

업로더는 status stream 구독 및 완료 대기 로직이 추가로 필요하다.

---

## 5. 정리

- **Stream Manager 역할**: 로컬 파일을 S3로 업로드하고, status stream으로 결과를 알림.
- **업로더 역할**: 태스크 전달, status stream 확인, **업로드 성공 시에만 로컬 파일 삭제**.

삭제는 반드시 업로더가 하고, Stream Manager는 삭제를 수행하지 않는다.
