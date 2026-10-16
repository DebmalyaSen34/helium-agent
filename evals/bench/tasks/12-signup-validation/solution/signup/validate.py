def _email_error(email) -> str | None:
    if not isinstance(email, str) or not email.strip():
        return "email is required"
    email = email.strip()
    if email.count("@") != 1:
        return "invalid email"
    local, domain = email.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        return "invalid email"
    return None


def validate_signup(data: dict) -> list[str]:
    """Return a list of problems with a signup form; empty means valid."""
    errors = []
    email_error = _email_error(data.get("email"))
    if email_error:
        errors.append(email_error)

    password = data.get("password") or ""
    if len(password) < 8:
        errors.append("password too short")
    if not any(ch.isdigit() for ch in password):
        errors.append("password needs a digit")

    if "age" in data:
        age = data["age"]
        if isinstance(age, bool) or not isinstance(age, int) or not 13 <= age <= 120:
            errors.append("invalid age")
    return errors
