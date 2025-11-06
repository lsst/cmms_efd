from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from nicegui import ui

from backend.logger_setup import logger, LOG_TIME_FORMAT
from config_loader import read_config_from_db

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()

ASSET_ENDPOINT = os.getenv("CMMS_ASSET_ENDPOINT")
USERNAME = os.getenv("CMMS_USERNAME")
PASSWORD = os.getenv("CMMS_PASSWORD")
AUTH_URL = os.getenv("AUTH_URL")


def get_token() -> Optional[str]:
    """
    Authenticate to CMMS and return an access token.

    Returns
    -------
    str or None
        Authentication token if successful, otherwise None.
    """
    if not AUTH_URL or not USERNAME or not PASSWORD:
        ui.notify("Authentication configuration missing (.env)", type="negative")
        logger.error(f"{LOG_TIME_FORMAT()} Missing authentication environment variables.")
        return None

    try:
        response = requests.post(
            AUTH_URL,
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10,
            verify=False,
        )
        response.raise_for_status()
        token = response.json().get("data", {}).get("_id")

        if not token:
            ui.notify("Authentication succeeded but no token returned.", type="warning")
            logger.warning(f"{LOG_TIME_FORMAT()} Token missing in CMMS authentication response.")
            return None

        logger.info(f"{LOG_TIME_FORMAT()} CMMS authentication successful.")
        return token

    except Exception as exc:
        ui.notify("Authentication failed", type="negative")
        logger.error(f"{LOG_TIME_FORMAT()} CMMS authentication failed: {exc}")
        return None


def get_asset_details(token: str, asset_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve asset data from CMMS.

    Parameters
    ----------
    token : str
        CMMS authorization token.
    asset_id : str
        Identifier of the requested CMMS asset.

    Returns
    -------
    dict or None
        Asset details.
    """
    try:
        url = f"{ASSET_ENDPOINT.rstrip('/')}/{asset_id}"
        headers = {
            "Content-Type": "application/json",
            "CMDBuild-Authorization": token,
        }

        response = requests.get(url, headers=headers, timeout=10, verify=False)
        response.raise_for_status()

        return response.json().get("data", {})

    except Exception as exc:
        logger.warning(f"{LOG_TIME_FORMAT()} Failed to retrieve asset {asset_id}: {exc}")
        return None


def extract_attribute(details: Dict[str, Any], attribute: str) -> str:
    """
    Safely extract an attribute value from an asset record.

    Parameters
    ----------
    details : dict
        CMMS asset record.
    attribute : str
        Target attribute name.

    Returns
    -------
    str
        Extracted value or "N/A" if not available.
    """
    if not details:
        return "N/A"

    # Exact key match preferred
    if attribute in details:
        return str(details[attribute])

    # Case-insensitive fallback
    for key, value in details.items():
        if key.lower() == attribute.lower():
            return str(value)

    return "N/A"


def create_ui() -> None:
    """
    Render the CMMS asset viewer UI.
    """
    ui.label("CMMS Assets Viewer").classes("text-h5 text-bold mt-4 mb-2")
    container = ui.column().classes("w-full")

    async def load_assets() -> None:
        """
        Load asset data and update the UI display.
        """
        token = get_token()
        if not token:
            return

        try:
            configs = read_config_from_db()
        except Exception as exc:
            ui.notify("Failed to read local configuration.", type="negative")
            logger.error(f"{LOG_TIME_FORMAT()} Failed local config read: {exc}")
            return

        if not configs:
            ui.notify("No configured assets found.", type="warning")
            return

        rows: List[Dict[str, str]] = []
        for entry in configs:
            asset_id = entry.get("asset_id")
            name = entry.get("name", "")
            attribute = entry.get("attribute", "")

            details = get_asset_details(token, str(asset_id))
            value = extract_attribute(details, attribute)

            rows.append(
                {
                    "ID": str(asset_id),
                    "Name": name,
                    "Attribute": attribute,
                    "CMMS Value": value,
                }
            )

        if not rows:
            ui.notify("Data retrieval finished but no rows to display.", type="warning")
            return

        columns = [{"name": col, "label": col, "field": col} for col in rows[0].keys()]

        container.clear()
        ui.table(columns=columns, rows=rows).classes("w-full mt-4")

        logger.info(f"{LOG_TIME_FORMAT()} Asset table updated with {len(rows)} rows.")

    ui.button("Load Assets", on_click=load_assets).classes("mt-3 bg-blue-600 text-white")
