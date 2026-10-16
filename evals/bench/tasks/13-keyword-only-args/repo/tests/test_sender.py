from notify.sender import send


def test_send_returns_payload():
    assert send("hi", 1, 1.0)["message"] == "hi"
