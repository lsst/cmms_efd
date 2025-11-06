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

import os
import sys
import asyncio
from typing import Optional

import requests
from dotenv import load_dotenv

from logger_setup import logger, LOG_TIME_FORMAT
from error_utils import safe_execution

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from config_loader import read_config_from_db
from pm_handler import maintenance_loop
from efd_monitor import monitor_subsystem

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

load_dotenv()

AUTH_URL = os.getenv("AUTH_URL")
USERNAME = os.getenv("CMMS_USERNAME")
PASSWORD = os.getenv("CMMS_PASSWORD")


@safe_execution(retries=3, delay=3)
async def get_token() -> str | None:
    """
    Authenticate to CMMS and return an access token.

    Returns
    -------
    str or None
        The authentication token if successful, otherwise None.
    """
    if not AUTH_URL:
        logger.error("AUTH_URL is not defined in environment variables.")
        return None

    headers = {"Content-Type": "application/json"}
    credentials = {"username": USERNAME, "password": PASSWORD}

    response = requests.post(
        AUTH_URL, headers=headers, json=credentials, verify=False, timeout=10
    )
    response.raise_for_status()

    token = response.json().get("data", {}).get("_id")
    if not token:
        logger.warning("Token field missing in authentication response.")
        return None

    logger.info(f"{LOG_TIME_FORMAT()} Authentication successful.")
    return token


async def main() -> None:
    """
    Entry point for backend execution.

    Steps
    -----
    1. Obtain CMMS authentication token.
    2. Load monitoring configurations.
    3. Start telemetry monitoring and preventive maintenance loops.
    """
    site = "usdf"
    db_name = "efd"

    token = await get_token()
    if not token:
        logger.error(f"{LOG_TIME_FORMAT()} Unable to start backend without authentication token.")
        return

    try:
        configs = read_config_from_db()
    except Exception as exc:
        logger.error(f"{LOG_TIME_FORMAT()} Failed to load configuration database: {exc}", exc_info=True)
        return

    if not configs:
        logger.warning(f"{LOG_TIME_FORMAT()} No telemetry configurations found. Backend will not execute monitoring.")
        return

    tasks = [monitor_subsystem(token, site, db_name, cfg) for cfg in configs]
    tasks.append(maintenance_loop(token))

    logger.info(f"{LOG_TIME_FORMAT()} Starting backend tasks ({len(tasks)} total).")

    try:
        await asyncio.gather(*tasks)
    except Exception as exc:
        logger.error(f"{LOG_TIME_FORMAT()} Unhandled exception during asynchronous execution: {exc}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        logger.critical(f"{LOG_TIME_FORMAT()} Fatal error in backend main: {exc}", exc_info=True)
