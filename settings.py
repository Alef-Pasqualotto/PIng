import json
from copy import deepcopy
from threading import RLock

from app_paths import config_path


DEFAULT_CONFIG = {
    "network": {
        "ssid": "Chamada",
        "password": "12345678",
        "port": 8000,
    }
}

_lock = RLock()


def load_config() -> dict:
    path = config_path()
    with _lock:
        if not path.exists():
            save_config(deepcopy(DEFAULT_CONFIG))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}

    result = deepcopy(DEFAULT_CONFIG)
    result["network"].update(data.get("network", {}))
    return result


def save_config(config: dict) -> dict:
    result = deepcopy(DEFAULT_CONFIG)
    result["network"].update(config.get("network", {}))
    path = config_path()
    with _lock:
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def update_network(ssid: str, password: str) -> dict:
    config = load_config()
    config["network"]["ssid"] = ssid.strip()
    config["network"]["password"] = password
    return save_config(config)
