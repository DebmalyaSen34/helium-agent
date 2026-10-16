from billing.totals import compute_total


def monthly_report(invoices) -> str:
    """One line per invoice plus a grand total; uses compute_total for each invoice."""
    rows = []
    grand = 0
    for invoice in invoices:
        amount = compute_total(invoice.lines, invoice.region)
        grand += amount
        rows.append(f"{invoice.customer}: {amount}")
    rows.append(f"TOTAL: {grand}")
    return "\n".join(rows)
