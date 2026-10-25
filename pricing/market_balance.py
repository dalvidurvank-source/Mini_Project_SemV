"""Engine-owned DSR from matched, attributable backend supply/demand records.

Arrivals alone never stand in for demand. Missing evidence yields a neutral
factor. The optional CSV is maintained by the operator, not farmer input.
"""
import csv
import calendar
import os
from datetime import date
from pathlib import Path

from pricing.fair_price_engine import calculate_dsr, calculate_dsr_multiplier

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('crop','state','district','market','variety','period_start','period_end',
          'supply_kg','demand_kg','source','available_on')


def market_balance(selection, target_month, as_of):
    result = {'status':'unavailable', 'ratio':None, 'multiplier':1.0,
              'supply_kg':None, 'demand_kg':None, 'source':None,
              'period':target_month, 'reason':'No matched, measured regional demand and supply record is available. Arrivals are supply, not demand.'}
    path = Path(os.environ.get('AGROLINK_BALANCE_CSV', ROOT/'data/market_balance.csv'))
    if not path.is_file():
        return result
    try:
        with path.open(encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            if not set(FIELDS).issubset(reader.fieldnames or []):
                raise ValueError('Supply/demand file is missing required columns.')
            records = []
            for row in reader:
                if any(row[k] != selection.get(k, 'Tomato' if k == 'crop' else '') for k in ('crop','state','district','market','variety')):
                    continue
                start, end = date.fromisoformat(row['period_start']), date.fromisoformat(row['period_end'])
                # Only complete matching calendar months; no cross-unit or cross-period inference.
                year, month = map(int, target_month.split('-'))
                if (start, end) != (date(year,month,1), date(year,month,calendar.monthrange(year,month)[1])):
                    continue
                available = date.fromisoformat(row['available_on'])
                if available > as_of:
                    continue
                if not row['source'].strip():
                    raise ValueError('Supply/demand evidence has no source.')
                ratio = calculate_dsr(row['supply_kg'],row['demand_kg'])
                records.append((row,ratio))
        if not records:
            return result
        if len(records) != 1:
            raise ValueError('Conflicting or duplicate supply/demand evidence for this market and month.')
        row, ratio = records[0]
        sensitivity = float(os.environ.get('AGROLINK_DSR_SENSITIVITY','0.10'))
        multiplier = calculate_dsr_multiplier(ratio,sensitivity)
        return {**result, 'status':'available','ratio':ratio,'multiplier':multiplier,
                'supply_kg':float(row['supply_kg']),'demand_kg':float(row['demand_kg']),
                'source':row['source'], 'available_on':row['available_on'],
                'sensitivity':sensitivity, 'reason':'Matched backend supply and demand evidence; sensitivity is configured policy, not a learned relationship.'}
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return {**result, 'status':'invalid_evidence', 'reason':f'DSR was left neutral: {exc}'}
