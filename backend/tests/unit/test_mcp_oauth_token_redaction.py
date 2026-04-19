from models.app import App


def _sample_app() -> App:
    return App(
        id='app1',
        name='demo',
        uid='owner',
        private=False,
        approved=True,
        status='approved',
        category='utilities-and-tools',
        author='owner',
        description='demo',
        image='img',
        capabilities={'chat'},
        external_integration={
            'mcp_server_url': 'https://mcp.example.com',
            'mcp_oauth_tokens': {
                'client_id': 'cid',
                'client_secret': 'csecret',
                'access_token': 'atoken',
                'refresh_token': 'rtoken',
                'code_verifier': 'pkce',
                'token_endpoint': 'https://oauth.example/token',
                'redirect_uri': 'https://api.omi.me/v1/apps/mcp/callback',
                'expires_at': 12345,
            },
        },
    )


def test_to_reduced_dict_redacts_mcp_oauth_tokens():
    app = _sample_app()

    reduced = app.to_reduced_dict()

    assert 'external_integration' in reduced
    assert reduced['external_integration']['mcp_server_url'] == 'https://mcp.example.com'
    assert 'mcp_oauth_tokens' not in reduced['external_integration']


def test_to_safe_response_dict_redacts_mcp_oauth_tokens():
    app = _sample_app()

    safe = app.to_safe_response_dict()

    assert 'external_integration' in safe
    assert safe['external_integration']['mcp_server_url'] == 'https://mcp.example.com'
    assert 'mcp_oauth_tokens' not in safe['external_integration']


def test_reduce_dict_redacts_mcp_oauth_tokens_from_cached_dicts():
    raw = _sample_app().model_dump(mode='json')

    reduced = App.reduce_dict(raw)

    assert 'external_integration' in reduced
    assert reduced['external_integration']['mcp_server_url'] == 'https://mcp.example.com'
    assert 'mcp_oauth_tokens' not in reduced['external_integration']


def test_reduce_dict_does_not_inject_external_integration_when_missing():
    raw = {
        'id': 'app2',
        'name': 'plain-app',
        'uid': 'owner',
        'private': False,
        'approved': True,
        'status': 'approved',
        'category': 'utilities-and-tools',
        'author': 'owner',
        'description': 'demo',
        'image': 'img',
        'capabilities': ['chat'],
    }

    reduced = App.reduce_dict(raw)

    assert 'external_integration' not in reduced
