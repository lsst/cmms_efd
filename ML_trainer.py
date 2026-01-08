from __future__ import annotations

from typing import Optional, Dict, Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from backend.logger_setup import logger, LOG_TIME_FORMAT
from config_loader import (
    init_ml_storage,
    save_ml_linear_model,
    load_latest_ml_linear_model,
    fetch_efd_history,
)
from linear_regression_model import LinearRegressionModel

R2_MIN_ACCEPT: float = 0.30
RMSE_MIN_IMPROVEMENT: float = 1.0e-6
SLOPE_MIN_ABS: float = 1.0e-10
MIN_SAMPLES: int = 5


def compute_rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Compute the Root Mean Square Error (RMSE).

    Parameters
    ----------
    y_true : numpy.ndarray
        Ground-truth values.
    y_pred : numpy.ndarray
        Predicted values.

    Returns
    -------
    float
        RMSE value.
    """
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def compute_r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Compute the coefficient of determination R².

    Parameters
    ----------
    y_true : numpy.ndarray
        Ground-truth values.
    y_pred : numpy.ndarray
        Model predictions.

    Returns
    -------
    float
        R² coefficient.
    """
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))

    if ss_tot == 0.0:
        return 0.0

    return float(1.0 - ss_res / ss_tot)


def _build_dataframe_from_history(
    measurement: str,
    field: str,
    sal_index: Optional[int],
) -> Optional[pd.DataFrame]:
    """
    Build a DataFrame from the telemetry history stored in SQLite.

    Parameters
    ----------
    measurement : str
        EFD measurement name.
    field : str
        Telemetry field name.
    sal_index : int or None
        Optional SAL index.

    Returns
    -------
    pandas.DataFrame or None
        Cleaned DataFrame ready for training, or None if not enough data.
    """
    history = fetch_efd_history(
        measurement=measurement,
        field=field,
        salIndex=sal_index,
    )

    if not history:
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: no history in efd_history for "
            f"{measurement}.{field}[{sal_index}]",
        )
        return None

    df = pd.DataFrame(history)

    if df.empty or "timestamp_utc" not in df.columns or "value" not in df.columns:
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: invalid history structure for "
            f"{measurement}.{field}[{sal_index}]",
        )
        return None

    df["timestamp_utc"] = pd.to_datetime(
        df["timestamp_utc"],
        utc=True,
        errors="coerce",
    )
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    df = df.dropna(subset=["timestamp_utc", "value"])

    if df.empty:
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: no valid samples after cleaning for "
            f"{measurement}.{field}[{sal_index}]",
        )
        return None

    df = df.sort_values("timestamp_utc")

    return df


def _prepare_training_arrays(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """
    Prepare feature and target arrays from the cleaned DataFrame.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame with columns ``timestamp_utc`` and ``value``.

    Returns
    -------
    tuple of numpy.ndarray
        Tuple (x_values, y_values) where x_values are time in seconds
        since the first timestamp and y_values are the numeric telemetry
        values.
    """
    t0 = df["timestamp_utc"].min()
    df["t_sec"] = (df["timestamp_utc"] - t0).dt.total_seconds()

    x_values = df["t_sec"].astype(float).values
    y_values = df["value"].astype(float).values

    return x_values, y_values


def train_linear_regression(
    measurement: str,
    field: str,
    sal_index: Optional[int] = None,
) -> Optional[LinearRegressionModel]:
    """
    Train a linear regression model using the full historical dataset.

    This function performs a complete machine learning cycle:

    1. Load all historical data for (measurement, field, sal_index)
       from the SQLite database.
    2. Clean and validate the dataset.
    3. Build the time axis in seconds from the first timestamp.
    4. Fit a scikit-learn LinearRegression model.
    5. Compute RMSE and R².
    6. Load the previously active model for the same signal, if any.
    7. Compare the new model against the previous one.
    8. Persist a new version only if it improves according to the
       defined thresholds.

    Parameters
    ----------
    measurement : str
        EFD measurement name.
    field : str
        Telemetry field name.
    sal_index : int or None
        Optional SAL index for disambiguating signals.

    Returns
    -------
    LinearRegressionModel or None
        The accepted model instance (either new or previous). Returns
        None when the available data are not sufficient to train a model.
    """
    init_ml_storage()

    df = _build_dataframe_from_history(
        measurement=measurement,
        field=field,
        sal_index=sal_index,
    )

    if df is None:
        return None

    x_values, y_values = _prepare_training_arrays(df)

    if x_values.size < MIN_SAMPLES:
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: insufficient samples "
            f"({x_values.size}<{MIN_SAMPLES}) for "
            f"{measurement}.{field}[{sal_index}]",
        )
        return None

    logger.info(
        f"{LOG_TIME_FORMAT()} ML: training window | samples={x_values.size}, "
        f"measurement={measurement}, field={field}, salIndex={sal_index}",
    )

    x_matrix = x_values.reshape(-1, 1)

    previous_info: Optional[Dict[str, Any]] = load_latest_ml_linear_model(
        measurement=measurement,
        field=field,
        salIndex=sal_index,
    )

    previous_model: Optional[LinearRegressionModel]
    if previous_info is not None:
        previous_model = LinearRegressionModel.from_params(
            slope=previous_info["slope"],
            intercept=previous_info["intercept"],
            rmse=previous_info["rmse"],
            r2=previous_info["r2"],
            train_size=previous_info["train_size"],
        )
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: loaded previous model | "
            f"version={previous_info['version']}, "
            f"slope={previous_model.slope:.6e}, "
            f"intercept={previous_model.intercept:.6e}, "
            f"r2={previous_model.r2:.6f}, rmse={previous_model.rmse:.6f}",
        )
    else:
        previous_model = None
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: no previous model for "
            f"{measurement}.{field}[{sal_index}]",
        )

    logger.info(
        f"{LOG_TIME_FORMAT()} ML: training scikit-learn LinearRegression "
        f"for {measurement}.{field}[{sal_index}]",
    )
    regressor = LinearRegression()
    regressor.fit(x_matrix, y_values)

    y_pred_new = regressor.predict(x_matrix)
    new_rmse = compute_rmse(y_values, y_pred_new)
    new_r2 = compute_r2(y_values, y_pred_new)

    new_model = LinearRegressionModel.from_sklearn(
        model=regressor,
        rmse=new_rmse,
        r2=new_r2,
        train_size=x_values.size,
    )

    logger.info(
        f"{LOG_TIME_FORMAT()} ML: new model parameters | "
        f"slope={new_model.slope:.6e}, intercept={new_model.intercept:.6e}, "
        f"r2={new_model.r2:.6f}, rmse={new_model.rmse:.6f}",
    )

    if abs(new_model.slope) < SLOPE_MIN_ABS:
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: slope too small "
            f"(|slope|<{SLOPE_MIN_ABS:.1e}), skipping save",
        )
        return previous_model if previous_model is not None else new_model

    if new_model.r2 < R2_MIN_ACCEPT:
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: R² below threshold "
            f"({new_model.r2:.3f}<{R2_MIN_ACCEPT:.2f}), skipping save",
        )
        return previous_model if previous_model is not None else new_model

    if previous_model is not None:
        y_pred_old = previous_model.predict(x_values)
        old_rmse = compute_rmse(y_values, y_pred_old)
        old_r2 = compute_r2(y_values, y_pred_old)

        logger.info(
            f"{LOG_TIME_FORMAT()} ML: previous model metrics | "
            f"r2={old_r2:.6f}, rmse={old_rmse:.6f}",
        )

        rmse_improvement = old_rmse - new_model.rmse
        logger.info(
            f"{LOG_TIME_FORMAT()} ML: RMSE improvement={rmse_improvement:.6f}",
        )

        if rmse_improvement <= RMSE_MIN_IMPROVEMENT:
            logger.info(
                f"{LOG_TIME_FORMAT()} ML: new model rejected "
                f"(improvement <= {RMSE_MIN_IMPROVEMENT:.1e}), "
                f"keeping previous version",
            )
            return previous_model

    params = new_model.to_params()

    save_ml_linear_model(
        measurement=measurement,
        field=field,
        salIndex=sal_index,
        slope=new_model.slope,
        intercept=new_model.intercept,
        rmse=new_model.rmse,
        r2=new_model.r2,
        train_size=new_model.train_size,
        params=params,
    )

    logger.info(
        f"{LOG_TIME_FORMAT()} ML: new model accepted and saved for "
        f"{measurement}.{field}[{sal_index}]",
    )

    return new_model
