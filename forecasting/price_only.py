"""Price-only reporting-session forecasts. No missing dates are imputed.

Thresholds below are configurable engineering policies, not accuracy promises.
Every candidate is refit at each chronological origin. Selection uses an earlier
window; the final window is evaluated only after the winner is frozen.
"""
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
import os
import json
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import SimpleExpSmoothing

ROOT = Path(__file__).resolve().parents[1]
FILES = (ROOT / 'price_data.csv', ROOT / 'price_data (25-26).csv')
UNIT_CONFIG = ROOT / 'backend/price_only_units.json'
COLUMNS = ('t', 'cmdty', 'market_id', 'market_name', 'state_id', 'state_name',
           'district_id', 'district_name', 'variety', 'p_min', 'p_max', 'p_modal')
KEYS = ['t', 'cmdty', 'market_id', 'variety']
CANDIDATES = ('LAST_OBSERVED', 'RECENT_MEAN', 'SES')


@dataclass(frozen=True)
class Policy:
    min_train: int = 10
    selection_count: int = 5
    test_count: int = 5
    max_gap_days: int = 7
    mean_window: int = 5

    def __post_init__(self):
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in asdict(self).values()):
            raise ValueError('All price-only policy values must be positive integers.')
        if self.min_train < 3:
            raise ValueError('Minimum training history must be at least 3 sessions.')

    @classmethod
    def environment(cls):
        return cls(**{k: int(os.environ.get('AGROLINK_PO_' + k.upper(), v)) for k, v in asdict(cls()).items()})


def unit_configuration():
    unit = os.environ.get('AGROLINK_PRICE_ONLY_UNIT', '')
    evidence = os.environ.get('AGROLINK_PRICE_ONLY_UNIT_EVIDENCE', '').strip()
    # Explicit environment overrides must provide a complete pair. Otherwise
    # use the persisted confirmation scoped to the two named source exports.
    if not any(key in os.environ for key in ('AGROLINK_PRICE_ONLY_UNIT','AGROLINK_PRICE_ONLY_UNIT_EVIDENCE')):
        try:
            saved = json.loads(UNIT_CONFIG.read_text(encoding='utf-8'))
            if isinstance(saved, dict) and sorted(saved.get('files', [])) == sorted(p.name for p in FILES):
                unit = saved.get('unit', '')
                evidence = saved.get('evidence', '')
                evidence = evidence.strip() if isinstance(evidence,str) else ''
        except (OSError, ValueError, TypeError):
            pass
    valid = unit in ('INR/quintal', 'INR/kg') and bool(evidence)
    return {'configured': valid, 'unit': unit if valid else 'unverified source price units',
            'evidence': evidence if valid else None,
            'reason': None if valid else 'Price units are unverified. Converted recommendations remain disabled until the export currency and weight unit are confirmed by the administrator.'}


def load_sources(paths=FILES):
    frames, audit = [], []
    for path in paths:
        raw = pd.read_csv(path, dtype='string')
        missing = sorted(set(COLUMNS) - set(raw.columns))
        if missing:
            raise ValueError(f'{path.name}: missing columns: {missing}')
        data = raw[list(COLUMNS)].copy()
        raw_duplicates = int(data.duplicated().sum())
        data['t'] = pd.to_datetime(data['t'], format='%Y-%m-%d', errors='coerce')
        invalid_date = data['t'].isna()
        for key in COLUMNS[1:9]:
            data[key] = data[key].str.strip()
        for key in ('p_min', 'p_max', 'p_modal'):
            data[key] = pd.to_numeric(data[key], errors='coerce')
        numeric = data[['p_min', 'p_max', 'p_modal']].to_numpy(dtype=float, na_value=np.nan)
        valid_price = pd.Series(np.isfinite(numeric).all(axis=1), index=data.index)
        valid_price &= (data.p_min >= 0) & (data.p_modal > 0) & (data.p_min <= data.p_modal) & (data.p_modal <= data.p_max)
        valid_names = data[list(COLUMNS[1:9])].notna().all(axis=1) & data[list(COLUMNS[1:9])].ne('').all(axis=1)
        valid_ids = data[['market_id','state_id','district_id']].apply(lambda c: c.str.fullmatch(r'\d+').fillna(False)).all(axis=1)
        valid = (~invalid_date & valid_price & valid_names & valid_ids & data.cmdty.str.casefold().eq('tomato')).fillna(False)
        data = data.loc[valid].copy()
        for key in ('market_id','state_id','district_id'):
            data[key] = data[key].map(lambda v: str(int(v)))
        audit.append({'file': path.name, 'raw_rows': len(raw), 'valid_rows_before_deduplication': len(data),
                      'exact_duplicates': raw_duplicates, 'invalid_dates': int(invalid_date.sum()),
                      'invalid_prices': int((~valid_price.fillna(False)).sum()),
                      'rejected_rows': int((~valid).sum()), 'missing_cells': int(raw.isna().sum().sum()),
                      'first_date': data.t.min().date().isoformat() if len(data) else None,
                      'last_date': data.t.max().date().isoformat() if len(data) else None,
                      'observed_months': sorted(data.t.dt.strftime('%Y-%m').unique().tolist()),
                      'market_count': int(data.market_id.nunique()),
                      'possible_export_limit': len(raw) == 1000,
                      'export_limit_note': 'Exactly 1,000 rows: possible export/page limit; completeness is not verified.' if len(raw) == 1000 else 'Completeness is not verified.'})
        data['source_file'] = path.name
        frames.append(data)
    combined = pd.concat(frames, ignore_index=True)
    # Only byte-equivalent normalized observations are deduplicated; preserve all
    # contributing filenames even when a duplicate appeared in multiple exports.
    columns = list(COLUMNS)
    combined = combined.groupby(columns, dropna=False, as_index=False).agg(source_files=('source_file', lambda s: sorted(set(s))))
    return combined.sort_values('t').reset_index(drop=True), audit


@lru_cache(maxsize=1)
def source_data():
    return load_sources()


def market_catalog():
    data, _ = source_data()
    columns = ['state_name', 'district_name', 'market_name', 'market_id', 'variety']
    records = data[columns].drop_duplicates().sort_values(columns).rename(columns={'state_name':'state','district_name':'district','market_name':'market'})
    return records.to_dict('records')


def series_for(market_id, variety):
    data, _ = source_data()
    rows = data[(data.market_id == str(market_id)) & (data.variety == variety)].copy()
    if rows.empty:
        raise ValueError('Unknown price-only market ID / variety combination.')
    return rows


def prepare_segment(rows, policy):
    rows = rows.sort_values('t').copy()
    if rows.duplicated(KEYS, keep=False).any():
        raise ValueError('Conflicting observations for the same market, variety and reporting date. Resolve the source conflict first.')
    for key in ('market_name', 'district_id', 'state_id'):
        if rows[key].nunique() != 1:
            raise ValueError('Conflicting market metadata. An explicit identity reconciliation is required.')
    gaps = rows.t.diff().dt.days
    cuts = np.flatnonzero((gaps > policy.max_gap_days).to_numpy())
    start = int(cuts[-1]) if len(cuts) else 0
    return rows.iloc[start:].copy(), {'excluded_earlier_sessions': start,
            'long_gap_count': int((gaps > policy.max_gap_days).sum()),
            'largest_gap_days': int(gaps.max()) if len(rows) > 1 else 0}


def predict(values, method, policy):
    values = np.asarray(values, dtype=float)
    if not len(values) or not np.isfinite(values).all() or np.any(values <= 0):
        raise ValueError('Prices must be positive and finite.')
    if method == 'LAST_OBSERVED':
        result = values[-1]
    elif method == 'RECENT_MEAN':
        result = values[-policy.mean_window:].mean()
    elif method == 'SES':
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            fitted = SimpleExpSmoothing(values, initialization_method='estimated').fit(optimized=True)
        if any('converg' in str(w.message).lower() for w in caught):
            raise ValueError('Smoothing optimization did not converge.')
        result = fitted.forecast(1)[0]
    else:
        raise ValueError('Unknown forecast model.')
    if not np.isfinite(result) or result <= 0:
        raise ValueError('The model produced a non-positive or non-finite forecast.')
    return float(result)


def evaluate(values, dates, method, start, stop, policy):
    points = []
    for target in range(start, stop):
        forecast = predict(values[:target], method, policy)
        points.append({'origin': dates[target-1], 'target': dates[target], 'actual': float(values[target]), 'prediction': forecast})
    errors = np.array([p['prediction'] - p['actual'] for p in points])
    with np.errstate(over='ignore', invalid='ignore'):
        mae, rmse = float(np.abs(errors).mean()), float(np.sqrt(np.square(errors).mean()))
    if not np.isfinite([mae,rmse]).all():
        raise ValueError('Evaluation produced non-finite error metrics.')
    return {'MAE': mae, 'RMSE': rmse,
            'count': len(points), 'first_target': points[0]['target'], 'last_target': points[-1]['target'], 'points': points}


def backtest(rows, policy=None):
    policy = policy or Policy.environment()
    base = {'status': 'unavailable', 'policy': asdict(policy), 'horizon': {'value':1,'unit':'reporting_session'},
            'forecast_date': None, 'statistical_interval': None}
    try:
        segment, gap_info = prepare_segment(rows, policy)
    except ValueError as exc:
        return {**base, 'reason': str(exc)}
    n = len(segment)
    required = policy.min_train + policy.selection_count + policy.test_count
    base.update({'gap_info':gap_info, 'segment_sessions':n, 'required_sessions':required,
                 'missing_calendar_days':int((rows.t.max()-rows.t.min()).days+1-len(rows)),
                 'segment_missing_calendar_days':int((segment.t.max()-segment.t.min()).days+1-n),
                 'segment_start': segment.t.iloc[0].date().isoformat(), 'forecast_origin':segment.t.iloc[-1].date().isoformat()})
    if n < required:
        return {**base, 'reason':f'Insufficient history: latest usable segment has {n} reporting sessions; policy requires {required} ({policy.min_train} training + {policy.selection_count} selection + {policy.test_count} final evaluation).'}
    values = segment.p_modal.to_numpy(dtype=float)
    dates = segment.t.dt.strftime('%Y-%m-%d').tolist()
    selection_start = n - policy.selection_count - policy.test_count
    final_start = n - policy.test_count
    selection, failures = {}, {}
    for candidate in CANDIDATES:
        try:
            selection[candidate] = evaluate(values, dates, candidate, selection_start, final_start, policy)
        except (ValueError, RuntimeError, FloatingPointError, np.linalg.LinAlgError) as exc:
            failures[candidate] = str(exc)
    # Baseline must be measurable. Ties choose simpler candidates in declared order.
    if 'LAST_OBSERVED' not in selection:
        return {**base, 'reason':'Baseline evaluation failed.', 'candidate_failures':failures}
    winner = min(selection, key=lambda k: (selection[k]['MAE'], CANDIDATES.index(k)))
    try:
        final = evaluate(values, dates, winner, final_start, n, policy)
        baseline_final = final if winner == 'LAST_OBSERVED' else evaluate(values, dates, 'LAST_OBSERVED', final_start, n, policy)
        forecast = predict(values, winner, policy)
    except (ValueError, RuntimeError, FloatingPointError, np.linalg.LinAlgError) as exc:
        return {**base, 'reason':f'Frozen winner failed final evaluation or forecasting: {exc}', 'selection':selection, 'selected_model':winner}
    warnings_out = ['Forecast is for the next reporting session, not the next calendar day. No target calendar date is known.',
                    'Short-series backtests are diagnostic; no accuracy guarantee or calibrated confidence interval is provided.',
                    'Export completeness is unverified; consult the source audit for possible row limits.']
    if winner != 'LAST_OBSERVED' and final['MAE'] >= baseline_final['MAE']:
        warnings_out.append('The frozen selected model did not beat the last-observed baseline on final holdout. It was not reselected using this holdout.')
    return {**base, 'status':'eligible', 'reason':None, 'selected_model':winner, 'prediction':forecast,
            'selection':selection, 'evaluation': final, 'baseline_evaluation':baseline_final,
            'candidate_failures':failures, 'warnings':warnings_out}


@lru_cache(maxsize=256)
def cached_backtest(market_id, variety, policy):
    return backtest(series_for(market_id, variety), policy)
