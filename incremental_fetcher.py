from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.logger_setup import logger, LOG_TIME_FORMAT
from influx_query import EfdQueryClient
from config_loader import insert_efd_history_point, fetch_efd_history

load_dotenv()


class IncrementalEfdFetcher:
    """
    Incremental EFD telemetry downloader for CDIAT.

    This class retrieves historical telemetry from the Engineering
    Facility Database (EFD) in fixed backward windows (default: 5 days),
    preventing memory saturation inside Jupyter or Panel environments.

    Fetched samples are inserted into the internal SQLite history
    storage, relying on unique constraints to avoid duplicates.

    Parameters
    ----------
    measurement : str
        Name of the EFD measurement.
    field : str
        Name of the field to download.
    sal_index : int or None
        Optional SAL index for signal disambiguation.
    window_days : int
        Fixed size of each backward fetch window.
    """

    def __init__(
        self,
        measurement: str,
        field: str,
        sal_index: Optional[int] = None,
        window_days: int = 5,
    ) -> None:
        self.measurement = measurement
        self.field = field
        self.sal_index = sal_index
        self.window_days = window_days
        self.client = EfdQueryClient()

    def _get_last_timestamp(self) -> datetime:
        """
        Recover the last stored timestamp from SQLite history.

        Returns
        -------
        datetime
            Most recent timestamp found, otherwise current UTC time.
        """
        history = fetch_efd_history(
            measurement=self.measurement,
            field=self.field,
            salIndex=self.sal_index,
        )

        if not history:
            return datetime.utcnow()

        last = history[-1]["timestamp_utc"]
        return datetime.fromisoformat(last)

    @staticmethod
    def _fmt(ts: datetime) -> str:
        """
        Format timestamps using ISO-8601 for Influx queries.

        Returns
        -------
        str
            Formatted timestamp.
        """
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _build_query(self, t_start: datetime, t_end: datetime) -> str:
        """
        Construct an explicit time-range query for InfluxDB.

        Parameters
        ----------
        t_start : datetime
            Start boundary (inclusive).
        t_end : datetime
            End boundary (exclusive).

        Returns
        -------
        str
            A valid InfluxQL query for the given range.
        """
        sal_clause = (
            f" AND salIndex = {self.sal_index}"
            if self.sal_index is not None
            else ""
        )

        return (
            f'SELECT "{self.field}" '
            f'FROM "{self.measurement}" '
            f'WHERE time >= \'{self._fmt(t_start)}\' '
            f'AND time < \'{self._fmt(t_end)}\'{sal_clause}'
        )

    def fetch_incremental(self) -> Dict[str, Any]:
        """
        Fetch telemetry in backward time windows until no more results remain.

        Returns
        -------
        dict
            Summary of operation including batch count, points inserted,
            and last processed timestamp.
        """
        end_ts = self._get_last_timestamp()
        total_points = 0
        batches = 0

        logger.info(
            f"{LOG_TIME_FORMAT()} Incremental fetch start | "
            f"measurement={self.measurement}, field={self.field}, "
            f"salIndex={self.sal_index}"
        )

        while True:
            start_ts = end_ts - timedelta(days=self.window_days)
            query = self._build_query(start_ts, end_ts)

            logger.info(f"{LOG_TIME_FORMAT()} Fetch query: {query}")

            df = self.client.query(query)

            if df.empty:
                logger.info(f"{LOG_TIME_FORMAT()} No more data for this window.")
                break

            if "time" not in df.columns:
                logger.info(f"{LOG_TIME_FORMAT()} Missing time column in EFD return.")
                break

            df = df.rename(columns={"time": "timestamp"})
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            df = df.sort_values("timestamp")

            col = self.field
            if col not in df.columns:
                quoted = f'"{self.field}"'
                if quoted in df.columns:
                    df = df.rename(columns={quoted: col})
                else:
                    logger.info(
                        f"{LOG_TIME_FORMAT()} Field mismatch in EFD data: {self.field}"
                    )
                    break

            for _, row in df.iterrows():
                insert_efd_history_point(
                    timestamp_utc=row["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    measurement=self.measurement,
                    field=self.field,
                    value=float(row[col]),
                    salIndex=self.sal_index,
                )
                total_points += 1

            batches += 1
            end_ts = start_ts

            logger.info(
                f"{LOG_TIME_FORMAT()} Batch complete | rows={len(df)}, "
                f"next_end={self._fmt(end_ts)}"
            )

        logger.info(
            f"{LOG_TIME_FORMAT()} Incremental fetch completed | "
            f"batches={batches}, points={total_points}"
        )

        return {
            "batches": batches,
            "points_inserted": total_points,
            "last_timestamp_processed": self._fmt(end_ts),
        }
