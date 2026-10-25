"""Versioned local application storage, separate from imported market data."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1]/'data/agrolink_app.sqlite3'


@contextmanager
def connect():
    path=Path(os.environ.get('AGROLINK_APP_DB',DEFAULT))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=10000')
    try:
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version > 2:
            raise RuntimeError('Application database version is newer than this server.')
        if version==0:
            db.executescript('''
              BEGIN IMMEDIATE;
              CREATE TABLE IF NOT EXISTS app_users (
                id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('farmer','buyer')),
                password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS app_sessions (
                token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                csrf TEXT NOT NULL, expires_at REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS app_login_failures (key TEXT NOT NULL, attempted_at REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS login_failure_window ON app_login_failures(key,attempted_at);
              CREATE TABLE IF NOT EXISTS app_listings (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES app_users(id),
                status TEXT NOT NULL CHECK(status IN ('draft','published','archived')),
                version INTEGER NOT NULL DEFAULT 1, payload TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS listing_owners ON app_listings(owner_id,status);
              CREATE TABLE IF NOT EXISTS app_photos (
                id TEXT PRIMARY KEY, listing_id TEXT NOT NULL REFERENCES app_listings(id) ON DELETE CASCADE,
                content_type TEXT NOT NULL, content BLOB NOT NULL);
              CREATE TABLE IF NOT EXISTS app_offers (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES app_users(id),
                listing_id TEXT REFERENCES app_listings(id),
                status TEXT NOT NULL CHECK(status IN ('active','withdrawn')),
                version INTEGER NOT NULL DEFAULT 1, payload TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS offer_owners ON app_offers(owner_id,status);
              PRAGMA user_version=1;
              COMMIT;
            ''')
        # Explicit additive migration: existing accounts, listings and quotes survive.
        if version < 2:
            db.executescript('''
              BEGIN IMMEDIATE;
              CREATE TABLE IF NOT EXISTS app_orders (
                id TEXT PRIMARY KEY,
                farmer_id TEXT NOT NULL REFERENCES app_users(id),
                buyer_id TEXT NOT NULL REFERENCES app_users(id),
                listing_id TEXT NOT NULL REFERENCES app_listings(id),
                offer_id TEXT NOT NULL REFERENCES app_offers(id),
                status TEXT NOT NULL CHECK(status IN
                  ('proposed','accepted','ready','collected','delivered','completed','cancelled','rejected','expired')),
                version INTEGER NOT NULL DEFAULT 1,
                quantity_kg TEXT NOT NULL, snapshot TEXT NOT NULL,
                expires_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                actuals TEXT,
                request_key TEXT NOT NULL, request_fingerprint TEXT NOT NULL,
                UNIQUE(farmer_id,request_key));
              CREATE INDEX IF NOT EXISTS order_inventory ON app_orders(listing_id,status);
              CREATE INDEX IF NOT EXISTS order_capacity ON app_orders(offer_id,status);
              CREATE INDEX IF NOT EXISTS order_parties ON app_orders(farmer_id,buyer_id);
              CREATE TABLE IF NOT EXISTS app_order_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL REFERENCES app_orders(id),
                actor_id TEXT REFERENCES app_users(id),
                status TEXT NOT NULL, occurred_at TEXT NOT NULL, details TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS app_order_requests (
                actor_id TEXT NOT NULL REFERENCES app_users(id), request_key TEXT NOT NULL,
                order_id TEXT NOT NULL REFERENCES app_orders(id), fingerprint TEXT NOT NULL,
                PRIMARY KEY(actor_id,request_key));
              PRAGMA user_version=2;
              COMMIT;
            ''')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()
