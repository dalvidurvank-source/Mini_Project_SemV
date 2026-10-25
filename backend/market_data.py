"""Official tomato-market ingestion and small local persistence.

The data.gov.in current-price resource is a snapshot feed.  Raw responses are
archived separately from normalized SQLite observations.  Imports are parsed
and validated before a transaction starts, so a failed refresh cannot replace
the last usable dataset.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import csv
import io
import json
import math
import os
import shutil
import sqlite3

RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
API_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "market_data.sqlite3"
DEFAULT_RAW_DIR = ROOT / "data" / "market_data" / "raw"
SOURCE_PAGE = "https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi"


@dataclass(frozen=True)
class Observation:
    state: str
    district: str
    market: str
    commodity: str
    variety: str
    grade: str | None
    observation_date: str
    min_price: float
    max_price: float
    modal_price: float
    currency: str | None
    weight_unit: str | None
    unit_evidence: str | None

    @property
    def market_key(self) -> str:
        # The official API supplies no market ID.  This key is explicitly an
        # internal stable key for the exact supplied identity, never an alias.
        identity = "\x1f".join((self.state, self.district, self.market, self.commodity,
                                self.variety, self.grade or ""))
        return "official:" + sha256(identity.encode("utf-8")).hexdigest()[:16]


def _connect(path: Path = DEFAULT_DB) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS raw_imports (
          id INTEGER PRIMARY KEY,
          source TEXT NOT NULL,
          retrieved_at TEXT NOT NULL,
          payload_path TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL UNIQUE,
          rows_received INTEGER NOT NULL,
          rows_valid INTEGER NOT NULL,
          rows_rejected INTEGER NOT NULL,
          pages INTEGER NOT NULL,
          source_total INTEGER,
          note TEXT
        );
        CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY,
          raw_import_id INTEGER NOT NULL REFERENCES raw_imports(id),
          source TEXT NOT NULL,
          resource_id TEXT,
          market_key TEXT NOT NULL,
          external_market_id TEXT,
          state TEXT NOT NULL,
          district TEXT NOT NULL,
          market TEXT NOT NULL,
          commodity TEXT NOT NULL,
          variety TEXT NOT NULL,
          grade TEXT,
          observation_date TEXT NOT NULL,
          retrieved_at TEXT NOT NULL,
          min_price REAL NOT NULL,
          max_price REAL NOT NULL,
          modal_price REAL NOT NULL,
          currency TEXT,
          weight_unit TEXT,
          unit_evidence TEXT,
          provenance TEXT NOT NULL,
          UNIQUE(source, market_key, observation_date, min_price, max_price, modal_price)
        );
        CREATE INDEX IF NOT EXISTS observations_series_date
          ON observations(source, market_key, observation_date);
    """)
    return connection


def _text(value, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValueError(f"{field} is empty")
    return result


def _date(value) -> str:
    raw = _text(value, "observation date")
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"invalid observation date: {raw!r}")


def _price(value, field: str) -> float:
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        raise ValueError(f"{field} is not numeric")
    if not math.isfinite(result):
        raise ValueError(f"{field} is not finite")
    return result


def normalize_record(record: dict, *, currency: str | None = None,
                     weight_unit: str | None = None,
                     unit_evidence: str | None = None) -> Observation:
    lowered = {str(k).strip().casefold(): v for k, v in record.items()}

    def get(*names):
        for name in names:
            if name.casefold() in lowered:
                return lowered[name.casefold()]
        return None

    minimum = _price(get("min_price", "min price", "min price (rs./quintal)"), "minimum price")
    maximum = _price(get("max_price", "max price", "max price (rs./quintal)"), "maximum price")
    modal = _price(get("modal_price", "modal price", "modal price (rs./quintal)"), "modal price")
    if minimum < 0 or modal <= 0 or not minimum <= modal <= maximum:
        raise ValueError("prices must satisfy 0 <= minimum <= positive modal <= maximum")

    commodity = _text(get("commodity", "cmdty"), "commodity")
    if commodity.casefold() != "tomato":
        raise ValueError("record is not Tomato")

    # Historical AGMARKNET downloads name the unit in their price headers.
    explicit_quintal = any("rs./quintal" in str(k).casefold() for k in record)
    if explicit_quintal and not weight_unit:
        currency, weight_unit = "INR", "quintal"
        unit_evidence = "Official CSV price headers explicitly state Rs./Quintal."
    if bool(currency) != bool(weight_unit) or bool(currency) != bool(unit_evidence):
        raise ValueError("currency, weight unit and unit evidence must be supplied together")
    if currency and (currency != "INR" or weight_unit not in ("quintal", "kg")):
        raise ValueError("only verified INR/quintal or INR/kg records are supported")

    grade = str(get("grade") or "").strip() or None
    return Observation(
        state=_text(get("state", "state_name"), "state"),
        district=_text(get("district", "district_name"), "district"),
        market=_text(get("market", "market_name"), "market"),
        commodity=commodity,
        variety=_text(get("variety"), "variety"),
        grade=grade,
        observation_date=_date(get("arrival_date", "arrival date", "reported date", "t")),
        min_price=minimum, max_price=maximum, modal_price=modal,
        currency=currency, weight_unit=weight_unit, unit_evidence=unit_evidence,
    )


def _archive(payload: bytes, suffix: str, raw_dir: Path) -> tuple[Path, str]:
    digest = sha256(payload).hexdigest()
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{digest}.{suffix}"
    if not path.exists():
        path.write_bytes(payload)
    return path, digest


def _store(records: list[Observation], payload: bytes, *, source: str,
           suffix: str, rows_received: int, rows_rejected: int, pages: int,
           source_total: int | None, note: str | None, db_path: Path,
           raw_dir: Path) -> dict:
    retrieved_at = datetime.now(timezone.utc).isoformat()
    archive, digest = _archive(payload, suffix, raw_dir)
    connection = _connect(db_path)
    try:
        with connection:
            existing = connection.execute(
                "SELECT id FROM raw_imports WHERE payload_sha256=?", (digest,)
            ).fetchone()
            if existing:
                return {"status": "unchanged", "raw_import_id": existing["id"],
                        "rows_received": rows_received, "rows_valid": len(records),
                        "rows_rejected": rows_rejected, "inserted": 0,
                        "payload_path": str(archive)}
            cursor = connection.execute("""
                INSERT INTO raw_imports(source,retrieved_at,payload_path,payload_sha256,
                  rows_received,rows_valid,rows_rejected,pages,source_total,note)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (source, retrieved_at, str(archive), digest, rows_received,
                  len(records), rows_rejected, pages, source_total, note))
            import_id = cursor.lastrowid
            before = connection.total_changes
            for item in records:
                connection.execute("""
                  INSERT OR IGNORE INTO observations(
                    raw_import_id,source,resource_id,market_key,external_market_id,
                    state,district,market,commodity,variety,grade,observation_date,
                    retrieved_at,min_price,max_price,modal_price,currency,weight_unit,
                    unit_evidence,provenance)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (import_id, source, RESOURCE_ID if source == "data.gov.in" else None,
                      item.market_key, None, item.state, item.district, item.market,
                      item.commodity, item.variety, item.grade, item.observation_date,
                      retrieved_at, item.min_price, item.max_price, item.modal_price,
                      item.currency, item.weight_unit, item.unit_evidence,
                      SOURCE_PAGE if source == "data.gov.in" else str(archive)))
            inserted = connection.total_changes - before
        return {"status": "imported", "raw_import_id": import_id,
                "rows_received": rows_received, "rows_valid": len(records),
                "rows_rejected": rows_rejected, "inserted": inserted,
                "payload_path": str(archive)}
    finally:
        connection.close()


def import_csv(path: Path, *, currency: str | None = None,
               weight_unit: str | None = None, unit_evidence: str | None = None,
               db_path: Path = DEFAULT_DB, raw_dir: Path = DEFAULT_RAW_DIR) -> dict:
    payload = path.read_bytes()
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header")
    records, errors = [], []
    for line, row in enumerate(reader, start=2):
        try:
            records.append(normalize_record(row, currency=currency,
                                            weight_unit=weight_unit,
                                            unit_evidence=unit_evidence))
        except ValueError as exc:
            errors.append(f"line {line}: {exc}")
    if not records:
        raise ValueError("CSV contains no valid tomato observations; " + "; ".join(errors[:5]))
    return _store(records, payload, source="official_csv", suffix="csv",
                  rows_received=len(records) + len(errors), rows_rejected=len(errors),
                  pages=1, source_total=None,
                  note="; ".join(errors[:20]) or None, db_path=db_path, raw_dir=raw_dir)


def _request_json(params: dict, timeout: float) -> dict:
    request = Request(API_URL + "?" + urlencode(params),
                      headers={"User-Agent": "AgroLink/1.0 official-market-refresh"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"data.gov.in returned HTTP {response.status}")
            return json.load(response)
    except HTTPError as exc:
        if exc.code == 429:
            retry = exc.headers.get("Retry-After")
            detail = f" Retry after {retry} seconds." if retry else ""
            raise RuntimeError("data.gov.in rate limit returned HTTP 429." + detail +
                               " Keep the last valid dataset and retry later with a personal portal API key.") from exc
        if exc.code in (401, 403):
            raise RuntimeError("data.gov.in rejected the API key; configure a valid personal DATA_GOV_IN_API_KEY.") from exc
        raise RuntimeError(f"data.gov.in returned HTTP {exc.code}") from exc


def fetch_api(api_key: str, *, state: str | None = None,
              district: str | None = None, market: str | None = None,
              variety: str | None = None, grade: str | None = None,
              page_size: int = 100, timeout: float = 30,
              max_pages: int = 1000, requester=_request_json) -> tuple[list[dict], dict]:
    if not api_key.strip():
        raise ValueError("DATA_GOV_IN_API_KEY is required")
    if page_size < 1 or max_pages < 1:
        raise ValueError("page_size and max_pages must be positive")
    base = {"api-key": api_key, "format": "json", "limit": page_size,
            "filters[commodity]": "Tomato"}
    for key, value in (("state.keyword", state), ("district", district),
                       ("market", market), ("variety", variety), ("grade", grade)):
        if value:
            base[f"filters[{key}]"] = value
    offset, pages, records, totals = 0, [], [], set()
    while len(pages) < max_pages:
        payload = requester({**base, "offset": offset}, timeout)
        if payload.get("status") != "ok" or not isinstance(payload.get("records"), list):
            raise RuntimeError(f"Unexpected data.gov.in response: {payload.get('message', 'missing records')}")
        page = payload["records"]
        try:
            total = int(payload["total"])
            count = int(payload["count"])
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("data.gov.in response omitted numeric total/count pagination fields")
        if count != len(page):
            raise RuntimeError("data.gov.in count does not match returned records")
        totals.add(total)
        pages.append(payload)
        records.extend(page)
        if len(records) >= total:
            break
        if not page:
            raise RuntimeError("data.gov.in pagination stopped before the advertised total")
        offset += len(page)  # honors the documented 10-row sample-key cap
    else:
        raise RuntimeError("data.gov.in pagination exceeded the configured page safeguard")
    if len(totals) != 1 or len(records) != next(iter(totals), 0):
        raise RuntimeError("data.gov.in total changed during pagination; refresh was not stored")
    return records, {"pages": pages, "total": len(records), "page_count": len(pages)}


def refresh_api(*, api_key: str | None = None, state: str | None = None,
                district: str | None = None, market: str | None = None,
                variety: str | None = None, grade: str | None = None,
                page_size: int = 100, timeout: float = 30,
                db_path: Path = DEFAULT_DB, raw_dir: Path = DEFAULT_RAW_DIR,
                requester=_request_json) -> dict:
    key = api_key if api_key is not None else os.environ.get("DATA_GOV_IN_API_KEY", "")
    raw, metadata = fetch_api(key, state=state, district=district, market=market,
                              variety=variety, grade=grade, page_size=page_size,
                              timeout=timeout, requester=requester)
    records, errors = [], []
    for index, row in enumerate(raw):
        try:
            # The live API fields do not declare currency/weight units.  Keep
            # them unverified rather than inferring units from convention.
            records.append(normalize_record(row))
        except ValueError as exc:
            errors.append(f"record {index}: {exc}")
    if raw and not records:
        raise ValueError("API returned no valid tomato observations")
    payload = json.dumps(metadata["pages"], ensure_ascii=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _store(records, payload, source="data.gov.in", suffix="json",
                  rows_received=len(raw), rows_rejected=len(errors),
                  pages=metadata["page_count"], source_total=metadata["total"],
                  note="; ".join(errors[:20]) or
                       "Snapshot feed; API schema does not declare price weight units.",
                  db_path=db_path, raw_dir=raw_dir)


def observations(db_path: Path = DEFAULT_DB) -> list[dict]:
    if not db_path.exists():
        return []
    connection = _connect(db_path)
    try:
        rows = connection.execute("""
          SELECT source,market_key,external_market_id,state,district,market,
                 commodity,variety,grade,observation_date,retrieved_at,
                 min_price,max_price,modal_price,currency,weight_unit,
                 unit_evidence,provenance
          FROM observations ORDER BY observation_date, id
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def status(db_path: Path = DEFAULT_DB) -> dict:
    if not db_path.exists():
        return {"configured": False, "observations": 0, "imports": 0,
                "latest_observation": None, "latest_retrieval": None}
    connection = _connect(db_path)
    try:
        row = connection.execute("""
          SELECT COUNT(*) observations, COUNT(DISTINCT raw_import_id) imports,
                 MAX(observation_date) latest_observation,
                 MAX(retrieved_at) latest_retrieval,
                 COUNT(DISTINCT market_key) markets
          FROM observations
        """).fetchone()
        conflicts = connection.execute("""
          SELECT COUNT(*) FROM (
            SELECT source,market_key,observation_date
            FROM observations GROUP BY source,market_key,observation_date
            HAVING COUNT(DISTINCT printf('%.12g|%.12g|%.12g',min_price,max_price,modal_price)) > 1
          )
        """).fetchone()[0]
        return {"configured": True, **dict(row), "conflicting_keys": conflicts,
                "resource_id": RESOURCE_ID, "api_url": API_URL,
                "source_page": SOURCE_PAGE,
                "api_units_verified": False,
                "api_unit_note": "The tested API schema names price fields but does not declare currency or weight unit."}
    finally:
        connection.close()
