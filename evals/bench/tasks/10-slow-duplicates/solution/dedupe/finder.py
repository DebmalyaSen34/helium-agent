def find_duplicates(items: list) -> list:
    """Values that appear more than once, in the order their second occurrence is seen."""
    seen = set()
    reported = set()
    duplicates = []
    for item in items:
        if item in seen:
            if item not in reported:
                reported.add(item)
                duplicates.append(item)
        else:
            seen.add(item)
    return duplicates
