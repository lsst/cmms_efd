import sys
import os
import pandas as pd
from nicegui import ui
from config_loader import read_config_from_db
from influx_query import EfdQueryClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def get_measurements_from_db() -> list[str]:
    """Return a sorted list of unique measurements from the configuration database."""
    try:
        configs = read_config_from_db()
        return sorted(set(row['measurement'] for row in configs if row.get('measurement')))
    except Exception as error:
        ui.notify(f'Error reading measurements: {error}', type='negative')
        return []


def get_fields_from_db(measurement: str) -> list[str]:
    """Return a sorted list of fields for a given measurement."""
    try:
        configs = read_config_from_db()
        return sorted(set(row['field'] for row in configs if row.get('measurement') == measurement))
    except Exception as error:
        ui.notify(f'Error reading fields: {error}', type='negative')
        return []


def get_config(measurement: str, field: str) -> dict | None:
    """Return the configuration dictionary for the selected measurement and field."""
    configs = read_config_from_db()
    for row in configs:
        if row.get('measurement') == measurement and row.get('field') == field:
            return row
    return None


def to_ng_columns(columns: list[str]) -> list[dict]:
    """Convert a list of column names to NiceGUI table format."""
    return [{'name': c, 'label': c, 'field': c} for c in columns]


def create_ui() -> None:
    """Render the Send Data to RSP interface using NiceGUI."""
    ui.label('Send Data to RSP').classes('text-h5 text-bold mt-4 mb-4')

    measurement_select = ui.select([], label='Measurement', with_input=True).classes('w-full mb-2')
    field_select = ui.select([], label='Field').classes('w-full mb-2')
    interval_input = ui.input(label='Time Interval (e.g., 24h, 2d, 30d)').classes('w-full mb-2')
    limit_input = ui.input(label='Limit (number of results)').classes('w-full mb-2')

    result_container = ui.column().classes('w-full mt-4')

    async def load_measurements() -> None:
        """Load available measurements from the configuration database."""
        measurements = get_measurements_from_db()
        if not measurements:
            ui.notify('No measurements found in database.', type='warning')
            return
        measurement_select.options = measurements
        ui.notify('Measurements loaded successfully.', type='positive')

    async def load_fields(e) -> None:
        """Load available fields for the selected measurement."""
        fields = get_fields_from_db(e.value)
        field_select.options = fields
        if fields:
            ui.notify(f'Fields loaded for {e.value}', type='positive')
        else:
            ui.notify('No fields found for this measurement.', type='warning')

    measurement_select.on('update:model-value', load_fields)

    async def run_query() -> None:
        """Execute an EFD query based on user-selected parameters."""
        measurement = measurement_select.value
        field = field_select.value
        interval = interval_input.value
        limit = limit_input.value

        if not all([measurement, field, interval, limit]):
            ui.notify('Please fill in all fields before running the query.', type='warning')
            return

        config = get_config(measurement, field)
        if not config:
            ui.notify('No matching configuration found in database.', type='warning')
            return

        site = config.get('site', 'base')
        db_name = config.get('db_name', 'telem')

        try:
            client_efd = EfdQueryClient(site=site, db_name=db_name)
            query = (
                f'SELECT "{field}" FROM "{measurement}" '
                f'WHERE time > now() - {interval} ORDER BY time DESC LIMIT {limit}'
            )
            df = client_efd.query(query)

            result_container.clear()
            if df.empty:
                ui.notify('Query returned no results.', type='info')
            else:
                ui.label('Query Results').classes('text-subtitle1 mt-2 mb-2')
                columns = to_ng_columns(df.columns)
                rows = df.to_dict(orient='records')
                ui.table(columns=columns, rows=rows).classes('w-full')
        except Exception as error:
            ui.notify(f'Query error: {error}', type='negative')

    ui.button('Load Measurements', on_click=load_measurements).classes('mt-2 bg-blue-600 text-white')
    ui.button('Run Query', on_click=run_query).classes('mt-2 bg-green-600 text-white')
