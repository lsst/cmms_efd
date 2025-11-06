import os
import requests
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from nicegui import ui

load_dotenv()

AUTH_URL = os.getenv('AUTH_URL')
USERNAME = os.getenv('CMMS_USERNAME')
PASSWORD = os.getenv('CMMS_PASSWORD')
BASE_URL = os.getenv('URL_CREATE_PM_INSTANCE')


def get_token() -> str | None:
    """Authenticate against CMMS and return a token, or None on failure."""
    credentials = {'username': USERNAME, 'password': PASSWORD}
    try:
        response = requests.post(AUTH_URL, json=credentials, verify=False)
        response.raise_for_status()
        return response.json().get('data', {}).get('_id')
    except Exception as error:
        ui.notify(f'Error obtaining token: {error}', type='negative')
        return None


def fetch_all_instances(token: str) -> list[dict]:
    """Fetch all maintenance order instances from CMMS."""
    headers = {'CMDBuild-Authorization': token}
    try:
        response = requests.get(BASE_URL, headers=headers, verify=False)
        response.raise_for_status()
        return response.json().get('data', [])
    except Exception as error:
        ui.notify(f'Error fetching instances: {error}', type='negative')
        return []


def fetch_activity_data(token: str, activity_id: str) -> dict:
    """Fetch details for a given maintenance activity."""
    url = f'{BASE_URL}/{activity_id}'
    headers = {'CMDBuild-Authorization': token}
    try:
        response = requests.get(url, headers=headers, verify=False)
        response.raise_for_status()
        return response.json().get('data', {})
    except Exception as error:
        ui.notify(f'Error fetching activity: {error}', type='negative')
        return {}


def extract_register_notes(register_html: str) -> list[str]:
    """Extract 'notes' text from CMMS Register HTML content."""
    if not register_html:
        return []
    soup = BeautifulSoup(register_html, 'html.parser')
    return [span.get_text(strip=True) for span in soup.select("span[data-block='notes']")]


def create_ui() -> None:
    """Render the Data Catcher interface using NiceGUI."""
    ui.label('Data Catcher').classes('text-h5 text-bold mt-4 mb-2')

    token = get_token()
    if not token:
        ui.notify('Authentication failed — cannot continue.', type='negative')
        return

    instances = fetch_all_instances(token)
    if not instances:
        ui.notify('No maintenance orders found.', type='warning')
        return

    options_map = {
        inst.get('Description', f"ID {inst.get('_id')}"): inst.get('_id')
        for inst in instances
    }

    selected_orders = ui.select(
        options=list(options_map.keys()),
        label='Select Maintenance Orders',
        multiple=True,
        with_input=True,
    ).classes('w-full mt-2')

    result_container = ui.column().classes('w-full mt-4')

    async def run_fetch() -> None:
        """Fetch notes from selected maintenance activities and display results."""
        result_container.clear()
        selected_descriptions = selected_orders.value or []
        if not selected_descriptions:
            ui.notify('Please select at least one order.', type='warning')
            return

        for desc in selected_descriptions:
            act_id = options_map.get(desc)
            if not act_id:
                continue

            result_container.add(ui.separator())
            result_container.add(ui.label(f'Activity ID: {act_id}').classes('text-bold'))

            data = fetch_activity_data(token, act_id)

            # Notes (direct field)
            notes_direct = data.get('Notes')
            result_container.add(ui.label('Notes (Direct)').classes('text-subtitle2 mt-2'))
            result_container.add(ui.label(notes_direct if notes_direct else 'None'))

            # Notes (parsed from HTML register)
            register_html = data.get('Register')
            notes_register = extract_register_notes(register_html)
            result_container.add(ui.label('Notes (From Register)').classes('text-subtitle2 mt-2'))
            if notes_register:
                for note in notes_register:
                    result_container.add(ui.label(f'- {note}'))
            else:
                result_container.add(ui.label('None'))

    ui.button('Run', on_click=run_fetch).classes('mt-3 bg-blue-600 text-white')
