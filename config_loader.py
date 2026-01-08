# This file is part of {{ fourbad123.CDIAT_PROYECT }}.
#
# Developed for the LSST System.
# This product includes software developed by the LSST Project
# (https://www.lsst.org).
# See the COPYRIGHT file at the top-level directory of this distribution
# for details of code ownership.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional, Dict, List

import pytz
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, "intDB.db")
CHILE_TZ = pytz.timezone("America/Santiago")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    logger.addHandler(handler)

def _execute_query(
    query: str,
    params: Iterable[Any] | None = None,
    db_path: str = DB_PATH,
) -> None:
    """
    Execute a write query (INSERT, UPDATE, DELETE).

    Parameters
    ----------
    query : str
        SQL statement to be executed.
    params : Iterable[Any] or None
        Positional parameters for the query.
    db_path : str
        Path to the SQLite database file.
    """
    params = params or ()
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(query, params)
            conn.commit()
    except Exception as exc:
        logger.error(f"DB write failed: {exc}")


def _execute_fetch(
    query: str,
    params: Iterable[Any] | None = None,
    db_path: str = DB_PATH,
) -> list[tuple]:
    """
    Execute a SELECT query and return all rows.

    Parameters
    ----------
    query : str
        SQL SELECT statement.
    params : Iterable[Any] or None
        Positional parameters for the query.
    db_path : str
        Path to the SQLite database file.

    Returns
    -------
    list of tuple
        Result rows returned by the query.
    """
    params = params or ()
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    except Exception as exc:
        logger.error(f"DB fetch failed: {exc}")
        return []

def read_config_from_db(db_path: str = DB_PATH) -> list[dict]:
    """
    Read all configuration entries from `config_interval`.

    Returns
    -------
    list of dict
    """
    rows = _execute_fetch(
        """
        SELECT id, name, measurement, field, asset_id, attribute,
               db_name, time_interval, salIndex, type_telemetry
        FROM config_interval
        """,
        db_path=db_path,
    )

    return [
        {
            "id": row[0],
            "name": row[1],
            "measurement": row[2],
            "field": row[3],
            "asset_id": row[4],
            "attribute": row[5],
            "db_name": row[6],
            "time_interval": row[7],
            "salIndex": row[8],
            "type_telemetry": row[9],
        }
        for row in rows
    ]


def insert_config(entry: dict, db_path: str = DB_PATH) -> None:
    """
    Insert a new configuration entry.
    """
    _execute_query(
        """
        INSERT INTO config_interval
        (name, measurement, field, asset_id, attribute, db_name,
         time_interval, salIndex, type_telemetry)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry["name"],
            entry["measurement"],
            entry["field"],
            entry["asset_id"],
            entry["attribute"],
            entry["db_name"],
            entry.get("time_interval", "24h"),
            entry.get("salIndex"),
            entry.get("type_telemetry"),
        ),
        db_path=db_path,
    )
    logger.debug(f"Inserted config: {entry['name']}")


def update_config(entry: dict, db_path: str = DB_PATH) -> None:
    """
    Update an existing configuration entry.
    """
    if "id" not in entry:
        raise ValueError("Configuration update requires 'id' field.")

    _execute_query(
        """
        UPDATE config_interval
        SET name = ?, measurement = ?, field = ?, asset_id = ?, attribute = ?,
            db_name = ?, time_interval = ?, salIndex = ?, type_telemetry = ?
        WHERE id = ?
        """,
        (
            entry["name"],
            entry["measurement"],
            entry["field"],
            entry["asset_id"],
            entry["attribute"],
            entry["db_name"],
            entry.get("time_interval", "24h"),
            entry.get("salIndex"),
            entry.get("type_telemetry"),
            entry["id"],
        ),
        db_path=db_path,
    )
    logger.debug(f"Updated configuration: {entry['id']}")

def has_24h_passed_since_last_run(db_path: str = DB_PATH) -> bool:
    """
    Check whether 24 hours have elapsed since the last shutter run.
    """
    rows = _execute_fetch(
        "SELECT last_run FROM shutter_schedule WHERE id = 1",
        db_path=db_path,
    )

    if not rows:
        return True

    try:
        last_run = datetime.strptime(rows[0][0], "%Y-%m-%dT%H:%M:%S")
        last_run = CHILE_TZ.localize(last_run)
        now = datetime.now(CHILE_TZ)
        return (now - last_run) >= timedelta(hours=24)
    except Exception:
        return True


def save_shutter_activation_to_db(
    db_path: str,
    asset_id: str,
    num_activations: int,
) -> None:
    """
    Record shutter activation count.
    """
    timestamp = datetime.now(CHILE_TZ).strftime("%Y-%m-%dT%H:%M:%S")
    _execute_query(
        """
        INSERT INTO shutter_activations (asset_id, last_update, last_activations)
        VALUES (?, ?, ?)
        """,
        (asset_id, timestamp, num_activations),
        db_path=db_path,
    )


def update_last_run_timestamp(db_path: str = DB_PATH) -> None:
    """
    Update the last shutter run timestamp.
    """
    now = datetime.now(CHILE_TZ).strftime("%Y-%m-%dT%H:%M:%S")
    _execute_query(
        """
        INSERT INTO shutter_schedule (id, last_run)
        VALUES (1, ?)
        ON CONFLICT(id)
        DO UPDATE SET last_run = excluded.last_run
        """,
        (now,),
        db_path=db_path,
    )


def get_last_run_timestamp(db_path: str = DB_PATH) -> Optional[datetime]:
    """
    Retrieve the last shutter run timestamp.
    """
    rows = _execute_fetch(
        "SELECT last_run FROM shutter_schedule WHERE id = 1",
        db_path=db_path,
    )

    if rows and rows[0][0]:
        try:
            naive_dt = datetime.strptime(rows[0][0], "%Y-%m-%dT%H:%M:%S")
            return CHILE_TZ.localize(naive_dt)
        except Exception:
            return None

    return None

def save_trigger_event(
    config_id: str,
    frequency: int,
    frequency_um: str,
    db_path: str = DB_PATH,
) -> None:
    """
    Save or update a trigger event.
    """
    ts = datetime.now(CHILE_TZ).isoformat()
    _execute_query(
        """
        INSERT INTO trigger_log (config_id, last_trigger_time, frequency, frequencyUM)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(config_id)
        DO UPDATE SET
            last_trigger_time = excluded.last_trigger_time,
            frequency = excluded.frequency,
            frequencyUM = excluded.frequencyUM
        """,
        (config_id, ts, frequency, frequency_um),
        db_path=db_path,
    )


def get_last_trigger_info(
    config_id: str,
    db_path: str = DB_PATH,
) -> tuple[Optional[datetime], Optional[int], Optional[str]]:
    """
    Retrieve trigger log info.
    """
    rows = _execute_fetch(
        """
        SELECT last_trigger_time, frequency, frequencyUM
        FROM trigger_log
        WHERE config_id = ?
        """,
        (config_id,),
        db_path=db_path,
    )

    if not rows:
        return None, None, None

    ts_raw, freq, freq_um = rows[0]

    try:
        last_ts = datetime.fromisoformat(ts_raw)
    except Exception:
        last_ts = None

    return last_ts, freq, freq_um

def insert_efd_history_point(
    timestamp_utc: str,
    measurement: str,
    field: str,
    value: float,
    salIndex: Optional[int],
    db_path: str = DB_PATH,
) -> None:
    """
    Insert a telemetry data point into `efd_history`, ensuring no duplicates.
    """
    try:
        _execute_query(
            """
            INSERT INTO efd_history (
                timestamp_utc, measurement, field, value, salIndex
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (timestamp_utc, measurement, field, value, salIndex),
            db_path=db_path,
        )
        logger.debug(
            f"Inserted EFD data point: {timestamp_utc} {measurement}.{field}[{salIndex}] = {value}"
        )
    except Exception as exc:
        logger.error(f"EFD history insert failed: {exc}")


def fetch_efd_history(
    measurement: str,
    field: str,
    salIndex: Optional[int],
    db_path: str = DB_PATH,
) -> List[Dict[str, Any]]:
    """
    Fetch ordered telemetry history for a given signal.
    """
    rows = _execute_fetch(
        """
        SELECT timestamp_utc, measurement, field, value, salIndex
        FROM efd_history
        WHERE measurement = ?
          AND field = ?
          AND (salIndex IS ? OR salIndex = ?)
        ORDER BY timestamp_utc ASC
        """,
        (measurement, field, salIndex, salIndex),
        db_path=db_path,
    )

    return [
        {
            "timestamp_utc": r[0],
            "measurement": r[1],
            "field": r[2],
            "value": float(r[3]),
            "salIndex": r[4],
        }
        for r in rows
    ]


def init_ml_storage(db_path: str = DB_PATH) -> None:
    """
    Ensure ML indexes exist.
    """
    try:
        _execute_query(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ml_linear_models_unique
            ON ml_linear_models (measurement, field, salIndex, version)
            """,
            db_path=db_path,
        )
        logger.debug("ML storage (linear regression) initialized.")
    except Exception as exc:
        logger.error(f"Failed to initialize ML storage: {exc}")


def save_ml_linear_model(
    measurement: str,
    field: str,
    salIndex: Optional[int],
    slope: float,
    intercept: float,
    rmse: float,
    r2: float,
    train_size: int,
    params: Dict[str, Any],
    db_path: str = DB_PATH,
) -> int:
    """
    Save a linear regression model into the ml_linear_models table.
    """
    trained_at = datetime.now(CHILE_TZ).isoformat()

    rows = _execute_fetch(
        """
        SELECT MAX(version)
        FROM ml_linear_models
        WHERE measurement = ?
          AND field = ?
          AND (salIndex IS ? OR salIndex = ?)
        """,
        (measurement, field, salIndex, salIndex),
        db_path=db_path,
    )

    next_version = (rows[0][0] or 0) + 1

    _execute_query(
        """
        UPDATE ml_linear_models
        SET is_active = 0
        WHERE measurement = ?
          AND field = ?
          AND (salIndex IS ? OR salIndex = ?)
          AND is_active = 1
        """,
        (measurement, field, salIndex, salIndex),
        db_path=db_path,
    )

    _execute_query(
        """
        INSERT INTO ml_linear_models (
            measurement, field, salIndex, version,
            slope, intercept, rmse, r2, train_size,
            params_json, is_active, trained_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            measurement,
            field,
            salIndex,
            next_version,
            slope,
            intercept,
            rmse,
            r2,
            train_size,
            json.dumps(params, ensure_ascii=False),
            trained_at,
        ),
        db_path=db_path,
    )

    logger.debug(
        f"Saved Linear Regression model v{next_version} for "
        f"{measurement}.{field}[{salIndex}] (r2={r2}, rmse={rmse})"
    )

    return next_version


def load_latest_ml_linear_model(
    measurement: str,
    field: str,
    salIndex: Optional[int],
    db_path: str = DB_PATH,
) -> Optional[Dict[str, Any]]:
    """
    Load the latest active linear regression model.
    """
    rows = _execute_fetch(
        """
        SELECT id, version, slope, intercept, rmse, r2, train_size,
               params_json, trained_at
        FROM ml_linear_models
        WHERE measurement = ?
          AND field = ?
          AND (salIndex IS ? OR salIndex = ?)
          AND is_active = 1
        ORDER BY version DESC
        LIMIT 1
        """,
        (measurement, field, salIndex, salIndex),
        db_path=db_path,
    )

    if not rows:
        return None

    row = rows[0]

    return {
        "id": row[0],
        "version": row[1],
        "slope": row[2],
        "intercept": row[3],
        "rmse": row[4],
        "r2": row[5],
        "train_size": row[6],
        "params": json.loads(row[7]),
        "trained_at": row[8],
    }
