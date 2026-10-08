# AgroLink — Algorithmic Fair-Price Agricultural Marketplace

AgroLink is a farmer-to-consumer agricultural marketplace designed to improve price transparency and reduce dependency on intermediaries. The system combines agricultural market data, time-series forecasting, transportation costs, and demand–supply conditions to generate an explainable **Fair Price Band** for agricultural produce.

## Key Features

* Farmer and consumer marketplace
* Agricultural produce listings
* Historical market-data analysis
* **VAR (Vector Autoregression) price forecasting**
* **VAR Base Market Price** prediction
* Nearest-market/hub transportation-cost calculation
* Demand–supply analysis
* Algorithmic Fair Price Calculator Engine
* Explainable fair-price breakdown
* Configurable fair-price range
* Order and listing management

## Pricing Pipeline

```text
Agricultural Market Data
          ↓
    Data Processing
          ↓
     VAR Forecast
          ↓
  VAR Base Market Price
          ↓
 ┌────────┼─────────┐
 ↓        ↓         ↓
Transport D/S    Platform
  Cost   Effect   Overhead
 └────────┼─────────┘
          ↓
   Fair Price Engine
          ↓
    Fair Price Band
```

The **VAR forecast is the Base Market Price, not the final fair price**. The Fair Price Engine combines it with transportation, demand–supply, and platform-cost factors.

## Technology

* **Python** — Forecasting and pricing algorithms
* **VAR / Time-Series Analysis** — Market-price forecasting
* **FastAPI** — Backend/API
* **Database** — Marketplace and agricultural data
* **Mermaid** — UML and DFD documentation

## Project Structure

```text
AgroLink/
├── forecasting/
│   └── var_forecaster.py
├── pricing/
│   └── fair_price.py
├── tests/
├── data/
│   └── tomato.csv
├── api/
├── frontend/
└── README.md
```

## Main Workflow

1. Farmer creates a produce listing.
2. AgroLink retrieves relevant agricultural market data.
3. The VAR model forecasts the next-period wholesale price.
4. The forecast becomes the **VAR Base Market Price**.
5. Transportation cost is calculated using the relevant nearest hub.
6. Demand and supply are analyzed.
7. The Fair Price Engine combines these factors.
8. AgroLink generates a recommended **Fair Price and Fair Price Band**.
9. The result is displayed with an explainable price breakdown.

## Initial Use Case

The initial implementation focuses on **tomato** market-price forecasting using historical Indian agricultural market data.

## Testing

Run the Python test suite with:

```bash
python -m unittest discover
```

The pricing module is designed to be independently testable and includes validation for demand–supply calculations, transportation units, pricing bounds, and edge cases.

## Project Goal

AgroLink aims to provide a **transparent, explainable, and data-driven agricultural pricing mechanism** while connecting farmers and consumers through a direct digital marketplace.

