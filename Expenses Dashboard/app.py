"""Geneva Expenses Dashboard — salary-cycle version.

Run locally with:
    streamlit run app.py

The main budgeting period follows the salary cycle:
    23rd of one month -> 22nd of the next month

The existing storage.py salary-cycle helpers are used, so configured salary-date
overrides are respected as well.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st

import categorize
import storage

st.set_page_config(page_title="Geneva Expenses", page_icon="💸", layout="wide")

C = storage.CURRENCY


def chf(value: float) -> str:
    return f"{C} {value:,.2f}"


# --------------------------------------------------------------------------- #
# Sidebar: add an expense
# --------------------------------------------------------------------------- #
def render_add_form(categories: list[str]) -> bool:
    st.sidebar.header("➕ Add expense")
    date = st.sidebar.date_input("Date", value=dt.date.today(), key="new_expense_date")
    amount = st.sidebar.number_input(
        f"Amount ({C})", min_value=0.0, step=1.0, format="%.2f",
        key="new_expense_amount",
    )
    category = st.sidebar.selectbox(
        "Category", categories, key="new_expense_category"
    )
    description = st.sidebar.text_input(
        "Description", placeholder="e.g. Migros, TPG pass…",
        key="new_expense_description",
    )
    spread_over_period = st.sidebar.checkbox(
        "Spread this expense over a date range",
        key="date_range_spread_toggle",
        help="Split the amount evenly across salary cycles touched by the selected period.",
    )
    spread_start = spread_end = None
    if spread_over_period:
        spread_start = st.sidebar.date_input(
            "Starting date", value=date, key="new_expense_spread_start"
        )
        spread_end = st.sidebar.date_input(
            "Ending date", value=date, key="new_expense_spread_end"
        )
    fixed = st.sidebar.checkbox(
        "Fixed monthly expense",
        key="new_expense_fixed",
        help=(
            "Save this as a recurring monthly expense. It will be added "
            "automatically each month on the selected day."
        ),
    )
    submitted = st.sidebar.button(
        "Add", use_container_width=True, key="add_expense_button"
    )

    if submitted:
        if amount <= 0:
            st.sidebar.error("Amount must be greater than 0.")
        elif fixed and spread_over_period:
            st.sidebar.error(
                "Date-range spreading is for one-off expenses, not recurring rules."
            )
        elif spread_over_period and spread_end < spread_start:
            st.sidebar.error("The ending date must be on or after the starting date.")
        else:
            if fixed:
                storage.add_fixed_expense(
                    date, amount, category, description
                )
                generated = storage.generate_fixed_expenses(dt.date.today())
                st.sidebar.success(
                    f"Saved {chf(amount)} · {category} as a monthly fixed expense "
                    f"(day {date.day})."
                )
                if generated:
                    st.sidebar.caption(f"{generated} fixed expense occurrence(s) generated.")
            else:
                storage.add_expense(
                    date, amount, category, description,
                    spread_start if spread_over_period else None,
                    spread_end if spread_over_period else None,
                )
                note = (
                    " · averaged over selected salary cycles"
                    if spread_over_period else ""
                )
                st.sidebar.success(
                    f"Added {chf(amount)} · {category}{note}"
                )
            return True
    return False


# --------------------------------------------------------------------------- #
# Fixed monthly expenses
# --------------------------------------------------------------------------- #
def render_fixed_expenses(categories: list[str]) -> None:
    """Show and manage recurring monthly expense templates."""
    fixed = storage.load_fixed_expenses()

    with st.sidebar.expander(" Fixed monthly expenses"):
        if not fixed:
            st.caption(
                "No fixed expenses yet. Tick **Fixed monthly expense** "
                "when adding one above."
            )
            return

        st.caption(
            "These are added automatically each month. Existing generated "
            "transactions stay in your expense history if you remove a rule."
        )

        for item in fixed:
            label = item["description"] or item["category"]
            st.markdown(
                f"**{label}** · {chf(item['amount'])}/month  "
                f"· day {item['day']}"
            )
            st.caption(f"{item['category']} · starts {item['start_date']}")
            if st.button(
                "Remove",
                key=f"remove_fixed_{item['id']}",
                use_container_width=True,
            ):
                storage.delete_fixed_expense(item["id"])
                st.rerun()


# --------------------------------------------------------------------------- #
# CSV import (with auto-categorization)
# --------------------------------------------------------------------------- #
def render_import(categories: list[str]) -> None:
    with st.expander("📥 Import expenses from a CSV file"):
        st.caption(
            "Upload a CSV with columns **date, amount, description** "
            "(a `category` column is optional). Missing categories are guessed "
            "automatically from the description — you can fix any before saving."
        )
        st.download_button(
            "Download a blank template",
            "date,amount,description,category\n"
            "2026-07-01,1850,July rent,\n",
            file_name="expenses_template.csv",
            mime="text/csv",
        )

        upload = st.file_uploader(
            "Choose a CSV", type=["csv"], key="import_csv"
        )
        if upload is None:
            return

        try:
            raw = pd.read_csv(upload)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not read that file: {exc}")
            return

        raw.columns = [str(c).strip().lower() for c in raw.columns]
        missing = {"date", "amount"} - set(raw.columns)
        if missing:
            st.error(
                f"Missing required column(s): {', '.join(sorted(missing))}."
            )
            return

        prepared = pd.DataFrame(
            {
                "date": pd.to_datetime(raw["date"], errors="coerce"),
                "amount": pd.to_numeric(raw["amount"], errors="coerce"),
                "description": raw.get(
                    "description",
                    pd.Series([""] * len(raw)),
                )
                .fillna("")
                .astype(str),
            }
        )

        given = (
            raw["category"].fillna("").astype(str)
            if "category" in raw.columns
            else pd.Series([""] * len(raw))
        )

        prepared["category"] = [
            g.strip() if g.strip() else categorize.guess_category(d)
            for g, d in zip(given, prepared["description"])
        ]

        bad = prepared[
            prepared["date"].isna() | prepared["amount"].isna()
        ]
        prepared = prepared.dropna(
            subset=["date", "amount"]
        ).reset_index(drop=True)

        if len(bad):
            st.warning(
                f"{len(bad)} row(s) skipped for an invalid date or amount."
            )

        if prepared.empty:
            st.error("No valid rows to import.")
            return

        st.write(
            f"**Review {len(prepared)} row(s)** — edit categories if needed:"
        )
        edited = st.data_editor(
            prepared,
            use_container_width=True,
            hide_index=True,
            column_config={
                "date": st.column_config.DateColumn("Date"),
                "amount": st.column_config.NumberColumn(
                    f"Amount ({C})", format="%.2f"
                ),
                "description": "Description",
                "category": st.column_config.SelectboxColumn(
                    "Category",
                    options=categories + ["Other"],
                    required=True,
                ),
            },
            key="import_editor",
        )

        if st.button(
            f"✅ Import {len(edited)} expense(s)", type="primary"
        ):
            added = storage.add_expenses(edited)
            st.success(f"Imported {added} expense(s).")
            st.rerun()


# --------------------------------------------------------------------------- #
# Income — salary-cycle aware
# --------------------------------------------------------------------------- #
def readable_salary_cycle_label(
    start: pd.Timestamp,
    salary_dates: dict | None = None,
) -> str:
    """Return a human-readable salary-cycle label with month names."""
    salary_dates = salary_dates or {}
    start = pd.Timestamp(start).normalize()
    next_month = start.to_period("M") + 1
    next_start = storage.salary_date_for_month(
        str(next_month),
        salary_dates,
    )
    end = next_start - pd.Timedelta(days=1)
    return f"{start:%d %B %Y} → {end:%d %B %Y}"



def income_for_month_with_start(month, income_data):
    """Return configured monthly income, but zero before the first salary."""
    start_date = income_data.get("salary_start_date")
    if start_date:
        start_period = pd.to_datetime(start_date).to_period("M")
        if pd.Period(month, freq="M") < start_period:
            return 0.0
    return storage.income_for_month(month)


def render_income_control(
    selected_cycle_start: pd.Timestamp | None,
    cycle_starts: list[pd.Timestamp],
) -> float:
    """Show income controls and return income for the selected salary scope.

    A salary cycle uses the income received at its start. With the default
    salary date, the cycle is 23rd -> 22nd, so the 2026-09-23 -> 2026-10-22
    cycle uses the September income setting.
    """
    data = storage.load_income()

    if selected_cycle_start is None:
        total = sum(
            income_for_month_with_start(start.strftime("%Y-%m"), data)
            for start in cycle_starts
        )
        n = len(cycle_starts)

        with st.expander(
            f"💰 Salary income — {chf(data['default'])} / cycle"
        ):
            new_default = st.number_input(
                f"Usual salary income ({C})",
                min_value=0.0,
                step=100.0,
                value=float(data["default"]),
                format="%.2f",
                key="inc_default",
                help=(
                    "This is the income assigned to each salary cycle unless "
                    "that cycle has an override."
                ),
            )

            if st.button("Save income"):
                storage.save_income(
                    new_default,
                    data["overrides"],
                    data.get("salary_dates", {}),
                )
                st.rerun()

            st.caption(
                f"Total income over the {n} cycle(s) in view: {chf(total)}"
            )

            if data["overrides"]:
                st.caption(
                    "Cycles with a custom income amount: "
                    + ", ".join(sorted(data["overrides"]))
                )

        return total

    income_month = selected_cycle_start.strftime("%Y-%m")
    current = income_for_month_with_start(income_month, data)
    is_override = income_month in data["overrides"]
    cycle_label = readable_salary_cycle_label(
        selected_cycle_start, data.get("salary_dates", {})
    )

    with st.expander(
        f"💰 Income for {cycle_label} — {chf(current)}"
    ):
        val = st.number_input(
            f"Income for this salary cycle ({C})",
            min_value=0.0,
            step=100.0,
            value=float(current),
            format="%.2f",
            key="inc_cycle",
            help=(
                f"This cycle starts on {selected_cycle_start:%Y-%m-%d}, "
                f"so it uses the income setting for {income_month}."
            ),
        )

        start_date = data.get("salary_start_date")
        before_first_salary = bool(
            start_date
            and pd.Timestamp(selected_cycle_start).normalize()
            < pd.Timestamp(start_date).normalize()
        )

        same = st.checkbox(
            "Use this as my usual salary income",
            value=(not is_override) and not before_first_salary,
            disabled=before_first_salary,
            help=(
                "Your usual salary starts from the first salary payment. "
                "For earlier cycles, income is CHF 0 unless you explicitly "
                "save a cycle-specific override."
            ),
        )

        if before_first_salary:
            st.caption(
                f"Before your first salary payment ({pd.Timestamp(start_date):%d %B %Y}), "
                "the usual salary is not applied."
            )

        if st.button("Save income"):
            overrides = dict(data["overrides"])

            if same:
                overrides.pop(income_month, None)
                storage.save_income(
                    val,
                    overrides,
                    data.get("salary_dates", {}),
                    data.get("salary_start_date"),
                )
            else:
                overrides[income_month] = val
                storage.save_income(
                    data["default"],
                    overrides,
                    data.get("salary_dates", {}),
                    data.get("salary_start_date"),
                )

            st.rerun()

    return val


# --------------------------------------------------------------------------- #
# Main views
# --------------------------------------------------------------------------- #
def render_kpis(
    active_df: pd.DataFrame,
    label: str,
    income: float,
    *,
    averaged: bool,
    other_spent: float,
    actual_count: int,
) -> None:
    total = float(active_df["amount"].sum())
    remaining = income - total

    biggest = active_df.groupby("category")["amount"].sum()
    top_cat = biggest.idxmax() if not biggest.empty else "—"

    spent_label = "Spent (avg)" if averaged else "Spent"
    rem_label = "Remaining (avg)" if averaged else "Remaining"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Income", chf(income))
    c2.metric(f"{spent_label} · {label}", chf(total))
    invested = float(active_df.loc[active_df["category"].eq("Investment"), "amount"].sum())
    c2.caption(f"of which {chf(invested)} invested")
    c3.metric(
        rem_label,
        chf(remaining),
        f"{remaining / income * 100:.0f}% left"
        if income > 0
        else None,
    )
    c4.metric(
        "Top category",
        top_cat,
        chf(biggest.max()) if not biggest.empty else "",
    )

    other_remaining = income - other_spent
    other_name = (
        "As paid (with lump sums)" if averaged else "Averaged"
    )
    st.caption(
        f"{actual_count} transaction(s) · {other_name}: "
        f"spent {chf(other_spent)} · remaining {chf(other_remaining)}"
    )


def render_what_if(active_df: pd.DataFrame, income: float, label: str) -> None:
    """Show how selected expenses would change spending, without editing data."""
    with st.expander("🔎 What if (excludes expenses)?", expanded=False):
        if active_df.empty:
            st.info("There are no expenses in this view to exclude.")
            return

        candidates = active_df.reset_index(drop=True).copy()
        candidates["date"] = pd.to_datetime(candidates["date"])
        option_rows = {}
        for row_number, row in candidates.iterrows():
            description = str(row.get("description", "")).strip() or "No description"
            option_rows[
                f"{row['date']:%Y-%m-%d} · {chf(float(row['amount']))} · "
                f"{row['category']} · {description} · #{row_number + 1}"
            ] = row_number

        selected = st.multiselect(
            "Choose expenses to remove from this calculation",
            options=list(option_rows),
            key="what_if_expenses",
            help="This is only a simulation. Your expenses remain unchanged.",
        )
        selected_rows = [option_rows[label] for label in selected]
        removed = float(candidates.loc[selected_rows, "amount"].sum()) if selected_rows else 0.0
        current_spent = float(candidates["amount"].sum())
        hypothetical_spent = current_spent - removed
        a, b, c = st.columns(3)
        a.metric(f"Spent · {label}", chf(current_spent))
        b.metric("If selected expenses were absent", chf(hypothetical_spent),
                 chf(-removed) if removed else None)
        c.metric("Remaining after that", chf(income - hypothetical_spent))


def render_table(
    scope_df: pd.DataFrame,
    all_df: pd.DataFrame,
    categories: list[str],
) -> None:
    st.subheader("Expenses")
    st.caption(
        "Edit any cell, delete a row with the ✖ that appears on hover, "
        "or add a new row at the bottom — then click **Save changes**."
    )

    left, mid, right = st.columns([2, 1, 1])
    search = left.text_input("Search description", "")
    picked = mid.multiselect(
        "Filter categories", categories, default=[]
    )
    sort_choice = right.selectbox(
        "Sort by",
        [
            "Date (newest first)",
            "Date (oldest first)",
            "Amount (high → low)",
            "Amount (low → high)",
        ],
    )

    shown = scope_df.copy()

    if search:
        shown = shown[
            shown["description"].str.contains(
                search, case=False, na=False
            )
        ]

    if picked:
        shown = shown[shown["category"].isin(picked)]

    sort_spec = {
        "Date (newest first)": ("date", False),
        "Date (oldest first)": ("date", True),
        "Amount (high → low)": ("amount", False),
        "Amount (low → high)": ("amount", True),
    }
    sort_col, ascending = sort_spec[sort_choice]
    shown = shown.sort_values(sort_col, ascending=ascending)

    editor_df = shown[
        [
            "date",
            "amount",
            "category",
            "description",
            "spread_start",
            "spread_end",
        ]
    ].copy()
    editor_df["date"] = pd.to_datetime(editor_df["date"])
    editor_df["spread_start"] = pd.to_datetime(editor_df["spread_start"])
    editor_df["spread_end"] = pd.to_datetime(editor_df["spread_end"])

    edited = st.data_editor(
        editor_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "date": st.column_config.DateColumn(
                "Date",
                format="YYYY-MM-DD",
                required=True,
            ),
            "amount": st.column_config.NumberColumn(
                f"Amount ({C})",
                format="%.2f",
                min_value=0.0,
                required=True,
            ),
            "category": st.column_config.SelectboxColumn(
                "Category",
                options=categories + ["Other"],
                required=True,
            ),
            "description": st.column_config.TextColumn(
                "Description"
            ),
            "spread_start": st.column_config.DateColumn(
                "Spread starts", format="YYYY-MM-DD"
            ),
            "spread_end": st.column_config.DateColumn(
                "Spread ends", format="YYYY-MM-DD"
            ),
        },
        key="expense_editor",
    )

    total_shown = pd.to_numeric(
        edited["amount"], errors="coerce"
    ).sum()
    st.caption(
        f"{len(edited)} expense(s) · {chf(total_shown)} shown"
    )

    if st.button("💾 Save changes", type="primary"):
        # Preserve every row that isn't in the current editable view
        # (other salary cycles, or rows hidden by search/category filters),
        # then splice in the edited rows.
        outside = all_df.loc[
            ~all_df.index.isin(shown.index),
            storage.EXPENSE_COLUMNS,
        ]

        new_full = pd.concat(
            [outside, edited], ignore_index=True
        )

        written = storage.overwrite_expenses(new_full)
        st.success(
            f"Saved — {written} expense(s) on file."
        )
        # The save happens during a rerun already. Preserve the current view
        # explicitly before the follow-up rerun reloads the edited CSV.
        st.session_state["_resume_salary_cycle"] = st.session_state.get(
            "salary_cycle_choice"
        )
        st.session_state["_resume_spending_view"] = st.session_state.get(
            "spending_view_mode"
        )
        st.rerun()


def render_by_category(cycle_df: pd.DataFrame) -> None:
    header, toggle = st.columns([2, 1])
    header.subheader("Spending by category")

    if cycle_df.empty:
        st.info("No expenses in this salary cycle yet.")
        return

    by_cat = (
        cycle_df.groupby("category")["amount"]
        .sum()
        .sort_values(ascending=False)
    )

    chart = toggle.radio(
        "Chart",
        ["Pie", "Bar"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if chart == "Pie":
        fig = px.pie(
            names=by_cat.index,
            values=by_cat.values,
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate=(
                "%{label}<br>"
                + C
                + " %{value:,.2f} (%{percent})<extra></extra>"
            ),
        )
        fig.update_layout(
            showlegend=True,
            margin=dict(t=10, b=10, l=10, r=10),
            height=340,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(
            by_cat,
            horizontal=True,
            color="#4C9BE8",
        )


def render_trend(
    all_df: pd.DataFrame,
    salary_dates: dict[str, str] | None = None,
) -> None:
    st.subheader("Salary-cycle trend")

    if all_df.empty:
        st.info("Add expenses to see your salary-cycle trend.")
        return

    cycle_df = storage.add_salary_cycles(all_df, salary_dates)
    cycle_totals = (
        cycle_df.assign(
            component=cycle_df["category"].eq(storage.INVESTMENT_CATEGORY)
            .map({True: "Investments", False: "Expenses"})
        )
        .groupby(["salary_cycle_start", "salary_cycle", "component"])["amount"]
        .sum()
        .unstack("component", fill_value=0)
        .reindex(columns=["Expenses", "Investments"], fill_value=0)
        .sort_index()
    )

    # Keep the real cycle start dates as the x values. This guarantees true
    # chronological ordering while the displayed tick labels remain simple
    # month names such as "August", "September", "October".
    cycle_starts = cycle_totals.index.get_level_values("salary_cycle_start")
    cycle_labels = cycle_totals.index.get_level_values("salary_cycle")
    values = cycle_totals.sum(axis=1).to_numpy()

    trend = cycle_totals.copy()
    trend["cycle_start"] = cycle_starts
    trend["total"] = values
    trend = trend.reset_index(drop=True).melt(
        id_vars=["cycle_start", "total"],
        var_name="component",
        value_name="amount",
    )

    fig = px.bar(
        trend,
        x="cycle_start",
        y="amount",
        color="component",
        color_discrete_map={
            "Expenses": "#5FB98E",
            "Investments": "#E76F6F",
        },
        category_orders={"component": ["Expenses", "Investments"]},
        custom_data=["total"],
    )
    fig.update_traces(
        hovertemplate="%{x|%d %B %Y}<br>"
        + "%{fullData.name}: "
        + C
        + " %{y:,.2f}<br>Total outflow: "
        + C
        + " %{customdata[0]:,.2f}<extra></extra>"
    )
    fig.update_xaxes(
        tickmode="array",
        tickvals=cycle_starts,
        ticktext=cycle_starts.strftime("%B"),
        title=None,
    )
    fig.update_yaxes(title=None)
    fig.update_layout(
        barmode="stack",
        showlegend=True,
        legend_title_text=None,
        margin=dict(t=10, b=10, l=10, r=10),
        height=340,
    )
    st.caption("Expenses are green; investments are red and shown separately.")
    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        },
    )

    if len(cycle_totals) >= 2:
        delta = values[-1] - values[-2]
        arrow = "🔺" if delta > 0 else "🔻"
        st.caption(
            f"{arrow} {chf(abs(delta))} vs previous salary cycle "
            f"({cycle_labels[-2]} → {cycle_labels[-1]})"
        )


def render_category_trend(all_df: pd.DataFrame) -> None:
    st.subheader("Category trend over time")

    if all_df["month"].nunique() < 2:
        st.info(
            "Add expenses across at least two months to see "
            "category trends."
        )
        return

    grouped = (
        all_df.groupby(["month", "category"])["amount"]
        .sum()
        .reset_index()
    )

    # Fill months where a category had no spend so each line stays
    # continuous rather than looking like missing data.
    long = (
        grouped.pivot(
            index="month",
            columns="category",
            values="amount",
        )
        .fillna(0.0)
        .sort_index()
        .reset_index()
        .melt(
            id_vars="month",
            var_name="category",
            value_name="amount",
        )
    )

    fig = px.line(
        long,
        x="month",
        y="amount",
        color="category",
        markers=True,
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig.update_layout(
        height=380,
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis_title=None,
        yaxis_title=C,
        legend_title_text="",
    )
    fig.update_traces(
        hovertemplate=(
            "%{x}<br>%{fullData.name}: "
            + C
            + " %{y:,.2f}<extra></extra>"
        )
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "One line per category — follow how each one's "
        "monthly spend evolves."
    )


# --------------------------------------------------------------------------- #
# Salary-date control
# --------------------------------------------------------------------------- #
def render_salary_date_control(
    selected_cycle_start: pd.Timestamp | None,
    income_data: dict,
) -> None:
    """Allow the user to override the salary date for a specific month.

    By default storage.py uses the 23rd. This lets the user change it to the
    actual payment date when the 23rd falls on a weekend/holiday, for example
    2026-05-22 instead of 2026-05-23.
    """
    if selected_cycle_start is None:
        return

    salary_dates = dict(income_data.get("salary_dates", {}))
    month_key = selected_cycle_start.strftime("%Y-%m")

    configured = salary_dates.get(month_key)
    default_date = (
        pd.to_datetime(configured).date()
        if configured
        else storage.salary_date_for_month(
            month_key,
            salary_dates,
        ).date()
    )

    with st.expander("📅 Salary date for this cycle"):
        st.caption(
            "Normally your salary date is the 23rd. If the 23rd is a "
            "weekend or holiday, set the actual date your salary was paid. "
            "This changes the start/end dates of the salary cycle."
        )

        selected_date = st.date_input(
            f"Salary date in {month_key}",
            value=default_date,
            key=f"salary_date_{month_key}",
        )

        if selected_date.month != selected_cycle_start.month:
            st.error(
                f"The salary date must stay in {selected_cycle_start:%B %Y}."
            )
            return

        if st.button(
            "Save salary date",
            key=f"save_salary_date_{month_key}",
        ):
            updated_dates = dict(salary_dates)
            normal_default = storage.salary_date_for_month(
                month_key,
                {},
            ).date()

            if selected_date == normal_default:
                # Remove the override if the user puts it back to the 23rd.
                updated_dates.pop(month_key, None)
            else:
                updated_dates[month_key] = selected_date.isoformat()

            storage.save_income(
                income_data["default"],
                income_data["overrides"],
                updated_dates,
                income_data.get("salary_start_date"),
            )
            st.success(
                f"Salary date for {month_key} saved as "
                f"{selected_date:%Y-%m-%d}."
            )
            st.rerun()


# --------------------------------------------------------------------------- #
# Salary-cycle helpers for the UI
# --------------------------------------------------------------------------- #
def build_cycle_starts(
    all_df: pd.DataFrame,
    salary_dates: dict[str, str],
    today: dt.date,
) -> list[pd.Timestamp]:
    """Build every salary-cycle start needed by the dashboard.

    Includes empty cycles between the first recorded expense and the latest
    relevant date, plus the current cycle even if it has no expenses yet.
    """
    current_start = storage.salary_cycle_start(
        pd.Timestamp(today),
        salary_dates,
    )

    relevant_min = [all_df["date"].min()]
    relevant_max = [all_df["date"].max()]
    if "spread_start" in all_df:
        spread_starts = pd.to_datetime(all_df["spread_start"], errors="coerce").dropna()
        spread_ends = pd.to_datetime(all_df["spread_end"], errors="coerce").dropna()
        if not spread_starts.empty:
            relevant_min.append(spread_starts.min())
        if not spread_ends.empty:
            relevant_max.append(spread_ends.max())
    min_date = pd.Timestamp(min(relevant_min))
    max_date = pd.Timestamp(max(relevant_max))

    first_start = storage.salary_cycle_start(
        min_date,
        salary_dates,
    )
    last_start = max(
        current_start,
        storage.salary_cycle_start(max_date, salary_dates),
    )

    starts: list[pd.Timestamp] = []
    cursor = pd.Timestamp(first_start).normalize()

    while cursor <= last_start:
        starts.append(cursor)

        next_month = cursor.to_period("M") + 1
        next_start = storage.salary_date_for_month(
            str(next_month),
            salary_dates,
        )

        # Defensive guard against a malformed/custom salary-date setup.
        if next_start <= cursor:
            next_start = (
                cursor.to_period("M").to_timestamp()
                + pd.offsets.MonthBegin(1)
                + pd.Timedelta(days=22)
            )

        cursor = pd.Timestamp(next_start).normalize()

    return starts


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("💸 Geneva Expenses Dashboard")

    # Generate recurring expenses through the end of the CURRENT salary cycle,
    # not just through today. This matters because a cycle can contain future
    # dates (e.g. a rent payment on the 1st of next month). Generation is
    # idempotent, so rerunning Streamlit does not create duplicates.
    income_data = storage.load_income()
    salary_dates = income_data.get("salary_dates", {})
    today = pd.Timestamp(dt.date.today()).normalize()
    current_cycle_start = storage.salary_cycle_start(today, salary_dates)
    current_cycle_end = (
        storage.salary_date_for_month(
            str(current_cycle_start.to_period("M") + 1),
            salary_dates,
        )
        - pd.Timedelta(days=1)
    )
    storage.generate_fixed_expenses(current_cycle_end)

    all_df = storage.load_expenses()
    categories = storage.all_categories(all_df)

    expense_added = render_add_form(categories)
    if expense_added:
        # The Add button already triggered this run; reload here instead of
        # forcing a second rerun that can reset the selected spending view.
        all_df = storage.load_expenses()
        categories = storage.all_categories(all_df)
    render_fixed_expenses(categories)
    render_import(categories)

    if all_df.empty:
        st.info(
            "No expenses yet. Add your first one from the sidebar on "
            "the left 👈, or import a CSV above."
        )
        return

    # Income data was loaded above so salary-date overrides are respected.

    # Add salary-cycle fields to the real expense data.
    all_df = storage.add_salary_cycles(
        all_df,
        salary_dates,
    )

    # The averaged dataset needs the cycle fields recomputed because
    # storage.amortize() creates new allocation dates.
    amort_df = storage.amortize(all_df, salary_dates)
    amort_df = storage.add_salary_cycles(
        amort_df,
        salary_dates,
    )

    cycle_starts = build_cycle_starts(
        all_df,
        salary_dates,
        today,
    )

    # Show the most recent/current cycle first.
    cycle_starts = sorted(
        set(cycle_starts) | {current_cycle_start},
        reverse=True,
    )

    cycle_labels = {
        start: readable_salary_cycle_label(
            start,
            salary_dates,
        )
        for start in cycle_starts
    }

    # ------------------------------------------------------------------ #
    # Period selector
    # ------------------------------------------------------------------ #
    fcol1, fcol2 = st.columns([2.2, 1.4])

    cycle_options = ["All cycles"] + [
        cycle_labels[start] for start in cycle_starts
    ]

    resume_cycle = st.session_state.pop("_resume_salary_cycle", None)
    if resume_cycle in cycle_options:
        st.session_state["salary_cycle_choice"] = resume_cycle
    resume_view = st.session_state.pop("_resume_spending_view", None)
    if resume_view in ["Actual (as paid)", "Averaged (amortized)"]:
        st.session_state["spending_view_mode"] = resume_view

    current_label = cycle_labels.get(
        current_cycle_start,
        readable_salary_cycle_label(
            current_cycle_start,
            salary_dates,
        ),
    )

    default_index = (
        cycle_options.index(current_label)
        if current_label in cycle_options
        else 1
    )

    cycle_choice = fcol1.selectbox(
        "Salary cycle",
        cycle_options,
        index=default_index,
        key="salary_cycle_choice",
        help=(
            "The budgeting period follows your salary: normally from "
            "the 23rd of one month through the 22nd of the next."
        ),
    )

    # Resolve the selected cycle before rendering the salary-date editor.
    if cycle_choice == "All cycles":
        selected_cycle_start = None
    else:
        selected_cycle_start = next(
            start
            for start, cycle_label in cycle_labels.items()
            if cycle_label == cycle_choice
        )

    render_salary_date_control(
        selected_cycle_start,
        income_data,
    )

    view = fcol2.radio(
        "Spending view",
        ["Actual (as paid)", "Averaged (amortized)"],
        horizontal=True,
        key="spending_view_mode",
        help=(
            "Averaged allocates an expense with a date range evenly across "
            "the salary cycles touched by that period."
        ),
    )

    averaged = view.startswith("Averaged")

    # ------------------------------------------------------------------ #
    # Convert the selected label back to a cycle start.
    # ------------------------------------------------------------------ #
    if cycle_choice == "All cycles":
        selected_cycle_start = None
        label = "all cycles"

        def in_scope(df: pd.DataFrame) -> pd.DataFrame:
            return df

        scope_cycle_starts = cycle_starts
    else:
        selected_cycle_start = next(
            start
            for start, cycle_label in cycle_labels.items()
            if cycle_label == cycle_choice
        )
        label = cycle_choice

        def in_scope(df: pd.DataFrame) -> pd.DataFrame:
            return df[
                df["salary_cycle_start"] == selected_cycle_start
            ]

        scope_cycle_starts = [selected_cycle_start]

    actual_scope = in_scope(all_df)
    amort_scope = in_scope(amort_df)

    active_scope = (
        amort_scope if averaged else actual_scope
    )
    other_scope = (
        actual_scope if averaged else amort_scope
    )
    trend_source = (
        amort_df if averaged else all_df
    )

    income = render_income_control(
        selected_cycle_start,
        scope_cycle_starts,
    )

    render_kpis(
        active_scope,
        label,
        income,
        averaged=averaged,
        other_spent=float(other_scope["amount"].sum()),
        actual_count=len(actual_scope),
    )
    render_what_if(active_scope, income, label)

    st.divider()

    left, right = st.columns(2)

    with left:
        render_by_category(active_scope)

    with right:
        render_trend(
            trend_source,
            income_data.get("salary_dates", {}),
        )

    st.divider()
    render_category_trend(trend_source)

    st.divider()

    # The table always edits real expenses, never the amortized dataset.
    render_table(
        actual_scope,
        all_df,
        categories,
    )


if __name__ == "__main__":
    main()
