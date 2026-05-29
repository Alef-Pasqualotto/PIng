"""
preflight.py
============
Pre-flight compatibility check GUI.
Runs before your application starts and tells the user — in plain language —
whether their machine fully supports local network hosting.

Embed this in your app by calling:
    from preflight import run_preflight
    if not run_preflight():
        sys.exit()          # user chose to exit
    # ... launch your app

Or run standalone:
    python preflight.py
"""

import subprocess
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable

# ── Palette ───────────────────────────────────────────────────────────────────
BG          = "#0f1117"
BG_CARD     = "#181c27"
BG_CARD2    = "#1e2333"
BORDER      = "#2a3050"
TEXT        = "#e8eaf6"
TEXT_DIM    = "#6b7280"
ACCENT      = "#4f8ef7"
GREEN       = "#22c55e"
GREEN_DIM   = "#14532d"
YELLOW      = "#f59e0b"
YELLOW_DIM  = "#451a03"
RED_C       = "#ef4444"

WIN_W, WIN_H = 520, 500


# ── Driver check (runs in background thread) ──────────────────────────────────

def _check_hosted_network_support() -> tuple[bool, str]:
    """
    Returns (supported: bool, detail: str).
    Searches netsh wlan show drivers for the hosted-network support line,
    regardless of Windows UI language.
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "drivers"],
            capture_output=True, text=True,
            timeout=10, encoding="utf-8", errors="replace"
        )
        out = result.stdout
    except Exception as e:
        return False, f"Não foi possível pesquisar o driver de rede: {e}"

    if not out.strip():
        return False, "No wireless adapter found or Wi-Fi is disabled."

    KEYWORDS = (
        "hosted network",   # English
        "rede alojada",     # Portuguese (PT)
        "rede hospedada",   # Portuguese (BR)
        "red hospedada",    # Spanish
        "réseau hébergé",   # French
        "gehostetes netzwerk",  # German
    )
    YES_VALUES = ("yes", "sim", "sí", "oui", "ja", "supported", "suportado")

    for line in out.splitlines():
        lower = line.lower()
        if any(kw in lower for kw in KEYWORDS):
            value = line.split(":")[-1].strip().lower()
            supported = any(v in value for v in YES_VALUES)
            return supported, line.strip()

    # Could not find the line — treat as unknown / unsupported
    return False, "Não foi possível determinar o suporte do driver de rede."


# ── Main GUI ──────────────────────────────────────────────────────────────────

class PreflightApp(tk.Tk):

    def __init__(self, on_continue: Callable | None = None,
                 on_exit: Callable | None = None):
        super().__init__()

        self._on_continue = on_continue
        self._on_exit     = on_exit
        self._result: bool | None = None

        self.title("Análise de Compatibilidade")
        self.resizable(False, False)
        self.configure(bg=BG)
        self._center(WIN_W, WIN_H)
        self._build_ui()
        self._run_check()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Outer padding frame
        outer = tk.Frame(self, bg=BG, padx=28, pady=24)
        outer.pack(fill="both", expand=True)

        # Header
        tk.Label(outer, text="Análise de Sistema",
                 bg=BG, fg=TEXT_DIM,
                 font=("Courier New", 10, "bold"),
                 anchor="w").pack(fill="x")

        tk.Label(outer, text="Analisando seu \ndispositivo...",
                 bg=BG, fg=TEXT,
                 font=("Georgia", 26, "bold"),
                 anchor="w", justify="left").pack(fill="x", pady=(4, 20))

        # Card
        self._card = tk.Frame(outer, bg=BG_CARD,
                              highlightbackground=BORDER,
                              highlightthickness=1,
                              padx=20, pady=18)
        self._card.pack(fill="x")

        # Icon + title row
        row = tk.Frame(self._card, bg=BG_CARD)
        row.pack(fill="x")

        self._icon_lbl = tk.Label(row, text="◌", fg=TEXT_DIM, bg=BG_CARD,
                                  font=("Courier New", 28, "bold"))
        self._icon_lbl.pack(side="left", padx=(0, 14))

        title_col = tk.Frame(row, bg=BG_CARD)
        title_col.pack(side="left", fill="both", expand=True)

        self._status_lbl = tk.Label(title_col, text="Realizando checagem...",
                                    bg=BG_CARD, fg=TEXT,
                                    font=("Georgia", 14, "bold"),
                                    anchor="w")
        self._status_lbl.pack(fill="x")

        self._sub_lbl = tk.Label(title_col, text="Só um minutinho",
                                 bg=BG_CARD, fg=TEXT_DIM,
                                 font=("Courier New", 9),
                                 anchor="w", wraplength=320, justify="left")
        self._sub_lbl.pack(fill="x", pady=(4, 0))

        # Detail box (shown after check)
        self._detail_frame = tk.Frame(self._card, bg=BG_CARD2,
                                      highlightbackground=BORDER,
                                      highlightthickness=1,
                                      padx=14, pady=10)
        self._detail_lbl = tk.Label(self._detail_frame, text="",
                                    bg=BG_CARD2, fg=TEXT_DIM,
                                    font=("Courier New", 9),
                                    anchor="w", justify="left",
                                    wraplength=400)
        self._detail_lbl.pack(fill="x")

        # Spacer
        tk.Frame(outer, bg=BG, height=1).pack(fill="x", pady=12)

        # Button row (hidden until check finishes)
        self._btn_frame = tk.Frame(outer, bg=BG)
        self._btn_frame.pack(fill="x", side="bottom")

        # Spinner animation
        self._spinner_chars = ["◐", "◓", "◑", "◒"]
        self._spinner_idx   = 0
        self._spinning      = True
        self._animate()

    def _make_btn(self, parent, text, bg, fg, cmd, border=None):
        cfg = dict(text=text, bg=bg, fg=fg,
                   font=("Courier New", 10, "bold"),
                   relief="flat", cursor="hand2",
                   padx=22, pady=10,
                   activebackground=bg, activeforeground=fg,
                   command=cmd)
        btn = tk.Button(parent, **cfg)
        if border:
            wrap = tk.Frame(parent, bg=border, padx=1, pady=1)
            wrap.pack(side="left", padx=(0, 10))
            btn.pack(in_=wrap)
        else:
            btn.pack(side="left", padx=(0, 10))
        return btn

    # ── animation ─────────────────────────────────────────────────────────────

    def _animate(self):
        if self._spinning:
            self._icon_lbl.config(
                text=self._spinner_chars[self._spinner_idx % 4],
                fg=ACCENT
            )
            self._spinner_idx += 1
            self.after(120, self._animate)

    # ── check ─────────────────────────────────────────────────────────────────

    def _run_check(self):
        def worker():
            supported, detail = _check_hosted_network_support()
            self.after(0, lambda: self._show_result(supported, detail))
        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, supported: bool, detail: str):
        self._spinning = False
        self._result   = supported

        if supported:
            self._icon_lbl.config(text="✓", fg=GREEN)
            self._card.config(highlightbackground=GREEN)
            self._status_lbl.config(
                text="Seu dispositivo é compatível.",
                fg=GREEN)
            self._sub_lbl.config(
                text="Seu dispositivo suporta a criação de uma rede. "
                     "O aplicativo funcionará com todas as funcionalidades habilitadas.",
                fg=TEXT_DIM)
            self._detail_lbl.config(
                text=f"Informação de driver:  {detail}", fg=TEXT_DIM)
        else:
            self._icon_lbl.config(text="⚠", fg=YELLOW)
            self._card.config(highlightbackground=YELLOW)
            self._status_lbl.config(
                text="Compatibilidade limitada detectada.",
                font=("Courier New", 12, "bold"),
                fg=YELLOW)
            self._sub_lbl.config(
                text="O seu dispositivo não consegue criar redes independentes."
                "O sistema ainda funcionará, mas vai precisar estar conectado "
                "a uma rede (como Wi-Fi ou cabeada) para poder conectar com "
                "outros dispositivos. Todos os dispositivos precisam estar "
                "na mesma rede para serem visíveis para o computador.",
                fg=TEXT_DIM)
            self._detail_lbl.config(
                text=f"Informação de Driver: {detail}", fg=TEXT_DIM)

        # Show detail box
        self._detail_frame.pack(fill="x", pady=(14, 0))
        self._detail_lbl.pack(fill="x")

    # ── utils ─────────────────────────────────────────────────────────────────

    def _center(self, w: int, h: int):
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")


# ── Public API ────────────────────────────────────────────────────────────────

def run_preflight(on_continue: Callable | None = None,
                  on_exit: Callable | None = None) -> bool:
    """
    Show the pre-flight GUI and block until the user clicks Continue or Exit.

    Parameters
    ----------
    on_continue : optional callback(supported: bool)
        Called when the user clicks Continue. Receives True if driver is
        fully compatible, False if degraded mode.
    on_exit : optional callback()
        Called when the user clicks Exit. Defaults to sys.exit(0).

    Returns
    -------
    True  — user clicked Continue (driver supported)
    False — user clicked Continue on a degraded machine
    Raises SystemExit if user clicked Exit and no on_exit was provided.
    """
    result_holder = [None]

    def _cont(supported: bool):
        result_holder[0] = supported
        if on_continue:
            on_continue(supported)

    app = PreflightApp(on_continue=_cont, on_exit=on_exit)
    app.mainloop()

    return bool(result_holder[0])


# ── Standalone ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    def on_cont(supported: bool):
        if supported:
            print("Lançar aplicativo normalmente...")
        else:
            print("Lançar aplicativo com rede compartilhada...")

    run_preflight(on_continue=on_cont)