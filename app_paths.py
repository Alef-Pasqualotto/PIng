import os
import sys
from pathlib import Path


APP_NAME = "PIng"


def resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath(*parts)


def data_dir() -> Path:
    root = os.environ.get("PING_DATA_DIR")
    if root:
        path = Path(root)
    else:
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        path = Path(appdata) / APP_NAME if appdata else Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "attendance.db"


def config_path() -> Path:
    return data_dir() / "config.json"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path() -> Path:
    return log_dir() / "ping.log"
