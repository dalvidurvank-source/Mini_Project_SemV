"""Refresh or import official tomato observations.

Examples:
  python -m backend.market_data_cli refresh --state Maharashtra
  python -m backend.market_data_cli import-csv downloads/tomato.csv
"""
from pathlib import Path
import argparse
import json

from backend.market_data import import_csv, refresh_api, status


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    refresh = sub.add_parser("refresh", help="Fetch the current data.gov.in snapshot")
    for name in ("state", "district", "market", "variety", "grade"):
        refresh.add_argument(f"--{name}")
    refresh.add_argument("--page-size", type=int, default=100)
    imported = sub.add_parser("import-csv", help="Import an official downloaded CSV")
    imported.add_argument("path", type=Path)
    imported.add_argument("--currency", choices=("INR",))
    imported.add_argument("--weight-unit", choices=("quintal", "kg"))
    imported.add_argument("--unit-evidence")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.command == "refresh":
        result = refresh_api(state=args.state, district=args.district,
                             market=args.market, variety=args.variety,
                             grade=args.grade, page_size=args.page_size)
    elif args.command == "import-csv":
        result = import_csv(args.path, currency=args.currency,
                            weight_unit=args.weight_unit,
                            unit_evidence=args.unit_evidence)
    else:
        result = status()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
