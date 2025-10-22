import base64
import json
import os
from datetime import date, timedelta

from flask import render_template

from src.models.league import db, Team, Newsletter, NewsletterComment, UserSubscription, Player, SupplementalLoan
from src.routes.api import _deliver_newsletter_via_webhook, issue_user_token, render_newsletter
from src.agents import weekly_agent
from src.agents.weekly_newsletter_agent import _enforce_loanee_metadata
from src.api_football_client import APIFootballClient


class _DummyResponse:
    status_code = 200
    text = 'ok'


def test_auto_send_uses_prior_season_subscriptions(app, monkeypatch):
    monkeypatch.setenv('N8N_EMAIL_WEBHOOK_URL', 'https://example.com/webhook')
    monkeypatch.setenv('EMAIL_FROM_NAME', 'Loan Army Test')
    monkeypatch.setenv('EMAIL_FROM_ADDRESS', 'newsletter@example.com')

    prev_team = Team(team_id=123, name='Club FC', country='England', season=2023)
    curr_team = Team(team_id=123, name='Club FC', country='England', season=2024)
    db.session.add_all([prev_team, curr_team])
    db.session.commit()

    subscription = UserSubscription(
        email='fan@example.com',
        team_id=prev_team.id,
        active=True,
        unsubscribe_token='tok-prev-season',
    )
    db.session.add(subscription)
    db.session.commit()

    newsletter = Newsletter(
        team_id=curr_team.id,
        title='Club FC Weekly',
        content=json.dumps({'title': 'Club FC Weekly'}),
        structured_content=json.dumps({
            'title': 'Club FC Weekly',
            'summary': 'Summary placeholder',
            'sections': [],
        }),
        issue_date=date(2024, 9, 20),
        week_start_date=date(2024, 9, 13),
        week_end_date=date(2024, 9, 19),
        published=True,
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)

    sent_payloads: list[dict] = []

    def fake_post(url, headers=None, timeout=None, json=None, **kwargs):
        sent_payloads.append({'url': url, 'json': json})
        return _DummyResponse()

    monkeypatch.setattr('requests.post', fake_post)

    with app.test_request_context('/'):
        result = _deliver_newsletter_via_webhook(newsletter)

    assert result['status'] == 'ok'
    assert result['recipient_count'] == 1
    assert sent_payloads and sent_payloads[0]['json']['email'] == 'fan@example.com'


def test_deliver_newsletter_uses_link_base_for_unsubscribe(app, monkeypatch):
    monkeypatch.setenv('N8N_EMAIL_WEBHOOK_URL', 'https://example.com/webhook')
    monkeypatch.setenv('NEWSLETTER_LINK_BASE_URL', 'https://app.loan.army')

    team = Team(team_id=999, name='Link FC', country='England', season=2024)
    db.session.add(team)
    db.session.commit()

    subscription = UserSubscription(
        email='linkfan@example.com',
        team_id=team.id,
        active=True,
        unsubscribe_token='tok-link-test',
    )
    db.session.add(subscription)
    db.session.commit()

    newsletter = Newsletter(
        team_id=team.id,
        title='Link FC Weekly',
        content=json.dumps({'title': 'Link FC Weekly'}),
        structured_content=json.dumps({'title': 'Link FC Weekly', 'sections': []}),
        issue_date=date(2024, 9, 20),
        week_start_date=date(2024, 9, 13),
        week_end_date=date(2024, 9, 19),
        published=True,
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)

    captured: list[dict] = []

    def fake_post(url, headers=None, timeout=None, json=None, **kwargs):
        captured.append({'url': url, 'json': json})
        return _DummyResponse()

    monkeypatch.setattr('requests.post', fake_post)

    with app.test_request_context('/'):
        _deliver_newsletter_via_webhook(newsletter)

    assert captured, 'Expected payload to be sent via webhook'
    unsubscribe_url = captured[0]['json']['meta']['unsubscribe_url']
    assert unsubscribe_url == 'https://app.loan.army/subscriptions/unsubscribe/tok-link-test'


def test_newsletter_template_includes_buy_me_coffee_button(app):
    with app.app_context():
        html = render_template(
            'newsletter_email.html',
            title='Weekly Update',
            team_name='Go On Loan',
            range=('Jan 1', 'Jan 7'),
            summary='Summary',
            highlights=[],
            sections=[],
            unsubscribe_url='https://example.com/unsub',
        )

    assert html.count('data-slug="GoOnLoan"') == 2
    assert 'Buy me a coffee' in html


def test_lint_and_enrich_infers_player_id_from_latest_lookup(app, monkeypatch):
    with app.app_context():
        content = {
            'title': 'Weekly Update',
            'summary': '',
            'sections': [
                {
                    'title': 'Highlights',
                    'items': [
                        {
                            'player_name': 'H. Ogunneye',
                            'loan_team': 'Newport County',
                            'stats': {
                                'minutes': 90,
                                'goals': 0,
                                'assists': 0,
                                'yellows': 0,
                                'reds': 0,
                            },
                        }
                    ]
                }
            ]
        }

        lookup_key = weekly_agent._normalize_player_key('H. Ogunneye')
        weekly_agent._set_latest_player_lookup({
            lookup_key: [
                {
                    'player_id': 555,
                    'loan_team_api_id': 200,
                    'loan_team_name': 'Newport County',
                }
            ]
        })

        monkeypatch.setattr(weekly_agent, '_player_photo_for', lambda pid: f'https://cdn.example.com/players/{pid}.png')
        monkeypatch.setattr(weekly_agent, '_team_logo_for_player', lambda pid, loan_team_name=None: f'https://cdn.example.com/teams/{pid}.png')

        adjusted, changed = weekly_agent._apply_player_lookup(content)
        assert changed is True

        enriched = weekly_agent.lint_and_enrich(adjusted)
        item = enriched['sections'][0]['items'][0]
        assert item['player_id'] == 555
        assert item['player_photo'] == 'https://cdn.example.com/players/555.png'
        assert item['loan_team_logo'] == 'https://cdn.example.com/teams/555.png'

        weekly_agent._set_latest_player_lookup({})


def test_lint_and_enrich_attaches_sofascore_id_when_present(app):
    with app.app_context():
        player = Player(player_id=777, name='Harrison Ogunneye')
        # Expecting new sofascore_id column to persist Sofascore mapping
        player.sofascore_id = 1101989
        db.session.add(player)
        db.session.commit()

        content = {
            'title': 'Weekly Update',
            'sections': [
                {
                    'title': 'Active Loans',
                    'items': [
                        {
                            'player_id': 777,
                            'player_name': 'H. Ogunneye',
                            'loan_team': 'Newport County',
                            'stats': {
                                'minutes': 90,
                                'goals': 0,
                                'assists': 0,
                                'yellows': 0,
                                'reds': 0,
                            },
                        }
                    ],
                }
            ],
        }

        enriched = weekly_agent.lint_and_enrich(content)
        item = enriched['sections'][0]['items'][0]
        assert item['player_id'] == 777
        assert item.get('sofascore_player_id') == 1101989


def test_supplemental_loans_preserve_sofascore_id_in_summary(app, monkeypatch):
    with app.app_context():
        parent = Team(team_id=101, name='Parent FC', country='England', season=2025)
        loan_team = Team(team_id=202, name='Loan FC', country='England', season=2025)
        db.session.add_all([parent, loan_team])
        db.session.commit()

        supplemental = SupplementalLoan(
            player_name='Jordan Loan',
            parent_team_id=parent.id,
            parent_team_name=parent.name,
            loan_team_id=loan_team.id,
            loan_team_name=loan_team.name,
            season_year=2025,
            sofascore_player_id=1101989,
        )
        db.session.add(supplemental)
        db.session.commit()

        client = APIFootballClient()
        monkeypatch.setattr(client, 'get_team_name', lambda *_args, **_kwargs: parent.name)

        week_start = date(2025, 9, 15)
        week_end = week_start + timedelta(days=6)

        summary = client.summarize_parent_loans_week(
            parent_team_db_id=parent.id,
            parent_team_api_id=parent.team_id,
            season=2025,
            week_start=week_start,
            week_end=week_end,
            include_team_stats=False,
            db_session=db.session,
        )

        supplemental_items = [it for it in summary['loanees'] if it.get('source') == 'supplemental']
        assert supplemental_items, 'Expected supplemental source entries in weekly summary'
        assert supplemental_items[0].get('sofascore_player_id') == 1101989
        assert supplemental_items[0].get('loan_team_country') == 'England'


def test_newsletter_templates_render_sofascore_embed_when_available(app):
    sections = [
        {
            'title': 'Active Loans',
            'items': [
                {
                    'player_name': 'H. Ogunneye',
                    'loan_team': 'Newport County',
                    'stats': {
                        'minutes': 90,
                        'goals': 0,
                        'assists': 0,
                        'yellows': 0,
                        'reds': 0,
                    },
                    'sofascore_player_id': 1101989,
                }
            ],
        }
    ]

    with app.app_context():
        email_html = render_template(
            'newsletter_email.html',
            title='Weekly Update',
            team_name='Go On Loan',
            sections=sections,
            highlights=[],
        )
        web_html = render_template(
            'newsletter_web.html',
            title='Weekly Update',
            team_name='Go On Loan',
            sections=sections,
            highlights=[],
        )

    expected_src = 'https://widgets.sofascore.com/embed/player/1101989?widgetTheme=dark'
    assert expected_src in email_html
    assert expected_src in web_html
    assert 'Sofascore for H. Ogunneye' in email_html
    assert 'Sofascore for H. Ogunneye' in web_html


def test_templates_hide_stats_for_untracked_players(app):
    sections = [
        {
            'title': 'Active Loans',
            'items': [
                {
                    'player_name': 'Jordan Loan',
                    'loan_team': 'Lower League FC',
                    'week_summary': 'Jordan Loan is on our radar but stats are unavailable from the provider.',
                    'can_fetch_stats': False,
                    'stats': {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0},
                    'links': ['https://example.com/update'],
                    'sofascore_player_id': 123456,
                }
            ],
        }
    ]

    with app.app_context():
        email_html = render_template(
            'newsletter_email.html',
            title='Weekly Update',
            team_name='Go On Loan',
            sections=sections,
            highlights=[],
        )
        web_html = render_template(
            'newsletter_web.html',
            title='Weekly Update',
            team_name='Go On Loan',
            sections=sections,
            highlights=[],
        )

    assert "We can’t track detailed stats for this player yet." in email_html
    assert "We can’t track detailed stats for this player yet." in web_html
    assert "0’" not in email_html
    assert "0’" not in web_html


def test_enforce_metadata_handles_core_supplemental_and_internet():
    core_item = {
        'player_name': 'Core Player',
        'player_id': 777,
        'stats': {'minutes': 120, 'goals': 1, 'assists': 0, 'yellows': 0, 'reds': 0},
        'sofascore_player_id': 555,
    }
    supplemental_item = {
        'player_name': 'Supp Player',
        'stats': {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0},
    }
    internet_item = {
        'player_name': 'Supp Player',
        'links': ['https://example.com'],
        'stats': {'minutes': 0},
        'sofascore_player_id': 999,
        'player_photo': 'https://example.com/photo.png',
    }

    content = {
        'sections': [
            {'title': 'Active Loans', 'items': [core_item, supplemental_item]},
            'legacy-string-section',
            {'title': 'What the Internet is Saying', 'items': [internet_item]},
        ]
    }

    meta_pid = {
        777: {'can_fetch_stats': True, 'sofascore_player_id': 555},
    }
    meta_key = {
        weekly_agent._normalize_player_key('Supp Player'): {
            'can_fetch_stats': False,
            'sofascore_player_id': 222,
        }
    }

    updated = _enforce_loanee_metadata(content, meta_pid, meta_key)
    active = updated['sections'][0]['items'][0]
    supplemental = updated['sections'][0]['items'][1]
    internet = updated['sections'][2]['items'][0]

    # Core players retain stats and sofascore ids
    assert active.get('can_fetch_stats') is True
    assert 'stats' in active
    assert active.get('sofascore_player_id') == 555

    # Supplemental players drop stats, keep sofascore, and are marked non-trackable
    assert supplemental.get('can_fetch_stats') is False
    assert 'stats' not in supplemental
    assert supplemental.get('sofascore_player_id') == 222

    # Internet section strips stats/cards and marks skip_lookup
    assert internet.get('skip_lookup') is True
    assert 'stats' not in internet
    assert 'sofascore_player_id' not in internet


def _write_png(path: str) -> None:
    """Write a tiny opaque PNG for tests without Pillow dependencies."""
    tiny_png = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAYAAACNMs+9AAAAI0lEQVQoU2NkYGD4z0AEYBxVSFJgKgImBqoEUx0NFA0AoFoGBPX57HAAAAAASUVORK5CYII="
    )
    with open(path, 'wb') as fh:
        fh.write(tiny_png)


def test_newsletter_web_render_includes_social_meta(app, client, monkeypatch):
    monkeypatch.setenv('PUBLIC_BASE_URL', 'https://goonloan.test')
    monkeypatch.setenv('TWITTER_HANDLE', '@goonloan')
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    static_root = app.static_folder
    newsletters_dir = os.path.join(static_root, 'newsletters')
    if os.path.isdir(newsletters_dir):
        for root, dirs, files in os.walk(newsletters_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))

    team_logo_rel = os.path.join('assets', 'test-team-logo.png')
    team_logo_path = os.path.join(static_root, team_logo_rel)
    os.makedirs(os.path.dirname(team_logo_path), exist_ok=True)
    _write_png(team_logo_path)

    team = Team(team_id=987, name='Meta FC', country='England', season=2025, logo=f'/static/{team_logo_rel}')
    db.session.add(team)
    db.session.commit()

    summary_text = 'Goals, minutes, and form tracker for every United loanee this week.'

    newsletter = Newsletter(
        team_id=team.id,
        title='Manchester United Loan Watch — Week Ending 21 Sep 2025',
        content=json.dumps({'title': 'ignored for test'}),
        structured_content=json.dumps({
            'title': 'Manchester United Loan Watch — Week Ending 21 Sep 2025',
            'summary': summary_text,
            'range': ['2025-09-15', '2025-09-21'],
        }),
        issue_date=date(2025, 9, 21),
        week_start_date=date(2025, 9, 15),
        week_end_date=date(2025, 9, 21),
        published=True,
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)

    admin_token = issue_user_token('admin@example.com', role='admin')['token']
    headers = {
        'Authorization': f'Bearer {admin_token}',
        'X-API-Key': 'test-admin-key',
    }

    response = client.get(f'/newsletters/{newsletter.id}/render.html', headers=headers)

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    expected_slug = '2025-09-21'
    image_path = os.path.join(static_root, 'newsletters', expected_slug, 'cover.jpg')
    assert os.path.isfile(image_path), 'cover.jpg should be generated on render'

    assert '<meta property="og:type" content="article">' in html
    assert '<meta name="description" content="Goals, minutes, and form tracker for every United loanee this week.">' in html
    assert '<meta property="og:title" content="Manchester United Loan Watch — Week Ending 21 Sep 2025">' in html
    assert '<meta name="twitter:card" content="summary_large_image">' in html
    assert '<meta name="twitter:site" content="@goonloan">' in html

    og_url = 'content="https://goonloan.test/newsletters/2025-09-21"'
    assert f'<meta property="og:url" {og_url}>' in html

    og_image = 'content="https://goonloan.test/static/newsletters/2025-09-21/cover.jpg"'
    assert f'<meta property="og:image" {og_image}>' in html

def test_render_newsletter_includes_team_logo(app):
    with app.app_context():
        team = Team(team_id=555, name='Logo FC', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        content = {
            'title': 'Logo FC Weekly',
            'summary': 'Summary text',
            'team_logo': 'https://cdn.example.com/logo-fc.png',
            'sections': [
                {
                    'title': 'Highlights',
                    'items': [
                        {
                            'player_name': 'Player One',
                            'loan_team': 'Loan City',
                            'player_photo': 'https://cdn.example.com/player-one.jpg',
                        }
                    ]
                }
            ],
        }

        newsletter = Newsletter(
            team_id=team.id,
            title='Logo FC Weekly',
            content=json.dumps(content),
            structured_content=json.dumps(content),
            published=True,
        )
        db.session.add(newsletter)
        db.session.commit()
        newsletter_id = newsletter.id

    render_fn = getattr(render_newsletter, '__wrapped__', render_newsletter)

    with app.test_request_context(f'/newsletters/{newsletter_id}?fmt=email'):
        resp = render_fn(newsletter_id, 'email')

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'https://cdn.example.com/logo-fc.png' in html


def test_get_newsletter_returns_rendered_and_comments(app, client):
    with app.app_context():
        team = Team(team_id=456, name='Detail FC', country='England', season=2025)
        db.session.add(team)
        db.session.commit()

        content = {
            'title': 'Detail FC Weekly',
            'summary': 'Summary text',
            'rendered': {'web_html': '<h1>Detail FC Weekly</h1>'},
        }
        newsletter = Newsletter(
            team_id=team.id,
            title='Detail FC Weekly',
            content=json.dumps(content),
            structured_content=json.dumps(content),
            published=True,
        )
        db.session.add(newsletter)
        db.session.commit()

        comment = NewsletterComment(
            newsletter_id=newsletter.id,
            author_email='fan@example.com',
            author_name='Supporter',
            body='Brilliant issue!',
        )
        db.session.add(comment)
        db.session.commit()

        newsletter_id = newsletter.id

    resp = client.get(f'/newsletters/{newsletter_id}')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['id'] == newsletter_id
    assert payload['rendered']['web_html'] == '<h1>Detail FC Weekly</h1>'
    assert isinstance(payload['comments'], list)
    assert payload['comments'][0]['body'] == 'Brilliant issue!'


def test_admin_preview_send_routes_to_admin_emails(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')
    monkeypatch.setenv('ADMIN_EMAILS', 'admin1@example.com, admin2@example.com ')

    team = Team(team_id=321, name='Admin FC', country='England', season=2024)
    db.session.add(team)
    db.session.commit()

    newsletter = Newsletter(
        team_id=team.id,
        title='Admin FC Preview',
        content=json.dumps({'title': 'Admin FC Preview'}),
        structured_content=json.dumps({'title': 'Admin FC Preview', 'summary': 'Summary'}),
        issue_date=date(2024, 9, 20),
        week_start_date=date(2024, 9, 13),
        week_end_date=date(2024, 9, 19),
        published=False,
    )
    db.session.add(newsletter)
    db.session.commit()

    captured = {}

    def fake_deliver(
        n,
        *,
        recipients=None,
        subject_override=None,
        webhook_url_override=None,
        http_method_override=None,
        dry_run=False,
    ):
        captured['newsletter_id'] = n.id
        captured['recipients'] = recipients
        captured['subject'] = subject_override
        captured['dry_run'] = dry_run
        return {'status': 'ok', 'recipient_count': len(recipients or [])}

    monkeypatch.setattr('src.routes.api._deliver_newsletter_via_webhook', fake_deliver)

    token = issue_user_token('admin1@example.com', role='admin')['token']
    headers = {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
    }

    resp = client.post(
        f'/newsletters/{newsletter.id}/send',
        json={'test_to': '__admins__', 'subject': 'Preview Subject', 'dry_run': True},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'ok'
    assert body['recipient_count'] == 2
    assert body['admin_preview'] is True
    assert body['admin_recipients'] == ['admin1@example.com', 'admin2@example.com']
    assert captured['newsletter_id'] == newsletter.id
    assert captured['recipients'] == ['admin1@example.com', 'admin2@example.com']
    assert captured['subject'] == 'Preview Subject'
    assert captured['dry_run'] is True

    refreshed = Newsletter.query.get(newsletter.id)
    assert not refreshed.email_sent


def test_delete_newsletter_removes_record_and_comments(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=901, name='Delete FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    newsletter = Newsletter(
        team_id=team.id,
        title='Delete Me Weekly',
        content=json.dumps({'title': 'Delete Me Weekly'}),
        structured_content=json.dumps({'title': 'Delete Me Weekly', 'summary': 'Summary'}),
        issue_date=date(2025, 9, 19),
        week_start_date=date(2025, 9, 12),
        week_end_date=date(2025, 9, 18),
        published=True,
    )
    db.session.add(newsletter)
    db.session.commit()

    comment = NewsletterComment(
        newsletter_id=newsletter.id,
        author_email='deleter@example.com',
        body='Remove this please',
    )
    db.session.add(comment)
    db.session.commit()

    token = issue_user_token('admin@example.com', role='admin')['token']
    headers = {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
    }

    resp = client.delete(f'/newsletters/{newsletter.id}', headers=headers)

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'deleted'
    assert payload['newsletter_id'] == newsletter.id

    assert Newsletter.query.get(newsletter.id) is None
    assert NewsletterComment.query.filter_by(newsletter_id=newsletter.id).count() == 0


def _auth_headers(role_email='admin@example.com'):
    token = issue_user_token(role_email, role='admin')['token']
    return {
        'Authorization': f'Bearer {token}',
        'X-API-Key': 'test-admin-key',
    }


def _make_newsletter(team_id, *, issue_day=1, published=False, title_prefix='Bulk', idx=0):
    issue_dt = date(2025, 9, issue_day)
    week_end = issue_dt - timedelta(days=1)
    week_start = week_end - timedelta(days=6)
    newsletter = Newsletter(
        team_id=team_id,
        title=f'{title_prefix} Issue {idx + 1}',
        content=json.dumps({'title': f'{title_prefix} Issue {idx + 1}'}),
        structured_content=json.dumps({'title': f'{title_prefix} Issue {idx + 1}', 'summary': 'Summary'}),
        issue_date=issue_dt,
        week_start_date=week_start,
        week_end_date=week_end,
        published=published,
    )
    db.session.add(newsletter)
    db.session.commit()
    db.session.refresh(newsletter)
    return newsletter


def test_admin_bulk_publish_with_filter_params_and_exclusions(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=701, name='Bulk Publish FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    inside_1 = _make_newsletter(team.id, issue_day=1, idx=0, published=False)
    inside_2 = _make_newsletter(team.id, issue_day=8, idx=1, published=False)
    inside_excluded = _make_newsletter(team.id, issue_day=15, idx=2, published=False)
    inside_already = _make_newsletter(team.id, issue_day=22, idx=3, published=True)
    outside = _make_newsletter(team.id, issue_day=30, idx=4, published=False)
    outside.issue_date = date(2025, 10, 6)
    db.session.commit()

    payload = {
        'publish': True,
        'filter_params': {
            'issue_start': '2025-09-01',
            'issue_end': '2025-09-30',
        },
        'exclude_ids': [inside_excluded.id],
        'expected_total': 4,
    }

    resp = client.post('/admin/newsletters/bulk-publish', json=payload, headers=_auth_headers('bulk@example.com'))

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['publish'] is True
    assert body['updated'] == 2
    assert body.get('unchanged') == 1
    meta = body.get('meta') or {}
    assert meta.get('mode') == 'filters'
    assert meta.get('total_matched') == 4
    assert meta.get('total_selected') == 3
    assert meta.get('total_excluded') == 1
    assert inside_excluded.id in meta.get('excluded_ids', [])

    db.session.refresh(inside_1)
    db.session.refresh(inside_2)
    db.session.refresh(inside_excluded)
    db.session.refresh(inside_already)
    db.session.refresh(outside)

    assert inside_1.published is True
    assert inside_2.published is True
    assert inside_excluded.published is False
    assert inside_already.published is True
    assert outside.published is False


def test_admin_bulk_publish_filters_require_expected_total(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=702, name='Bulk Guard FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    _make_newsletter(team.id, issue_day=1, idx=0, published=False)
    _make_newsletter(team.id, issue_day=8, idx=1, published=False)

    resp = client.post(
        '/admin/newsletters/bulk-publish',
        json={
            'publish': True,
            'filter_params': {'issue_start': '2025-09-01', 'issue_end': '2025-09-30'},
        },
        headers=_auth_headers('guard@example.com'),
    )

    assert resp.status_code == 400
    body = resp.get_json()
    assert 'expected_total' in body.get('error', '') or body.get('field') == 'expected_total'


def test_admin_bulk_delete_with_filters_and_exclusions(app, client, monkeypatch):
    monkeypatch.setenv('ADMIN_API_KEY', 'test-admin-key')

    team = Team(team_id=703, name='Bulk Delete FC', country='England', season=2025)
    db.session.add(team)
    db.session.commit()

    keep_excluded = _make_newsletter(team.id, issue_day=1, idx=0, published=False)
    delete_one = _make_newsletter(team.id, issue_day=8, idx=1, published=False)
    delete_two = _make_newsletter(team.id, issue_day=15, idx=2, published=True)
    delete_three = _make_newsletter(team.id, issue_day=22, idx=3, published=False)
    outside = _make_newsletter(team.id, issue_day=30, idx=4, published=False)
    outside.issue_date = date(2025, 10, 6)
    db.session.commit()

    resp = client.delete(
        '/admin/newsletters/bulk',
        json={
            'filter_params': {
                'issue_start': '2025-09-01',
                'issue_end': '2025-09-30',
            },
            'exclude_ids': [keep_excluded.id],
            'expected_total': 4,
        },
        headers=_auth_headers('deleter@example.com'),
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body['deleted'] == 3
    meta = body.get('meta') or {}
    assert meta.get('mode') == 'filters'
    assert meta.get('total_matched') == 4
    assert meta.get('total_selected') == 3
    assert meta.get('total_excluded') == 1
    assert keep_excluded.id in meta.get('excluded_ids', [])

    remaining_ids = {row.id for row in Newsletter.query.all()}
    assert remaining_ids == {keep_excluded.id, outside.id}
