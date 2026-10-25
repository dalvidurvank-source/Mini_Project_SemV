from __future__ import annotations

from typing import Optional, Any

import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller
RAW_REQUIRED = [
    "State Name",
    "District Name",
    "Market Name",
    "Variety",
    "Group",
    "Arrivals (Tonnes)",
    "Min Price (Rs./Quintal)",
    "Max Price (Rs./Quintal)",
    "Modal Price (Rs./Quintal)",
    "Reported Date",
]

MODEL_COLUMNS = [
    "wholesale_price",
    "arrival_volume",
]


DEFAULT_MAX_LAGS = 12
MAX_MISSING_FRACTION = 0.15

def load_mandi_csv(path: str) -> pd.DataFrame:
    """
    Load and validate the raw mandi CSV.

    Parameters
    ----------
    path : str
        Path to the CSV file.

    Returns
    -------
    pandas.DataFrame
        Loaded raw mandi dataset.
    """

    try:
        df = pd.read_csv(path)

    except UnicodeDecodeError:
        df = pd.read_csv(
            path,
            encoding="latin1"
        )

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
    )

    missing = [
        column
        for column in RAW_REQUIRED
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Missing required columns:\n"
            + "\n".join(
                f"  - {column}"
                for column in missing
            )
        )

    return df



def clean_mandi_data(
    df: pd.DataFrame,
    state: Optional[str] = None,
    market: Optional[str] = None,
    variety: Optional[str] = None,
) -> pd.DataFrame:
    """
    Clean the raw mandi dataset.

    Operations:
        - clean text fields
        - parse dates
        - convert price/arrival columns to numeric
        - remove invalid observations
        - filter state/market/variety
        - remove duplicates
        - sort chronologically

    The CSV is commodity-specific, e.g. Tomato.csv,
    so no Commodity column is required.
    """

    data = df.copy()

    data.columns = (
        data.columns
        .astype(str)
        .str.strip()
    )

    missing_columns = [
        column for column in RAW_REQUIRED if column not in data.columns
    ]
    if missing_columns:
        raise ValueError(
            "Missing required columns:\n"
            + "\n".join(f"  - {column}" for column in missing_columns)
        )

    text_columns = [
        "State Name",
        "District Name",
        "Market Name",
        "Variety",
        "Group",
    ]

    for column in text_columns:

        data[column] = (
            data[column]
            .astype("string")
            .str.strip()
        )


    # Large commodity exports repeat the same dates across many mandis.
    # Parse each distinct value once while preserving first-value format inference.
    unique_dates = data["Reported Date"].drop_duplicates()
    parsed_dates = pd.to_datetime(
        unique_dates,
        dayfirst=True,
        errors="coerce"
    )
    data["Reported Date"] = data["Reported Date"].map(
        pd.Series(parsed_dates.to_numpy(), index=unique_dates)
    )

    

    numeric_columns = [
        "Arrivals (Tonnes)",
        "Min Price (Rs./Quintal)",
        "Max Price (Rs./Quintal)",
        "Modal Price (Rs./Quintal)",
    ]

    for column in numeric_columns:

        if pd.api.types.is_numeric_dtype(data[column]) and not pd.api.types.is_bool_dtype(data[column]):
            # read_csv already inferred native numeric values; text cleanup would
            # allocate millions of unnecessary strings before converting back.
            data[column] = pd.to_numeric(data[column], errors="coerce")
            continue

        data[column] = pd.to_numeric(
            data[column]
            .astype("string")
            .str.replace(
                ",",
                "",
                regex=False
            )
            .str.replace(
                "₹",
                "",
                regex=False
            )
            .str.strip(),
            errors="coerce"
        )

    data = data.dropna(
        subset=[
            "Reported Date",
            "Arrivals (Tonnes)",
            "Modal Price (Rs./Quintal)",
        ]
    )

    data = data[
        data["Reported Date"].notna()
        & np.isfinite(data["Arrivals (Tonnes)"])
        & np.isfinite(data["Modal Price (Rs./Quintal)"])
        & (data["Arrivals (Tonnes)"] >= 0)
        & (data["Modal Price (Rs./Quintal)"] > 0)
    ].copy()

    # --------------------------------------------------------
    # Filter state
    # --------------------------------------------------------

    if state is not None:

        data = data[
            data["State Name"]
            .str.lower()
            ==
            state.strip().lower()
        ]


    if market is not None:

        data = data[
            data["Market Name"]
            .str.lower()
            ==
            market.strip().lower()
        ]

    # --------------------------------------------------------
    # Filter variety
    # --------------------------------------------------------

    if variety is not None:

        data = data[
            data["Variety"]
            .str.lower()
            ==
            variety.strip().lower()
        ]

    # --------------------------------------------------------
    # Remove duplicates and sort
    # --------------------------------------------------------

    data = (
        data
        .drop_duplicates()
        .sort_values("Reported Date")
        .reset_index(drop=True)
    )

    if data.empty:

        raise ValueError(
            "No observations remain after filtering. "
            "Check state, market and variety values."
        )

    return data


# ============================================================
# FIND DENSE MARKETS
# ============================================================

def find_dense_markets(
    df: pd.DataFrame,
    min_months: int = 60,
    min_coverage: float = 0.70,
    top_n: int = 10,
) -> pd.DataFrame:
    """
    Find state/market/variety combinations with sufficient
    historical monthly coverage.

    This prevents selecting an extremely sparse market series.
    """

    data = df.copy()

    data["Reported Date"] = pd.to_datetime(
        data["Reported Date"],
        dayfirst=True,
        errors="coerce"
    )

    data = data.dropna(
        subset=["Reported Date"]
    )

    data["month"] = (
        data["Reported Date"]
        .dt.to_period("M")
    )

    # --------------------------------------------------------
    # Count observed months per market
    # --------------------------------------------------------

    coverage = (
        data
        .groupby(
            [
                "State Name",
                "Market Name",
                "Variety",
            ]
        )["month"]
        .nunique()
        .reset_index(
            name="observed_months"
        )
    )

    # --------------------------------------------------------
    # Determine full date range
    # --------------------------------------------------------

    min_month = data["month"].min()
    max_month = data["month"].max()

    total_months = (
        max_month.ordinal
        - min_month.ordinal
        + 1
    )

    coverage[
        "total_possible_months"
    ] = total_months

    coverage[
        "coverage_ratio"
    ] = (
        coverage["observed_months"]
        /
        coverage["total_possible_months"]
    )

    # --------------------------------------------------------
    # Filter sufficiently dense series
    # --------------------------------------------------------

    coverage = coverage[
        (coverage["observed_months"] >= min_months)&(coverage["coverage_ratio"] >= min_coverage)]

    coverage = coverage.sort_values(
        [
            "coverage_ratio",
            "observed_months",
        ],
        ascending=False
    )

    return coverage.head(top_n)


# ============================================================
# CREATE MONTHLY SERIES
# ===========================================================

def create_monthly_series(
    cleaned: pd.DataFrame,
    minimum_observations: int = 12,
) -> pd.DataFrame:
    """
    Convert irregular mandi observations into monthly data.

    wholesale_price:
        Arrival-weighted monthly Modal Price.

    Formula:

        sum(ModalPrice * Arrival)
        ------------------------
             sum(Arrival)

    arrival_volume:
        Total monthly arrivals.

    Multiple valid daily observations within a month are combined using
    arrival-weighted modal price. Missing months remain absent; they are not
    created or treated as zero-price observations.

    minimum_observations:
        Minimum number of observed months required in the returned series.
    """

    data = cleaned.copy()

    # --------------------------------------------------------
    # Make sure numeric types are correct
    # --------------------------------------------------------

    data["Arrivals (Tonnes)"] = pd.to_numeric(
        data["Arrivals (Tonnes)"],
        errors="coerce"
    )

    data["Modal Price (Rs./Quintal)"] = pd.to_numeric(
        data["Modal Price (Rs./Quintal)"],
        errors="coerce"
    )

    data["Reported Date"] = pd.to_datetime(
        data["Reported Date"],
        dayfirst=True,
        errors="coerce",
    )
    data = data.dropna(
        subset=[
            "Reported Date",
            "Arrivals (Tonnes)",
            "Modal Price (Rs./Quintal)",
        ]
    )
    data = data[
        np.isfinite(data["Arrivals (Tonnes)"])
        & np.isfinite(data["Modal Price (Rs./Quintal)"])
        & (data["Arrivals (Tonnes)"] >= 0)
        & (data["Modal Price (Rs./Quintal)"] > 0)
    ].drop_duplicates()

    if minimum_observations < 0:
        raise ValueError("minimum_observations must not be negative.")


    data["month"] = (
        data["Reported Date"]
        .dt.to_period("M")
    )

    # --------------------------------------------------------
    # Arrival-weighted price
    # --------------------------------------------------------

    data["weighted_price"] = (
        data["Modal Price (Rs./Quintal)"].astype(float)
        *
        data["Arrivals (Tonnes)"].astype(float)
    )

    # --------------------------------------------------------
    # Aggregate
    # --------------------------------------------------------

    monthly = (
        data
        .groupby("month", as_index=True)
        .agg(
            weighted_price_sum=(
                "weighted_price",
                "sum"
            ),
            arrival_volume=(
                "Arrivals (Tonnes)",
                "sum"
            ),
        )
    )

    # --------------------------------------------------------
    # Calculate weighted monthly wholesale price
    # --------------------------------------------------------

    monthly["wholesale_price"] = np.where(
        monthly["arrival_volume"] > 0,
        (
            monthly["weighted_price_sum"]
            /
            monthly["arrival_volume"]
        ),
        np.nan
    )

    monthly = monthly[
        [
            "wholesale_price",
            "arrival_volume",
        ]
    ].copy()

    # --------------------------------------------------------
    # Convert PeriodIndex -> Timestamp index
    # --------------------------------------------------------

    monthly.index = (
        monthly.index.to_timestamp()
    )

    monthly.index.name = "date"

    # --------------------------------------------------------
    # Force numerical dtype
    # --------------------------------------------------------

    monthly["wholesale_price"] = (
        pd.to_numeric(
            monthly["wholesale_price"],
            errors="coerce"
        )
        .astype(np.float64)
    )

    monthly["arrival_volume"] = (
        pd.to_numeric(
            monthly["arrival_volume"],
            errors="coerce"
        )
        .astype(np.float64)
    )

    monthly = monthly.replace(
        [np.inf, -np.inf],
        np.nan
    )

    monthly = monthly.dropna()

    if len(monthly) < minimum_observations:

        raise ValueError(
            f"Fewer than {minimum_observations} monthly observations are available."
        )

    return monthly


# ============================================================
# REGULARIZE MONTHLY DATA
# ============================================================

def regularize_monthly_series(
    monthly: pd.DataFrame,
    max_missing_fraction: float = MAX_MISSING_FRACTION,
) -> pd.DataFrame:
    """
    Make monthly observations equally spaced.

    Only a small amount of missing data is interpolated.
    Large gaps are rejected.
    """

    if monthly.empty:

        raise ValueError(
            "Monthly data is empty."
        )

    monthly = (
        monthly
        .copy()
    )
    original_count = len(monthly)
    monthly.index = (
        pd.to_datetime(monthly.index)
        .to_period("M")
        .to_timestamp()
    )
    monthly = monthly.sort_index()

    # --------------------------------------------------------
    # Full monthly calendar
    # --------------------------------------------------------

    full_index = pd.date_range(
        start=monthly.index.min().to_period("M").to_timestamp(),
        end=monthly.index.max().to_period("M").to_timestamp(),
        freq="MS",
    )

    regular = monthly.reindex(
        full_index
    )

    regular.index.name = "date"

    # --------------------------------------------------------
    # Missing fraction
    # --------------------------------------------------------

    missing_mask = (
        regular[MODEL_COLUMNS]
        .isna()
        .any(axis=1)
    )

    missing_fraction = (
        missing_mask.mean()
    )

    if (
        missing_fraction
        >
        max_missing_fraction
    ):

        raise ValueError(
            f"{missing_fraction:.1%} of monthly "
            f"observations are missing. "
            f"Maximum allowed is "
            f"{max_missing_fraction:.1%}."
        )

    # --------------------------------------------------------
    # Interpolate missing months
    # --------------------------------------------------------

    regular["wholesale_price"] = (
        regular["wholesale_price"]
        .interpolate(
            method="time"
        )
        .ffill()
        .bfill()
    )

    regular["arrival_volume"] = (
        regular["arrival_volume"]
        .interpolate(
            method="linear"
        )
        .ffill()
        .bfill()
    )

    # --------------------------------------------------------
    # Force numerical types again
    # --------------------------------------------------------

    regular["wholesale_price"] = (
        pd.to_numeric(
            regular["wholesale_price"],
            errors="coerce"
        )
        .astype(np.float64)
        .clip(lower=0)
    )

    regular["arrival_volume"] = (
        pd.to_numeric(
            regular["arrival_volume"],
            errors="coerce"
        )
        .astype(np.float64)
        .clip(lower=0)
    )

    regular.index = pd.DatetimeIndex(regular.index)
    regular = regular.asfreq("MS")

    regular = regular.replace([np.inf, -np.inf], np.nan)

    if regular[MODEL_COLUMNS].isna().any().any():

        raise ValueError(
            "Missing or invalid values remain after monthly regularization."
        )

    if not np.isfinite(
        regular[MODEL_COLUMNS].to_numpy(dtype=np.float64)
    ).all():
        raise ValueError(
            "Non-finite values remain after monthly regularization."
        )

    regularized_count = len(regular)
    if original_count != regularized_count:
        print(
            f"Regularized monthly series: "
            f"{original_count} observed months -> "
            f"{regularized_count} monthly periods"
        )

    return regular


# ============================================================
# ADF STATIONARITY TEST
# ============================================================

def adf_test(
    series: pd.Series,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """
    Perform the Augmented Dickey-Fuller test.

    H0:
        The series is non-stationary.

    Decision:
        p-value < alpha -> stationary.
    """

    s = (
        pd.to_numeric(
            series,
            errors="coerce"
        )
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
        .dropna()
        .astype(np.float64)
    )

    if len(s) < 8:

        return {
            "adf_statistic": np.nan,
            "p_value": np.nan,
            "stationary": False,
            "reason": "Too few observations",
        }

    if s.nunique() <= 1:

        return {
            "adf_statistic": np.nan,
            "p_value": 0.0,
            "stationary": True,
            "reason": "Constant series",
        }

    try:

        result = adfuller(
            s.to_numpy(
                dtype=np.float64
            ),
            autolag="AIC",
            result_object=False,
        )

    except Exception as exc:

        return {
            "adf_statistic": np.nan,
            "p_value": np.nan,
            "stationary": False,
            "reason": f"ADF failed: {exc}",
        }

    return {
        "adf_statistic": float(
            result[0]
        ),
        "p_value": float(
            result[1]
        ),
        "stationary": bool(
            result[1] < alpha
        ),
        "reason": "",
    }


# PREPARE DATA FOR VAR

def _prepare_monthly_input(
    historical_data: pd.DataFrame,
) -> pd.DataFrame:
    """Normalize raw or prepared monthly data to the VAR input shape."""

    if set(MODEL_COLUMNS).issubset(historical_data.columns):

        monthly = historical_data.copy()

        if "date" in monthly.columns:

            monthly["date"] = pd.to_datetime(
                monthly["date"],
                errors="coerce"
            )
            monthly = monthly.set_index("date")

        monthly.index = pd.to_datetime(monthly.index)
        monthly = regularize_monthly_series(monthly[MODEL_COLUMNS])
        return monthly

    cleaned = clean_mandi_data(historical_data)
    monthly = create_monthly_series(cleaned)
    return regularize_monthly_series(monthly)


def _require_non_negative_finite(
    series: pd.Series,
    variable_name: str,
) -> pd.Series:
    """Validate values before any log transform."""

    converted = pd.to_numeric(
        series,
        errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)

    if converted.isna().any():
        raise ValueError(
            f"{variable_name} contains NaN or invalid values."
        )

    if not np.isfinite(converted.to_numpy(dtype=np.float64)).all():
        raise ValueError(
            f"{variable_name} contains NaN or infinite values."
        )

    if (converted < 0).any():
        raise ValueError(
            f"{variable_name} contains negative values and cannot be log-transformed."
        )

    return converted.astype(np.float64)


def prepare_for_var(
    monthly: pd.DataFrame,
    alpha: float = 0.05,
    transform_log: bool = False,
):
    """
    Prepare the VAR variables after stationarity testing.

    For VAR_LOG, the endogenous variables are log1p-transformed before
    stationarity testing. Only variables that remain non-stationary are
    differenced.
    """

    data = (
        monthly[MODEL_COLUMNS]
        .copy()
        .sort_index()
    )

    data.index = pd.to_datetime(data.index)
    data = regularize_monthly_series(data)

    data = (
        data
        .apply(pd.to_numeric, errors="coerce")
        .astype(np.float64)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    if transform_log:

        for column in MODEL_COLUMNS:
            data[column] = _require_non_negative_finite(
                data[column],
                column,
            )
            data[column] = np.log1p(data[column])

    diagnostics = {
        column: adf_test(
            data[column],
            alpha
        )
        for column in MODEL_COLUMNS
    }

    transformed = pd.DataFrame(index=data.index)
    differenced_columns = []
    transformed_columns = []

    for column in MODEL_COLUMNS:

        if transform_log:
            transformed_columns.append(column)

        if diagnostics[column]["stationary"]:
            transformed[column] = data[column]
        else:
            transformed[column] = data[column].diff()
            differenced_columns.append(column)

    transformed = (
        transformed
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
        .astype(np.float64)
    )

    transformed.index = pd.DatetimeIndex(transformed.index)
    transformed = transformed.asfreq("MS")

    if len(transformed) < 20:
        raise ValueError(
            "Too few observations remain after "
            "stationarity transformation."
        )

    last_levels = data.iloc[-1].copy()

    return (
        transformed,
        differenced_columns,
        last_levels,
        diagnostics,
        transformed_columns,
    )

# Add after prepare_for_var()

def _validate_var_matrix(model_data: pd.DataFrame) -> pd.DataFrame:
    """Clean and validate the matrix before VAR estimation."""

    data = model_data.copy()

    if not isinstance(data.index, pd.DatetimeIndex):
        data.index = pd.to_datetime(data.index)

    data = data.sort_index()

    if data.index.has_duplicates:
        raise ValueError("VAR input contains duplicate dates.")

    for column in data.columns:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data = data.replace([np.inf, -np.inf], np.nan)
    data.index = pd.DatetimeIndex(data.index)
    data = data.asfreq("MS")

    nan_counts = data.isna().sum()
    if nan_counts.any():
        bad = nan_counts[nan_counts > 0]
        raise ValueError(
            "VAR input contains NaN values after preprocessing: "
            f"{bad.to_dict()}. "
            f"Rows={len(data)}, "
            f"Date range={data.index.min()} to {data.index.max()}"
        )

    if len(data) < 20:
        raise ValueError(
            f"Too few observations for VAR fitting: {len(data)}"
        )

    values = data.to_numpy(dtype=np.float64)

    if not np.isfinite(values).all():
        raise ValueError("VAR input contains non-finite values.")

    std = data.std(ddof=0)

    constant_columns = std[std <= 1e-12].index.tolist()

    if constant_columns:
        raise ValueError(
            "VAR input contains near-constant columns: "
            f"{constant_columns}"
        )

    return data


def _standardize_var_matrix(
    model_data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Standardize variables before least-squares estimation.

    This improves numerical conditioning when wholesale_price and
    arrival_volume have very different scales.
    """

    data = _validate_var_matrix(model_data)

    means = data.mean()
    scales = data.std(ddof=0)

    if (scales <= 1e-12).any():
        bad = scales[scales <= 1e-12].index.tolist()
        raise ValueError(
            f"Cannot standardize near-constant VAR variables: {bad}"
        )

    scaled = (data - means) / scales

    if not np.isfinite(scaled.to_numpy(dtype=np.float64)).all():
        raise ValueError(
            "Standardization produced NaN or infinite VAR values."
        )

    return scaled.astype(np.float64), means, scales

# VAR Lag Selection

def choose_lag_order(
    model_data: pd.DataFrame,
    p_lags: Optional[int] = None,
    max_lags: int = DEFAULT_MAX_LAGS,
    standardize: bool = True,
) -> int:
    """
    Select VAR lag order using AIC.

    Individual numerically unstable lag candidates are skipped.
    The input is validated before any Statsmodels/LAPACK operation.
    """

    data = _validate_var_matrix(model_data)

    n = len(data)
    k = data.shape[1]

    if p_lags is not None:
        if not isinstance(p_lags, int) or p_lags < 1:
            raise ValueError("p_lags must be a positive integer.")

        if n <= p_lags + k + 2:
            raise ValueError(
                f"Insufficient observations ({n}) for VAR lag {p_lags}."
            )

        return p_lags

    if standardize:
        data, _, _ = _standardize_var_matrix(data)

    safe_max = min(
        max_lags,
        max(1, (n - 1) // (k + 2))
    )

    candidates: list[tuple[float, int]] = []
    fit_errors: list[str] = []

    for lag in range(1, safe_max + 1):
        try:
            model = VAR(data)
            fitted = model.fit(lag)

            aic = float(fitted.aic)

            if not np.isfinite(aic):
                fit_errors.append(
                    f"VAR({lag}): non-finite AIC"
                )
                continue

            candidates.append((aic, lag))

        except (
            np.linalg.LinAlgError,
            ValueError,
            FloatingPointError,
        ) as exc:
            fit_errors.append(
                f"VAR({lag}): {exc}"
            )
            continue

    if not candidates:
        detail = fit_errors[-1] if fit_errors else "unknown numerical failure"
        raise ValueError(
            "No numerically stable VAR model could be fitted. "
            f"Tried VAR(1) through VAR({safe_max}). "
            f"Last error: {detail}"
        )

    candidates.sort(key=lambda item: (item[0], item[1]))

    return candidates[0][1]


# ============================================================
# FIT VAR
# ============================================================

def fit_var(
    model_data: pd.DataFrame,
    p_lags: int,
    standardize: bool = True,
):
    """
    Fit a Statsmodels VAR model after numerical validation.

    standardize=True is the default for standalone fitting.
    The final forecasting path passes already-standardized data with
    standardize=False so the forecast can be transformed back correctly.
    """

    data = _validate_var_matrix(model_data)

    if standardize:
        data, _, _ = _standardize_var_matrix(data)

    if len(data) <= p_lags + 2:
        raise ValueError(
            "Not enough observations for the selected VAR lag."
        )

    try:
        model = VAR(data)

        return model.fit(
            p_lags,
            trend="c",
        )

    except (
        np.linalg.LinAlgError,
        ValueError,
        FloatingPointError,
    ) as exc:
        raise ValueError(
            f"VAR({p_lags}) fitting failed: {exc}"
        ) from exc


# ============================================================
# RESTORE ORIGINAL PRICE SCALE
# ============================================================

def restore_forecast_scale(
    forecast: np.ndarray,
    last_levels: pd.Series,
    differenced_columns: list[str] | bool,
    transform_log: bool = False,
) -> np.ndarray:
    """
    Restore forecasts to the original scale for both the level and log models.
    """

    restored = np.asarray(forecast, dtype=np.float64).copy()

    if restored.ndim == 1:
        restored = restored.reshape(1, -1)

    if isinstance(differenced_columns, bool):
        columns_to_restore = list(MODEL_COLUMNS) if differenced_columns else []
    else:
        columns_to_restore = list(differenced_columns)

    last = last_levels.reindex(MODEL_COLUMNS).to_numpy(dtype=np.float64)

    if last.shape[0] != restored.shape[1]:
        raise ValueError(
            "Forecast width does not match the endogenous variable set."
        )

    if not np.isfinite(last).all():
        raise ValueError(
            "Last series values contain NaN or infinite entries."
        )

    for index, column in enumerate(MODEL_COLUMNS):

        if column in columns_to_restore:
            restored[:, index] = last[index] + np.cumsum(restored[:, index])

        if transform_log:
            restored[:, index] = np.expm1(restored[:, index])

    if not np.isfinite(restored).all():
        raise ValueError(
            "Forecast reconstruction produced NaN or infinite values."
        )

    return restored


# ============================================================
# FIT AND FORECAST A SINGLE MODEL CONFIGURATION
# ============================================================

def _fit_and_forecast_model(
    monthly_data: pd.DataFrame,
    p_lags: Optional[int] = None,
    transform_log: bool = False,
    steps: int = 1,
) -> dict[str, Any]:
    """
    Prepare a model configuration, condition the numerical input,
    fit the VAR, recursively forecast one or more steps, restore the original scale,
    and return the result.
    """

    monthly = (
        monthly_data[MODEL_COLUMNS]
        .copy()
        .sort_index()
    )
    monthly = regularize_monthly_series(monthly)

    (
        model_data,
        differenced_columns,
        last_levels,
        stationarity,
        transformed_columns,
    ) = prepare_for_var(
        monthly,
        transform_log=transform_log,
    )

    # Numerical conditioning before Statsmodels/LAPACK.
    conditioned_data, scale_mean, scale_std = _standardize_var_matrix(
        model_data
    )

    lag = choose_lag_order(
        conditioned_data,
        p_lags=p_lags,
        standardize=False,
    )

    fitted_model = fit_var(
        conditioned_data,
        lag,
        standardize=False,
    )

    if not isinstance(steps, int) or not 1 <= steps <= 3:
        raise ValueError("steps must be an integer from 1 through 3.")

    forecast_scaled = fitted_model.forecast(
        conditioned_data.values[-lag:],
        steps=steps,
    )

    # Return from standardized space to the transformed VAR space.
    forecast = (
        forecast_scaled * scale_std.to_numpy()
        + scale_mean.to_numpy()
    )

    restored = restore_forecast_scale(
        forecast,
        last_levels,
        differenced_columns,
        transform_log=transform_log,
    )

    predicted_price = max(
        0.0,
        float(restored[0, 0]),
    )

    if not np.isfinite(predicted_price):
        raise ValueError(
            "Forecasted wholesale price is not finite."
        )

    return {
        "model_data": model_data,
        "conditioned_model_data": conditioned_data,
        "differenced_columns": differenced_columns,
        "last_transformed_levels": last_levels.copy(),
        "transformed_columns": transformed_columns,
        "stationarity": stationarity,
        "lag": int(lag),
        "forecast_scaled": forecast_scaled,
        "forecast": forecast,
        "restored_forecast": restored,
        "predicted_price": predicted_price,
        "predicted_prices": [max(0.0, float(value)) for value in restored[:, 0]],
        "predicted_arrivals": [max(0.0, float(value)) for value in restored[:, 1]],
    }


# ============================================================
# FORECAST BASE PRICE
# ============================================================

def predict_base_price(
    historical_data: pd.DataFrame,
    p_lags: Optional[int] = None,
) -> float:
    """Predict the next-period wholesale price using the selected validation winner."""

    monthly = _prepare_monthly_input(historical_data)

    level_report = _evaluate_single_model(
        monthly,
        p_lags=p_lags,
        test_size=0.20,
        transform_log=False,
    )
    log_report = _evaluate_single_model(
        monthly,
        p_lags=p_lags,
        test_size=0.20,
        transform_log=True,
    )

    selected_model = _select_best_model(level_report, log_report)
    selected_lag = level_report["lag"] if selected_model == "VAR_LEVEL" else log_report["lag"]
    selected_forecast = _fit_and_forecast_model(
        monthly,
        p_lags=selected_lag,
        transform_log=(selected_model == "VAR_LOG"),
    )

    return float(selected_forecast["predicted_price"])


def _select_best_model(
    level_report: dict[str, Any],
    log_report: dict[str, Any],
) -> str:
    """Choose the final VAR model using MAE as the primary objective."""

    candidates = {
        "VAR_LEVEL": level_report["metrics"],
        "VAR_LOG": log_report["metrics"],
    }

    best_name = "VAR_LEVEL"
    best_mae = candidates[best_name]["MAE"]
    best_rmse = candidates[best_name]["RMSE"]

    for model_name in ["VAR_LOG"]:
        mae = candidates[model_name]["MAE"]
        rmse = candidates[model_name]["RMSE"]
        if mae < best_mae - 1e-12:
            best_name = model_name
            best_mae = mae
            best_rmse = rmse
        elif abs(mae - best_mae) <= 1e-9 and rmse < best_rmse:
            best_name = model_name
            best_mae = mae
            best_rmse = rmse

    return best_name


def _evaluate_single_model(
    monthly_raw: pd.DataFrame,
    p_lags: Optional[int] = None,
    test_size: float | int = 0.20,
    transform_log: bool = False,
) -> dict[str, Any]:
    """Perform rolling one-step evaluation for one VAR variant."""

    monthly_raw = monthly_raw[MODEL_COLUMNS].copy().sort_index()

    if len(monthly_raw) < 24:
        raise ValueError(
            "At least 24 observed monthly records are recommended for evaluation."
        )

    if isinstance(test_size, float):
        if not (0 < test_size < 1):
            raise ValueError("Float test_size must be between 0 and 1.")
        n_test = max(1, int(np.ceil(len(monthly_raw) * test_size)))
    elif isinstance(test_size, int) and test_size > 0:
        n_test = test_size
    else:
        raise ValueError("test_size must be a positive integer or a fraction between 0 and 1.")

    if len(monthly_raw) - n_test < 18:
        raise ValueError("Training history is too small for VAR evaluation.")

    model_data_full, differenced_columns_full, _, diagnostics_full, transformed_columns_full = prepare_for_var(
        monthly_raw,
        transform_log=transform_log,
    )
    full_lag = choose_lag_order(model_data_full, p_lags=p_lags)

    test_dates = monthly_raw.index[-n_test:]
    actual_values = []
    predicted_values = []
    naive_values = []
    valid_dates = []

    for target_date in test_dates:
        history = monthly_raw[monthly_raw.index < target_date].copy()
        if history.empty:
            continue

        naive_prediction = float(history["wholesale_price"].iloc[-1])

        try:
            history_regular = regularize_monthly_series(history)
            model_fit = _fit_and_forecast_model(
                history_regular,
                p_lags=full_lag,
                transform_log=transform_log,
            )
            prediction = model_fit["predicted_price"]
            actual = float(monthly_raw.loc[target_date, "wholesale_price"])

            if np.isfinite(prediction) and np.isfinite(actual) and np.isfinite(naive_prediction):
                predicted_values.append(prediction)
                naive_values.append(naive_prediction)
                actual_values.append(actual)
                valid_dates.append(target_date)
        except (TypeError, ValueError):
            continue

    if len(actual_values) < 5:
        raise ValueError("Too few valid test predictions were produced.")

    actual = np.asarray(actual_values, dtype=np.float64)
    predicted = np.asarray(predicted_values, dtype=np.float64)
    naive = np.asarray(naive_values, dtype=np.float64)

    model_mae, model_rmse, model_mape = _error_metrics(actual, predicted)
    naive_mae, naive_rmse, naive_mape = _error_metrics(actual, naive)

    comparison = pd.DataFrame(
        {
            "actual_wholesale_price": actual,
            "predicted_wholesale_price": predicted,
            "naive_price": naive,
        },
        index=pd.DatetimeIndex(valid_dates),
    )

    metrics = {
        "MAE": model_mae,
        "RMSE": model_rmse,
        "MAPE": model_mape,
        "lag": int(full_lag),
    }

    naive_metrics = {
        "MAE": naive_mae,
        "RMSE": naive_rmse,
        "MAPE": naive_mape,
    }

    return {
        "metrics": metrics,
        "naive_metrics": naive_metrics,
        "comparison": comparison,
        "differenced_columns": differenced_columns_full,
        "transformed_columns": transformed_columns_full,
        "stationarity": diagnostics_full,
        "lag": int(full_lag),
    }


def evaluate_var(
    monthly_raw: pd.DataFrame,
    p_lags: Optional[int] = None,
    test_size: float | int = 0.20,
    transform_log: bool = False,
):
    """Backward-compatible wrapper for evaluating the baseline level VAR model."""

    result = _evaluate_single_model(
        monthly_raw,
        p_lags=p_lags,
        test_size=test_size,
        transform_log=transform_log,
    )
    return result["metrics"], result["comparison"]


def _error_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
) -> tuple[float, float, float]:
    """
    Compute MAE, RMSE and MAPE for one-step errors.
    """

    actual = np.asarray(actual, dtype=np.float64)
    predicted = np.asarray(predicted, dtype=np.float64)

    if actual.shape != predicted.shape:
        raise ValueError("Actual and predicted arrays must have the same shape.")

    if actual.size == 0:
        raise ValueError("Cannot compute metrics from an empty prediction set.")

    error = actual - predicted
    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(error ** 2)))

    nonzero = actual != 0
    if np.any(nonzero):
        mape = float(np.mean(np.abs(error[nonzero] / actual[nonzero])) * 100)
    else:
        mape = float("nan")

    return mae, rmse, mape


# ============================================================
# MODEL REPORT
# ============================================================

def get_model_report(
    historical_data: pd.DataFrame,
    p_lags: Optional[int] = None,
    test_size: float | int = 0.20,
) -> dict[str, Any]:
    """Generate a complete AgroLink VAR model report with both level and log variants."""

    monthly_raw = _prepare_monthly_input(historical_data)

    var_level = _evaluate_single_model(
        monthly_raw,
        p_lags=p_lags,
        test_size=test_size,
        transform_log=False,
    )
    var_log = _evaluate_single_model(
        monthly_raw,
        p_lags=p_lags,
        test_size=test_size,
        transform_log=True,
    )

    common_dates = sorted(set(var_level["comparison"].index) & set(var_log["comparison"].index))
    comparison = pd.DataFrame(
        {
            "actual_wholesale_price": monthly_raw.loc[common_dates, "wholesale_price"],
            "var_level_prediction": var_level["comparison"].loc[common_dates, "predicted_wholesale_price"],
            "var_log_prediction": var_log["comparison"].loc[common_dates, "predicted_wholesale_price"],
            "naive_price": var_level["comparison"].loc[common_dates, "naive_price"],
        }
    )
    comparison.index.name = "date"

    evaluation = {
        "VAR_LEVEL": {
            "MAE": var_level["metrics"]["MAE"],
            "RMSE": var_level["metrics"]["RMSE"],
            "MAPE": var_level["metrics"]["MAPE"],
            "lag": var_level["lag"],
        },
        "VAR_LOG": {
            "MAE": var_log["metrics"]["MAE"],
            "RMSE": var_log["metrics"]["RMSE"],
            "MAPE": var_log["metrics"]["MAPE"],
            "lag": var_log["lag"],
        },
        "NAIVE": {
            "MAE": var_level["naive_metrics"]["MAE"],
            "RMSE": var_level["naive_metrics"]["RMSE"],
            "MAPE": var_level["naive_metrics"]["MAPE"],
        },
    }

    selected_model = _select_best_model(var_level, var_log)
    selected_lag = var_level["lag"] if selected_model == "VAR_LEVEL" else var_log["lag"]
    selected_forecast = _fit_and_forecast_model(
        monthly_raw,
        p_lags=selected_lag,
        transform_log=(selected_model == "VAR_LOG"),
    )

    return {
        "selected_model": selected_model,
        "selected_lag": selected_lag,
        "transformed_variables": selected_forecast["transformed_columns"],
        "differenced_variables": selected_forecast["differenced_columns"],
        "last_transformed_levels": selected_forecast["last_transformed_levels"],
        "stationarity": selected_forecast["stationarity"],
        "evaluation": evaluation,
        "metrics": evaluation,
        "predicted_base_price": float(selected_forecast["predicted_price"]),
        "comparison": comparison,
        "monthly_data": monthly_raw,
        "var_level": var_level,
        "var_log": var_log,
        "selected_forecast": selected_forecast,
    }


# ============================================================
# ACTUAL VS PREDICTED PLOT
# ============================================================

def plot_actual_vs_predicted(
    comparison: pd.DataFrame,
) -> None:
    """Display actual vs predicted wholesale prices across all trend series."""

    try:
        import matplotlib
        matplotlib.use("Agg", force=True)
        import matplotlib.pyplot as plt
    except ImportError:
        print("\nMatplotlib is not installed. Install it using: pip install matplotlib")
        return

    plt.figure(figsize=(12, 5))
    plt.plot(comparison.index, comparison["actual_wholesale_price"], label="Actual")
    plt.plot(comparison.index, comparison["var_level_prediction"], label="VAR_LEVEL")
    plt.plot(comparison.index, comparison["var_log_prediction"], label="VAR_LOG")
    if "naive_price" in comparison.columns:
        plt.plot(comparison.index, comparison["naive_price"], label="Naive")
    plt.xlabel("Date")
    plt.ylabel("Wholesale Price (INR/Quintal)")
    plt.title("Tomato VAR: Actual vs Predicted Wholesale Price")
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    output_path = "tomato_var_comparison.png"
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"\nSaved comparison plot to: {output_path}")


# ============================================================
# MAIN
# ============================================================
    
if __name__ == "__main__":
    CSV_PATH = "data/Tomato.csv"
    raw = load_mandi_csv(
        CSV_PATH
    )

    print(
        "\n========================================"
    )

    print(
        "TOMATO VAR FORECASTING"
    )

    print(
        "========================================"
    )

    print(
        "Tomato dataset loaded successfully"
    )

    parsed_dates = pd.to_datetime(
        raw["Reported Date"],
        dayfirst=True,
        errors="coerce",
    )

    print(
        "raw observation count:",
        len(raw)
    )

    print(
        "raw date range:",
        parsed_dates.min(),
        "to",
        parsed_dates.max()
    )

    # ========================================================
    # 2. FIND DENSE MARKETS
    # ========================================================

    dense_markets = find_dense_markets(
        raw,
        min_months=60,
        min_coverage=0.70,
        top_n=10
    )

    if dense_markets.empty:

        raise ValueError(
            "No tomato market has at least "
            "60 observed months and 70% coverage."
        )

    print(
        "\ntop dense market candidates:"
    )

    print(
        dense_markets.to_string(
            index=False
        )
    )

    # ========================================================
    # 3. SELECT BEST MARKET
    # ========================================================

    best_market = (
        dense_markets.iloc[0]
    )

    STATE = str(
        best_market[
            "State Name"
        ]
    )

    MARKET = str(
        best_market[
            "Market Name"
        ]
    )

    VARIETY = str(
        best_market[
            "Variety"
        ]
    )

    coverage = float(
        best_market[
            "coverage_ratio"
        ]
    )

    print(
        "\nselected state:",
        STATE
    )

    print(
        "selected market:",
        MARKET
    )

    print(
        "selected variety:",
        VARIETY
    )

    print(
        "coverage:",
        f"{coverage:.2%}"
    )

    # ========================================================
    # 4. CLEAN SELECTED MARKET
    # ========================================================

    cleaned = clean_mandi_data(
        raw,
        state=STATE,
        market=MARKET,
        variety=VARIETY
    )

    print(
        "\nFiltered raw observations:",
        len(cleaned)
    )

    # ========================================================
    # 5. MONTHLY AGGREGATION
    # ========================================================

    monthly_raw = create_monthly_series(
        cleaned
    )

    print(
        "\nmonthly observation count:",
        len(monthly_raw)
    )

    # ========================================================
    # 6. REGULARIZE FINAL MODEL SERIES
    # ========================================================

    monthly_model = regularize_monthly_series(
        monthly_raw
    )

    print(
        "monthly date range:",
        monthly_raw.index.min().date(),
        "to",
        monthly_raw.index.max().date()
    )

    print(
        "monthly model observations after "
        "regularization:",
        len(monthly_model)
    )

    latest_monthly_obs = monthly_model.iloc[-1]
    print(
        "\nLatest monthly observation:",
        monthly_model.index[-1],
        "wholesale_price=INR",
        f"{float(latest_monthly_obs['wholesale_price']):.2f}",
        "arrival_volume=",
        f"{float(latest_monthly_obs['arrival_volume']):.2f}",
        "tonnes",
    )

    # ========================================================
    # 7. DISPLAY LATEST 12 MONTHS
    # ========================================================

    print(
        "\nLatest 12 months:"
    )

    print(
        monthly_model.tail(12).to_string()
    )

    # ========================================================
    # 8. MODEL REPORT
    # Evaluation uses monthly_raw so interpolation
    # never sees future test months.
    # ========================================================

    report = get_model_report(
        monthly_raw,
        p_lags=None,
        test_size=0.20,
    )

    var_level = report["var_level"]
    var_log = report["var_log"]
    level_metrics = var_level["metrics"]
    log_metrics = var_log["metrics"]
    naive_metrics = var_level["naive_metrics"]
    selected_model = report["selected_model"]
    selected_lag = report["selected_lag"]
    last_observed_price = float(monthly_raw["wholesale_price"].iloc[-1])

    var_level_full = _fit_and_forecast_model(
        monthly_raw,
        p_lags=level_metrics["lag"],
        transform_log=False,
    )
    var_log_full = _fit_and_forecast_model(
        monthly_raw,
        p_lags=log_metrics["lag"],
        transform_log=True,
    )

    selected_forecast = var_level_full if selected_model == "VAR_LEVEL" else var_log_full
    final_base_price = float(selected_forecast["predicted_price"])
    percentage_change = 100.0 * (final_base_price - last_observed_price) / last_observed_price if last_observed_price != 0 else float("nan")

    print("\nselected Tomato market:", MARKET)
    print("coverage:", f"{coverage:.2%}")
    print("\nADF results:")
    for name, result in report["stationarity"].items():
        p_value = result["p_value"]
        p_text = "NA" if pd.isna(p_value) else f"{float(p_value):.6f}"
        print(f"    {name}: p={p_text}, stationary={result['stationary']}")

    print("\nVAR_LEVEL lag:", level_metrics["lag"])
    print("VAR_LOG lag:", log_metrics["lag"])

    print("\nVAR_LEVEL metrics:")
    print(f"    MAE : {level_metrics['MAE']:.4f}")
    print(f"    RMSE: {level_metrics['RMSE']:.4f}")
    print(f"    MAPE: {level_metrics['MAPE']:.4f}")

    print("\nVAR_LOG metrics:")
    print(f"    MAE : {log_metrics['MAE']:.4f}")
    print(f"    RMSE: {log_metrics['RMSE']:.4f}")
    print(f"    MAPE: {log_metrics['MAPE']:.4f}")

    print("\nNaive metrics:")
    print(f"    MAE : {naive_metrics['MAE']:.4f}")
    print(f"    RMSE: {naive_metrics['RMSE']:.4f}")
    print(f"    MAPE: {naive_metrics['MAPE']:.4f}")

    print("\nselected final model:", selected_model)
    print("selected final lag:", selected_lag)
    print("final forecast model:", selected_model)
    print("final forecast lag:", selected_forecast["lag"])
    print("last observed price:", f"INR {last_observed_price:.2f}")
    print("VAR_LEVEL full-history forecast:", f"INR {var_level_full['predicted_price']:.2f}")
    print("VAR_LOG full-history forecast:", f"INR {var_log_full['predicted_price']:.2f}")
    print("Final VAR Base Price:", f"INR {final_base_price:.2f}")
    print("Percentage change:", f"{percentage_change:.4f}%")

    print("\nActual vs Predicted wholesale prices:")
    print(report["comparison"].to_string())

    plot_actual_vs_predicted(report["comparison"])
