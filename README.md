# AgroLink — farmer fair-price MVP

A React/JavaScript frontend connected to the Python pricing engine, official market-data imports, road logistics and delivery-life checks. The Accounts & marketplace workspace adds farmer/buyer accounts, persistent harvest listings and buyer-submitted quotes. Calculator and demo workflows remain available separately. Orders and payments are not implemented; no observations or live offers are fabricated.

## Start locally

Use a Python environment with [requirements.txt](requirements.txt), then run from the repository root:

```powershell
python -m pip install -r requirements.txt
python -m backend.server
```

In a second terminal:

```powershell
cd frontend
npm.cmd install
npm.cmd run dev
```

Open http://127.0.0.1:5173. The default source is the small root price-only exports. Selecting monthly VAR loads the approximately 195 MB Tomato dataset lazily and may take tens of seconds. Datasets and model reports are cached inside the backend process; restart it after replacing CSVs. CSVs stay on the backend, outside frontend assets.

For the actual test environment used during development, Python was `C:/Users/Durvank/AppData/Local/Programs/Python/Python313/python.exe`. The commands above also work with an activated environment containing the dependencies.

The frontend uses Vite's `/api` proxy. For a separate backend origin, see [frontend/.env.example](frontend/.env.example) and configure `VITE_API_BASE_URL` before starting/building Vite. Set `AGROLINK_FRONTEND_ORIGIN` on the backend for direct cross-origin calls. There are no frontend secrets.

Build with `npm.cmd run build` inside `frontend`. A production host needs an `/api` proxy or a bundle built with the API origin configured. The standard-library HTTP server is a local MVP adapter, not a production deployment server.

## Official recent-data refresh and import

The official OGD resource is [Current Daily Price of Various Commodities from Various Markets (Mandi)](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi), resource `9ef84268-d588-465a-a308-a864a43d0070`. Its tested API is:

```text
GET https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
```

The API requires the `api-key` query parameter. The official OAS page provides a sample key limited to 10 rows per response and says a personal key is available after portal login under My Account. Configure the personal key without committing it:

```powershell
$env:DATA_GOV_IN_API_KEY = '<your personal data.gov.in key>'
python -m backend.market_data_cli refresh --state Maharashtra
python -m backend.market_data_cli status
```

The importer paginates with `offset` and `limit`, advances by the actual returned count, checks the advertised total, and refuses a truncated or changing result. The tested filters are state, district, market, commodity, variety and grade. The response preserves state, district, market, commodity, variety, grade, arrival date, minimum, maximum and modal price. Retrieval time and raw response provenance are stored separately.

On 2026-10-23 a live Maharashtra/Tomato query returned two current records, both dated 2026-10-23: APMC Ratnagiri (Nachane) / Other / Local grade and Pune(Pimpri) / Local / Local grade. The exact response rows are retained as the reproducible fallback fixture [data_gov_in_maharashtra_tomato_2026-10-23.csv](data/import_examples/data_gov_in_maharashtra_tomato_2026-10-23.csv). A following command received HTTP 429. The OAS page documents the sample-key row cap but does not publish a numeric request quota, so the client preserves the last valid database and reports throttling rather than retrying aggressively.

The current API behaved as a daily snapshot and exposed no observation-date filter. It did not supply 60–90 historical sessions. For an official historical export, use the same validated importer:

```powershell
python -m backend.market_data_cli import-csv C:\Downloads\official_tomato_history.csv
```

Historical AGMARKNET CSV headers such as `Modal Price (Rs./Quintal)` provide direct unit evidence and are detected. Bare `min_price`/`max_price`/`modal_price` API headers do not declare currency or weight unit, so those records remain usable for recorded display but cannot enter the fair-price engine. If an official download has bare headers but accompanying documentation establishes its unit, supply all three fields explicitly:

```powershell
python -m backend.market_data_cli import-csv C:\Downloads\official_tomato_history.csv `
  --currency INR --weight-unit quintal `
  --unit-evidence 'Citation or text from the official download documentation'
```

SQLite at `data/market_data.sqlite3` stores normalized observations; immutable raw payloads are archived under `data/market_data/raw/`. Both runtime paths are ignored by Git. Imports are transactional, content-addressed and repeatable. Exact duplicates are ignored, conflicts remain visible and block forecasting, and a failed refresh leaves the last valid dataset intact. The official API supplies no market ID, so AgroLink creates an internal stable key from the exact state/district/market/commodity/variety/grade tuple and clearly labels it as internal.

## Price-only data audit

Files are read separately from VAR inputs:

| File | Rows | Actual observation coverage | Markets |
| --- | ---: | --- | ---: |
| [price_data.csv](price_data.csv) | 1,000 | 2024-11-19–2025-01-01 | 49 |
| [price_data (25-26).csv](price_data%20(25-26).csv) | 1,000 | 2025-09-23–2025-10-30 | 50 |

Both contain Tomato prices from Maharashtra. The combined data contain 54 market-ID/variety combinations and five observed months. Neither file contains 2026 observations. The loader audit found no invalid dates, invalid prices, missing cells, exact duplicates, or conflicting daily keys in these actual files. Exactly 1,000 rows per export raises a possible pagination/export-limit concern, but does not prove truncation; source completeness remains unverified.

Actual schema: `t`, `cmdty`, `market_id`, `market_name`, `state_id`, `state_name`, `district_id`, `district_name`, `variety`, `p_min`, `p_max`, `p_modal`. There are no arrivals or unit columns.

The loader validates required fields, finite positive modal prices, non-negative minimum prices, `min <= modal <= max`, canonical numeric IDs and ISO dates. Invalid rows are audited and excluded. Identical normalized observations are deduplicated while retaining every contributing filename. Conflicting prices for one market-ID/variety/date make that series unavailable; they are not averaged. Conflicting state/district/market metadata also blocks a series rather than guessing an alias.

No arrivals, missing observations or seasonal inputs are invented. Market IDs remain explicit in the API and market selector. Similar names are not used to silently merge separate markets. Missing calendar-day counts and gap diagnostics appear in the per-market report.

## Confirmed source units

The project owner confirmed on 2026-10-23 that both root exports use **INR per quintal**. This confirmation is recorded in [backend/price_only_units.json](backend/price_only_units.json), scoped to the two source filenames. Converted recommendations are now enabled for eligible series without additional environment setup.

Source forecasts enter the existing engine as INR/quintal; prices shown in INR/kg divide by 100. For example, 1,010 INR/quintal = 10.10 INR/kg. A batch transport cost of INR 800 across 500 kg deducts 1.60 INR/kg, producing a midpoint of 8.50 INR/kg before the configured band.

[backend/.env.example](backend/.env.example) documents optional environment overrides. If either AGROLINK_PRICE_ONLY_UNIT or AGROLINK_PRICE_ONLY_UNIT_EVIDENCE is exported, both must form a complete supported pair; partial or empty overrides disable the saved fallback. Supported override units are INR/quintal and INR/kg. The server does not auto-load .env files. Saved metadata must contain evidence and match the actual source filenames; otherwise the original unit gate remains in effect.

Unknown-unit fallback is retained and tested. If the confirmation is removed, unsupported, or superseded by incomplete overrides, the application permits only native-unit previews and blocks converted recommendations. New datasets with different units need their own confirmation.

## Forecast policy and evaluation

[forecasting/price_only.py](forecasting/price_only.py) implements:

- Exactly **one subsequent reporting session**, not the next calendar day. The target date is always unknown/null. Longer horizons are rejected until independently implemented and evaluated.
- The latest usable segment, split at gaps **greater than seven calendar days**. Long gaps are never compressed into apparently consecutive daily data. Short gaps remain real reporting-session intervals, not fabricated observations. The chart uses actual dates and breaks its line at long gaps.
- At least **20 sessions**: 10 initial training sessions, five subsequent selection targets, and five later final-evaluation targets. For longer segments the expanding training prefix is larger.
- Candidates: `LAST_OBSERVED`, `RECENT_MEAN` (up to the latest five reporting sessions), and statsmodels `SimpleExpSmoothing` with estimated initialization/optimized smoothing.
- Every rolling forecast is fitted from observations strictly before its target. All candidates are compared on the same earlier selection targets by MAE; ties prefer last-price, then mean, then smoothing. Failed candidates are excluded. The last-price baseline must itself be evaluable.
- The selection winner is frozen before the final five targets. Its final MAE/RMSE and the last-price baseline's final errors are reported separately. Final-holdout performance never changes the frozen winner; if the winner loses to the baseline on final holdout, an explicit warning is shown.
- The frozen method is finally refitted using the entire usable segment to predict the subsequent reporting session. Non-finite/non-positive outputs or final model failure make forecasting unavailable. There is no silent alternate-market or alternate-source substitution.
- No statistical confidence percentage or prediction interval is claimed. A short holdout is diagnostic evidence, not an accuracy certification.

These are **engineering safeguards, not universal statistical minimums or guarantees**. Configure them with `AGROLINK_PO_MIN_TRAIN`, `AGROLINK_PO_SELECTION_COUNT`, `AGROLINK_PO_TEST_COUNT`, `AGROLINK_PO_MAX_GAP_DAYS`, and `AGROLINK_PO_MEAN_WINDOW`. Positive integer values are required; initial training must be at least three sessions. Changing policy changes eligibility and must be followed by report regeneration and review.

The next reporting session does not have a known selling date. Price-only requests with `selling_date`, unsupported horizons, an unsupported method override, or harvest dates after the historical origin are rejected. Stale-data analysis requires `acknowledge_stale: true`. No 2025 forecast is labelled a current October 2026 price.

## Measured cases and reports

Under the default policy, **27 of 54** series qualify for a diagnostic forecast; 27 are unavailable. The owner-confirmed INR/quintal metadata now enables converted recommendations for these eligible series.

| Market / variety | Latest-segment sessions | Selected method | Forecast, source units | Final MAE, source units | Last-price final MAE |
| --- | ---: | --- | ---: | ---: | ---: |
| Pune / Local (ID 172) | 30 | Recent mean | 1,010 | 158 | 110 |
| Pune(Pimpri) / Local (ID 2494) | 36 | SES | 1,466.67 | 90.04 | 180 |
| Bhusaval / Other (ID 1438) | 29 | Last observed | 1,200 | 160 | 160 |
| Ahmednagar / Other (ID 153) | 1 | Unavailable | — | — | — |

All example forecasts have origins in the supplied historical data. Pune's origin is 2025-10-30. Its final errors are from 2025-10-26 through 2025-10-30. It won selection but lost to the baseline on final holdout, which is disclosed rather than hidden.

Deliverables:

- [reports/price_only_eligibility.csv](reports/price_only_eligibility.csv): every market-ID/variety, eligibility/reason, segment dates, missing-day/gap counts, winner, forecast, separate errors and evaluation counts.
- [reports/price_only_backtesting.json](reports/price_only_backtesting.json): complete source audit, policy, unit status, candidate failures, per-origin actuals/predictions, and selection/final partitions for each series.

Reproduce both from the repository root:

```powershell
python -m backend.report_price_only
```

## Architecture and preserved behavior

```text
React source selector -> centralized API client -> Python HTTP adapter
  price_only -> root CSV validation -> market ID + variety
             -> latest usable segment -> selection -> frozen final evaluation
             -> native preview OR confirmed-unit conversion
  var        -> existing Tomato loader/cleaner -> monthly price + arrivals -> VAR
  confirmed forecast -> existing deterministic price engine -> explainable result
```

[backend/price_only_api.py](backend/price_only_api.py) owns the new adapter contracts. [backend/server.py](backend/server.py) routes explicit sources, retains legacy routes/default VAR behavior, and calls the existing pricing functions. The frontend explicitly selects the root exports by default; existing clients omitting `source` continue to use VAR.

[forecasting/var_forecaster.py](forecasting/var_forecaster.py), [pricing/fair_price_engine.py](pricing/fair_price_engine.py), [pricing/price_pipeline.py](pricing/price_pipeline.py), and the logistics code were not changed by this upgrade. VAR still uses price and arrivals, its stationarity/coverage safeguards, and its existing model selection/evaluation. It forecasts one month after its final observed month. Its existing full-history lag-selection behavior is preserved; its metrics should not be presented as independently tuned out-of-sample confidence.

The large [data/raw/Tomato.csv](data/raw/Tomato.csv) has 2,338,352 raw rows, dated 2000-10-19 through 2024-02-01. The previous audit found 25 null modal prices and one null maximum price. Existing cleaning retains 2,310,853 rows dated 2001-02-08 through 2024-02-01. Prices are explicitly labelled INR/quintal and arrivals tonnes. The existing demonstration pipeline points to `data/Tomato.csv`; the web adapter uses the actual raw path, without changing the demonstration.

The existing price formula is:

```text
fair_INR_per_quintal = max(0, forecast × demand_supply × quality × location
                            - transport_INR_per_quintal)
```

Transport is **deducted** to estimate farm-gate return. It is not an additive delivered-price calculation. Neutral multipliers remain 1.0 because reliable regional demand and calibrated quality/location coefficients do not exist. Quality is self-reported metadata only. Packaging, handling, production costs, weather and synthetic logistics estimates are excluded and disclosed.

Confirmed INR/kg forecasts multiply by 100 before entering the engine. Confirmed INR/quintal forecasts enter directly. Batch quantity in quintals multiplies by 100 to become kg. INR 800 transport / 500 kg deducts INR 1.60/kg once. Returned recommendation and chart prices are INR/kg; `forecast.base` and result `forecast.metrics` use the legacy INR/quintal contract. The detailed `forecast.report` always retains native-source units. Proposed-price comparisons match the displayed two-decimal paise boundaries.

The band offset defaults to INR 25/quintal on either side (`AGROLINK_BAND_OFFSET`), with a zero lower floor. It is a configurable policy, not statistical uncertainty.

## API contract

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Lightweight process readiness; datasets are lazy |
| `GET /api/sources` | Explicit `var`, `price_only` and `official` sources |
| `GET /api/catalog?source=price_only` | Root-export market IDs/varieties, modes, unit gate and supported horizon |
| `GET /api/catalog?source=official` | Exact imported official identities, varieties/grades, persistence and unit status |
| `GET /api/catalog` | Preserved legacy VAR catalog |
| `GET /api/history?...` | History and metadata for explicitly selected source; price-only includes eligibility, policy and separate evaluation information |
| `GET /api/price-only/audit` | Raw-source audit and current policy/configuration |
| `GET /api/market-data/status` | Local official-import counts, dates, conflicts and verified source contract |
| `POST /api/market-analysis` | Recorded observation, historical target evaluation, or fresh one-session forecast |
| `POST /api/forecast-preview` | Acknowledged native-unit diagnostic forecast, with no price calculation |
| `POST /api/recommendations` | Existing deterministic recommendation, gated by units for price-only |

Price-only history query fields: `source`, `state`, `district`, `market`, `market_id`, `variety`, plus `market_grade` for official imports. Only Tomato is supported. Identities are validated against the supplied labels; no market alias is guessed.

`POST /api/market-analysis` requires `mode`:

- `recorded`: requires `target_date`; returns `kind=recorded_price`, a separate actual observation, and `forecast=null`.
- `historical`: requires a target date that is an actual reporting session; model fitting uses only observations strictly before it and returns the actual separately. Historical publication availability timestamps are unknown, so this is not described as a fully point-in-time simulation.
- `future`: rejects an exact target date and supports only one subsequent reporting session. When the latest observation exceeds `AGROLINK_FRESHNESS_DAYS` (default 7), it requires explicit stale-data acknowledgment and is labelled as a historical next-session projection rather than a current market-price forecast. It remains unavailable when the evaluated history policy fails.

Example native forecast request:

```json
{
  "source": "price_only",
  "mode": "historical",
  "target_date": "2025-10-30",
  "crop": "Tomato",
  "state": "Maharashtra",
  "district": "Pune",
  "market": "Pune",
  "market_id": "172",
  "variety": "Local",
  "method": "auto",
  "horizon": 1,
  "horizon_unit": "reporting_session",
  "selling_date": ""
}
```

For a converted recommendation also include `quantity`, `unit` (`kg` or `quintal`), `transport_cost` (INR for the entire batch), `quality` (`Unspecified`, `A`, `B`, or `C`), and `harvest_date` (on/before the historical forecast origin). The browser collects these fields, but its unconfigured preview does not allocate costs or produce a price band. VAR retains required harvest/selling dates and the monthly horizon restriction.

History returns `eligibility.status` (`eligible` or `unavailable`), its reason, segment counts, gap diagnostics, selected model, selection/final evaluation dates and counts, `supported_horizons` via catalog, `can_recommend`, `units`, actual observations and source filenames. The unreleased next-session prediction is omitted from history until the acknowledged forecast action. Historical holdout predictions are provided as evaluation evidence.

The preview response has `kind=forecast_preview`, `forecast.prediction_native`, `forecast.metric_unit`, `forecast.origin`, `forecast.horizon`, `forecast.forecast_date=null`, full `forecast.report`, context and warnings. It has no `prices` object. A recommendation additionally has `prices` in INR/kg, a deterministic breakdown, calculation timestamp, neutral multipliers and limitations. Detailed report prices/errors retain native-source units; the result's top-level model base/metrics use INR/quintal for backward compatibility.

Invalid selections, unsupported horizons/dates, missing units, stale future inputs, conflicts and insufficient data return HTTP 422. Unknown endpoints return 404. Unexpected internal failures return a safe 500 message; details stay server-side. Browser inputs survive request failures and 30-second client timeouts; duplicate submission is blocked. Official raw imports and normalized observations use local persistence; user calculations are not saved.

## Verification

From the root:

```powershell
python -m unittest forecasting.test_price_only backend.test_market_data backend.test_official_market_api backend.test_price_only_api backend.test_server logistics.test_logistics logistics.test_market_data logistics.test_road_hub_selector logistics.test_dijkstra_end_to_end_optimizer logistics.test_end_to_end_routes logistics.test_prototype_metrics
cd frontend
npm.cmd test
npm.cmd run build
```

The Python tests cover official API pagination/truncation, transactional refresh, duplicate prevention, conflicts, units, dates, recorded/historical/future semantics, source validation/provenance, gap splitting, eligibility, chronological prefixes, independent holdout selection, baseline ties, smoothing failure, invalid predictions, conversion, transport allocation, stale inputs, unsupported horizons, HTTP contracts and existing behavior. Converted-price tests use synthetic fixtures with a test-only unit contract, not invented confirmation for the live API.

Manual browser verification uses the actual running backend/CSV data for a qualifying market and an unavailable market. It checks source switching, historical acknowledgment, native-unit preview, model errors/limitations, responsive rendering and preservation of entries after simulated network errors. All 64 existing logistics tests remain part of regression validation.

Weather and AI integrations are not configured. Accounts, harvests, photos and buyer offers now use the separate application SQLite database documented below. Authentication is application-managed; no external identity provider is configured. HTTP and SQLite use the Python standard library. The HTTP adapter remains a local development server rather than a production hosting stack.

Verification completed on 2026-10-23: 106 Python tests and 11 frontend tests passed; the production Vite build passed with its existing non-blocking large-bundle advisory. Live API checks returned the official Pune(Pimpri) recorded observation with `forecast=null`, rejected its one-session future forecast for insufficient history, and verified the root Pune ID 172 historical target 2025-10-30 trained only through 2025-10-29. The generated [market/horizon report](reports/market_horizon_eligibility.md) and [machine-readable report](reports/market_horizon_eligibility.json) record every exact series, supported mode, evaluated horizon, evidence count, tested examples, source contract and current blocker. Regenerate them after every refresh or import with `python -m backend.report_market_eligibility`.


The measured report used Python 3.13.2, NumPy 2.3.5, pandas 2.3.3, statsmodels 0.15.0, and SciPy 1.16.3. The requirements range includes the already-installed statsmodels version. Optimizer outputs can vary across dependency versions; regenerate the reports after changing the environment.


Unit activation on 2026-10-23: persisted the project owner confirmation for both exports and enabled INR/quintal-to-INR/kg recommendations. Historical horizons and stale-data safeguards remain unchanged.

## Location/date/quality scenario comparison

Run `python -m backend.compare_scenarios` from the repository root to start an isolated loopback HTTP server and exercise the actual datasets and calculation code. It writes [comparison summary](reports/scenario_comparison.md), [all HTTP cases](reports/scenario_comparison.csv), and [full results](reports/scenario_comparison.json). The 2026-10-23 run passed 474 expected HTTP outcomes with zero assertion failures, including all 54 price-only series and three VAR locations. Eligible cases compare four quality selections, earlier harvest dates, quantity-unit equivalence and transport changes; unsupported dates/grades/horizons are rejected.

Live browser checks additionally compared Pune, Pune(Pimpri), Kolhapur and Kamthi across Unspecified/A/B/C, confirmed unchanged pricing for an earlier historical harvest date, and checked inline rejection of a current 2026 harvest. Quality has no configured premium; harvest dates do not retarget the model's forecast origin. These are disclosed limitations, not evidence that market prices never vary with quality or time.

## Farmer route and return calculator

The default UI loads `data/raw/Tomato.csv` automatically and starts with Maharashtra / Nashik / Nasik / Other, matching the saved Nashik yard pin. Source, calculation mode and forecast method are internal. The farmer enters crop quantity, harvest and expected sale dates, farm GPS coordinates and selling-market coordinates. Vehicle assumptions can be edited; regional supply and demand are never farmer inputs.

### Try it

Start the backend and frontend as described above, then click **Try the Mumbai -> Nashik sample**. This fills a 500 kg sample with SPIT college in Mumbai as the prototype pickup and Nasik as the destination. Confirm the quantity and click **Calculate route & return**. The prototype origin is explicitly labelled; it is not a farm. Saved yard coordinates are user supplied and require entrance confirmation.

For a real farm, use GPS while at the pickup point or enter latitude/longitude. The selected mandi supplies the price series; the destination pin must correspond to that mandi. Changing the selected market updates its saved pin or clears the coordinates when none is known. Coordinates are sent to OSRM for custom routing only when a calculation is requested.

### Routing and transport

`GET /api/listing-defaults` returns crop/market defaults, sample locations and editable vehicle assumptions. `POST /api/listing-estimate` performs the integrated calculation:

1. Haversine measures direct distance and screens nearby candidate hubs.
2. For exact saved prototype points, use the repository's directed OSRM road matrix. Custom coordinates use the OSRM Table API with distance and duration annotations. Near a saved point is not treated as the saved point; no fabricated connector legs are added.
3. Dijkstra minimizes total travel time over the available directed location-to-location road legs. These are OSRM fastest-driving legs, not an exhaustive street graph or globally shortest-distance routes. Unreachable legs are excluded. Failed routing returns a visible error; direct distance is never substituted for road distance.
4. Transport cost is outbound distance times the configured return allowance, divided by vehicle mileage, multiplied by fuel price, plus per-trip loading, unloading and toll charges. Trips = ceil(shipment kg / vehicle capacity). The final partial load still incurs a full trip. The whole batch cost is allocated over the original quantity.
5. The existing monthly model pipeline evaluates VAR_LEVEL, VAR_LOG and baseline models against chronological data. The selected market and supported selling month determine the forecast.
6. Engine-owned DSR uses matched backend evidence when available, then the engine deducts route-derived transport cost. Market proceeds, net proceeds, route stops, road/direct distances, trips, timestamps and assumptions are shown separately. Net proceeds remain negative when costs exceed revenue; the legacy fair-price band separately retains its zero floor.

Default transport assumptions are a 1,000 kg vehicle, 12 km/l, INR 95/l fuel, full empty return, INR 100 loading and INR 100 unloading per trip, and zero tolls. They are editable planning assumptions, not live quotes or a calibrated carrier tariff. Driver hire, maintenance, production costs, cold-chain feasibility, live traffic and truck restrictions are not modeled. Return distance is an allowance, not a separately routed return journey.

Custom routes require network access to `https://router.project-osrm.org`. Configure `AGROLINK_OSRM_URL` on the server for another OSRM deployment. Successful matrices are cached in memory by coordinates for up to an hour. The saved sample works offline using the timestamped road matrix; no new routing package or API key is required. API reference: [OSRM Table service](https://project-osrm.org/docs/v5.24.0/api/#table-service).

### Engine-owned DSR

The repository has arrivals (supply), but no measured demand series. The engine reports DSR unavailable and uses a neutral multiplier until matched evidence is available. It does not invent demand from arrivals, prices, or farmer shipment size. Caller DSR overrides and the removed farmer supply/demand inputs are rejected.

An operator may create `data/market_balance.csv` using the header in `data/market_balance.example.csv`, or set `AGROLINK_BALANCE_CSV` to a backend-maintained CSV. Required columns:

`crop,state,district,market,variety,period_start,period_end,supply_kg,demand_kg,source,available_on`

Both quantities must use kg for the same complete calendar month and exact market/variety. `source` records evidence, and `available_on` must be on or before the selected market's forecast-origin observation. Future evidence, mismatched markets and mismatched periods are not used. Duplicate, conflicting, malformed or zero-demand records leave the multiplier neutral with an explicit reason. The example file has no fabricated records.

DSR = supply / demand. Multiplier = clamp(1 + sensitivity * (1 - DSR), 0.85, 1.15). `AGROLINK_DSR_SENSITIVITY` defaults to 0.10 as an explicit policy, not a learned or validated relationship. Quality and location premiums remain neutral.

### Forecast limits and verification

The bundled monthly data ends in February 2024. A current listing therefore shows a historical demonstration forecast for the month after the selected series ends; the requested selling date is preserved separately. It is not a verified current market price. Fresh observations and a supported 1-3 month horizon are required for a current monthly estimate. Forecasts are monthly, not daily. This flow does not save or publish a crop listing.

Run the actual repository-data HTTP checks with:

```powershell
python -m backend.verify_listing_flow
```

This exercises the default locations, real Haversine/Dijkstra route, transport, monthly forecast, kg/quintal equivalence, multi-trip loads and invalid requests. Results are saved in `reports/listing_flow_check.json`. No external routing request is needed for the saved sample.

Focused tests:

```powershell
python -m unittest backend.test_listing logistics.test_listing_route pricing.test_market_balance
cd frontend
npm.cmd test
npm.cmd run build
```

Restart the backend after updating the project. The frontend timeout is 120 seconds for initial dataset/model loading.

Browser checks use installed Google Chrome and Playwright (`npm.cmd install` installs the test runner). Run `npm.cmd run test:e2e` in `frontend`. The test runner starts isolated servers on ports 18080 and 15173, exercises the actual dataset and saved route, and checks GPS, error recovery and mobile overflow. It uses `.venv-local` by default; set `AGROLINK_TEST_PYTHON` to another Python executable if needed. Screenshots are written to `frontend/test-results/`.

Verification on 2026-10-24: the saved sample used 172.156 km of road legs (141.3 km direct distance), INR 2,925.80 transport for 500 kg, and a selected recent-mean market reference of approximately INR 14.07/kg targeting February 2024. Estimated net proceeds were INR 4,108.32 (INR 8.22/kg). These are historical demo results with editable transport assumptions, not a current price or transport quotation. Seven actual-data HTTP cases and four Chrome browser scenarios passed. A custom-coordinate live OSRM request also returned road distance/duration successfully. The production build passed with the chart split into a separately loaded chunk.

## Farmer harvest and buyer delivery tab

The farmer workspace has **Price calculator** and **My harvest & buyers** tabs. Harvest details are shared. The calculator displays delivery-life eligibility alongside its historical price estimate. Forecast dates never replace actual harvest age.

In the buyer tab, enter quantity, harvest date/time, condition, earliest pickup date, optional exact pickup time and farm coordinates. **Save harvest & find buyers** saves a draft in this browser's local storage and evaluates the directory. Drafts can be restored or deleted; they are not public listings. Buyer selection prepares a draft preview only: no order, reservation, message or payment is created. Buyer/farmer authentication and RBAC remain a later phase.

The directory in `data/buyers.demo.json` contains three labelled demo buyers at saved Nashik, Pimpalgaon and Chhatrapati Sambhajinagar prototype pins. These are test destinations, not registered businesses or verified demand. They do not feed DSR. The sample uses saved OSRM road legs; custom origins use OSRM requests. Route failure disables the buyer without substituting straight-line distance.

Delivery checks in `logistics/shelf_life.py` use:

```text
remaining buffer = planning window - age since harvest - waiting for pickup
                 - earlier vehicle trips and returns - final outbound journey
                 - final handling - safety margin
```

One vehicle makes sequential trips. The last load must arrive within the window. Date-only harvests count from midnight conservatively. Local times use Asia/Kolkata. Without an exact pickup time, pickup is immediate today or at the start of the selected future pickup day.

- **Within delivery window:** sufficient planning buffer; draft selection enabled.
- **Limited delivery window:** at most six hours of buffer, or uncertain/very-ripe condition; acknowledgment required.
- **Selling unavailable:** delivery exceeds the window, or the crop is marked damaged/spoiled; selection disabled and rejected by the server.
- **Route unavailable:** dependable road routing failed; selection disabled.

`POST /api/buyer-suggestions` evaluates all directory buyers. `POST /api/buyer-selection` rechecks route and time before accepting a draft. Caller destination, lifetime and eligibility overrides cannot enable a blocked buyer. Editing harvest details invalidates suggestions; checks older than one minute require refresh.

Tomato planning budgets are 48 hours for a firm-ripe shaded lot, 24 hours for very-ripe or uncertain lots, and zero for lots marked damaged/spoiled. Each trip allows two hours for handling; four hours are reserved as a safety margin. These are conservative project assumptions from harvest, not validated expiry predictions or food-safety certification. They do not model temperature or quantify spoilage. Refrigeration does not automatically extend the budget. Local agronomic validation is needed before real trading. [UC ANR tomato handling guidance](https://ucanr.edu/sites/default/files/2019-09/311224.pdf) explains condition-dependent storage life; it does not validate these exact project budgets for every harvested lot.

For a demonstration, click **Try a near-expiry harvest** and then **Save harvest & find buyers**. A 500 kg lot harvested about 38 hours earlier at the prototype Mumbai pickup yields a warning for Nasik and blocks the farther city-centre destination. No real buyer is contacted.

Run `python -m unittest logistics.test_delivery_life backend.test_buyers` for focused backend checks, and `npm.cmd run test:e2e` in `frontend` for browser checks. Coverage includes expiry boundaries, pickup delays, final-trip timing, crop condition, date-only harvests, route failures, forged eligibility, warning acknowledgment, elapsed-time rechecks, draft restore/delete, stale suggestions and mobile layout.

Verification on 2026-10-24: 145 Python tests, 11 frontend utility tests, nine Chrome browser scenarios and the production build passed. The near-expiry browser scenario used actual saved road routes, required acknowledgment for Nasik, and disabled the farther buyer. A direct HTTP selection request for that blocked buyer returned 422.

## Buyer ranking by estimated net return

The harvest/buyer tab now compares financially rankable, delivery-eligible buyers by estimated net proceeds, rather than distance or transport cost alone. Road routing, vehicle capacity, per-trip transport and delivery-life checks reuse the existing logistics functions. The server recomputes these values, purchase capacity and the ranking when a draft is prepared. Client-supplied offer prices, fees, totals, DSR multipliers, destinations and ranking results are not used. Vehicle/fuel settings remain validated, shared farmer planning assumptions, not verified transport quotations.

### Formula and comparable quantities

For harvest quantity H kg and buyer capacity C kg, the planned sale quantity Q is H for a full sale, or min(H, C) only when the farmer explicitly enables partial sales and the buyer supports them. Otherwise insufficient capacity excludes selection. A buyer minimum, if specified, also applies. Remaining unsold quantity is H - Q and has no assumed resale value.

```text
gross = round_half_up(Q * offer_price_INR_per_kg, 2)
trips = ceil(Q / vehicle_capacity_kg)
transport = existing route_transport(..., Q).total_trip_cost_inr
other_charges = sum(each declared fixed, per-kg or percentage-of-gross charge,
                    individually rounded half-up to paise)
net_return = gross - transport - other_charges
net_per_planned_sellable_kg = round_half_up(net_return / Q, 2)
```

Monetary calculations use Decimal. Net losses are retained. Fuel, mileage, return allowance, loading, unloading and tolls are included once through the existing transport estimator; charge components are not added again. Driver hire, maintenance, production costs and unspecified fees remain outside the estimate. No spoilage-quantity or quality-price deduction is invented: the interface explicitly reports that no defensible loss estimate exists and that the quoted quantity may differ from actual accepted weight or grade. DSR is never applied to buyer offers or ranking. Demo directory entries do not become demand evidence.

Only equal sale quantities are compared. Full-harvest offers form one group; partial offers form separate groups for each exact planned sale quantity. Within a group, higher total net return ranks first; equal monetary returns share a rank, with identifier order used only for stable presentation. A partial sale is never declared better than a full sale by comparing unlike quantities. Delivery warnings remain visible and still require acknowledgment. Failed delivery checks and invalid/rejected offers cannot be selected.

### Offers, missing data and demonstration terms

The default `data/buyers.demo.json` still contains no price quotes or confirmed purchase capacities. Those buyers are visibly **Not financially ranked**; their gross/net returns stay unavailable. Eligible unpriced selections prepare an **unpriced enquiry**, not an agreed sale. Historical or forecast mandi prices are never substituted for a buyer offer. No forecast benchmark was added because the directory lacks verified buyer-to-market series mappings; the existing historical calculator remains separate.

The server supports an optional `offer` object on a directory record:

- `kind`: `demo_offer` or `buyer_offer`. A demo record cannot claim a real buyer offer.
- `price_inr_per_kg`: positive, finite INR/kg price with at most two decimal places. Missing prices stay unranked; invalid prices disable selection.
- `max_quantity_kg`: positive purchase capacity, required for financial comparison.
- `min_quantity_kg`: optional non-negative minimum; omitted means no specified minimum.
- `partial_sales_supported`: boolean, default false.
- `selling_charges`: optional list of `{label, type, value}`; types are `fixed`, `per_kg`, `percent_of_gross`. Only explicit known charges are included.
- Actual `buyer_offer` records require attributable `source` and an unexpired, timezone-aware `valid_until`. This is an operator-maintained quote contract, not account verification or an authenticated order.

Set `AGROLINK_BUYERS_FILE` to an operator-maintained JSON directory to supply evidence-backed terms. The default path and unpriced buyer workflow require no configuration change. There is no database migration and no new runtime dependency. The HTTP routes remain `/api/buyer-suggestions` and `/api/buyer-selection`.

Illustrative prices exist only in `backend/test_fixtures/buyer_offers.demo.json`. Browser tests explicitly point their isolated backend at that fixture; normal application startup does not load it. This allows deterministic ranking tests without inventing live offers. Test fixture examples include a farther Pimpalgaon offer exceeding Nasik's net return, shared fuel-cost changes reversing the ranking, separate partial-sale groups, an unpriced destination and backend rejection of forged totals. Drafts, demo labels, local harvest storage and future RBAC boundaries remain intact. No payments, orders or verified buyers were added.

### Files for this change

- `pricing/buyer_return.py`: authoritative quote validation, Decimal finances and comparable-quantity ranking.
- `backend/buyers.py`: reuse logistics for actual sale quantity, enforce capacity, recompute ranking at draft selection and load optional server-owned terms.
- `frontend/src/components/BuyerFinancials.jsx`: offer provenance, capacity, gross/net values, fees, rank explanations and assumptions.
- `frontend/src/components/BuyerMarketplace.jsx` and `frontend/src/styles.css`: partial-sale opt-in, financial cards, best-in-group highlighting and unpriced enquiry behavior.
- `pricing/test_buyer_return.py`, `backend/test_buyer_ranking.py`, `frontend/tests/buyer-ranking.spec.js`: financial, integration and real-browser coverage.
- `backend/test_fixtures/buyer_offers.demo.json` and `frontend/playwright.config.js`: isolated illustrative quote terms for tests only.
- `backend/.env.example` and this README: optional directory configuration, formula, setup and limitations.

Verification for financial ranking on 2026-10-24: all 165 Python tests passed using the explicit backend, pricing, forecasting and logistics test modules (default unittest discovery does not include the logistics namespace). All 11 frontend utility tests and all 14 Chrome scenarios passed, including the five new financial browser scenarios. `npm.cmd run build` passed. Browser financial tests use the isolated quote fixture and actual saved road routes; they do not claim that fixture prices are real offers. A normal-directory check confirmed all three default buyers retain `missing_offer` status with null financial returns.

## Accounts, persistent listings and role permissions

Open **Accounts & marketplace** and create a Farmer / seller or Buyer account. No accounts, credentials, harvests or buyer quotes are seeded. The calculator and **My harvest & buyers** tab remain public demonstration tools; they cannot access the private application database. The authenticated workspace does not load the demo offer directory.

Farmers can create multiple harvests, keep private drafts, publish to signed-in buyers, edit, archive and restore their own lots. Listings include quantity, variety, self-reported grade/condition, dates, pickup coordinates, notes and up to three photos. Use **Copy calculator details** to copy an existing form, then review it before publishing. Photos must be JPEG, PNG or WebP, up to 2 MB each. Publishing shares photos and the pickup point with buyer accounts; archived/private lots remain owner-only. A crop marked damaged or outside its delivery planning window cannot be published.

Buyers can browse published harvests that still fit their planning window, and post general quotes or quotes for a specific published lot. Terms include INR/kg price, minimum/maximum quantity, grade/variety, delivery coordinates, quote expiry, delivery deadline, partial-purchase support and an additional fixed selling charge. The buyer can edit or withdraw only their own offers. Expired and withdrawn quotes are excluded automatically from matching. A buyer's deadline can block a journey even when the crop's general lifetime budget would permit it.

Farmer comparisons reuse the existing offer validation, Haversine/Dijkstra, route transport, delivery checks and net-return ranking. Crop quantity, age, condition, grade and coordinates come from the farmer's stored listing; offer terms and destination come from the buyer's stored quote. Client-supplied copies cannot override either. Matched account quotes are labelled account-submitted, not independently verified. DSR remains unapplied. The **Prepare non-binding enquiry** action rechecks the stored records and produces a preview only. It does not create an accepted order, reserve quantity, send a message or process payment. Those belong to the next workflow phase.

### Permissions enforced by the API

| Account | Allowed access |
| --- | --- |
| Anonymous | Public calculator/demo APIs; register/sign in; no private listings, offers or photos |
| Farmer | Create/read/update/archive own harvests and photos; compare active matching quotes for own lots |
| Buyer | Read published harvests/photos; create/read/update/withdraw own buyer offers |

Ownership is derived from the authenticated database session, never an `owner_id`, role or identity in the request. Reading/editing another owner's private record returns 404. A role-inappropriate operation returns 403; an expired/missing session returns 401. Updates require the current numeric `version`; stale writes return 409 rather than silently overwriting another device's changes. Account roles are selected at registration and cannot be changed through the API.

### Storage and session setup

The server automatically creates application schema version 2 in `data/agrolink_app.sqlite3`, with an explicit additive migration from version 1 that preserves existing accounts, sessions, listings, photos and quotes. It is separate from `data/market_data.sqlite3` and existing CSVs. Tables also store orders, action request keys and timestamped order events. Reopening the browser, signing in elsewhere or restarting the backend preserves these records on that server. The application database and SQLite journal files are ignored by Git. Preserve/back up the database when retaining real pilot data; deleting it removes application accounts and records. No manual migration command, cloud service, API key or new runtime package is required.

Optional environment settings (the server does not automatically load `.env`):

- `AGROLINK_APP_DB`: alternate application database path.
- `AGROLINK_FRONTEND_ORIGIN`: exact browser origin for direct API access and CSRF origin checks. Local Vite proxies work with localhost/127.0.0.1 on port 5173.
- `AGROLINK_COOKIE_SECURE=1`: use Secure session cookies when deployed behind HTTPS; leave unset for local HTTP.

Passwords use salted PBKDF2-HMAC-SHA256 with 600,000 iterations. Only hashes are stored. Sessions use random opaque tokens with only their SHA-256 hashes in SQLite, seven-day expiry, HttpOnly/SameSite cookies and server-side logout invalidation. State-changing account requests require an origin check, a custom application header and an authenticated CSRF token (registration/login use the application header and origin check). The browser keeps the CSRF token in memory; credentials are not stored in local storage. Sign-in failures are throttled per IP/account pair, with an additional IP-wide limit; registrations are limited to 20 attempts per IP per 15 minutes. See the [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) for the underlying practices. These controls do not constitute a production security certification.

This remains a local/pilot application: the standard-library HTTP adapter is not a production deployment server. Public hosting needs HTTPS and a production hosting setup. Email verification, password recovery, business verification, payments, carrier tracking and dispute handling are not implemented. Orders and stock reservations are described below. Account names, grades and quotes are self-reported. Multi-crop price/delivery support, calibrated shelf-life prediction and fresh forecast data remain separate work.

### Account API routes

- `GET /api/auth/me`, `POST /api/auth/register`, `/api/auth/login`, `/api/auth/logout`.
- `GET/POST /api/app/listings`; `GET/PATCH/DELETE /api/app/listings/{id}` (DELETE archives).
- `POST /api/app/listings/{id}/photos`; `GET/DELETE /api/app/photos/{id}`.
- `GET/POST /api/app/offers`; `PATCH/DELETE /api/app/offers/{id}` (DELETE withdraws).
- `POST /api/app/listings/{id}/buyers` and `/selection` for owner-scoped live comparisons/enquiry previews.
- `GET/POST /api/app/orders`, `GET /api/app/orders/{id}`, `POST /api/app/orders/{id}` for a participant's order history, proposals and lifecycle actions.

Frontend requests send `X-Agrolink-Client: 1`, JSON bodies and the session's `X-CSRF-Token` for mutations. Session cookies are sent automatically. Photos are served with permission checks, declared image content types, `nosniff` and no-store caching. Uploaded content is bounded and must match a supported image signature. Limits are enforced on the server as well as the UI.

Account tests run against a temporary isolated SQLite database, with no seeded production users. Chrome scenarios exercise separate farmer/buyer contexts, real photo persistence, reload/login restoration, quote ranking, withdrawal, CSRF/role rejection, multiple drafts, archiving and mobile layout. Existing demo/forecast tests remain part of regression. The CSV and catalog loaders now serialize concurrent initial loads so multiple browser sessions do not allocate several copies of the 195 MB dataset.

Authenticated `GET /api/app/config` supplies delivery policy independently of the large market dataset. CSV cleaning parses repeated date values once and avoids converting native numeric columns to strings before converting them back. Cleaning and forecasting results remain covered by regression tests and the actual-data HTTP check. The local server defaults BLAS/OpenMP/MKL thread counts to one for its small statistical fits, while respecting explicitly configured environment values. The first historical forecast can take a few minutes on slower machines: `/listing-estimate` allows 180 seconds, while other frontend API requests retain the 120-second timeout. Live quote comparisons do not run the historical VAR fitting pipeline.

Verification on 2026-10-25: **179 Python tests, 11 frontend tests, all 17 Chrome scenarios and the production build passed**. Seven real-data HTTP comparison cases also passed with the prior historical price result preserved. Browser checks use a temporary application database, test accounts, a test photo and explicit test-location coordinates. They do not create production users or assert that sample locations are actual farms or verified buyers.

To try the live workflow locally: restart the backend, refresh the frontend, open **Accounts & marketplace**, and create a Farmer account. Save/publish a harvest. Use another browser or a private window to create a Buyer account, browse the published lot and post an offer. Return to the Farmer account and choose **Compare live buyer offers**. Two ordinary tabs on the same browser share a session cookie, so they cannot maintain two different signed-in identities simultaneously. Existing browser-only demo drafts are not silently migrated: restore a demo draft in its tab and explicitly copy/review the calculator details when saving an account listing.

Main implementation files: `backend/database.py`, `backend/accounts.py`, `backend/trading.py`, `backend/workspace_api.py`, and their integration in `backend/server.py` / `backend/buyers.py`. The frontend adds `AccountWorkspace.jsx`, `FarmerDashboard.jsx`, `BuyerDashboard.jsx`, `LiveComparison.jsx` and `WorkspaceFields.jsx`, reusing existing finance, shelf-life and location components. Coverage is in `backend/test_workspace.py`, `backend/test_dataset_loading.py` and `frontend/tests/accounts.spec.js`; browser tests use an isolated temporary app database and remove their own test files afterwards.

## Persisted order proposals and inventory reservations

This section supersedes earlier historical descriptions of orders and reservations as future work. In **Accounts & marketplace**, a farmer publishes a harvest, compares live offers and prepares the existing non-binding enquiry. After reviewing quantity, price, fees, pickup/delivery locations and deadlines, the farmer explicitly agrees and chooses **Send order proposal**. The named buyer reviews the saved terms under **Orders & reservations**, explicitly agrees and chooses **Accept & reserve quantity**. A proposal alone does not reserve stock. These are local application agreements between unverified accounts, not payment or legal-enforcement services.

The lifecycle is:

```text
Proposed → Accepted → Ready for pickup → Collected → Delivered → Completed
```

The farmer marks readiness; the buyer confirms collection and records delivery; the farmer acknowledges the recorded delivery outcomes to complete. The buyer may reject a proposal. Either participant may cancel before collection. Proposals expire at quote expiry. Accepted/ready reservations expire at the agreed delivery deadline. Expired uncollected quantities stop counting immediately in inventory/budget calculations; a transactional sweep on order reads and writes records the expiry event. There is no background notification or messaging service, so use **Refresh orders** to see the other party's changes.

Stock and purchase capacity are checked under a SQLite `BEGIN IMMEDIATE` transaction when the buyer accepts. Concurrent buyers cannot reserve more than the harvest's remaining quantity. **Maximum purchase quantity means a shared lifetime purchase budget for that offer**, including general offers across different farmers/listings. Accepted, collected, delivered and completed orders consume that budget. Cancellation or expiry before collection releases it. A new offer represents a separate declared budget; it is not independently verified demand. Marketplace comparisons use the remaining harvest and offer capacity. Partial orders require permission from both saved records. Decimal quantities and existing Decimal/paise financial calculations are retained.

Each proposal snapshots saved harvest/quote versions, price, quantity, charges, pickup/delivery locations, delivery deadline, route provenance and transport assumptions. Caller-supplied prices, identities and financial totals cannot replace those records. Live comparisons use the listing's saved transport settings and partial-sale permission; edit the listing to change them. If a listing or offer changes before acceptance, a new proposal is required. Once any quantity is reserved or consumed, its listing/quote terms are locked against editing to reset inventory; withdrawal/archiving does not alter an existing agreement. Use cancellation to release an uncollected reservation, or create a separate listing/offer for a separate lot/budget.

Routes and delivery feasibility are checked at proposal and acceptance. Collection rechecks harvest age, timing and the agreed deadline against the saved dependable route and transport assumptions; it does not claim a fresh traffic or carrier check. Limited delivery windows require acknowledgment. Buyer-declared accepted weight, actual grade and delivery/rejection notes are recorded separately from the immutable agreed terms. Short or rejected deliveries require a reason. Collected stock stays consumed: rejected weight is not automatically returned to saleable inventory. There is no post-collection cancellation or dispute resolution; a farmer who disputes outcomes leaves the delivered order open and resolves directly with the buyer.

Every successful transition appends an actor and UTC timestamp to the event history. Proposals and actions require an authenticated participant, CSRF/origin checks, explicit consent where applicable, record versions and unique request keys. Reusing a key for the same request safely returns its existing order; reusing it for different terms/actions returns a conflict. The UI retains request keys across network retries in the mounted view. After a reload, inspect persisted orders before submitting a new proposal. Orders are preserved by the additive version-2 migration and application database backups.

Implementation: [order service](backend/orders.py), [schema migration](backend/database.py), [HTTP integration](backend/workspace_api.py), [order workspace](frontend/src/components/OrderWorkspace.jsx). Focused regression coverage is in [order HTTP tests](backend/test_orders.py) and the mutual-agreement Chrome scenario in [account browser tests](frontend/tests/accounts.spec.js).

```powershell
& 'C:/Users/Durvank/AppData/Local/Programs/Python/Python313/python.exe' -B -m unittest backend.test_orders backend.test_workspace backend.test_buyers backend.test_buyer_ranking pricing.test_buyer_return logistics.test_delivery_life logistics.test_listing_route
```

The checked-in/local `.venv-local` launcher on this machine currently references a missing Python 3.14 installation. Recreate that environment or use the installed interpreter above (with the existing dependencies). For browser tests, set `AGROLINK_TEST_PYTHON` to the working interpreter before `npm.cmd run test:e2e` inside `frontend`.

Verification for the order/reservation change on 2026-10-25: **72 focused Python tests** (including 16 new order tests), **11 frontend utility tests**, **all four account Chrome scenarios** (including the new mutual-agreement/delivery scenario), and the **production frontend build** passed. The earlier 179-test/full-browser/actual-data results above are historical; those full suites were not rerun for this change. Tests used temporary application databases and synthetic test accounts, with the installed Python 3.13 interpreter.
