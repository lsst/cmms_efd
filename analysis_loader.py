from __future__ import annotations

import sqlite3
from typing import Optional
import pandas as pd
from datetime import datetime
import pytz
import os

from backend.logger_setup import logger, LOG_TIME_FORMAT
from backend.config_loader import _execute_fetch, DB_PATH


CHILE_TZ = pytz.timezone("America/Santiago")


def load_history_dataframe(
    measurement: str,
    field: str,
    sal_index: int,
    db_path: str = DB_PATH
) -> Optional[pd.DataFrame]:
    """
    Load historical EFD data for a specific telemetry variable.

    Parameters
    ----------
    measurement : str
        EFD measurement name.
    field : str
        Telemetry variable stored in history.
    sal_index : int
        SAL index used to distinguish identical measurements.
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pandas.DataFrame or None
        DataFrame with columns:
        ["timestamp", "value"]
        or None if no data is found.
    """
    rows = _execute_fetch(
        """
        SELECT timestamp, value
        FROM efd_history
        WHERE measurement = ?
          AND field = ?
          AND salIndex = ?
        ORDER BY timestamp ASC
        """,
        (measurement, field, sal_index),
        db_path=db_path,
    )

    if not rows:
        logger.info(
            f"{LOG_TIME_FORMAT()} ANALYSIS: no historical data "
            f"for {measurement}.{field} (salIndex={sal_index})"
        )
        return None

    df = pd.DataFrame(rows, columns=["timestamp", "value"])

    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    except Exception as exc:
        logger.error(
            f"{LOG_TIME_FORMAT()} ANALYSIS: timestamp parse error | {exc}"
        )
        return None

    df["value"] = df["value"].astype(float)
    return df


def load_history_last_n_days(
    measurement: str,
    field: str,
    sal_index: int,
    days: int,
    db_path: str = DB_PATH
) -> Optional[pd.DataFrame]:
    """
    Load historical data limited to the last N days.

    Parameters
    ----------
    measurement : str
        EFD measurement name.
    field : str
        Telemetry variable stored in history.
    sal_index : int
        SAL index.
    days : int
        Number of days to include in the filtered output.
    db_path : str
        Path to the SQLite database.

    Returns
    -------
    pandas.DataFrame or None
        Filtered DataFrame.
    """
    full_df = load_history_dataframe(measurement, field, sal_index, db_path)

    if full_df is None:
        return None

    cutoff = datetime.now(tz=CHILE_TZ).astimezone(pytz.UTC) - pd.Timedelta(days=days)
    filtered = full_df[full_df["timestamp"] >= cutoff]

    if filtered.empty:
        logger.info(
            f"{LOG_TIME_FORMAT()} ANALYSIS: no data in the last {days} days "
            f"for {measurement}.{field}"
        )
        return None

    return filtered
