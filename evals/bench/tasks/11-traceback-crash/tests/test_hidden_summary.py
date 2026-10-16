import subprocess
import sys
from decimal import Decimal

from sales.summary import summarize


def test_summarize_multiple_regions():
    rows = [
        {"region": "EMEA", "amount": "1,200.50"},
        {"region": "APAC", "amount": "99"},
        {"region": "EMEA", "amount": "10"},
    ]
    assert summarize(rows) == {"EMEA": Decimal("1210.50"), "APAC": Decimal("99")}


def test_empty():
    assert summarize([]) == {}


def test_report_script_runs():
    out = subprocess.run(
        [sys.executable, "report.py", "sample_orders.csv"], capture_output=True, text=True, check=True
    ).stdout
    assert out.splitlines() == ["EMEA: 1210.50", "AMER: 500.25", "APAC: 99"]
