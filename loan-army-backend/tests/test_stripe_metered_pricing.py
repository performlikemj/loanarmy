from types import SimpleNamespace

import stripe

from src.models.league import db, UserAccount, StripeConnectedAccount
from src.routes import stripe_journalist as stripe_journalist_routes
from src.routes.api import _user_serializer


def _auth_header(email: str) -> dict:
    token = _user_serializer().dumps({'email': email})
    return {'Authorization': f'Bearer {token}'}


def test_create_price_uses_metered_billing_with_meter(client, monkeypatch):
    user = UserAccount(
        email='journalist@example.com',
        display_name='Test Journalist',
        display_name_lower='test journalist',
        is_journalist=True,
    )
    db.session.add(user)
    db.session.flush()

    account = StripeConnectedAccount(
        journalist_user_id=user.id,
        stripe_account_id='acct_test_123',
        onboarding_complete=True,
        payouts_enabled=True,
        charges_enabled=True,
        details_submitted=True,
    )
    db.session.add(account)
    db.session.commit()

    created = {}

    def fake_product_create(**kwargs):
        created['product'] = kwargs
        return SimpleNamespace(id='prod_test_123')

    def fake_price_create(**kwargs):
        created['price'] = kwargs
        return SimpleNamespace(id='price_test_123')

    def fake_request(method, url, params=None):
        if method.lower() == 'get' and url == '/v1/billing/meters':
            return SimpleNamespace(data=[])
        if method.lower() == 'post' and url == '/v1/billing/meters':
            return SimpleNamespace(id='mtr_test_123', event_name=params.get('event_name'))
        raise AssertionError(f"Unexpected Stripe request {method} {url}")

    monkeypatch.setattr(stripe.Product, 'create', fake_product_create)
    monkeypatch.setattr(stripe.Price, 'create', fake_price_create)
    monkeypatch.setattr(stripe_journalist_routes, '_stripe_request', fake_request)

    response = client.post(
        '/api/stripe/journalist/create-price',
        json={'price': 3.5},
        headers=_auth_header(user.email),
    )

    assert response.status_code == 201
    assert created['price']['recurring']['usage_type'] == 'metered'
    assert created['price']['recurring']['meter'] == 'mtr_test_123'
