from signup.validate import validate_signup


def handle_signup(form: dict) -> tuple[int, dict]:
    errors = validate_signup(form)
    if errors:
        return 400, {"errors": errors}
    return 201, {"email": form["email"].strip().lower()}
