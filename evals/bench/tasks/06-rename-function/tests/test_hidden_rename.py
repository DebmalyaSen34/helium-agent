import inspect
from decimal import Decimal
from pathlib import Path

import billing
from billing import Invoice, compute_total
from billing.report import monthly_report


def test_new_name_works():
    assert compute_total([("a", Decimal("5.00"), 1)], "none") == Decimal("5.00")


def test_old_name_is_gone_everywhere():
    offenders = [
        str(path)
        for path in Path(".").rglob("*")
        if path.is_file() and ".bench_hidden" not in path.parts and ".git" not in path.parts
        and path.suffix in {".py", ".md"} and "calc_total" in path.read_text()
    ]
    assert offenders == []
    assert not hasattr(billing, "calc_total")


def test_callers_still_work():
    invoice = Invoice("acme", "eu")
    invoice.add("widget", "10.00", 2)
    assert invoice.total() == Decimal("24.00")
    assert monthly_report([invoice]).splitlines() == ["acme: 24.00", "TOTAL: 24.00"]
