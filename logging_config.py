import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler

from app_paths import log_path


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(threadName)s | %(message)s"
_configured = False


def configure_logging() -> logging.Logger:
    global _configured
    if _configured:
        return logging.getLogger("ping")

    level_name = os.environ.get("PING_LOG_LEVEL", "DEBUG" if not getattr(sys, "frozen", False) else "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    file_handler = RotatingFileHandler(
        log_path(), maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if not getattr(sys, "frozen", False):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)

    logging.captureWarnings(True)

    def log_uncaught(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logging.getLogger("ping.crash").critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback)
        )

    def log_thread_uncaught(args):
        logging.getLogger("ping.crash").critical(
            "Uncaught thread exception: thread=%s",
            args.thread.name if args.thread else "unknown",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_uncaught
    _configured = True
    logger = logging.getLogger("ping")
    logger.info("Logging initialized: level=%s file=%s", level_name.upper(), log_path())
    return logger


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"ping.{name}")
