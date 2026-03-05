# 업로더 업그레이드 계획 (aws-greengrass-labs-s3-file-uploader 참조)

[aws-greengrass-labs-s3-file-uploader](https://github.com/awslabs/aws-greengrass-labs-s3-file-uploader)를 참고하여 CAN Blackbox 업로더를 개선할 항목을 정리한다.

> **현재 상태**: 단일 파일 통합 완료. `directory_uploader.py`에 스캔·업로드·용량 정리·main 진입점이 통합되어 있으며, `file_watcher`, `storage_manager`, `stream_manager_*`, `uploader`는 삭제되었다.

---

## 1. 참조 프로젝트 개요

| 항목 | 내용 |
|------|------|
| 출처 | awslabs/aws-greengrass-labs-s3-file-uploader |
| 역할 | 폴더 모니터링 → S3 업로드 → 성공 시 삭제 |
| 특징 | asyncio 병렬 처리, Stream Manager status 스트림 분리 처리, Failure 시 재시도 |

---

## 2. 현황 vs 참조 비교

| 항목 | CAN Blackbox (현재) | s3-file-uploader (참조) |
|------|---------------------|--------------------------|
| 처리 방식 | 동기 (폴링 → 업로드 → status 대기 → 다음) | 비동기 (스캔 태스크 ∥ status 처리 태스크) |
| Failure 재시도 | 없음 (파일 유지, storage에서 용량 초과 시 삭제) | 있음 (filesProcessed 제외 → 다음 스캔에서 재전송) |
| 디렉터리 권한 체크 | 없음 | rwx 체크 후 부족 시 60초 대기 |
| 예외 복구 | file_watcher 예외 시 종료 | main 예외 시 60초 대기 후 재시작 |
| input_url 형식 | 절대 경로 문자열 | file:// + 경로 |
| 스트림 관리 | 기존 유지, 없으면 생성 | 시작 시 삭제 후 재생성 |

---

## 3. 업그레이드 항목

### 3.1 [우선순위: 높음] Failure/Canceled 재시도

**목표**: S3 업로드 실패 시 파일을 유지하고, 다음 스캔에서 자동 재전송 시도

**참조 로직**:
```python
# Failure/Canceled 시 __filesProcessed에서 제거 → 다음 스캔에서 재전송 대상
self.__filesProcessed.remove(file_url.partition("file://")[2])
```

**적용 방안**:
- `upload_file`이 Failure/Canceled 반환 시: 파일 삭제하지 않음, 이미 구현됨
- **추가 필요**: `uploader` 또는 `stream_manager_real`에서 "전송 시도한 파일" 목록 유지
- status가 Failure/Canceled면 해당 파일을 목록에서 제거 → 다음 file_watcher 스캔 시 재감지되어 재전송
- **주의**: 우리는 file_watcher가 "신규 안정 파일"만 콜백. 이미 한 번 전송 시도한 파일은 known에 있어 재콜백 안 됨
- **해결**: 전송 실패한 파일을 `known`/`stable`에서 제거하거나, "실패한 파일 목록"을 file_watcher에 전달하여 재처리 대상으로 포함

**작업 범위**:
- `file_watcher`: 실패 파일을 다시 콜백할 수 있는 인터페이스 (예: `on_retry_file` 또는 `failed_paths` 집합 전달)
- `uploader`: Failure 시 콜백으로 "재시도 대상" 등록
- 또는 `uploader`가 단일 파일 처리 시 실패하면 `known`에서 제외하는 방식을 file_watcher에 요청

---

### 3.2 [우선순위: 높음] asyncio 기반 병렬 처리

**목표**: 디렉터리 스캔과 status stream 처리를 병렬로 수행하여 처리량·지연 개선

**참조 구조**:
```python
tasks = [asyncio.create_task(self.__scan()), asyncio.create_task(self.__processStatus())]
await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
```

**적용 방안**:
- **태스크 1 (스캔)**: file_watcher 로직 — 폴링으로 신규 파일 감지 → append_message만 호출 (status 대기 X)
- **태스크 2 (status)**: status stream 폴링 — Success 메시지 수신 시 해당 파일 삭제
- 현재 `upload_file`이 append + _wait_for_status를 동기로 수행 → **분리**
  - `append_task(path)` → 시퀀스 번호 또는 input_url 반환
  - `process_status_stream()` → 배치로 status 읽고, Success인 input_url에 대해 파일 삭제

**작업 범위**:
- `stream_manager_real`: `append_task()`, `process_status_stream()` 메서드 분리
- `uploader`: asyncio 메인 루프, 두 태스크 병렬 실행
- `file_watcher`: asyncio 버전 또는 콜백에서 비동기 append만 호출

---

### 3.3 [우선순위: 중간] 디렉터리 권한 사전 체크

**목표**: watch_dir에 rwx 권한이 없을 때 조기 실패 및 안내

**참조 로직**:
```python
if ntpath.isdir(base_dir) and os.access(base_dir, os.R_OK|os.W_OK|os.X_OK):
    # 정상 스캔
else:
    self.__logger.error("... rwx access.")
    await asyncio.sleep(60)  # 1분 대기 후 재시도
```

**적용 방안**:
- `uploader` 또는 `file_watcher` 시작 시 `watch_dir`에 대한 `os.R_OK | os.W_OK | os.X_OK` 체크
- 부족 시: 에러 로그 출력, 60초 대기 후 재시도 (선택)

**작업 범위**:
- `file_watcher.run_file_watcher`: 시작 시 권한 체크 함수 추가
- 또는 `uploader.run_uploader`에서 사전 검증

---

### 3.4 [우선순위: 중간] 예외 시 재시작 루프

**목표**: 치명적 예외 발생 시 프로세스 종료 대신 일정 시간 대기 후 재시작

**참조 로직**:
```python
while True:
    try:
        du = DirectoryUploader(...)
        await du.Run()
    except Exception:
        logger.exception("Exception while running")
    finally:
        if du: du.Close()
    time.sleep(60)  # 1분 후 재시작
```

**적용 방안**:
- `run_uploader`를 `while True` 루프로 감싸고, 예외 시 60초 대기 후 재시도
- 설정으로 재시도 횟수/간격 조정 가능하게 (선택)

**작업 범위**:
- `uploader.run_uploader`: try/except + sleep + 재시도 루프

---

### 3.5 [우선순위: 낮음] input_url 형식 통일

**목표**: Stream Manager 권장 형식에 맞춤

**참조**: `input_url="file://" + file`

**현재**: `input_url = str(abs_path)` (절대 경로만)

**적용 방안**:
- `input_url = f"file://{abs_path}"` 로 변경
- AWS 문서상 절대 경로도 허용되나, `file://` 형식이 더 명확할 수 있음

**작업 범위**:
- `stream_manager_real.upload_file`: input_url 생성부 수정

---

### 3.6 [미적용] 스트림 시작 시 삭제

**참조**: 시작 시 export/status 스트림 삭제 후 재생성

**결정**: **적용하지 않음**

**이유**:
- 우리는 스트림 유지로 재시작 시 미완료 태스크 보존
- s3-file-uploader 방식은 매 시작 시 큐 초기화 → 데이터 손실 가능

---

### 3.7 [미적용] active file 제외

**참조**: 가장 최근 1개 파일을 업로드 대상에서 제외

**결정**: **적용하지 않음**

**이유**:
- CAN Blackbox는 file_watcher가 "크기 안정" 시점에만 콜백 → 쓰기 중인 파일은 이미 제외됨
- 단일 파일도 업로드해야 함

---

## 4. 모듈 통합 설계 (directory_uploader)

### 4.1 통합 방향 (적용 완료)

- **완전 통합**: 스캔 + 업로드 + status 처리 + storage trim + main 진입점을 `directory_uploader.py`로 통합
- **실행**: `python3 -m src.directory_uploader`

### 4.2 파일 구조 (현재 구현)

```
src/
├── directory_uploader.py   # 스캔 + 업로드(mock/real) + status + trim + main 통합
├── config_loader.py        # 설정 로드
└── can_logger.py           # CAN 로깅
```

- `file_watcher`, `storage_manager`, `stream_manager_*`, `uploader` 삭제됨

### 4.3 directory_uploader.py 설계

#### 클래스: DirectoryUploader

| 메서드/속성 | 시그니처 | 역할 |
|-------------|----------|------|
| `__init__` | `(watch_dir, client, max_total_mb, poll_interval)` | 초기화 |
| `_scan` / `run_file_watcher` | - | 폴더 스캔·안정 파일 감지. 방안 B 시 file_watcher에 위임 |
| `_process_status` | `() -> None` | status stream 폴링, Success 시 삭제 |
| `_trim_storage` | `() -> None` | max_total_mb 초과 시 오래된 파일 삭제 |
| `run` | `() -> int` | 메인 루프 (동기 또는 asyncio) |
| `close` | `() -> None` | 클라이언트 종료 |

#### 내부 상태

| 속성 | 타입 | 설명 |
|------|------|------|
| `_known` | `Set[Path]` | 이미 본 파일 |
| `_stable` | `dict[Path, (int, int)]` | (크기, 연속 동일 횟수) |
| `_pending` | `Set[Path]` | append 완료, status 대기 중 (실제 구현 시 사용) |
| `_failed` | `Set[Path]` | Failure/Canceled 시 known에서 제외하여 재시도 |

#### 흐름 (동기 버전, 1단계)

```
run() 루프:
  1. _scan()  → 신규 안정 파일 → client.upload_file(path)
  2. _trim_storage()
  3. sleep(poll_interval)
```

#### 흐름 (asyncio 버전, 2단계)

```
run():
  tasks = [_scan_loop(), _process_status_loop()]
  await asyncio.gather(*tasks)
```

### 4.4 file_watcher.py 유지 역할

- **목적**: 업로드 없이 폴더 감지만 필요할 때 사용
- **제공**: `run_file_watcher(config_path, on_new_file, after_scan)`, `_scan_new_files()`
- **변경 없음**: 기존 API 유지
- **directory_uploader와 관계**: directory_uploader는 file_watcher의 `_scan_new_files`를 import하여 재사용하거나, 동일 로직을 자체 구현

### 4.5 stream_manager_client 프로토콜

기존 `upload_file(path, delete_on_success)` 유지.  
asyncio 도입 시 `append_task(path)` + `process_status()` 분리 검토.

---

## 5. 구체적 클래스·함수 설계

### 5.1 DirectoryUploader (directory_uploader.py)

```python
class DirectoryUploader:
    """폴더 스캔 + S3 업로드 + status 처리 + storage trim 통합"""

    def __init__(
        self,
        watch_dir: Path,
        client: StreamManagerClientProtocol,
        *,
        max_total_mb: float = 500,
        poll_interval: int = 5,
        min_stable_polls: int = 2,
    ) -> None: ...

    def _scan(self) -> None:
        """스캔 → 안정 파일 → upload_file 호출.
        Failure 시 _failed에 추가하여 known에서 제외."""
        ...

    def _trim_storage(self) -> int:
        """storage_manager.trim_storage 호출, 삭제 개수 반환"""
        ...

    def run(self) -> int:
        """메인 루프. SIGINT 처리, run_file_watcher 호출 또는 자체 루프."""
        ...

    def close(self) -> None: ...
```

### 5.2 uploader.py (변경 후)

```python
def run_uploader(config_path: Optional[Path] = None) -> int:
    config = load_config(config_path)
    ...
    client = create_stream_manager_client(sm_cfg, ...)
    du = DirectoryUploader(
        watch_dir=Path(log_cfg["output_dir"]),
        client=client,
        max_total_mb=storage_cfg["max_total_mb"],
        poll_interval=watcher_cfg["poll_interval"],
    )
    try:
        return du.run()
    finally:
        du.close()
```

### 5.3 file_watcher 연동

- **방안 A**: directory_uploader가 `from src.file_watcher import _scan_new_files` 사용  
- **방안 B**: directory_uploader가 `run_file_watcher(on_new_file=..., after_scan=...)` 호출  
  → 방안 B 선택 시 uploader와 동일한 구조, DirectoryUploader는 `on_new_file` 내부에서 `client.upload_file` 호출

**권장**: 방안 B — `run_file_watcher`에 콜백 전달. file_watcher는 감지 전용으로 유지, DirectoryUploader가 업로드 로직 포함.

---

## 6. 구현 단계

### 6.1 단계 1: directory_uploader 추가 (동기)

| 순서 | 작업 | 내용 |
|------|------|------|
| 1-1 | directory_uploader.py 생성 | `DirectoryUploader` 클래스, `run_file_watcher` 호출 + `on_new_file`/`after_scan` |
| 1-2 | uploader.py 수정 | `DirectoryUploader` 인스턴스 생성 및 `run()` 호출로 변경 |
| 1-3 | 테스트 | 기존 uploader 테스트 통과 확인 |

### 6.2 단계 2: Failure 재시도

| 순서 | 작업 | 내용 |
|------|------|------|
| 2-1 | file_watcher 확장 | `forget_path(path)` 또는 `known`/`failed` 집합 주입 가능하게 |
| 2-2 | DirectoryUploader | Failure 시 `known`에서 제외하여 다음 스캔에서 재콜백 |
| 2-3 | 테스트 | Failure 시 재전송 시나리오 |

### 6.3 단계 3: asyncio 병렬 처리 (선택)

| 순서 | 작업 | 내용 |
|------|------|------|
| 3-1 | stream_manager_real | `append_task()`, `process_status_stream()` 분리 |
| 3-2 | DirectoryUploader | asyncio `_scan_loop`, `_process_status_loop` 구현 |
| 3-3 | uploader | `asyncio.run(du.run())` 호출 |

### 6.4 단계 4: 기타

| 순서 | 작업 | 내용 |
|------|------|------|
| 4-1 | 디렉터리 권한 체크 | `run()` 시작 시 rwx 검사 |
| 4-2 | 예외 재시작 | `run_uploader`에 try/except + 60초 대기 루프 |
| 4-3 | input_url 형식 | `file://` prefix 적용 |

---

## 7. 구현 순서 제안 (통합 반영)

| 순서 | 항목 | 예상 공수 | 비고 |
|------|------|----------|------|
| 1 | **directory_uploader 통합 (6.1)** | 중 | 신규 모듈, uploader 리팩터 |
| 2 | Failure/Canceled 재시도 (3.1) | 중 | file_watcher·DirectoryUploader 연동 |
| 3 | 디렉터리 권한 체크 (3.3) | 하 | directory_uploader.run() 내 |
| 4 | 예외 시 재시작 (3.4) | 하 | uploader.run_uploader 루프 |
| 5 | input_url 형식 (3.5) | 하 | 1줄 수정 |
| 6 | asyncio 병렬 처리 (3.2) | 상 | 선택, 구조 변경 큼 |

---

## 8. 산출물 (현재 구현)

- `directory_uploader.py`: 스캔 + 업로드(mock/real) + status + trim + main 통합
- `config.ini`: (선택) `restart_interval_sec` 등

---

## 9. 테스트 계획

- 기존 단위 테스트 유지
- `DirectoryUploader` 단위 테스트 추가 (Mock client)
- Failure 시 재전송 시나리오 테스트
- asyncio 버전 통합 테스트 (선택, Mock + 실제 Stream Manager)
- 디렉터리 권한 부족 시 동작 검증
