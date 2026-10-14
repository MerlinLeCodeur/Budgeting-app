from __future__ import annotations
import datetime as dt
from pathlib import Path
import sys
import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import storage
import wealth_storage

C = storage.CURRENCY
def money(x):
    return f"{C} {x:,.2f}"

st.set_page_config(page_title="Wealth", page_icon="📈", layout="wide")
st.title("📈 Wealth")
st.caption("Simple balance sheet. Cash comes automatically from Budget.")

cfg = wealth_storage.load()

def live_cash_today() -> float:
    """Current cash balance from the budgeting data, not the last wealth snapshot."""
    if not cfg["cash_start_date"]:
        return float(cfg["starting_cash"])

    today = pd.Timestamp(dt.date.today()).normalize()
    start = pd.Timestamp(cfg["cash_start_date"]).normalize()
    if today < start:
        return float(cfg["starting_cash"])

    expenses = storage.load_expenses()
    spent = 0.0
    if not expenses.empty:
        spent = float(expenses.loc[
            (expenses["date"] >= start) & (expenses["date"] <= today),
            "amount",
        ].sum())

    income_data = storage.load_income()
    salary_dates = income_data.get("salary_dates", {})
    salary_start = income_data.get("salary_start_date")
    salary_start = (
        pd.Timestamp(salary_start).normalize()
        if salary_start else None
    )

    income = 0.0
    for period in pd.period_range(start.to_period("M"), today.to_period("M"), freq="M"):
        month = str(period)
        salary_date = storage.salary_date_for_month(month, salary_dates)
        if start <= salary_date <= today and (salary_start is None or salary_date >= salary_start):
            income += storage.income_for_month(month)

    return round(float(cfg["starting_cash"]) + income - spent, 2)

with st.expander("⚙️ Cash starting point", expanded=not cfg["cash_start_date"]):
    a, b = st.columns(2)
    starting = a.number_input("Cash at start (CHF)", min_value=0.0,
                              value=float(cfg["starting_cash"]), step=100.0)
    start_date = b.date_input(
        "Tracking starts",
        value=pd.Timestamp(cfg["cash_start_date"]).date()
        if cfg["cash_start_date"] else dt.date.today()
    )
    if st.button("Save starting point"):
        wealth_storage.save_starting_cash(starting, start_date)
        st.rerun()

st.subheader("New snapshot")
st.caption("Enter aggregate investment values by currency. Individual positions are not tracked.")

snapshot_date = st.date_input("Snapshot date", value=dt.date.today())
history = wealth_storage.snapshots_df()
existing = None
if not history.empty:
    m = history[history["date"].dt.date == snapshot_date]
    if not m.empty:
        existing = m.iloc[0]

def old(col, default=0.0):
    return float(existing[col]) if existing is not None else default

st.markdown("**Investments**")
a, b, c = st.columns(3)
inv_chf = a.number_input("CHF", min_value=0.0, value=old("investments_chf"), step=100.0, key="investments_chf")
inv_eur = b.number_input("EUR", min_value=0.0, value=old("investments_eur"), step=100.0, key="investments_eur")
inv_usd = c.number_input("USD", min_value=0.0, value=old("investments_usd"), step=100.0, key="investments_usd")

st.markdown("**Crypto**")
crypto_chf_col, crypto_eur_col, crypto_usd_col = st.columns(3)

crypto_chf = crypto_chf_col.number_input(
    "CHF",
    min_value=0.0,
    value=0.0,
    step=100.0,
    key="crypto_chf",
)
crypto_eur = crypto_eur_col.number_input(
    "EUR",
    min_value=0.0,
    value=0.0,
    step=100.0,
    key="crypto_eur",
)
crypto_usd = crypto_usd_col.number_input(
    "USD",
    min_value=0.0,
    value=0.0,
    step=100.0,
    key="crypto_usd",
)

st.divider()
st.markdown("### FX rates")
st.caption("Used for both Investments and Crypto. Enter the CHF value of 1 unit of each currency.")
fx1, fx2 = st.columns(2)
eur_chf = fx1.number_input(
    "1 EUR = CHF",
    min_value=0.000001,
    value=old("eur_chf", 1.0),
    step=0.0001,
    format="%.6f",
    key="eur_chf_rate",
)
usd_chf = fx2.number_input(
    "1 USD = CHF",
    min_value=0.000001,
    value=old("usd_chf", 1.0),
    step=0.0001,
    format="%.6f",
    key="usd_chf_rate",
)

investment_total = inv_chf + inv_eur * eur_chf + inv_usd * usd_chf
crypto_total = (
    crypto_chf
    + crypto_eur * eur_chf
    + crypto_usd * usd_chf
)

st.caption(f"Total investments: **{money(investment_total)}**")
st.caption(f"Total crypto: **{money(crypto_total)}**")

other = st.number_input(
    "Other (CHF)",
    min_value=0.0,
    value=old("other"),
    step=100.0,
)

if st.button("Save snapshot", type="primary"):
    wealth_storage.add_snapshot(
        snapshot_date,
        inv_chf,
        inv_eur,
        inv_usd,
        eur_chf,
        usd_chf,
        crypto_total,
        other,
    )
    st.success(f"Snapshot saved for {snapshot_date:%d %B %Y}.")
    st.rerun()

wealth = wealth_storage.wealth_df()
if wealth.empty:
    st.info("Save your first snapshot to start tracking wealth.")
    st.stop()

latest = wealth.iloc[-1]
previous = wealth.iloc[-2] if len(wealth) >= 2 else None

# Cash is always read live from the Budget page's underlying data.
live_cash = live_cash_today()
live_date = dt.date.today()
live_net_worth = live_cash + float(latest["investments"]) + float(latest["crypto"]) + float(latest["other"])
previous_net_worth = (
    float(previous["net_worth"]) if previous is not None else None
)

st.divider()
st.subheader(f"Balance sheet · {live_date:%d %B %Y}")
a, b, c, d = st.columns(4)
a.metric("Net worth", money(live_net_worth))
b.metric("Cash", money(live_cash))
c.metric("Investments", money(latest["investments"]))
d.metric(
    "Change since last",
    money(live_net_worth - previous_net_worth)
    if previous_net_worth is not None else "—",
)

# Wealth composition
wealth_breakdown = pd.DataFrame({
    "Asset": ["Cash", "Investments", "Crypto", "Other"],
    "Value": [
        live_cash,
        float(latest["investments"]),
        float(latest["crypto"]),
        float(latest["other"]),
    ],
})
wealth_breakdown = wealth_breakdown[wealth_breakdown["Value"] > 0]

st.subheader("Wealth composition")
fig_pie = px.pie(
    wealth_breakdown,
    names="Asset",
    values="Value",
    hole=0.45,
)
fig_pie.update_traces(
    texttemplate="%{label}<br>CHF %{value:,.0f}<br>%{percent}",
    textposition="outside",
)
fig_pie.update_layout(
    height=420,
    margin=dict(t=10, b=10, l=10, r=10),
    showlegend=True,
    legend_title_text=None,
)
st.plotly_chart(
    fig_pie,
    use_container_width=True,
    config={"displayModeBar": True, "displaylogo": False},
)

st.markdown(
    f"**Cash:** {money(live_cash)}  \n"
    f"**Investments:** {money(latest['investments'])}  \n"
    f"**Crypto:** {money(latest['crypto'])}  \n"
    f"**Other:** {money(latest['other'])}"
)

st.divider()
st.subheader("Wealth over time")
if len(wealth) > 1:
    category_history = wealth.melt(
        id_vars=["date"],
        value_vars=["cash", "investments", "crypto", "other", "net_worth"],
        var_name="Category",
        value_name="Value",
    )
    category_history["Category"] = category_history["Category"].map({
        "cash": "Cash",
        "investments": "Investments",
        "crypto": "Crypto",
        "other": "Other",
        "net_worth": "Net worth",
    })
    fig_categories = px.line(
        category_history,
        x="date",
        y="Value",
        color="Category",
        markers=True,
        color_discrete_map={
            "Cash": "#4C9BE8",
            "Investments": "#5FB98E",
            "Crypto": "#F2A541",
            "Other": "#A78BFA",
            "Net worth": "#303846",
        },
    )
    fig_categories.update_layout(
        height=360,
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title=None,
        yaxis_title=C,
        legend_title_text=None,
    )
    st.plotly_chart(
        fig_categories,
        use_container_width=True,
        config={"displayModeBar": True, "displaylogo": False,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
    )
else:
    st.info("Take one more snapshot to see wealth and asset categories over time.")

with st.expander("Snapshot history"):
    table = wealth.copy()
    table["date"] = table["date"].dt.strftime("%Y-%m-%d")
    table = table[["date","net_worth","cash","investments","crypto","other"]].rename(
        columns={"date":"Date","net_worth":"Net worth","cash":"Cash",
                 "investments":"Investments","crypto":"Crypto","other":"Other"}
    )
    st.dataframe(table, hide_index=True, use_container_width=True)
