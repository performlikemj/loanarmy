import json

from flask import render_template

from src.models.league import db, Team, UserSubscription
from src.routes.api import issue_user_token


def _create_team(name: str, api_id: int = 100, country: str = "England", season: int = 2025):
    team = Team(
        team_id=api_id,
        name=name,
        country=country,
        season=season,
        is_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def _create_subscription(email: str, team: Team, *, token: str = "token-123", active: bool = True):
    sub = UserSubscription(
        email=email.lower(),
        team_id=team.id,
        preferred_frequency='weekly',
        active=active,
        unsubscribe_token=token,
    )
    db.session.add(sub)
    db.session.flush()
    return sub


def _auth_header(app, email="fan@example.com"):
    with app.app_context():
        payload = issue_user_token(email)
    return {'Authorization': f"Bearer {payload['token']}"}


def test_token_unsubscribe_get_deactivates_and_renders_confirmation(app, client, monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://example.com')
    with app.app_context():
        team = _create_team("Monaco", api_id=555)
        _create_subscription('fan@example.com', team, token='abc123')
        db.session.commit()

    resp = client.get('/subscriptions/unsubscribe/abc123')
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert 'You are unsubscribed' in body
    assert 'https://example.com/manage' in body

    with app.app_context():
        refreshed = UserSubscription.query.filter_by(unsubscribe_token='abc123').first()
        assert refreshed is not None
        assert refreshed.active is False


def test_token_unsubscribe_get_handles_already_inactive(app, client):
    with app.app_context():
        team = _create_team("Inactive Team", api_id=777)
        _create_subscription('fan@example.com', team, token='lazy-token', active=False)
        db.session.commit()

    resp = client.get('/subscriptions/unsubscribe/lazy-token')
    assert resp.status_code == 200
    assert 'Already unsubscribed' in resp.get_data(as_text=True)


def test_token_unsubscribe_get_invalid_token(app, client):
    resp = client.get('/subscriptions/unsubscribe/not-real')
    assert resp.status_code == 404
    assert 'Link expired or invalid' in resp.get_data(as_text=True)


def test_token_unsubscribe_post_json(app, client):
    with app.app_context():
        team = _create_team("Ajax", api_id=888)
        _create_subscription('fan@example.com', team, token='post-token')
        db.session.commit()

    resp = client.post('/subscriptions/unsubscribe/post-token')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['message'] == 'Unsubscribed successfully'
    with app.app_context():
        refreshed = UserSubscription.query.filter_by(unsubscribe_token='post-token').first()
        assert refreshed.active is False


def test_unsubscribe_confirmation_template_contains_links(app, monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://example.com')
    with app.app_context():
        html = render_template(
            'unsubscribe_confirmation.html',
            status='ok',
            headline='You are unsubscribed',
            body='Thanks for reading.',
            manage_url='https://example.com/manage',
            team_name='Monaco',
        )
    assert 'Monaco' in html
    assert 'Manage other preferences' in html
    assert 'https://example.com/manage' in html


def test_unsubscribe_by_email_uses_auth_email_when_missing(app, client):
    with app.app_context():
        team = _create_team('PSV Eindhoven', api_id=501)
        _create_subscription('fan@example.com', team)
        team_id = team.id
        db.session.commit()

    headers = {**_auth_header(app), 'Content-Type': 'application/json'}
    resp = client.post(
        '/subscriptions/unsubscribe',
        data=json.dumps({'team_ids': [team_id]}),
        headers=headers,
    )

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['count'] == 1

    with app.app_context():
        refreshed = UserSubscription.query.filter_by(email='fan@example.com', team_id=team_id).first()
        assert refreshed is not None
        assert refreshed.active is False


def test_update_my_subscriptions_creates_and_deactivates(app, client):
    with app.app_context():
        team_a = _create_team("Manchester United", api_id=1)
        team_b = _create_team("Nottingham Forest", api_id=2)
        team_a_id, team_b_id = team_a.id, team_b.id
        db.session.commit()

    headers = _auth_header(app)

    # Initial subscription to both teams
    resp = client.post(
        '/subscriptions/me',
        data=json.dumps({'team_ids': [team_a_id, team_b_id]}),
        headers={**headers, 'Content-Type': 'application/json'},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['created_count'] == 2
    assert payload['reactivated_count'] == 0
    assert payload['deactivated_count'] == 0
    assert {row['team_id'] for row in payload['subscriptions']} == {team_a_id, team_b_id}

    with app.app_context():
        rows = UserSubscription.query.filter_by(email='fan@example.com').all()
        assert len(rows) == 2
        assert all(row.active for row in rows)

    # Remove one subscription and ensure the other deactivates
    resp = client.post(
        '/subscriptions/me',
        data=json.dumps({'team_ids': [team_a_id]}),
        headers={**headers, 'Content-Type': 'application/json'},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['created_count'] == 0
    assert payload['reactivated_count'] == 0
    assert payload['deactivated_count'] == 1
    assert {row['team_id'] for row in payload['subscriptions']} == {team_a_id}

    with app.app_context():
        active_rows = UserSubscription.query.filter_by(email='fan@example.com', active=True).all()
        assert len(active_rows) == 1
        assert active_rows[0].team_id == team_a_id


def test_update_my_subscriptions_rejects_unauthenticated(client):
    resp = client.post('/subscriptions/me', json={'team_ids': []})
    assert resp.status_code == 401


def test_update_my_subscriptions_ignores_unknown_ids(app, client):
    with app.app_context():
        team = _create_team('Barcelona', api_id=10)
        team_id = team.id
        db.session.commit()

    headers = _auth_header(app)
    resp = client.post(
        '/subscriptions/me',
        json={'team_ids': [team_id, 9999, 'not-an-int']},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['created_count'] == 1
    assert set(data['ignored_team_ids']) == {9999, 'not-an-int'}
