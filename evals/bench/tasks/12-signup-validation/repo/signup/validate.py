def validate_signup(data: dict) -> list[str]:
    """Return a list of problems with a signup form; empty means valid."""
    errors = []
    if not data.get("email"):
        errors.append("email is required")
    return errors
