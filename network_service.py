import platform
import subprocess
from threading import RLock

import hotspot
import settings
from logging_config import get_logger


logger = get_logger("network")


_lock = RLock()
_started_by_app = False
_last_error = None


def compatibility() -> dict:
    if platform.system() != "Windows":
        return {
            "supported": False,
            "wireless_present": False,
            "reason": "unsupported_platform",
            "detail": "Esta versão do aplicativo foi preparada para Windows.",
        }
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "drivers"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        logger.exception("Network compatibility check failed")
        return {
            "supported": False,
            "wireless_present": False,
            "reason": "diagnostic_failed",
            "detail": f"Não foi possível consultar o adaptador Wi-Fi: {exc}",
        }

    output = result.stdout.lower()
    no_wireless_messages = (
        "there is no wireless interface",
        "não há nenhuma interface sem fio",
        "nao ha nenhuma interface sem fio",
        "no hay ninguna interfaz inalámbrica",
    )
    if any(message in output for message in no_wireless_messages):
        return {
            "supported": False,
            "wireless_present": False,
            "reason": "no_wireless_adapter",
            "detail": (
                "Nenhum adaptador Wi-Fi está disponível. Conecte ou habilite um adaptador Wi-Fi, "
                "ou use a rede Ethernet/Wi-Fi existente para os celulares acessarem o PIng."
            ),
        }

    supported = False
    for line in output.splitlines():
        if any(term in line for term in ("hosted network", "rede hospedada", "rede alojada")):
            value = line.rsplit(":", 1)[-1].strip()
            supported = value in {"yes", "sim", "sí", "oui", "ja"}
            break
    detail = "O adaptador oferece suporte à rede hospedada automática." if supported else (
        "O driver não oferece a rede hospedada antiga do Windows. Tente o Hotspot Móvel nas "
        "Configurações do Windows ou use uma rede existente."
    )
    return {
        "supported": supported,
        "wireless_present": True,
        "reason": None if supported else "hosted_network_unsupported",
        "detail": detail,
    }


def status() -> dict:
    config = settings.load_config()["network"]
    ip = hotspot.get_local_ip()
    port = int(config.get("port", 8000))
    with _lock:
        started = _started_by_app
        error = _last_error
    return {
        "started": started,
        "ssid": config["ssid"],
        "password": config["password"],
        "ip": ip,
        "port": port,
        "student_url": f"http://{ip}:{port}",
        "last_error": error,
        "compatibility": compatibility(),
    }


def start() -> dict:
    global _started_by_app, _last_error
    config = settings.load_config()["network"]
    support = compatibility()
    if not support["supported"]:
        logger.warning(
            "Automatic hotspot unavailable: reason=%s detail=%s",
            support.get("reason"), support["detail"],
        )
        raise RuntimeError(support["detail"])
    with _lock:
        try:
            hotspot.create_hotspot(config["ssid"], config["password"])
            _started_by_app = True
            _last_error = None
        except Exception as exc:
            logger.exception("Hotspot start failed: ssid=%r", config["ssid"])
            _started_by_app = False
            _last_error = str(exc)
            raise RuntimeError(str(exc)) from exc
    return status()


def stop() -> dict:
    global _started_by_app, _last_error
    with _lock:
        try:
            hotspot.stop_hotspot()
            _started_by_app = False
            _last_error = None
        except Exception as exc:
            logger.exception("Hotspot stop failed")
            _last_error = str(exc)
            raise RuntimeError(str(exc)) from exc
    return status()


def stop_if_started() -> None:
    with _lock:
        should_stop = _started_by_app
    if should_stop:
        try:
            stop()
        except RuntimeError:
            pass
