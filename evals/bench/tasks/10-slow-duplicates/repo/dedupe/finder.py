def find_duplicates(items: list) -> list:
    """Values that appear more than once, in the order their second occurrence is seen."""
    duplicates = []
    for index, item in enumerate(items):
        if item in items[:index] and item not in duplicates:
            duplicates.append(item)
    return duplicates
