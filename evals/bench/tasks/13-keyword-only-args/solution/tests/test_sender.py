from notify.sender import send


def test_send_returns_payload():
    assert send("hi", retries=1, timeout=1.0)["message"] == "hi"
