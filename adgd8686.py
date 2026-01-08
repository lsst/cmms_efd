from __future__ import annotations

import os
import sys
import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.logger_setup import logger, LOG_TIME_FORMAT
from influx_query import EfdQueryClient
from config_loader import insert_efd_history_point


# --------------------------------------------------------------------
# Load environment variables
# --------------------------------------------------------------------
load_dotenv()

EFD_URL = os.getenv("EFD_URL")
EFD_USERNAME = os.getenv("EFD_USERNAME")
EFD_PASSWORD = os.getenv("EFD_PASSWORD")

logger.info(f"{LOG_TIME_FORMAT()} DEBUG: EFD_URL={EFD_URL}")
logger.info(f"{LOG_TIME_FORMAT()} DEBUG: USER={EFD_USERNAME}")

# --------------------------------------------------------------------
# Initialize EFD Client with debug
# --------------------------------------------------------------------
try:
    client = EfdQueryClient(
        base_url=EFD_URL,
        username=EFD_USERNAME,
        password=EFD_PASSWORD,
    )
    logger.info(f"{LOG_TIME_FORMAT()} DEBUG: EfdQueryClient initialized")
except Exception as exc:
    logger.error(
        f"{LOG_TIME_FORMAT()} ERROR: Failed to initialize EfdQueryClient: {exc}",
        exc_info=True,
    )
    raise


# --------------------------------------------------------------------
# Query to fetch ALL DATA of one field
# --------------------------------------------------------------------
MEASUREMENT = "lsst.sal.HVAC.glycolSensor"
FIELD = "supplyTempChiller02"

query = f'SELECT "{FIELD}" FROM "{MEASUREMENT}"'
logger.info(f"{LOG_TIME_FORMAT()} BULK QUERY: {query}")

# --------------------------------------------------------------------
# Execute query with debug
# --------------------------------------------------------------------
try:
    df = client.query(query)
    logger.info(f"{LOG_TIME_FORMAT()} DEBUG: raw type={type(df)}")
    logger.info(f"{LOG_TIME_FORMAT()} DEBUG: raw columns={df.columns.tolist()}")
    logger.info(f"{LOG_TIME_FORMAT()} DEBUG: DF size={len(df)} rows")

except Exception as exc:
    logger.error(
        f"{LOG_TIME_FORMAT()} ERROR: Query failed: {exc}",
        exc_info=True,
    )
    raise


# --------------------------------------------------------------------
# Check if DataFrame is empty
# --------------------------------------------------------------------
if df.empty:
    logger.info(f"{LOG_TIME_FORMAT()} BULK: EFD returned NO DATA.")
    sys.exit(0)

logger.info(f"{LOG_TIME_FORMAT()} BULK: received {len(df)} rows")


# --------------------------------------------------------------------
# Insert into SQLite efd_history
# --------------------------------------------------------------------
rows_inserted = 0

for _, row in df.iterrows():
    ts = row["time"] if "time" in df.columns else None
    val = row[FIELD]

    insert_efd_history_point(
        timestamp_utc=str(ts),
        measurement=MEASUREMENT,
        field=FIELD,
        value=float(val),
        salIndex=None,
    )

    rows_inserted += 1

logger.info(
    f"{LOG_TIME_FORMAT()} BULK: Inserted {rows_inserted} points into efd_history"
)
