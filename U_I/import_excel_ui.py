from __future__ import annotations

import os
import sys
from typing import List, Dict, Any

import pandas as pd
from dotenv import load_dotenv
from nicegui import ui

from backend.logger_setup import logger, LOG_TIME_FORMAT
from config_loader import read_config_from_db

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()


def import_from_excel(file_path: str) -> pd.DataFrame:
    """
    Load and return data from an Excel file into a DataFrame.

    Parameters
    ----------
    file_path : str
        Path to the Excel file.

    Returns
    -------
    pandas.DataFrame
        DataFrame containing the imported Excel data or an empty DataFrame if import fails.
    """
    try:
        df = pd.read_excel(file_path)
        logger.info(f"{LOG_TIME_FORMAT()} Imported data from Excel file: {file_path}")
        return df
    except Exception as exc:
        ui.notify("Failed to import Excel file.", type="negative")
        logger.error(f"{LOG_TIME_FORMAT()} Excel import failed: {exc}")
        return pd.DataFrame()


def to_ng_columns(columns: List[str]) -> List[Dict[str, str]]:
    """
    Convert DataFrame column names into NiceGUI-compatible table column definitions.

    Parameters
    ----------
    columns : list of str
        Column names to convert.

    Returns
    -------
    list of dict
        NiceGUI table column definitions.
    """
    return [{"name": c, "label": c, "field": c} for c in columns]


def create_ui() -> None:
    """
    Render the Excel import and configuration preview interface.
    """
    ui.label("Import Excel Data").classes("text-h5 text-bold mt-4 mb-2")
    table_container = ui.column().classes("w-full")

    def handle_upload(event: Any) -> None:
        """
        Process the uploaded Excel file and display its preview.

        Parameters
        ----------
        event : Any
            NiceGUI upload event containing file metadata.
        """
        uploaded_file = event.name
        if not uploaded_file:
            ui.notify("No file uploaded.", type="warning")
            return

        try:
            file_path = os.path.join(event.path, uploaded_file)
            df = import_from_excel(file_path)
        except Exception as exc:
            ui.notify("Error reading uploaded file.", type="negative")
            logger.error(f"{LOG_TIME_FORMAT()} Failed to read uploaded file: {exc}")
            return

        if df.empty:
            ui.notify("The uploaded file is empty or invalid.", type="warning")
            return

        table_container.clear()
        ui.label("Imported Excel Data").classes("text-subtitle1 mb-2")

        preview = df.fillna("").head(50)
        columns = [
            col for col in preview.columns
            if col in ("name", "measurement", "field", "attribute")
        ]

        ng_columns = to_ng_columns(columns)
        rows = preview[columns].to_dict(orient="records")

        ui.table(columns=ng_columns, rows=rows).classes("w-full mt-2")
        logger.info(f"{LOG_TIME_FORMAT()} Displayed preview of uploaded Excel data.")

    ui.upload(
        label="Choose an Excel file",
        multiple=False,
        auto_upload=True,
        on_upload=handle_upload,
    ).classes("mt-2 mb-4")

    async def load_from_db() -> None:
        """
        Load and display configuration records stored in the local DB.
        """
        try:
            configs = read_config_from_db()
        except Exception as exc:
            ui.notify("Failed to read local configuration.", type="negative")
            logger.error(f"{LOG_TIME_FORMAT()} Local DB read failed: {exc}")
            return

        if not configs:
            ui.notify("No configurations found in the local database.", type="warning")
            return

        table_container.clear()
        ui.label("Configurations from Database").classes("text-subtitle1 mb-2")

        table_data = [
            {
                "Name": c.get("name", ""),
                "Measurement": c.get("measurement", ""),
                "Field": c.get("field", ""),
                "Attribute": c.get("attribute", ""),
            }
            for c in configs
        ]

        ng_columns = to_ng_columns(list(table_data[0].keys()))
        ui.table(columns=ng_columns, rows=table_data).classes("w-full mt-2")

        logger.info(f"{LOG_TIME_FORMAT()} Displayed {len(table_data)} local DB configurations.")

    ui.button("Load Configurations from DB", on_click=load_from_db).classes(
        "mt-4 bg-blue-600 text-white"
    )
