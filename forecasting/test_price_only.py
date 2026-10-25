"""Small deterministic fixtures, separate from all production CSVs."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

from forecasting.price_only import COLUMNS, Policy, backtest, load_sources, prepare_segment, predict


def observations(n=25, values=None, start='2025-09-01'):
    values = values if values is not None else [100.] * n
    return pd.DataFrame({'t':pd.date_range(start, periods=len(values)), 'cmdty':'Tomato',
        'market_id':'172','market_name':'Pune','state_id':'27','state_name':'Maharashtra',
        'district_id':'521','district_name':'Pune','variety':'Local',
        'p_min':0.,'p_max':10000.,'p_modal':values,'source_files':[['test.csv'] for _ in values]})


class LoaderTests(unittest.TestCase):
    def load(self, frames):
        with TemporaryDirectory() as tmp:
            paths = []
            for i, frame in enumerate(frames):
                path = Path(tmp) / f'fixture{i}.csv'
                data = frame[list(COLUMNS)].copy()
                data['t'] = data['t'].map(lambda v: v.strftime('%Y-%m-%d') if isinstance(v, pd.Timestamp) else v)
                data.to_csv(path, index=False)
                paths.append(path)
            return load_sources(paths)

    def test_duplicate_observations_preserve_source_provenance(self):
        rows, audit = self.load([observations(2), observations(2)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows.source_files.iloc[0], ['fixture0.csv','fixture1.csv'])
        self.assertEqual(audit[0]['raw_rows'], 2)
        self.assertFalse(audit[0]['possible_export_limit'])

    def test_bad_dates_nonfinite_prices_and_inconsistent_prices_rejected(self):
        frame = observations(5)
        frame['t'] = frame.t.astype(object)
        frame.loc[0,'t'] = 'invalid'
        frame.loc[1,'p_modal'] = float('inf')
        frame.loc[2,'p_modal'] = -1
        frame.loc[3,'p_max'] = 50
        rows, audit = self.load([frame])
        self.assertEqual(len(rows), 1)
        self.assertEqual(audit[0]['rejected_rows'],4)
        self.assertEqual(audit[0]['invalid_dates'],1)
        self.assertEqual(audit[0]['invalid_prices'],3)

    def test_conflicts_are_not_averaged_or_discarded(self):
        first, second = observations(2), observations(2)
        second.loc[0,'p_modal'] = 150
        rows, _ = self.load([first,second])
        with self.assertRaisesRegex(ValueError,'Conflicting observations'):
            prepare_segment(rows, Policy())

    def test_loader_does_not_create_arrivals(self):
        rows, _ = self.load([observations(3)])
        self.assertNotIn('arrival_volume', rows)
        self.assertNotIn('Arrivals (Tonnes)', rows)


class ForecastTests(unittest.TestCase):
    def test_long_gaps_split_segment_without_imputation(self):
        rows = pd.concat([observations(15,start='2025-01-01'),observations(12,start='2025-09-01')])
        segment, gaps = prepare_segment(rows, Policy())
        self.assertEqual(len(segment),12)
        self.assertEqual(gaps['excluded_earlier_sessions'],15)
        report = backtest(rows)
        self.assertEqual(report['status'],'unavailable')
        self.assertIn('12 reporting sessions',report['reason'])

    def test_insufficient_history_is_explicit(self):
        report = backtest(observations(19))
        self.assertEqual(report['status'],'unavailable')
        self.assertEqual(report['required_sessions'],20)

    def test_ties_prefer_last_price_baseline(self):
        report = backtest(observations())
        self.assertEqual(report['status'],'eligible')
        self.assertEqual(report['selected_model'],'LAST_OBSERVED')
        self.assertEqual(report['prediction'],100)
        self.assertEqual(report['evaluation']['MAE'],0)
        self.assertIsNone(report['forecast_date'])
        self.assertIsNone(report['statistical_interval'])

    def test_average_window_uses_only_recent_history(self):
        self.assertEqual(predict([1,2,3,4,5,6], 'RECENT_MEAN', Policy()),4)

    def test_final_holdout_does_not_change_model_selection(self):
        a, b = observations(), observations()
        b.loc[20:,'p_modal'] = [1000,2000,3000,4000,5000]
        ra, rb = backtest(a), backtest(b)
        self.assertEqual(ra['selection'],rb['selection'])
        self.assertEqual(ra['selected_model'],rb['selected_model'])
        self.assertNotEqual(ra['evaluation']['MAE'],rb['evaluation']['MAE'])

    def test_every_rolling_prediction_receives_only_past_values(self):
        original = predict
        histories=[]
        def spy(values, method, policy):
            histories.append((len(values),list(values)))
            return original(values,method,policy)
        rows = observations(values=list(range(100,125)))
        with patch('forecasting.price_only.predict',side_effect=spy):
            report = backtest(rows)
        for length, values in histories:
            self.assertEqual(values,list(range(100,100+length)))
        for point in report['evaluation']['points']:
            self.assertLess(point['origin'],point['target'])
        self.assertLess(report['selection'][report['selected_model']]['last_target'], report['evaluation']['first_target'])

    def test_failed_smoothing_candidate_cannot_win(self):
        original = predict
        def sometimes(values, method, policy):
            if method == 'SES':
                raise ValueError('test model failure')
            return original(values,method,policy)
        with patch('forecasting.price_only.predict',side_effect=sometimes):
            report = backtest(observations())
        self.assertEqual(report['selected_model'],'LAST_OBSERVED')
        self.assertIn('SES',report['candidate_failures'])

    def test_nonfinite_or_nonpositive_forecasts_rejected(self):
        fitted = MagicMock()
        fitted.forecast.return_value = [np.nan]
        with patch('forecasting.price_only.SimpleExpSmoothing') as model:
            model.return_value.fit.return_value = fitted
            with self.assertRaisesRegex(ValueError,'non-finite'):
                predict([100]*10,'SES',Policy())
        for bad in (np.nan,np.inf,-1,0):
            with self.assertRaises(ValueError):
                predict([100,bad],'LAST_OBSERVED',Policy())

    def test_policy_is_validated(self):
        for values in ({'min_train':0},{'test_count':0},{'max_gap_days':-1},{'selection_count':True}):
            with self.assertRaises(ValueError):
                Policy(**values)


if __name__ == '__main__':
    unittest.main()
