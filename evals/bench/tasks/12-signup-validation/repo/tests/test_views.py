from signup.views import handle_signup


def test_missing_email_is_rejected():
    status, body = handle_signup({})
    assert status == 400
