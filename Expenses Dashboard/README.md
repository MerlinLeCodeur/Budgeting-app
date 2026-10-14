# Geneva Expenses Dashboard

A personal budgeting and wealth-tracking dashboard built with Python and Streamlit. It runs locally on your computer and stores its data in simple CSV and JSON files alongside the app.

## Features

### Budget

- **Salary-cycle budgeting:** cycles normally run from the 23rd of one month through the 22nd of the next. You can set the actual salary date for a month when payday falls on a weekend or holiday; the cycle boundaries update accordingly.
- **Income tracking:** set a usual monthly salary and, when needed, a one-cycle override. The selected cycle uses the income assigned to the month in which that cycle starts.
- **Expense entry and editing:** add, search, filter, sort, edit, or delete expenses. Each expense has a date, amount in CHF, category, and description.
- **Date-range averaging:** optionally give a one-off expense a start and end date. The **Averaged (amortized)** view allocates it evenly across the salary cycles touched by that range. **Actual (as paid)** continues to show it in the cycle when it was paid. The original transaction remains one editable record.
- **What-if calculation:** temporarily exclude selected expenses to see hypothetical spending and remaining income. This is a simulation; it does not change your saved expenses.
- **Fixed monthly expenses:** create a recurring rule that generates monthly transactions. Removing a rule does not remove transactions already generated.
- **CSV import:** upload expenses, review and adjust categories, then import them. Categories can be guessed from descriptions.
- **Charts and trends:** view spending by category, salary-cycle totals over time, and trends for individual categories.

### Wealth

- **Cash balance:** calculated from a starting cash amount and date, plus recorded salary income, less expenses since that date.
- **Investment and crypto snapshots:** enter aggregate totals in CHF, EUR, and USD, with manually entered CHF exchange rates. Individual holdings are not tracked and FX rates are not fetched automatically.
- **Balance sheet and history:** see net worth and its cash, investment, crypto, and other components over time. Save snapshots to build the history.

## Requirements

- macOS, Windows, or Linux
- Python 3.10 or newer recommended
- Internet access for the initial installation of Python packages

The app itself runs locally; it does not require a paid cloud service. If the project folder is in iCloud Drive, its data files can sync through iCloud. Avoid editing the same data files on multiple devices at the same time.

## Run the app

Open Terminal, go to this project folder, and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the local address printed in Terminal (usually <http://localhost:8501>). On later runs, activate the existing environment and start Streamlit:

```bash
source .venv/bin/activate
streamlit run app.py
```

On Windows PowerShell, activate it with `.venv\Scripts\Activate.ps1` from inside the project folder. In Command Prompt, use `.venv\Scripts\activate.bat`.

## Import expenses

On the main dashboard, open **Import expenses from a CSV file**. The CSV must include:

| Column | Required? | Notes |
| --- | --- | --- |
| `date` | Yes | Use dates such as `2026-10-11` where possible. |
| `amount` | Yes | A numeric amount in CHF. |
| `description` | No | Used to suggest a category when one is not supplied. |
| `category` | No | Blank or missing categories are guessed from the description. |

Review the imported rows and categories before confirming. Invalid dates or amounts are skipped. Importing does not change the date-range fields on expenses already in the app.

## Local data files

The app keeps its data in this folder:

- `expenses.csv` — expense transactions, including optional date-range start and end dates.
- `income.json` — usual income, cycle-specific income overrides, and salary-date settings.
- `fixed_expenses.json` — recurring-expense rules and which monthly transactions have been generated.
- `wealth.json` — cash starting point and saved wealth snapshots.

Back up these files regularly. They contain personal financial information. Before sending the app folder to someone else, remove your own data files and the `.venv` folder; send the Python files, `pages` folder, `requirements.txt`, and this README instead. Each person can create their own environment and data files.

To test with a separate data folder without using your normal data, set `EXPENSES_DATA_DIR` before starting Streamlit. For example:

```bash
mkdir -p /tmp/expenses-demo
EXPENSES_DATA_DIR=/tmp/expenses-demo streamlit run app.py
```

## Main project files

- `app.py` — Budget dashboard.
- `pages/Wealth.py` — Wealth page.
- `storage.py` and `wealth_storage.py` — local data handling.
- `categorize.py` — description-to-category suggestions for imports.
- `requirements.txt` — Python package requirements.
