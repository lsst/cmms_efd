#!/usr/bin/env python3
import sys
import os
from nicegui import ui

# Local imports
import newSYS
import import_excel_ui
import send_rsp_ui
import asset_table
import log_viewer
import plot_interface_catcher

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def create_ui() -> None:
    """Build the main CMMS Integration UI with deferred (lazy) tab loading."""
    ui.label('CMMS Integration UI').classes('text-h4 text-bold mt-4 mb-6')

    # Tabs definition
    with ui.tabs().classes('w-full') as tabs:
        tab_sys = ui.tab('New SYS')
        tab_excel = ui.tab('Import Excel')
        tab_rsp = ui.tab('Send Data RSP')
        tab_assets = ui.tab('Asset Table')
        tab_monitor = ui.tab('Monitoring Data')
        tab_plot = ui.tab('Plot Catcher')

    # Tab panels container
    with ui.tab_panels(tabs, value=tab_sys).classes('w-full mt-2') as panels:
        panels_dict = {}

        def make_lazy_panel(tab, title, loader_func):
            """Helper to create panels that load only when activated."""
            with ui.tab_panel(tab) as panel:
                ui.label(f'{title} (click "Load" to initialize)').classes('text-h6 mb-2')
                container = ui.column().classes('mt-3')
                ui.button('Load', on_click=lambda: load_tab_content(container, loader_func, title)).classes(
                    'bg-blue-600 text-white mt-2'
                )
                panels_dict[tab] = container
       
        loaded_tabs = set()
       
        def load_tab_content(container, loader_func, tab_name: str) -> None:
            """Safely load UI content inside container (avoiding re-renders)."""
            
            if tab_name in loaded_tabs:
                ui.notify(f'{tab_name} already loaded.', type='info')
                return
            
            container.clear()

            try:
                loader_func()
                loaded_tabs.add(tab_name)
            except Exception as e:
                ui.notify(f'Error loading tab: {e}', type='negative')

        # Define each lazy-loaded tab
        make_lazy_panel(tab_sys, 'New SYS', newSYS.create_ui)
        make_lazy_panel(tab_excel, 'Import Excel', import_excel_ui.create_ui)
        make_lazy_panel(tab_rsp, 'Send Data RSP', send_rsp_ui.create_ui)
        make_lazy_panel(tab_assets, 'Asset Table', asset_table.create_ui)
        make_lazy_panel(tab_monitor, 'Monitoring Data', log_viewer.create_ui)
        make_lazy_panel(tab_plot, 'Plot Catcher', plot_interface_catcher.create_ui)

    ui.run(title='CMMS Integration UI', port=8501, reload=False)


if __name__ == '__main__':
    create_ui()
