import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from backend import server
import pandas as pd
from forecasting.var_forecaster import clean_mandi_data


class DatasetLoadingTests(unittest.TestCase):
    def test_date_and_numeric_fast_paths_preserve_cleaning(self):
        dates=['19 Aug 2013','20 Aug 2013','19 Aug 2013','not a date']
        raw=pd.DataFrame({'State Name':[' S ']*4,'District Name':[' D ']*4,
             'Market Name':[' M ']*4,'Variety':[' V ']*4,'Group':['Vegetables']*4,
             'Reported Date':dates,'Arrivals (Tonnes)':[2.,3.,2.,1.],
             'Min Price (Rs./Quintal)':[500.,600.,500.,100.],
             'Max Price (Rs./Quintal)':[900.,1000.,900.,200.],
             'Modal Price (Rs./Quintal)':[700.,800.,700.,150.]})
        numeric=clean_mandi_data(raw)
        formatted=raw.copy()
        for c in ['Arrivals (Tonnes)','Min Price (Rs./Quintal)','Max Price (Rs./Quintal)','Modal Price (Rs./Quintal)']:
            formatted[c]=formatted[c].map(lambda v:f'{v:,.1f}')
        text=clean_mandi_data(formatted)
        self.assertEqual(list(numeric['Reported Date']),list(pd.to_datetime(dates[:2],dayfirst=True)))
        self.assertEqual(list(numeric['Modal Price (Rs./Quintal)']),list(text['Modal Price (Rs./Quintal)']))
        self.assertEqual(len(numeric),2)

    def test_concurrent_cache_misses_share_one_csv_load(self):
        entered=threading.Event();release=threading.Event();start=threading.Barrier(4)
        marker=object()
        def load(path):
            entered.set()
            if not release.wait(5): raise RuntimeError('CSV loader test timed out.')
            return marker
        def caller():
            start.wait(timeout=5)
            return server.dataset()
        server._load_dataset.cache_clear()
        try:
            with patch.object(server,'load_mandi_csv',side_effect=load) as loader, patch.object(server,'clean_mandi_data',side_effect=lambda x:x):
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures=[pool.submit(caller) for _ in range(4)]
                    self.assertTrue(entered.wait(5))
                    release.set()
                    results=[f.result(timeout=5) for f in futures]
                self.assertEqual(loader.call_count,1)
                self.assertTrue(all(r is marker for r in results))
        finally:
            release.set();server._load_dataset.cache_clear()
