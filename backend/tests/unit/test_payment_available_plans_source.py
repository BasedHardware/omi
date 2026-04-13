from pathlib import Path

PAYMENT_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def test_available_plans_support_partial_billing_options():
    source = PAYMENT_SOURCE_FILE.read_text()

    assert 'if monthly_price_id:' in source
    assert 'if annual_price_id:' in source
    assert 'if not monthly_price_id or not annual_price_id:' not in source
