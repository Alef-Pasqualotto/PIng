import subprocess
import socket
import platform

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
    if system == "Linux":
        _run([
            "nmcli", "device", "wifi", "hotspot",
            "ifname", _wifi_interface_linux(),
            "ssid",   ssid,
            "password", password,
        ])

    elif system == "Windows":
        print("windows")
        _run(["netsh", "wlan", "set", "hostednetwork",
              "mode=allow", f"ssid={ssid}", f"key={password}"])
        _run(["netsh", "wlan", "start", "hostednetwork"])

    else:
        raise RuntimeError(f"Unsupported OS for hotspot creation: {system}")

    ip = get_local_ip()
    print(f"\n{'='*50}")
    print(f"  Hotspot created!")
    print(f"  SSID     : {ssid}")
    print(f"  Password : {password}")
    print(f"  Students should open: http://{ip}:8000")
    print(f"  Teacher dashboard  : http://{ip}:8000/teacher")
    print(f"{'='*50}\n")


def stop_hotspot() -> None:
    """Tears down the hotspot on app shutdown."""
    system = _system()

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
        print(f"[hotspot] stop_hotspot: unsupported OS ({system}), skipping.")


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
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
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
        pass
    return "wlan0"


def _run(cmd: list[str]) -> None:
    """Runs a shell command, raising RuntimeError on failure."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )