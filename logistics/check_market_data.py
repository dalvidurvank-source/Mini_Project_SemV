"""Validate and report the available Nashik tomato mandi-price dataset."""

from pathlib import Path
import sys

import pandas as pd

from .market_data import load_market_data, summarize_market_data, summarize_monthly_prices

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = (
    PROJECT_ROOT / "data" / "processed" / "tomato_nashik_available_data.csv"
)


def main() -> int:
    """Load the project dataset, confirm its scope, and print its summaries."""
    try:
        data = load_market_data(DATA_PATH)
    except FileNotFoundError:
        print(f"Market data file not found: {DATA_PATH}", file=sys.stderr)
        return 1
    except (ValueError, pd.errors.ParserError) as error:
        print(f"Could not validate market data at {DATA_PATH}: {error}", file=sys.stderr)
        return 1

    expected_names = {
        "cmdty": "tomato",
        "state_name": "maharashtra",
        "district_name": "nashik",
    }
    normalized_names = data[list(expected_names)].astype("string")
    for column in expected_names:
        normalized_names[column] = (
            normalized_names[column].str.strip().str.casefold()
        )
    scope_matches = normalized_names.eq(pd.Series(expected_names)).all(axis=1)
    if not scope_matches.all():
        invalid_records = data.loc[
            ~scope_matches, ["cmdty", "state_name", "district_name"]
        ]
        print(
            "Dataset scope check failed; expected every record to be Tomato "
            "from Nashik, Maharashtra. Offending records:\n"
            + invalid_records.to_string(),
            file=sys.stderr,
        )
        return 1

    summary = summarize_market_data(data)
    print(f"Records loaded: {summary['total_records']}")
    print(f"Unique markets: {summary['unique_markets']}")
    print(f"Unique observed dates: {summary['unique_observed_dates']}")
    print(f"Earliest date: {summary['earliest_date']:%Y-%m-%d}")
    print(f"Latest date: {summary['latest_date']:%Y-%m-%d}")
    print(
        "Dataset scope: confirmed every record is Tomato from Nashik, "
        f"Maharashtra ({len(data)} records)."
    )
    print("\nMonthly summary (available market observations; not a complete daily series):")
    print(summarize_monthly_prices(data).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
