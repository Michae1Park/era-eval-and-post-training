# Forecast accuracy: defaults

Walk-forward: each forecast is made the day after a release, for the next quarter, with the agent's leakage probe on. Errors are absolute % errors against the first-reported SEC value.

## Against actuals

| Metric | Forecasts | Agent MdAPE | Naive MdAPE | Agent beats naive | 95% CI | Wilcoxon p |
|---|---|---|---|---|---|---|
| revenue | 48 | 2.6% | 2.9% | 23/48 | 34.5%–61.7% | 0.176 |
| main_kpi | 42 | 1.3% | 1.2% | 17/42 | 27.0%–55.5% | 0.856 |
| eps_diluted | 47 | 45.9% | 77.9% | 34/43 | 64.8%–88.6% | – |

## EPS against consensus (Alpha Vantage)

Scored on the same GAAP actual. 23 of 47 quarters have a matching basis (Alpha Vantage's reported EPS within 5% of SEC GAAP diluted EPS); 24 are excluded (adjusted vs GAAP, or split-adjusted).

- Agent closer than consensus: **10/23** (43.5%, 95% CI 25.6%–63.2%)
- MdAPE: agent 24.3%, consensus 22.2% (Wilcoxon p 0.709)

| Quadrant (large miss > 10%) | Quarters | Meaning |
|---|---|---|
| both_close | 2 | Normal quarter |
| agent_beat_street | 3 | Agent right, Street wrong |
| agent_missed | 5 | Agent's own error: investigate |
| both_missed | 13 | Genuine surprise |

| Ticker | Quarter | GAAP actual | Agent | Consensus | Agent APE | Consensus APE | Quadrant |
|---|---|---|---|---|---|---|---|
| ABNB | 2025Q1 | 0.24 | -0.12 | 0.24 | 151.1% | 0.0% | agent_missed |
| ABNB | 2025Q2 | 1.03 | 0.58 | 0.94 | 43.7% | 8.7% | agent_missed |
| ABNB | 2025Q3 | 2.21 | 2.03 | 2.32 | 8.3% | 5.0% | both_close |
| ABNB | 2025Q4 | 0.56 | 0.43 | 0.66 | 23.3% | 17.9% | both_missed |
| BKNG | 2026Q2 | 2.53 | 2.22 | 2.45 | 12.4% | 3.2% | agent_missed |
| CART | 2025Q2 | 0.41 | 0.26 | 0.39 | 36.0% | 4.9% | agent_missed |
| CART | 2025Q3 | 0.51 | 0.53 | 0.79 | 3.9% | 54.9% | agent_beat_street |
| CART | 2026Q2 | 0.45 | 0.42 | 0.55 | 7.0% | 22.2% | agent_beat_street |
| DASH | 2025Q1 | 0.44 | 0.19 | -0.04 | 57.1% | 109.1% | both_missed |
| DASH | 2025Q2 | 0.65 | 0.18 | 0.43 | 72.7% | 33.9% | both_missed |
| DASH | 2025Q3 | 0.55 | 0.44 | 0.68 | 19.7% | 23.6% | both_missed |
| DASH | 2025Q4 | 0.48 | 0.38 | 0.58 | 21.8% | 20.8% | both_missed |
| DASH | 2026Q1 | 0.42 | 0.42 | 0.364 | 1.0% | 13.3% | agent_beat_street |
| DASH | 2026Q2 | 0.46 | 0.48 | 0.5 | 4.8% | 8.7% | both_close |
| EXPE | 2025Q3 | 7.33 | 6.01 | 6.95 | 18.1% | 5.2% | agent_missed |
| LYFT | 2026Q2 | 0.13 | 0.07 | 0.17 | 45.9% | 30.8% | both_missed |
| TRIP | 2025Q2 | 0.28 | 0.19 | 0.18 | 31.0% | 35.7% | both_missed |
| UBER | 2025Q1 | 0.83 | 0.44 | 0.69 | 47.5% | 16.9% | both_missed |
| UBER | 2025Q2 | 0.63 | 0.56 | 0.82 | 11.3% | 30.2% | both_missed |
| UBER | 2025Q3 | 3.11 | 0.63 | 0.69 | 79.9% | 77.8% | both_missed |
| UBER | 2025Q4 | 0.14 | 0.75 | 0.78 | 434.2% | 457.1% | both_missed |
| UBER | 2026Q1 | 0.13 | 0.71 | 0.71 | 449.9% | 446.1% | both_missed |
| UBER | 2026Q2 | 1.17 | 0.89 | 0.83 | 24.3% | 29.1% | both_missed |
