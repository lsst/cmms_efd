from __future__ import annotations

import os
import sys
from typing import Any, Optional

import pandas as pd
import panel as pn
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.logger_setup import logger, LOG_TIME_FORMAT
from influx_query import EfdQueryClient
from linear_trend import run_linear_trend
from flow_stability import run_flow_sability
from ML_trainer import train_linear_regression
from config_loader import insert_efd_history_point
from incremental_fetcher import IncrementalEfdFetcher

load_dotenv()


def create_predictive_panel() -> pn.Column:
    """
    Create the predictive analysis interface for CDIAT.

    Workflow
    --------
    1. User selects measurement, field and optional SAL index.
    2. User clicks "Fetch EFD History":
         - Data is fetched INCREMENTALLY in 10-day windows.
         - Each batch is saved into SQLite (efd_history).
         - The *last batch* is stored in memory for classical analysis.
    3. User clicks "Run Analysis":
         - Trend/Stability → use last in-memory batch.
         - ML → load full history from SQLite.
    """

    client = EfdQueryClient()

    title = pn.pane.Markdown("### Predictive Analysis Configuration")

    measurement = pn.widgets.Select(name="Measurement", options=[])
    field = pn.widgets.Select(name="Field", options=[])
    sal_input = pn.widgets.TextInput(name="SAL Index (optional)")

    analysis_model = pn.widgets.Select(
        name="Analysis Model",
        options={
            "Linear Trend": "LinearTrend",
            "Flow Stability": "FlowStability",
            "Linear Regression ML": "LinearRegressionML",
        },
        value="LinearTrend",
    )

    data_holder: dict[str, Optional[pd.DataFrame]] = {"df": None}

    def load_measurements(event: Any | None = None) -> None:
        try:
            measurements = client.get_measurements()
            measurement.options = measurements

            if measurements:
                measurement.value = measurements[0]

            logger.info(f"{LOG_TIME_FORMAT()} Measurements loaded.")
        except Exception as exc:
            logger.error(
                f"{LOG_TIME_FORMAT()} Measurement load failed: {exc}",
                exc_info=True,
            )

    def load_fields(event: Any | None = None) -> None:
        if not measurement.value:
            return

        try:
            fields = client.get_fields(measurement.value) or []
            field.options = fields

            if fields:
                field.value = fields[0]

            logger.info(
                f"{LOG_TIME_FORMAT()} Fields loaded for {measurement.value}."
            )
        except Exception as exc:
            logger.error(
                f"{LOG_TIME_FORMAT()} Field load failed: {exc}",
                exc_info=True,
            )

    measurement.param.watch(load_fields, "value")

    def fetch_history(event: Any | None = None) -> None:
        """
        Fetch EFD history incrementally (10-day windows) and store it
        inside `efd_history`. The last window is stored in memory.
        """
        if not measurement.value or not field.value:
            logger.info(f"{LOG_TIME_FORMAT()} Missing measurement or field.")
            return

        raw_sal = sal_input.value.strip()
        sal_index: Optional[int] = int(raw_sal) if raw_sal.isdigit() else None

        try:
            logger.info(
                f"{LOG_TIME_FORMAT()} Starting incremental fetch | "
                f"measurement={measurement.value}, field={field.value}, "
                f"salIndex={sal_index}"
            )

            batches = fetch_incremental_history(
                client=client,
                measurement=measurement.value,
                field=field.value,
                sal_index=sal_index,
                window_days=10,
            )

            if not batches:
                logger.info(
                    f"{LOG_TIME_FORMAT()} No data fetched from EFD."
                )
                return

            last_df = batches[-1]

            for df in batches:
                for _, row in df.iterrows():
                    ts_str = row["timestamp"].isoformat()
                    val = float(row[field.value])
                    insert_efd_history_point(
                        timestamp_utc=ts_str,
                        measurement=measurement.value,
                        field=field.value,
                        value=val,
                        salIndex=sal_index,
                    )

            data_holder["df"] = last_df

            logger.info(
                f"{LOG_TIME_FORMAT()} Incremental fetch completed | "
                f"windows={len(batches)}, last_rows={len(last_df)}"
            )

        except Exception as exc:
            logger.error(
                f"{LOG_TIME_FORMAT()} Incremental fetch failed: {exc}",
                exc_info=True,
            )
            data_holder["df"] = None

    def run_analysis(event: Any | None = None) -> None:
        """
        Run analysis depending on the model selection.
        Trend/Stability → use last in-memory DF.
        ML → use SQLite stored history.
        """
        model_name = analysis_model.value

        try:
            if model_name in ("LinearTrend", "FlowStability"):
                df = data_holder.get("df")

                if df is None or df.empty:
                    logger.info(
                        f"{LOG_TIME_FORMAT()} No data in memory. "
                        f"Run 'Fetch EFD History' first."
                    )
                    return

                if model_name == "LinearTrend":
                    run_linear_trend(df, field.value)

                elif model_name == "FlowStability":
                    run_flow_stability(df, field.value)

            elif model_name == "LinearRegressionML":
                raw_sal = sal_input.value.strip()
                sal_index: Optional[int] = (
                    int(raw_sal) if raw_sal.isdigit() else None
                )

                result = train_linear_regression(
                    measurement=measurement.value,
                    field=field.value,
                    sal_index=sal_index,
                )

                logger.info(f"{LOG_TIME_FORMAT()} ML result: {result}")

            else:
                logger.info(
                    f"{LOG_TIME_FORMAT()} Unknown analysis model."
                )

        except Exception as exc:
            logger.error(
                f"{LOG_TIME_FORMAT()} Analysis execution failed: {exc}",
                exc_info=True,
            )

    load_button = pn.widgets.Button(
        name="Load Measurements",
        button_type="primary",
        width=160,
    )
    load_button.on_click(load_measurements)

    fetch_button = pn.widgets.Button(
        name="Fetch EFD History (Incremental)",
        button_type="primary",
        width=250,
    )
    fetch_button.on_click(fetch_history)

    run_button = pn.widgets.Button(
        name="Run Analysis",
        button_type="success",
        width=160,
    )
    run_button.on_click(run_analysis)

    layout = pn.Column(
        title,
        pn.Row(measurement, field),
        pn.Row(sal_input),
        pn.Row(analysis_model),
        pn.Row(load_button, fetch_button, run_button),
        sizing_mode="stretch_width",
    )

    return layout
