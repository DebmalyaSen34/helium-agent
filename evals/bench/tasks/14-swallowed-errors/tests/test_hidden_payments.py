import pytest

from payments import transport
from payments.checkout import Order, checkout
from payments.errors import PaymentError
from payments.gateway import charge


def test_charge_success(monkeypatch):
    monkeypatch.setattr(transport, "post", lambda path, payload: {"id": "ch_1"})
    assert charge("tok", 100) == "ch_1"


def test_charge_raises_payment_error_chained(monkeypatch):
    def boom(path, payload):
        raise ConnectionError("provider unreachable")

    monkeypatch.setattr(transport, "post", boom)
    with pytest.raises(PaymentError) as info:
        charge("tok", 100)
    assert isinstance(info.value.__cause__, ConnectionError)


def test_bad_response_is_a_payment_error(monkeypatch):
    monkeypatch.setattr(transport, "post", lambda path, payload: {"status": "declined"})
    with pytest.raises(PaymentError):
        charge("tok", 100)


def test_checkout_marks_failed_orders(monkeypatch):
    def boom(path, payload):
        raise ConnectionError("provider unreachable")

    monkeypatch.setattr(transport, "post", boom)
    order = checkout(Order(1, 500), "tok")
    assert order.status == "payment_failed"
    assert order.charge_id is None
    assert "provider unreachable" in order.error


def test_checkout_success(monkeypatch):
    monkeypatch.setattr(transport, "post", lambda path, payload: {"id": "ch_9"})
    order = checkout(Order(2, 500), "tok")
    assert (order.status, order.charge_id, order.error) == ("paid", "ch_9", None)
