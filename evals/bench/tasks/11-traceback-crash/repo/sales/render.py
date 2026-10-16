def render(totals: dict) -> str:
    ordered = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return "\n".join(f"{region}: {amount}" for region, amount in ordered)
