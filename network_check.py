"""
network_check.py
================
Diagnoses why a locally-running server is unreachable from other devices.

Checks:
  1. Network interfaces, IPs, and their Public/Private profile
  2. Wireless driver — hosted network support (netsh wlan show drivers)
  3. Whether the target port is listening on 0.0.0.0
  4. Windows Firewall inbound rules for the port (via PowerShell — language-agnostic)
  5. ICMP (ping) inbound rule status
  6. Network profile recommendation (Public → Private)
  7. Reachability self-test from the local machine

Run as Administrator for full results.
Usage:
    python network_check.py --port 8000
    python network_check.py --port 8000 --fix
"""

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import winreg
from dataclasses import dataclass, field
from typing import Optional

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

OK   = f"{GREEN}[OK]{RESET}"
WARN = f"{YELLOW}[WARN]{RESET}"
FAIL = f"{RED}[FAIL]{RESET}"
INFO = f"{CYAN}[INFO]{RESET}"

# ── Helpers ───────────────────────────────────────────────────────────────────

def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace"
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except FileNotFoundError:
        return -1, "", f"Command not found: {cmd[0]}"


def run_ps(script: str, timeout: int = 15) -> tuple[int, str, str]:
    """Run a PowerShell script and return (rc, stdout, stderr)."""
    return run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=timeout
    )


def section(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")


# ── 1. Network Interfaces ─────────────────────────────────────────────────────

@dataclass
class Interface:
    name: str
    ips: list[str] = field(default_factory=list)
    gateway: Optional[str] = None
    profile: Optional[str] = None


def get_interfaces() -> list["Interface"]:
    _, out, _ = run(["ipconfig", "/all"])
    interfaces: list[Interface] = []
    current: Optional[Interface] = None

    for line in out.splitlines():
        stripped = line.strip()
        if not line.startswith(" ") and "adapter" in line.lower() and ":" in line:
            name = line.split("adapter", 1)[-1].strip().rstrip(":")
            current = Interface(name=name)
            interfaces.append(current)
        elif current is None:
            continue
        elif stripped.lower().startswith("ipv4 address"):
            ip = stripped.split(":", 1)[-1].strip().replace("(Preferred)", "").strip()
            if ip:
                current.ips.append(ip)
        elif stripped.lower().startswith("default gateway"):
            gw = stripped.split(":", 1)[-1].strip()
            if gw:
                current.gateway = gw

    return [i for i in interfaces if i.ips and not i.ips[0].startswith("::")]


def get_network_profiles(interfaces: list["Interface"]) -> None:
    REG_PATH = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\NetworkList\Profiles"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REG_PATH) as profiles_key:
            idx = 0
            profile_map: dict[str, str] = {}
            while True:
                try:
                    sub_name = winreg.EnumKey(profiles_key, idx)
                    idx += 1
                    with winreg.OpenKey(profiles_key, sub_name) as sub:
                        try:
                            name, _ = winreg.QueryValueEx(sub, "ProfileName")
                            cat, _  = winreg.QueryValueEx(sub, "Category")
                            label = {0: "Public", 1: "Private", 2: "Domain"}.get(cat, f"Unknown({cat})")
                            profile_map[name.lower()] = label
                        except OSError:
                            pass
                except OSError:
                    break
            for iface in interfaces:
                for profile_name, label in profile_map.items():
                    if profile_name in iface.name.lower() or iface.name.lower() in profile_name:
                        iface.profile = label
                        break
    except OSError:
        pass


def check_interfaces() -> list["Interface"]:
    section("1. Network Interfaces")
    interfaces = get_interfaces()
    get_network_profiles(interfaces)

    for iface in interfaces:
        profile_str = ""
        if iface.profile:
            colour = RED if iface.profile == "Public" else GREEN
            profile_str = f"  profile={colour}{iface.profile}{RESET}"
        gw_str = f"  gateway={iface.gateway}" if iface.gateway else ""
        print(f"  {INFO} {BOLD}{iface.name}{RESET}")
        print(f"        IPs : {', '.join(iface.ips)}{profile_str}{gw_str}")

    return interfaces


# ── 2. Wireless Driver — Hosted Network Support ───────────────────────────────

def check_wireless_driver() -> None:
    section("2. Wireless Driver — Hosted Network Support")

    _, out, err = run(["netsh", "wlan", "show", "drivers"], timeout=10)

    if not out.strip():
        print(f"  {WARN} No output from 'netsh wlan show drivers'.")
        print(f"         Wi-Fi adapter may be missing or disabled.")
        return

    lines = out.splitlines()

    # Look for the hosted network support line — value is on the same line after ':'
    # Works regardless of language by scanning for a line that contains a colon
    # and whose value is YES/NO/Sim/Não or equivalent.
    # Strategy: find the line that is 2-3 lines after the "Hosted Network" keyword,
    # OR find any line where the value after ':' is yes/no/sim/não.

    hosted_line: Optional[str] = None
    for i, line in enumerate(lines):
        lower = line.lower()
        # Match both English and common translations
        if any(kw in lower for kw in ("hosted network", "rede alojada", "rede hospedada",
                                       "red hospedada", "réseau hébergé")):
            hosted_line = line
            break

    if hosted_line is None:
        # Fallback: show all lines with yes/no values so user can identify it
        print(f"  {WARN} Could not identify the hosted network support line.")
        print(f"         Full driver output (look for the hosted network line):\n")
        for line in lines:
            if ":" in line and line.strip():
                print(f"         {line.strip()}")
        return

    # Extract value after the last ':'
    value = hosted_line.split(":")[-1].strip().lower()
    supported = value in ("yes", "sim", "sí", "oui", "ja", "yes.")

    if supported:
        print(f"  {OK} Hosted network supported by this driver.")
        print(f"         {hosted_line.strip()}")
    else:
        print(f"  {FAIL} Hosted network NOT supported.")
        print(f"         {hosted_line.strip()}")
        print(f"         {YELLOW}This driver cannot host a Wi-Fi hotspot in the traditional sense.")
        print(f"         You may need to use the Windows Mobile Hotspot feature instead,")
        print(f"         or update/replace the wireless driver.{RESET}")

    # Also show the driver name and version for reference
    for line in lines:
        lower = line.lower()
        if any(kw in lower for kw in ("driver", "version", "vendor", "fabricante",
                                       "fornecedor", "versão")):
            if ":" in line:
                print(f"  {INFO} {line.strip()}")


# ── 3. Port Binding ───────────────────────────────────────────────────────────

def check_port_binding(port: int) -> bool:
    section(f"3. Port {port} — Binding Check")

    _, out, _ = run(["netstat", "-ano"])
    listening_on: list[str] = []
    pid: Optional[str] = None

    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 4 and "LISTENING" in line:
            addr = parts[1]
            if f":{port}" in addr:
                listening_on.append(addr)
                pid = parts[-1] if len(parts) >= 5 else None

    if not listening_on:
        print(f"  {FAIL} Nothing is listening on port {port}.")
        print(f"         Start your server first, then re-run this script.")
        return False

    bound_all   = any(a.startswith("0.0.0.0") for a in listening_on)
    bound_local = any(a.startswith("127.0.0.1") for a in listening_on)

    for addr in listening_on:
        colour = GREEN if addr.startswith("0.0.0.0") else RED
        pid_str = f"  PID={pid}" if pid else ""
        print(f"  {INFO} Listening on {colour}{addr}{RESET}{pid_str}")

    if bound_all:
        print(f"  {OK} Server is bound to 0.0.0.0 — reachable from the network.")
    elif bound_local:
        print(f"  {FAIL} Server is bound to 127.0.0.1 (localhost only).")
        print(f"         Fix: make your server listen on 0.0.0.0 instead.")
    else:
        print(f"  {WARN} Server is bound to a specific IP — ensure it matches your Wi-Fi IP.")

    return bound_all


# ── 4. Firewall Rules (PowerShell — language-agnostic) ────────────────────────

def check_firewall_rules(port: int, fix: bool = False) -> None:
    section(f"4. Windows Firewall — Port {port} Rules")

    # Query by port filter first (fast, language-agnostic)
    ps_query = (
        f"Get-NetFirewallPortFilter | Where-Object {{ $_.LocalPort -eq '{port}' }} | "
        f"Get-NetFirewallRule | "
        f"Select-Object DisplayName, Enabled, Action, Profile | "
        f"ConvertTo-Json -Depth 2"
    )
    rc, out, err = run_ps(ps_query, timeout=20)

    if rc != 0 or not out.strip():
        print(f"  {FAIL} Could not query firewall rules via PowerShell.")
        if err.strip():
            print(f"         Error: {err.strip()[:200]}")
        print(f"         Try running as Administrator.")
        return

    # PowerShell returns a single object (dict) or array depending on match count
    try:
        raw = json.loads(out.strip())
        rules = raw if isinstance(raw, list) else [raw]
    except json.JSONDecodeError:
        print(f"  {WARN} Could not parse PowerShell output.")
        print(f"         Raw output: {out.strip()[:300]}")
        return

    if not rules:
        print(f"  {FAIL} No firewall rule found for port {port}.")
        if fix:
            _add_firewall_rule(port)
        else:
            print(f"         Run with --fix to add it automatically, or manually:")
            print(f"         {CYAN}netsh advfirewall firewall add rule name=\"MyServer_{port}\" "
                  f"dir=in action=allow protocol=TCP localport={port} profile=any{RESET}")
        return

    for rule in rules:
        name     = rule.get("DisplayName", "?")
        enabled  = str(rule.get("Enabled", "")).lower() in ("true", "1", "yes")
        action   = str(rule.get("Action", "")).lower()
        profile  = str(rule.get("Profile", ""))

        # Profile: PowerShell returns an integer or string
        # 1=Domain, 2=Private, 4=Public, 2147483647=Any
        profile_names = _decode_profile(profile)
        has_public = "Public" in profile_names or "Any" in profile_names
        is_allow   = action in ("allow", "2")

        status = OK if (enabled and is_allow and has_public) else FAIL
        print(f"  {status} Rule : {BOLD}{name}{RESET}")
        print(f"        Enabled={GREEN+'Yes'+RESET if enabled else RED+'No'+RESET}  "
              f"Action={GREEN+'Allow'+RESET if is_allow else RED+action+RESET}  "
              f"Profiles={', '.join(profile_names)}")

        if not enabled:
            print(f"         {RED}Rule is disabled — enable it in wf.msc or run with --fix.{RESET}")
            if fix:
                _set_rule_enabled(name)
        if not is_allow:
            print(f"         {RED}Rule blocks traffic — change Action to Allow.{RESET}")
        if not has_public:
            print(f"         {YELLOW}Public profile not included — add it or set to Any.{RESET}")
            if fix:
                _fix_rule_profiles(name)

    # ICMP check via PowerShell too
    print(f"\n  {INFO} Checking ICMP (ping) inbound rule …")
    ps_icmp = (
        "Get-NetFirewallRule | Where-Object { $_.Enabled -eq $true -and $_.Direction -eq 'Inbound' } | "
        "Get-NetFirewallPortFilter | Where-Object { $_.Protocol -eq 'ICMPv4' } | "
        "Select-Object Protocol | ConvertTo-Json -Depth 1"
    )
    _, icmp_out, _ = run_ps(ps_icmp, timeout=15)
    if icmp_out.strip() and "ICMPv4" in icmp_out:
        print(f"  {OK} ICMP inbound rule is enabled (ping should work).")
    else:
        print(f"  {WARN} No enabled ICMPv4 inbound rule found.")
        print(f"         Other devices cannot ping this machine.")
        if fix:
            _enable_icmp_rule()


def _decode_profile(profile_val: str) -> list[str]:
    """Convert PowerShell profile integer or string to readable names."""
    try:
        val = int(profile_val)
        if val == 2147483647 or val < 0:
            return ["Any"]
        names = []
        if val & 1: names.append("Domain")
        if val & 2: names.append("Private")
        if val & 4: names.append("Public")
        return names if names else [profile_val]
    except (ValueError, TypeError):
        return [profile_val] if profile_val else ["Unknown"]


def _add_firewall_rule(port: int) -> None:
    print(f"  {INFO} Adding firewall rule for port {port} …")
    rc, _, err = run([
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name=MyServer_{port}", "dir=in", "action=allow",
        "protocol=TCP", f"localport={port}", "profile=any"
    ])
    print(f"  {OK if rc == 0 else FAIL} {'Rule added.' if rc == 0 else 'Failed: ' + err.strip()}")


def _set_rule_enabled(name: str) -> None:
    print(f"  {INFO} Enabling rule '{name}' …")
    rc, _, err = run_ps(f"Set-NetFirewallRule -DisplayName '{name}' -Enabled True")
    print(f"  {OK if rc == 0 else FAIL} {'Done.' if rc == 0 else err.strip()[:120]}")


def _fix_rule_profiles(name: str) -> None:
    print(f"  {INFO} Setting rule '{name}' to all profiles …")
    rc, _, err = run_ps(f"Set-NetFirewallRule -DisplayName '{name}' -Profile Any")
    print(f"  {OK if rc == 0 else FAIL} {'Done.' if rc == 0 else err.strip()[:120]}")


def _enable_icmp_rule() -> None:
    print(f"  {INFO} Enabling ICMPv4 inbound rule …")
    rc, _, _ = run_ps(
        "Get-NetFirewallRule | Where-Object { $_.DisplayName -like '*ICMP*' -or $_.DisplayName -like '*Echo*' } "
        "| Set-NetFirewallRule -Enabled True"
    )
    print(f"  {OK if rc == 0 else FAIL} {'Done.' if rc == 0 else 'Could not enable — do it manually in wf.msc.'}")


# ── 5. Network Profile Recommendation ────────────────────────────────────────

def check_network_profile_recommendation(interfaces: list["Interface"]) -> None:
    section("5. Network Profile Recommendation")
    public_ifaces = [i for i in interfaces if i.profile == "Public"]
    if not public_ifaces:
        print(f"  {OK} No interfaces registered as Public.")
        return
    for iface in public_ifaces:
        print(f"  {FAIL} '{iface.name}' is set to {RED}Public{RESET}.")
        print(f"         Windows restricts inbound connections on Public networks.")
        print(f"         {YELLOW}Fix: Settings → Network & Internet → Wi-Fi → '{iface.name}' → Private{RESET}")


# ── 6. Reachability Self-Test ─────────────────────────────────────────────────

def check_reachability(interfaces: list["Interface"], port: int) -> None:
    section(f"6. Reachability Self-Test (port {port})")
    for iface in interfaces:
        for ip in iface.ips:
            try:
                with socket.create_connection((ip, port), timeout=2):
                    print(f"  {OK} {ip}:{port}  →  reachable  ({iface.name})")
            except ConnectionRefusedError:
                print(f"  {FAIL} {ip}:{port}  →  connection refused  (server not listening on this IP)")
            except OSError:
                print(f"  {WARN} {ip}:{port}  →  timed out  (firewall or network profile blocking)")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(port: int) -> None:
    section("Summary & Quick Fixes")
    print(f"""
  If a device on the same network still can't connect, work through this list:

  1. {BOLD}Wireless driver{RESET} must support hosted networks (check section 2).
  2. {BOLD}Server must bind to 0.0.0.0{RESET}, not 127.0.0.1 or localhost.
  3. {BOLD}Firewall rule{RESET} must exist for TCP port {port}, Enabled=True,
     Action=Allow, Profile=Any (or at least Public).
  4. {BOLD}Network profile{RESET} of the Wi-Fi adapter must be Private, not Public.
     → Settings → Network & Internet → Wi-Fi → your network → Private
  5. {BOLD}Use the correct IP{RESET}: use the IPv4 address of your Wi-Fi adapter
     (not localhost, not a VPN/virtual adapter IP).
  6. {BOLD}Third-party antivirus{RESET} may have its own firewall — disable it briefly to test.
  7. {BOLD}ICMP (ping){RESET}: if ping fails, enable the Echo Request rule in wf.msc.

  Re-run with {CYAN}--fix{RESET} to auto-apply firewall corrections (requires Administrator).
""")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose local server network reachability on Windows.")
    parser.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    parser.add_argument("--fix",  action="store_true",   help="Auto-fix firewall issues (requires Administrator)")
    args = parser.parse_args()

    print(f"\n{BOLD}{'='*60}")
    print(f"  Network Server Diagnostics  —  port {args.port}")
    print(f"{'='*60}{RESET}")

    if sys.platform != "win32":
        print(f"\n{RED}  This script is designed for Windows only.{RESET}")
        sys.exit(1)

    if not is_admin():
        print(f"\n{YELLOW}  ⚠  Not running as Administrator.")
        print(f"     Some checks may be incomplete (firewall, registry).")
        print(f"     Right-click the terminal → 'Run as administrator' for full results.{RESET}")

    interfaces = check_interfaces()
    check_wireless_driver()
    check_port_binding(args.port)
    check_firewall_rules(args.port, fix=args.fix)
    check_network_profile_recommendation(interfaces)
    check_reachability(interfaces, args.port)
    print_summary(args.port)


if __name__ == "__main__":
    main()