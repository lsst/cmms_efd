import logging
import pytz
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CHILE_TZ = pytz.timezone("America/Santiago")
LOG_FILE = PROJECT_ROOT.parent / "main.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_TIME_FORMAT1 = "%Y-%m-%d %H:%M:%S"

logger = logging.getLogger("CMMS_LOGGER")
logger.setLevel(logging.DEBUG)

if not logger.hasHandlers():
    fh = logging.FileHandler(LOG_FILE)
    fh.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt=LOG_TIME_FORMAT1
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)


def LOG_TIME_FORMAT() -> str:
    return datetime.now(CHILE_TZ).strftime(LOG_TIME_FORMAT1)
