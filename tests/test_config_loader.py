"""
설정 로더 단위 테스트
"""

import configparser
from pathlib import Path

import pytest

from src.config_loader import (
    get_can_config,
    get_logging_config,
    get_storage_config,
    get_stream_manager_config,
    get_watcher_config,
    load_config,
)


@pytest.fixture
def sample_ini() -> str:
    """샘플 INI 내용"""
    return """
[can]
interface = vcan0,vcan1
log_interval = 0
reconnect_max_retries = 5
reconnect_interval_sec = 2

[logging]
output_dir = ./logs
log_prefix = CBB_
rotation_max_mb = 10
max_logging_minutes = 30

[storage]
max_total_mb = 500

[watcher]
poll_interval = 5

[stream_manager]
use_mock = true
stream_name = CanBlackboxStream
s3_bucket = my-bucket
s3_prefix = can-logs/
"""


@pytest.fixture
def config_file(sample_ini: str, tmp_path: Path) -> Path:
    """임시 설정 파일 경로"""
    path = tmp_path / "config.ini"
    path.write_text(sample_ini, encoding="utf-8")
    return path


def test_load_config(config_file: Path) -> None:
    """설정 파일 로드 검증"""
    config = load_config(config_file)
    assert isinstance(config, configparser.ConfigParser)
    assert config.has_section("can")


def test_load_config_file_not_found() -> None:
    """존재하지 않는 설정 파일 시 FileNotFoundError"""
    with pytest.raises(FileNotFoundError, match="설정 파일을 찾을 수 없습니다"):
        load_config(Path("/nonexistent/config.ini"))


def test_get_can_config(config_file: Path) -> None:
    """CAN 설정 파싱 검증"""
    config = load_config(config_file)
    can = get_can_config(config)
    assert can["interfaces"] == ["vcan0", "vcan1"]
    assert can["log_interval"] == 0
    assert can["reconnect_max_retries"] == 5
    assert can["reconnect_interval_sec"] == 2


def test_get_logging_config(config_file: Path) -> None:
    """로깅 설정 파싱 검증"""
    config = load_config(config_file)
    logging = get_logging_config(config)
    assert logging["output_dir"] == "./logs"
    assert logging["log_prefix"] == "CBB_"
    assert logging["rotation_max_mb"] == 10


def test_get_logging_config_float_rotation() -> None:
    """rotation_max_mb 실수값 파싱"""
    config = configparser.ConfigParser()
    config.read_string(
        "[logging]\noutput_dir = ./logs\nrotation_max_mb = 0.5\n"
    )
    logging = get_logging_config(config)
    assert logging["rotation_max_mb"] == 0.5
    assert logging["max_logging_minutes"] == 30


def test_get_storage_config(config_file: Path) -> None:
    """저장소 설정 파싱 검증"""
    config = load_config(config_file)
    storage = get_storage_config(config)
    assert storage["max_total_mb"] == 500


def test_get_watcher_config(config_file: Path) -> None:
    """감시 설정 파싱 검증"""
    config = load_config(config_file)
    watcher = get_watcher_config(config)
    assert watcher["poll_interval"] == 5


def test_get_stream_manager_config(config_file: Path) -> None:
    """StreamManager 설정 파싱 검증"""
    config = load_config(config_file)
    sm = get_stream_manager_config(config)
    assert sm["use_mock"] is True
    assert sm["stream_name"] == "CanBlackboxStream"
    assert sm["s3_bucket"] == "my-bucket"
    assert sm["s3_prefix"] == "can-logs/"


def test_get_stream_manager_config_use_mock_false() -> None:
    """use_mock=false 파싱"""
    config = configparser.ConfigParser()
    config.read_string("[stream_manager]\nuse_mock = false\n")
    sm = get_stream_manager_config(config)
    assert sm["use_mock"] is False


def test_fallback_values() -> None:
    """섹션/키 누락 시 기본값 사용"""
    config = configparser.ConfigParser()
    config.read_string("[can]\ninterface = can0\n")
    can = get_can_config(config)
    assert can["interfaces"] == ["can0"]
    assert can["log_interval"] == 0  # fallback


def test_get_can_config_single_interface() -> None:
    """단일 인터페이스 파싱"""
    config = configparser.ConfigParser()
    config.read_string("[can]\ninterface = vcan0\n")
    can = get_can_config(config)
    assert can["interfaces"] == ["vcan0"]
