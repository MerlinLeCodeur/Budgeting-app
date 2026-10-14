from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import storage

BASE_DIR = Path(getattr(storage, "BASE_DIR", Path(__file__).resolve().parent))
WEALTH_JSON = BASE_DIR / "wealth.json"

def load():
    default = {"starting_cash": 0.0, "cash_start_date": None, "snapshots": []}
    if not WEALTH_JSON.exists():
        return default
    try:
        x = json.loads(WEALTH_JSON.read_text())
        return {"starting_cash": float(x.get("starting_cash", 0)),
                "cash_start_date": x.get("cash_start_date"),
                "snapshots": list(x.get("snapshots", []))}
    except Exception:
        return default

def save(x):
    WEALTH_JSON.write_text(json.dumps(x, indent=2))

def save_starting_cash(amount, date):
    x = load()
    x["starting_cash"] = round(float(amount), 2)
    x["cash_start_date"] = pd.Timestamp(date).strftime("%Y-%m-%d")
    save(x)

def add_snapshot(date, investments_chf=0, investments_eur=0,
                 investments_usd=0, eur_chf=1, usd_chf=1,
                 crypto=0, other=0):
    x = load()
    d = pd.Timestamp(date).strftime("%Y-%m-%d")
    eur_chf = float(eur_chf) if investments_eur else 1.0
    usd_chf = float(usd_chf) if investments_usd else 1.0
    total = (float(investments_chf) +
             float(investments_eur) * eur_chf +
             float(investments_usd) * usd_chf)
    snap = {
        "date": d,
        "investments": round(total, 2),
        "investments_breakdown": {
            "CHF": round(float(investments_chf), 2),
            "EUR": round(float(investments_eur), 2),
            "USD": round(float(investments_usd), 2),
            "EUR_CHF": eur_chf,
            "USD_CHF": usd_chf,
        },
        "crypto": round(float(crypto), 2),
        "other": round(float(other), 2),
    }
    x["snapshots"] = [s for s in x["snapshots"] if s.get("date") != d]
    x["snapshots"].append(snap)
    x["snapshots"].sort(key=lambda s: s["date"])
    save(x)

def snapshots_df():
    x = load()
    rows = []
    for s in x["snapshots"]:
        b = s.get("investments_breakdown")
        if isinstance(b, dict):
            chf = float(b.get("CHF", 0))
            eur = float(b.get("EUR", 0))
            usd = float(b.get("USD", 0))
            eur_quote = float(b.get("EUR_CHF", 1))
            usd_quote = float(b.get("USD_CHF", 1))
        else:
            chf = float(s.get("investments", 0))
            eur = usd = 0.0
            eur_quote = usd_quote = 1.0
        rows.append({
            "date": pd.Timestamp(s["date"]),
            "investments": float(s.get("investments", 0)),
            "investments_chf": chf,
            "investments_eur": eur,
            "investments_usd": usd,
            "eur_chf": eur_quote,
            "usd_chf": usd_quote,
            "crypto": float(s.get("crypto", 0)),
            "other": float(s.get("other", 0)),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

def cash_at(date):
    x = load()
    end = pd.Timestamp(date).normalize()
    if not x["cash_start_date"]:
        return float(x["starting_cash"])
    start = pd.Timestamp(x["cash_start_date"]).normalize()
    if end < start:
        return float(x["starting_cash"])
    expenses = storage.load_expenses()
    spent = (float(expenses.loc[
        (expenses["date"] >= start) & (expenses["date"] <= end), "amount"
    ].sum()) if not expenses.empty else 0.0)
    income_data = storage.load_income()
    income = 0.0
    for period in pd.period_range(start.to_period("M"), end.to_period("M"), freq="M"):
        month = str(period)
        salary_date = storage.salary_date_for_month(
            month, income_data.get("salary_dates", {})
        )
        if start <= salary_date <= end:
            income += storage.income_for_month(month)
    return round(float(x["starting_cash"]) + income - spent, 2)

def wealth_df():
    df = snapshots_df()
    if df.empty:
        return df
    df["cash"] = df["date"].map(cash_at)
    df["net_worth"] = df["cash"] + df["investments"] + df["crypto"] + df["other"]
    return df
