from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np
from sklearn.linear_model import LinearRegression


@dataclass
class LinearRegressionModel:
    """
    Scientific wrapper for a scikit-learn linear regression model.

    This class stores the learned parameters (slope, intercept)
    and provides utilities for:

    - Creating a model from scikit-learn.
    - Reconstructing a model from stored parameters.
    - Converting to a dictionary for JSON storage.
    - Predicting values using either the analytical equation or a
      reconstructed sklearn model.

    Parameters
    ----------
    slope : float
        Estimated coefficient of the linear model.
    intercept : float
        Estimated intercept of the linear model.
    rmse : float
        Root mean square error of the model.
    r2 : float
        Coefficient of determination of the model.
    train_size : int
        Number of samples used during model training.
    """
    slope: float
    intercept: float
    rmse: float
    r2: float
    train_size: int

    @classmethod
    def from_sklearn(
        cls,
        model: LinearRegression,
        rmse: float,
        r2: float,
        train_size: int,
    ) -> "LinearRegressionModel":
        """
        Create a LinearRegressionModel from a fitted sklearn model.

        Parameters
        ----------
        model : LinearRegression
            Fitted sklearn regression model.
        rmse : float
            Root mean square error.
        r2 : float
            Coefficient of determination.
        train_size : int
            Number of samples used in training.

        Returns
        -------
        LinearRegressionModel
        """
        slope = float(model.coef_[0])
        intercept = float(model.intercept_)

        return cls(
            slope=slope,
            intercept=intercept,
            rmse=rmse,
            r2=r2,
            train_size=train_size,
        )

    @classmethod
    def from_params(
        cls,
        slope: float,
        intercept: float,
        rmse: float,
        r2: float,
        train_size: int,
    ) -> "LinearRegressionModel":
        """
        Reconstruct the model from stored parameters.

        This method is used when loading historical models from SQLite.

        Returns
        -------
        LinearRegressionModel
        """
        return cls(
            slope=float(slope),
            intercept=float(intercept),
            rmse=float(rmse),
            r2=float(r2),
            train_size=int(train_size),
        )

    def to_params(self) -> Dict[str, Any]:
        """
        Convert model parameters into a dictionary suitable for JSON storage.

        Returns
        -------
        dict
            Dictionary with slope, intercept, rmse, r2 and train_size.
        """
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "rmse": self.rmse,
            "r2": self.r2,
            "train_size": self.train_size,
        }

    def to_sklearn(self) -> LinearRegression:
        """
        Convert stored parameters into a functional sklearn LinearRegression model.

        Returns
        -------
        LinearRegression
            Reconstructed sklearn model with identical mathematical behavior.
        """
        reg = LinearRegression()
        reg.coef_ = np.array([self.slope], dtype=float)
        reg.intercept_ = float(self.intercept)
        return reg

    def predict(self, x: np.ndarray) -> np.ndarray:
        """
        Predict output values using the analytical linear expression.

        Parameters
        ----------
        x : np.ndarray
            1D feature array.

        Returns
        -------
        np.ndarray
            Predicted values.
        """
        x = np.asarray(x, dtype=float)
        return self.slope * x + self.intercept
