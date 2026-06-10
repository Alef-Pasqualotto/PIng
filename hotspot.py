import subprocess
import socket
import platform
import re

from logging_config import get_logger


logger = get_logger("hotspot")

SSID     = "Chamada"
PASSWORD = "12345678"


def _system() -> str:
    return platform.system()  # "Linux" or "Windows"


# ---------------------------------------------------------------------------
# Hotspot control
# ---------------------------------------------------------------------------

def create_hotspot(ssid: str = SSID, password: str = PASSWORD) -> None:
    """
    Creates a Wi-Fi hotspot using OS-level commands.
    - Linux : nmcli (requires NetworkManager)
    - Windows: netsh (must be run as Administrator)
    Raises RuntimeError on unsupported OS or command failure.
    """
    system = _system()
    logger.info("Starting hotspot: platform=%s ssid=%r", system, ssid)
    if system == "Linux":
        _run([
            "nmcli", "device", "wifi", "hotspot",
            "ifname", _wifi_interface_linux(),
            "ssid",   ssid,
            "password", password,
        ])
    # elif system == "Windows":
    #     _run([
    #         "powershell", "-Command",
    #         "Start-Process ms-settings:network-mobilehotspot"
    #     ])
    #     print("[hotspot] Please enable the mobile hotspot manually in the Settings window that opened.")
    elif system == "Windows":
        _run(["netsh", "wlan", "set", "hostednetwork",
              "mode=allow", f"ssid={ssid}", f"key={password}"])
        _run(["netsh", "wlan", "start", "hostednetwork"])

    else:
        raise RuntimeError(f"Unsupported OS for hotspot creation: {system}")

    ip = get_local_ip()
    logger.info("Hotspot started: ssid=%r student_url=http://%s:8000", ssid, ip)


def stop_hotspot() -> None:
    """Tears down the hotspot on app shutdown."""
    system = _system()
    logger.info("Stopping hotspot: platform=%s", system)

    if system == "Linux":
        # nmcli brings down the connection named "Hotspot"
        try:
            _run(["nmcli", "connection", "down", "Hotspot"])
        except RuntimeError:
            # If it was never up or already down, ignore silently
            pass

    elif system == "Windows":
        try:
            _run(["netsh", "wlan", "stop", "hostednetwork"])
        except RuntimeError:
            pass

    else:
        logger.warning("Hotspot stop skipped on unsupported platform: %s", system)


# ---------------------------------------------------------------------------
# Network helpers
# ---------------------------------------------------------------------------

def get_local_ip() -> str:
    """
    Returns the notebook's current LAN/hotspot IP address.
    Opens a UDP socket (no data is actually sent) to determine
    which local interface would be used to reach the outside —
    this reliably returns the right IP even with multiple adapters.
    Falls back to 127.0.0.1 if nothing is reachable.
    """
    if _system() == "Windows":
        try:
            result = subprocess.run(
                ["ipconfig"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=10
            )
            addresses = re.findall(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", result.stdout)
            usable = [ip for ip in addresses if not ip.startswith(("127.", "169.254."))]
            if "192.168.137.1" in usable:
                return "192.168.137.1"
            if usable:
                return usable[0]
        except Exception:
            logger.exception("Could not determine Windows local IP with ipconfig")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        logger.exception("Could not determine local IP with UDP socket")
        return "127.0.0.1"


def _wifi_interface_linux() -> str:
    """
    Detects the first available wireless interface on Linux.
    Typical names: wlan0, wlp2s0, wlp3s0.
    Falls back to 'wlan0' if detection fails.
    """
    try:
        result = subprocess.run(
            ["nmcli", "-t", "-f", "DEVICE,TYPE", "device"],
            capture_output=True, text=True, check=True
        )
        for line in result.stdout.splitlines():
            device, _, dev_type = line.partition(":")
            if dev_type.strip() == "wifi":
                return device.strip()
    except Exception:
        logger.exception("Could not detect Linux Wi-Fi interface")
    return "wlan0"


def _run(cmd: list[str]) -> None:
    """Runs a shell command, raising RuntimeError on failure."""
    safe_cmd = ["key=***" if part.startswith("key=") else part for part in cmd]
    logger.debug("Running system command: %s", safe_cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    logger.debug(
        "System command finished: command=%s returncode=%s stdout=%r stderr=%r",
        safe_cmd, result.returncode, result.stdout.strip(), result.stderr.strip(),
    )
    if result.returncode != 0:
        logger.error("System command failed: command=%s returncode=%s", safe_cmd, result.returncode)
        detail = result.stderr.strip() or result.stdout.strip() or "Windows não informou detalhes."
        raise RuntimeError(f"Command failed: {' '.join(safe_cmd)}\ndetail: {detail}")
