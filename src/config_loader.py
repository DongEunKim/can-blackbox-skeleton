"""
설정 로더 - INI 파일 기반 설정 관리
"""

import configparser
from pathlib import Path
from typing import Optional


def load_config(config_path: Optional[Path] = None) -> configparser.ConfigParser:
    """
    INI 설정 파일을 로드한다.

    Args:
        config_path: 설정 파일 경로. None이면 config.ini 사용

    Returns:
        ConfigParser 인스턴스

    Raises:
        FileNotFoundError: 설정 파일이 없을 때
    """
    if config_path is None:
        config_path = Path("config.ini")
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {config_path}")

    config = configparser.ConfigParser()
    config.read(config_path, encoding="utf-8")
    return config


def get_can_config(config: configparser.ConfigParser) -> dict:
    """CAN 관련 설정을 딕셔너리로 반환한다."""
    section = "can"
    raw = config.get(section, "interface", fallback="vcan0")
    interfaces = [s.strip() for s in raw.split(",") if s.strip()]
    if not interfaces:
        interfaces = ["vcan0"]
    return {
        "interfaces": interfaces,
        "log_interval": config.getint(section, "log_interval", fallback=0),
        "reconnect_max_retries": config.getint(
            section, "reconnect_max_retries", fallback=5
        ),
        "reconnect_interval_sec": config.getint(
            section, "reconnect_interval_sec", fallback=2
        ),
    }


def get_logging_config(config: configparser.ConfigParser) -> dict:
    """로깅 관련 설정을 딕셔너리로 반환한다."""
    section = "logging"
    rotation_raw = config.get(section, "rotation_max_mb", fallback="10")
    try:
        rotation_max_mb = float(rotation_raw)
    except ValueError:
        rotation_max_mb = 10.0
    return {
        "output_dir": config.get(section, "output_dir", fallback="./logs"),
        "log_prefix": config.get(section, "log_prefix", fallback="CBB_"),
        "rotation_max_mb": rotation_max_mb,
        "max_logging_minutes": config.getint(
            section, "max_logging_minutes", fallback=30
        ),
    }


def get_storage_config(config: configparser.ConfigParser) -> dict:
    """저장소(용량) 관련 설정을 딕셔너리로 반환한다."""
    section = "storage"
    return {
        "max_total_mb": config.getint(section, "max_total_mb", fallback=500),
    }


def get_watcher_config(config: configparser.ConfigParser) -> dict:
    """폴더 감시 관련 설정을 딕셔너리로 반환한다."""
    section = "watcher"
    return {
        "poll_interval": config.getint(section, "poll_interval", fallback=5),
    }


def get_stream_manager_config(config: configparser.ConfigParser) -> dict:
    """StreamManager 관련 설정을 딕셔너리로 반환한다."""
    section = "stream_manager"
    use_mock_raw = config.get(section, "use_mock", fallback="true").lower()
    use_mock = use_mock_raw in ("true", "1", "yes")
    return {
        "use_mock": use_mock,
        "stream_name": config.get(section, "stream_name", fallback="CanBlackboxStream"),
        "status_stream_name": config.get(
            section, "status_stream_name", fallback="CanBlackboxStatusStream"
        ),
        "s3_bucket": config.get(section, "s3_bucket", fallback=""),
        "s3_prefix": config.get(section, "s3_prefix", fallback="can-logs/"),
    }
