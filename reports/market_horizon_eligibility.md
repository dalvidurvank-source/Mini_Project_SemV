# Market and horizon eligibility report

Generated: 2026-10-23T06:54:10.342016+00:00

## Verified official-source contract

- Resource: `9ef84268-d588-465a-a308-a864a43d0070` ([official page](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi)).
- Authentication: `api-key` is required. A personal key requires portal login; the documented sample key is capped at 10 rows per response.
- Pagination: `offset` and `limit`. The importer advances by the returned count, checks `count`, and refuses changing/truncated totals.
- Available filters: state, district, market, commodity, variety and grade. No observation-date filter is exposed.
- Fields: state, district, market, commodity, variety, grade, arrival date, minimum, maximum and modal price.
- The API supplies no market ID and does not declare price currency/weight units. AgroLink does not infer either.
- Live test on 2026-10-23 returned two Maharashtra tomato records dated 2026-10-23. A subsequent command received HTTP 429; the OAS page gave no numeric quota.
- The current resource is a snapshot and did not supply 60–90 historical sessions. Import official historical CSV exports to build an eligible series.

## Tested examples

- Recorded: Pune(Pimpri) on 2026-10-23 had modal price 1250.0 in unverified source units. The response contains `forecast: null`.
- Historical evaluation: Pune ID 172 target 2025-10-30; training ended 2025-10-29; actual 850.0 and forecast 1080.0 INR/quintal. The selected RECENT_MEAN model had final MAE 112.00, RMSE 158.49 over 5 targets; last-price baseline MAE 120.00.

## Eligibility

| Source | Market / variety / grade | Sessions | Latest | Recorded | Historical evaluation | Future | Reason |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| Official import | Pune(Pimpri) / Local / Local | 1 | 2026-10-23 | yes | no | no | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Official import | APMC Ratnagiri (Nachane) / Other / Local | 1 | 2026-10-23 | yes | no | no | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Ahmednagar (ID 153) / Other | 1 | 2025-10-28 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Rahata (ID 2382) / Other | 23 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Rahuri (ID 1803) / Other | 28 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Rahuri(Songaon) (ID 3114) / Other | 2 | 2025-10-07 | yes | no | no (stale) | Insufficient history: latest usable segment has 2 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Sangamner (ID 848) / Other | 23 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Shrirampur (ID 1435) / Other | 28 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Amrawati(Frui & Veg. Market) (ID 3111) / Local | 4 | 2025-10-29 | yes | no | no (stale) | Insufficient history: latest usable segment has 4 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Chattrapati Sambhajinagar (ID 581) / Other | 24 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Chandrapur(Ganjwad) (ID 2510) / Other | 18 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 18 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Bhusaval (ID 1438) / Other | 29 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Jalgaon (ID 159) / Other | 3 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 3 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Kolhapur (ID 160) / Other | 29 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Vadgaonpeth (ID 1453) / Local | 3 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 3 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Mumbai (ID 162) / Other | 5 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 5 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Hingna (ID 4754) / Local | 23 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Kalmeshwar (ID 1505) / Other | 28 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Kamthi (ID 3972) / Local | 33 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Nagpur (ID 163) / Local | 24 | 2025-10-30 | yes | no | no (stale) | Frozen winner failed final evaluation or forecasting: Smoothing optimization did not converge. |
| Root exports | Nagpur (ID 163) / Other | 23 | 2025-10-29 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Parshiwani (ID 2118) / Local | 5 | 2025-10-27 | yes | no | no (stale) | Insufficient history: latest usable segment has 5 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Ramtek (ID 2117) / Other | 20 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Navapur (ID 2074) / Other | 1 | 2024-12-31 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Chandvad (ID 574) / Local | 3 | 2025-10-04 | yes | no | no (stale) | Insufficient history: latest usable segment has 3 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Dindori (ID 1449) / Other | 10 | 2025-10-27 | yes | no | no (stale) | Insufficient history: latest usable segment has 10 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Ghoti (ID 1826) / Other | 1 | 2025-10-28 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Lasalgaon (ID 169) / Other | 1 | 2025-10-23 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Nasik (ID 168) / Other | 25 | 2025-10-29 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Pimpalgaon (ID 170) / Other | 24 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Junnar(Narayangaon) (ID 3960) / Local | 5 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 5 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Junnar(Otur) (ID 2492) / Local | 1 | 2025-09-29 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Khed(Chakan) (ID 2493) / Other | 27 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Manchar (ID 577) / Other | 8 | 2025-10-17 | yes | no | no (stale) | Insufficient history: latest usable segment has 8 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Pune (ID 172) / Local | 30 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Pune(Khadiki) (ID 2495) / Local | 29 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Pune(Manjri) (ID 4751) / Other | 28 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Pune(Moshi) (ID 4752) / Local | 27 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Pune(Pimpri) (ID 2494) / Local | 36 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Panvel (ID 1799) / Other | 33 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Ratnagiri (Nachane) (ID 1823) / Other | 2 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 2 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Islampur (ID 1457) / Other | 17 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 17 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Palus (ID 2081) / Other | 1 | 2025-10-26 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Vita (ID 2080) / Other | 1 | 2025-10-28 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Karad (ID 1459) / Other | 4 | 2025-10-29 | yes | no | no (stale) | Insufficient history: latest usable segment has 4 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Patan (ID 1831) / Other | 20 | 2025-10-28 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Phaltan (ID 1461) / Other | 8 | 2025-10-18 | yes | no | no (stale) | Insufficient history: latest usable segment has 8 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Satara (ID 1462) / Other | 26 | 2025-10-29 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Vai (ID 1464) / Local | 20 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Akluj (ID 1806) / Local | 21 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Akluj (ID 1806) / Other | 1 | 2024-12-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 1 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Mangal Wedha (ID 1467) / Local | 29 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Pandharpur (ID 579) / Other | 21 | 2025-10-30 | yes | yes | no (stale) | One-session model evaluated; future blocked by freshness |
| Root exports | Solapur (ID 176) / Other | 4 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 4 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Kalyan (ID 177) / Other | 4 | 2025-10-30 | yes | no | no (stale) | Insufficient history: latest usable segment has 4 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |
| Root exports | Murbad (ID 2067) / Other | 2 | 2024-12-13 | yes | no | no (stale) | Insufficient history: latest usable segment has 2 reporting sessions; policy requires 20 (10 training + 5 selection + 5 final evaluation). |

Historical mode forecasts a known reporting session and always trains on dates strictly before the target. Publication timestamps are unavailable, so results are not described as fully point-in-time simulations.
Future mode supports only one subsequent reporting session, never an exact calendar date. Longer horizons remain unavailable.
