

Canadian Cash Flow Forecaster is a Streamlit app for small businesses that uploads invoices and expenses, predicts future cash flow in CAD, flags liquidity risk, and gives practical recommendations to improve collections and control spending.
=======


A Streamlit dashboard that helps Canadian small businesses forecast short-term cash flow, monitor collection risk, and make better spending decisions. The app supports invoice and expense CSV uploads, shows projected cash balance, flags liquidity risk, and provides owner-friendly recommendations.

## What it does

- Upload invoice and expense CSV files
- Forecast cash flow in CAD
- Estimate business risk and cash pressure
- Highlight collection delays and recurring cost burden
- Show charts and downloadable forecast reports

## Sample CSV format

Invoices:

```csv
date,customer,invoice_amount,days_to_pay,status
2026-05-01,Maple Foods,8500,18,Paid
```

Expenses:

```csv
date,vendor,expense_amount,category,recurring
2026-05-02,Office Supply Co,1200,Operations,Yes
```

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

## Why this project matters

Cash flow is one of the biggest challenges for small businesses, especially when invoices are delayed and expenses stay fixed. This project turns that problem into a useful dashboard with real business value.
>>>>>>> 6f11ee2 (Initial commit)
