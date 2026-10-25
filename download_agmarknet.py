
"""Compatibility entry point for the verified official-market importer.

The earlier script depended on an unverified third-party ``agmarknet`` package
and hard-coded a historical query without validating the service contract.
This wrapper now exposes the tested data.gov.in refresh/import CLI.
"""
from backend.market_data_cli import main


if __name__ == "__main__":
    main()
