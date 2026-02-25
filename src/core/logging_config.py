import logging
import sys
from datetime import datetime
from logging import Logger
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


def get_logger(name: str = "app") -> Logger:
    """
    Returns a professionally configured logger.
    - Timezone-aware timestamps
    - Console logs
    - Daily rotating file logs (keep 365 days)
    - Logs include filename, function name, line number, level
    """
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger  # avoid duplicate handlers

    logger.setLevel(logging.INFO)

    # ----- Base formatter -----
    fmt = "%(asctime)s | %(levelname)-8s | %(filename)s:%(funcName)s:%(lineno)d | %(message)s"

    class TZFormatter(logging.Formatter):
        """Formatter that includes timezone in timestamps."""

        def formatTime(self, record, datefmt=None):
            dt = datetime.fromtimestamp(
                record.created
            ).astimezone()  # ← Added .astimezone()
            if datefmt:
                return dt.strftime(datefmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    # ----- Console handler -----
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(TZFormatter(fmt))
    logger.addHandler(ch)

    # log_path = Path(__file__).resolve().parent.parent.parent / "logs"
    log_path = Path.cwd() / "logs"
    log_path.mkdir(parents=True, exist_ok=True)
    # ----- File handler (daily rotation, keep 365 days) -----
    fh = TimedRotatingFileHandler(
        log_path / "app.log",
        when="midnight",
        interval=1,
        backupCount=365,
        encoding="utf-8",
    )
    fh.setFormatter(TZFormatter(fmt))
    logger.addHandler(fh)
    return logger
