# Location, date and quality comparison

474 real-data HTTP cases; 474 returned the expected status. 0 assertion failures.

All price-only market/variety combinations were tested. Costs are INR 800 per 500 kg batch unless a case explicitly changes them. All prices below are INR/kg.

| Market | Variety | Origin | Model | Forecast | Lower | Midpoint | Upper |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| Rahata | Other | 2025-10-30 | RECENT_MEAN | 8.90 | 7.05 | 7.30 | 7.55 |
| Rahuri | Other | 2025-10-30 | SES | 11.45 | 9.60 | 9.85 | 10.10 |
| Sangamner | Other | 2025-10-30 | SES | 9.54 | 7.69 | 7.94 | 8.19 |
| Shrirampur | Other | 2025-10-30 | RECENT_MEAN | 11.80 | 9.95 | 10.20 | 10.45 |
| Chattrapati Sambhajinagar | Other | 2025-10-30 | SES | 12.17 | 10.32 | 10.57 | 10.82 |
| Bhusaval | Other | 2025-10-30 | LAST_OBSERVED | 12.00 | 10.15 | 10.40 | 10.65 |
| Kolhapur | Other | 2025-10-30 | RECENT_MEAN | 12.60 | 10.75 | 11.00 | 11.25 |
| Hingna | Local | 2025-10-30 | RECENT_MEAN | 17.88 | 16.03 | 16.28 | 16.53 |
| Kalmeshwar | Other | 2025-10-30 | LAST_OBSERVED | 18.05 | 16.20 | 16.45 | 16.70 |
| Kamthi | Local | 2025-10-30 | SES | 23.07 | 21.22 | 21.47 | 21.72 |
| Nagpur | Other | 2025-10-29 | RECENT_MEAN | 22.25 | 20.40 | 20.65 | 20.90 |
| Ramtek | Other | 2025-10-30 | LAST_OBSERVED | 18.00 | 16.15 | 16.40 | 16.65 |
| Nasik | Other | 2025-10-29 | LAST_OBSERVED | 5.25 | 3.40 | 3.65 | 3.90 |
| Pimpalgaon | Other | 2025-10-30 | LAST_OBSERVED | 10.55 | 8.70 | 8.95 | 9.20 |
| Khed(Chakan) | Other | 2025-10-30 | RECENT_MEAN | 9.80 | 7.95 | 8.20 | 8.45 |
| Pune | Local | 2025-10-30 | RECENT_MEAN | 10.10 | 8.25 | 8.50 | 8.75 |
| Pune(Khadiki) | Local | 2025-10-30 | SES | 8.56 | 6.71 | 6.96 | 7.21 |
| Pune(Manjri) | Other | 2025-10-30 | LAST_OBSERVED | 15.00 | 13.15 | 13.40 | 13.65 |
| Pune(Moshi) | Local | 2025-10-30 | LAST_OBSERVED | 12.50 | 10.65 | 10.90 | 11.15 |
| Pune(Pimpri) | Local | 2025-10-30 | SES | 14.67 | 12.82 | 13.07 | 13.32 |
| Panvel | Other | 2025-10-30 | SES | 32.65 | 30.80 | 31.05 | 31.30 |
| Patan | Other | 2025-10-28 | LAST_OBSERVED | 11.50 | 9.65 | 9.90 | 10.15 |
| Satara | Other | 2025-10-29 | LAST_OBSERVED | 12.50 | 10.65 | 10.90 | 11.15 |
| Vai | Local | 2025-10-30 | LAST_OBSERVED | 10.00 | 8.15 | 8.40 | 8.65 |
| Akluj | Local | 2025-10-30 | LAST_OBSERVED | 15.00 | 13.15 | 13.40 | 13.65 |
| Mangal Wedha | Local | 2025-10-30 | LAST_OBSERVED | 13.00 | 11.15 | 11.40 | 11.65 |
| Pandharpur | Other | 2025-10-30 | LAST_OBSERVED | 14.00 | 12.15 | 12.40 | 12.65 |

Quality A, B, C and Unspecified must give identical prices: no calibrated quality coefficients are configured. Market differences reflect different observed series and varieties; the location multiplier itself remains neutral.

Earlier harvest dates leave the forecast origin unchanged. They are not an as-of-date backtest. Current 2026 harvest requests and any calendar selling-date requests are rejected by the price-only path. Monthly VAR permits different selling days within its supported month; it does not produce day-specific prices.

All results are historical decision support. Missing history is rejected, not filled or replaced by another market.

See [all HTTP cases](scenario_comparison.csv) and [full results](scenario_comparison.json).
