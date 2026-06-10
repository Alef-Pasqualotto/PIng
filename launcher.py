import socket
import threading
import time
import os
import sys
from pathlib import Path
from tkinter import Tk, filedialog, messagebox

import uvicorn
import webview

import database
import network_service
import settings
from app_paths import log_dir, log_path
from logging_config import configure_logging, get_logger
from main import app


configure_logging()
logger = get_logger("launcher")


class DesktopApi:
    def save_csv(self, session_id):
        try:
            session = database.get_session(int(session_id))
            if session is None:
                logger.warning("CSV save requested for missing session: %s", session_id)
                return False
            root = Tk()
            root.withdraw()
            path = filedialog.asksaveasfilename(
                title="Salvar lista de presença",
                defaultextension=".csv",
                initialfile=f"presenca_sessao_{session_id}_{session['date']}.csv",
                filetypes=[("Arquivo CSV", "*.csv")],
            )
            root.destroy()
            if not path:
                logger.info("CSV save canceled: session=%s", session_id)
                return False
            Path(path).write_text(database.export_session_csv(int(session_id)), encoding="utf-8-sig")
            logger.info("CSV saved: session=%s path=%s", session_id, path)
            return True
        except Exception:
            logger.exception("CSV save failed: session=%s", session_id)
            raise

    def get_log_path(self):
        return str(log_path())

    def open_log_folder(self):
        try:
            os.startfile(log_dir())
            return True
        except Exception:
            logger.exception("Could not open log folder: %s", log_dir())
            return False

    def open_mobile_hotspot_settings(self):
        try:
            os.startfile("ms-settings:network-mobilehotspot")
            logger.info("Windows Mobile Hotspot settings opened")
            return True
        except Exception:
            logger.exception("Could not open Windows Mobile Hotspot settings")
            return False


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            logger.exception("Port availability check failed: port=%s", port)
            return False
    return True


def show_error(message: str) -> None:
    root = Tk()
    root.withdraw()
    messagebox.showerror("PIng", message)
    root.destroy()


def main() -> int:
    logger.info("Desktop launcher starting: python=%s frozen=%s", sys.version, getattr(sys, "frozen", False))
    try:
        port = int(settings.load_config()["network"]["port"])
        if not port_available(port):
            message = f"A porta {port} já está em uso. Consulte o log em {log_path()}"
            logger.error(message)
            show_error(message)
            return 1

        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_config=None, log_level="debug")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True, name="ping-server")
        thread.start()
        deadline = time.time() + 10
        while not server.started and thread.is_alive() and time.time() < deadline:
            time.sleep(0.05)
        if not server.started:
            message = f"O servidor local não pôde ser iniciado. Consulte {log_path()}"
            logger.error(message)
            show_error(message)
            return 1

        logger.info("Server started: url=http://127.0.0.1:%s/teacher", port)
        window = webview.create_window(
            "PIng - Painel do professor",
            f"http://127.0.0.1:{port}/teacher",
            js_api=DesktopApi(),
            width=1220,
            height=790,
            min_size=(900, 620),
        )

        def shutdown():
            logger.info("Desktop shutdown started")
            network_service.stop_if_started()
            server.should_exit = True

        window.events.closed += shutdown
        try:
            webview.start(debug=os.environ.get("PING_WEBVIEW_DEBUG") == "1")
        finally:
            shutdown()
            thread.join(timeout=5)
        logger.info("Desktop launcher stopped cleanly")
        return 0
    except Exception:
        logger.exception("Fatal desktop launcher error")
        show_error(f"O PIng encontrou um erro inesperado. Consulte o log em {log_path()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
