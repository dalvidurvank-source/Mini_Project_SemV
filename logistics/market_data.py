"""Load and summarize observed tomato mandi prices for Nashik."""

from math import isfinite
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = (
    PROJECT_ROOT / "data" / "processed" / "tomato_nashik_available_data.csv"
)
REQUIRED_COLUMNS = (
    "t",
    "cmdty",
    "market_id",
    "market_name",
    "state_id",
    "state_name",
    "district_id",
    "district_name",
    "variety",
    "p_min",
    "p_max",
    "p_modal",
)
PRICE_COLUMNS = ("p_min", "p_max", "p_modal")
EXPECTED_NAMES = {
    "cmdty": "tomato",
    "state_name": "maharashtra",
    "district_name": "nashik",
}


def _format_invalid_records(
    data: pd.DataFrame,
    invalid_rows: pd.Series,
    columns: tuple[str, ...],
) -> str:
    """Format invalid CSV data-row numbers and their relevant values."""
    details = []
    for index in data.index[invalid_rows]:
        values = ", ".join(f"{column}={data.at[index, column]!r}" for column in columns)
        details.append(f"CSV data row {index + 2} ({values})")
    return "; ".join(details)


def load_market_data(csv_path: str | Path | None = None) -> pd.DataFrame:
    """Load and validate the observed Tomato prices for Nashik, Maharashtra.

    The default CSV path is resolved from the project root, independent of the
    current working directory. A custom path can be supplied for other datasets
    or tests. Returned dates and price columns are parsed to datetime and
    numeric types, respectively.
    """
    source_path = Path(csv_path) if csv_path is not None else DEFAULT_DATA_PATH
    data = pd.read_csv(source_path)

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in data]
    if missing_columns:
        raise ValueError(
            "Market data CSV is missing required columns: "
            + ", ".join(missing_columns)
        )
    if data.empty:
        raise ValueError(
            "Market data CSV contains no records; expected Tomato observations "
            "for Nashik, Maharashtra."
        )

    invalid_name_details = []
    for column, expected_name in EXPECTED_NAMES.items():
        normalized_names = data[column].astype("string").str.strip().str.casefold()
        invalid_rows = normalized_names.ne(expected_name).fillna(True)
        if invalid_rows.any():
            invalid_name_details.append(
                f"{column} expected {expected_name!r}: "
                f"{_format_invalid_records(data, invalid_rows, (column,))}"
            )
    if invalid_name_details:
        raise ValueError(
            "Market data must contain only Tomato records from Nashik, "
            "Maharashtra. "
            + "; ".join(invalid_name_details)
        )

    parsed_dates = pd.to_datetime(data["t"], errors="coerce")
    invalid_dates = parsed_dates.isna()
    if invalid_dates.any():
        raise ValueError(
            "Market data contains invalid dates in 't': "
            + _format_invalid_records(data, invalid_dates, ("t",))
        )
    data["t"] = parsed_dates

    invalid_numeric_details = []
    for column in PRICE_COLUMNS:
        raw_prices = data[column]
        numeric_prices = pd.to_numeric(raw_prices, errors="coerce")
        invalid_prices = numeric_prices.isna()
        if invalid_prices.any():
            invalid_numeric_details.append(
                f"{column}: "
                + _format_invalid_records(data, invalid_prices, (column,))
            )
        else:
            data[column] = numeric_prices
    if invalid_numeric_details:
        raise ValueError(
            "Market prices must be numeric. "
            + "; ".join(invalid_numeric_details)
        )

    non_finite_prices = data[list(PRICE_COLUMNS)].apply(
        lambda column: ~column.map(isfinite)
    ).any(axis=1)
    if non_finite_prices.any():
        raise ValueError(
            "Market prices must be finite: "
            + _format_invalid_records(data, non_finite_prices, PRICE_COLUMNS)
        )

    negative_prices = (data[list(PRICE_COLUMNS)] < 0).any(axis=1)
    invalid_order = ~(
        (data["p_min"] <= data["p_modal"]) & (data["p_modal"] <= data["p_max"])
    )
    price_errors = []
    if negative_prices.any():
        price_errors.append(
            "prices must be nonnegative: "
            + _format_invalid_records(data, negative_prices, PRICE_COLUMNS)
        )
    if invalid_order.any():
        price_errors.append(
            "prices must satisfy p_min <= p_modal <= p_max: "
            + _format_invalid_records(data, invalid_order, PRICE_COLUMNS)
        )
    if price_errors:
        raise ValueError("Invalid market prices. " + "; ".join(price_errors))

    return data


def summarize_market_data(data: pd.DataFrame) -> dict[str, int | pd.Timestamp]:
    """Return record, market, observed-date, and date-range statistics."""
    return {
        "total_records": len(data),
        "unique_markets": int(data["market_id"].nunique()),
        "unique_observed_dates": int(data["t"].nunique()),
        "earliest_date": data["t"].min(),
        "latest_date": data["t"].max(),
    }


def summarize_monthly_prices(data: pd.DataFrame) -> pd.DataFrame:
    """Aggregate recorded modal-price observations by calendar month.

    This reports an aggregate of available market observations, not a complete
    daily price series. Missing dates are not generated or filled.

    The returned frame has ``month`` (YYYY-MM), ``average_modal_price``,
    ``observation_count``, and ``unique_markets`` columns. An observation is one
    input record; market counts are distinct ``market_id`` values in that month.
    """
    monthly_data = data.assign(month=data["t"].dt.to_period("M").astype(str))
    return (
        monthly_data.groupby("month", as_index=False, sort=True)
        .agg(
            average_modal_price=("p_modal", "mean"),
            observation_count=("p_modal", "size"),
            unique_markets=("market_id", "nunique"),
        )
        .loc[
            :,
            [
                "month",
                "average_modal_price",
                "observation_count",
                "unique_markets",
            ],
        ]
    )
