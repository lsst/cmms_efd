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
import logging
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from nicegui import ui

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config_loader import read_config_from_db, insert_config, update_config  # noqa: E402
from influx_query import EfdQueryClient  # noqa: E402

load_dotenv()

AUTH_URL = os.getenv('AUTH_URL')
URL_ASSET_CARD = os.getenv('URL_ASSET_CARD')
CMMS_USERNAME = os.getenv('CMMS_USERNAME')
CMMS_PASSWORD = os.getenv('CMMS_PASSWORD')

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(handler)


def save_entry(entry: Dict[str, Any]) -> None:
    """Persist a configuration by updating when `id` is present, otherwise inserting.

    Parameters
    ----------
    entry : `dict`
        Configuration payload. If it contains a non-null ``id``, the record
        is updated by primary key. Otherwise, a new record is inserted.
        Expected keys: ``id`` (optional), ``name``, ``measurement``, ``field``,
        ``asset_id``, ``attribute``, ``db_name``, ``time_interval``,
        ``salIndex``, ``type_telemetry``.
    """
    try:
        # Prefer update-by-id if provided
        if entry.get('id') is not None:
            update_config(entry)
            ui.notify(f'Configuration updated (ID {entry["id"]}).', type='positive')
            return

        # Fallback: insert when there is no id
        insert_config(entry)
        ui.notify(f'Configuration inserted: {entry.get("name","")}', type='positive')
    except Exception as error:
        ui.notify(f'Error saving configuration: {error}', type='negative')


def create_ui() -> None:
    """Render the New SYS configuration console.

    This interface lets the user:
    - Load EFD measurements and fields.
    - Create a new configuration and save it to the database.
    - Review existing configurations and edit them via a popup dialog.
    """
    ui.label('New SYS Configuration').classes('text-h5 text-bold mt-4 mb-4')

    client = EfdQueryClient()

    with ui.card().classes('w-full p-4 mb-6'):
        ui.label('Create / Update Configuration').classes('text-subtitle1 mb-2')

        name_input = ui.input(label='Descriptive Name').classes('w-full mb-2')
        asset_id_input = ui.input(label='Asset ID').classes('w-full mb-2')
        attribute_input = ui.input(label='Attribute').classes('w-full mb-2')
        db_name_input = ui.input(label='Database Name').classes('w-full mb-2')
        time_interval_input = ui.input(label='Time Interval', value='24h').classes('w-full mb-2')
        sal_index_input = ui.input(label='SAL Index (optional)').classes('w-full mb-2')
        type_telemetry_input = ui.input(label='Telemetry Type').classes('w-full mb-2')

        measurement_select = ui.select(
            options={}, label='Measurement', with_input=True
        ).classes('w-full mb-2')
        field_select = ui.select(
            options=[], label='Field'
        ).classes('w-full mb-2')

        async def load_measurements() -> None:
            """Load EFD measurements into the measurement select.

            Returns
            -------
            None
                Updates the measurement select options.
            """
            ui.notify('Loading measurements...', type='info')
            try:
                measurements = client.get_measurements()
                if not measurements:
                    ui.notify('No measurements found in EFD.', type='warning')
                    return
                measurement_select.options = {m: m for m in measurements}
                measurement_select.update()
                ui.notify(f'{len(measurements)} measurements loaded.', type='positive')
            except Exception as error:
                ui.notify(f'Error loading measurements: {error}', type='negative')

        async def load_fields(_: object = None) -> None:
            """Load fields from EFD for the currently selected measurement.

            Parameters
            ----------
            _ : `object`, optional
                Unused event payload from the model update.

            Returns
            -------
            None
                Updates the field select options.
            """
            measurement = measurement_select.value
            if not measurement:
                ui.notify('Please select a measurement first.', type='warning')
                return
            ui.notify(f'Loading fields for {measurement}...', type='info')
            try:
                fields = client.get_fields(measurement)
                field_select.options = fields or []
                field_select.update()
                ui.notify(f'{len(fields or [])} fields loaded for {measurement}', type='positive')
            except Exception as error:
                ui.notify(f'Error loading fields: {error}', type='negative')

        measurement_select.on('update:model-value', load_fields)

        async def save_current() -> None:
            """Insert a new configuration using the creation form.

            Returns
            -------
            None
                Inserts and refreshes the list below.
            """
            entry = {
                'id': None,
                'name': name_input.value,
                'measurement': measurement_select.value,
                'field': field_select.value,
                'asset_id': asset_id_input.value,
                'attribute': attribute_input.value,
                'db_name': db_name_input.value,
                'time_interval': time_interval_input.value,
                'salIndex': int(sal_index_input.value)
                if sal_index_input.value and sal_index_input.value.isdigit() else None,
                'type_telemetry': type_telemetry_input.value,
            }
            save_entry(entry)
            await refresh_configs()

        with ui.row().classes('gap-3 mt-2'):
            ui.button('Load Measurements', on_click=load_measurements).classes('bg-blue-600 text-white')
            ui.button('Save Configuration', on_click=save_current).classes('bg-green-600 text-white')

    container_configs = ui.column().classes('w-full')

    async def refresh_configs() -> None:
        """Rebuild the saved configurations list with “Edit” popups.

        Queries the local database and renders a simple row-with-button
        list. Each “Edit” opens a dialog with prefilled values.
        """
        try:
            configs: List[Dict[str, Any]] = read_config_from_db()
        except Exception as error:
            container_configs.clear()
            ui.notify(f'Failed to read local DB: {error}', type='negative')
            return

        container_configs.clear()
        ui.label('Saved Configurations').classes('text-h6 mb-2')

        if not configs:
            ui.label('No saved configurations found.').classes('text-caption text-gray-600')
            return

        for cfg in configs:
            # IMPORTANT: cfg must include 'id' from DB.
            if 'id' not in cfg:
                # Without 'id' we cannot update reliably if name changes.
                # Show a warning once and continue rendering the row.
                logger.warning('Config row missing "id": update by PK will not be possible.')
            with container_configs:
                with ui.row().classes('items-center justify-between w-full border-b py-2'):
                    ui.label(
                        f'[{cfg.get("id","?")}] '
                        f'{cfg.get("name","")}  |  '
                        f'{cfg.get("measurement","")}  |  '
                        f'{cfg.get("field","")}'
                    ).classes('text-sm')

                    def open_editor(c: Dict[str, Any] = cfg) -> None:
                        """Open a modal editor prefilled with the selected configuration.

                        Parameters
                        ----------
                        c : `dict`
                            Row from the database with keys including ``id``.
                        """
                        dialog = ui.dialog()
                        with dialog, ui.card().classes('w-[520px] p-4'):
                            ui.label(f'Edit configuration (ID {c.get("id","?")})').classes('text-subtitle1 mb-2')
                            e_name = ui.input(label='Descriptive Name', value=c.get('name', '')).classes('w-full mb-2')
                            e_asset = ui.input(label='Asset ID', value=str(c.get('asset_id', '') or '')).classes('w-full mb-2')
                            e_attr = ui.input(label='Attribute', value=c.get('attribute', '')).classes('w-full mb-2')
                            e_db = ui.input(label='Database Name', value=c.get('db_name', '')).classes('w-full mb-2')
                            e_tint = ui.input(label='Time Interval', value=c.get('time_interval', '24h')).classes('w-full mb-2')
                            e_sal = ui.input(label='SAL Index (optional)', value=str(c.get('salIndex', '') or '')).classes('w-full mb-2')
                            e_type = ui.input(label='Telemetry Type', value=c.get('type_telemetry', '')).classes('w-full mb-2')
                            e_meas = ui.select(
                                options={c.get('measurement', ''): c.get('measurement', '')},
                                label='Measurement',
                                with_input=True,
                                value=c.get('measurement', '')
                            ).classes('w-full mb-2')

                            e_field = ui.select(
                                options=[c.get('field', '')] if c.get('field') else [],
                                label='Field',
                                value=c.get('field', '')
                            ).classes('w-full mb-2')

                            async def dlg_load_meas() -> None:
                                """Populate the measurement select inside the dialog.

                                Returns
                                -------
                                None
                                    Updates measurement options in place.
                                """
                                ui.notify('Loading measurements...', type='info')
                                try:
                                    mlist = client.get_measurements()
                                    if not mlist:
                                        ui.notify('No measurements found in EFD.', type='warning')
                                        return
                                    e_meas.options = {m: m for m in mlist}
                                    e_meas.update()
                                    ui.notify(f'{len(mlist)} measurements loaded.', type="positive")
                                except Exception as err:
                                    ui.notify(f'Error loading measurements: {err}', type='negative')

                            async def dlg_load_fields(_: object = None) -> None:
                                """Populate the field select based on the dialog's measurement.

                                Parameters
                                ----------
                                _ : `object`, optional
                                    Unused event payload.

                                Returns
                                -------
                                None
                                    Updates field options in place.
                                """
                                meas = e_meas.value
                                if not meas:
                                    ui.notify('Please select a measurement first.', type='warning')
                                    return
                                ui.notify(f'Loading fields for {meas}...', type='info')
                                try:
                                    flist = client.get_fields(meas)
                                    e_field.options = flist or []
                                    e_field.update()
                                    ui.notify(f'{len(flist or [])} fields loaded.', type='positive')
                                except Exception as err:
                                    ui.notify(f'Error loading fields: {err}', type='negative')

                            e_meas.on('update:model-value', dlg_load_fields)

                            async def apply_edit() -> None:
                                """Update the selected configuration using its primary key.

                                Returns
                                -------
                                None
                                    Saves data, closes the dialog, refreshes the list.
                                """
                                payload = {
                                    'id': c.get('id'),
                                    'name': e_name.value,
                                    'measurement': e_meas.value,
                                    'field': e_field.value,
                                    'asset_id': e_asset.value,
                                    'attribute': e_attr.value,
                                    'db_name': e_db.value,
                                    'time_interval': e_tint.value,
                                    'salIndex': int(e_sal.value) if e_sal.value and e_sal.value.isdigit() else None,
                                    'type_telemetry': e_type.value,
                                }
                                save_entry(payload)
                                dialog.close()
                                await refresh_configs()

                            with ui.row().classes('justify-end gap-2 mt-1'):
                                ui.button('Load Measurements', on_click=dlg_load_meas).classes('bg-blue-600 text-white')
                                ui.button('Save Changes', on_click=apply_edit).classes('bg-green-600 text-white')
                                ui.button('Cancel', on_click=lambda: dialog.close()).classes('bg-gray-200')

                        dialog.open()

                    ui.button('Edit', on_click=open_editor).classes('bg-amber-600 text-white')

    ui.timer(0.1, refresh_configs, once=True)
