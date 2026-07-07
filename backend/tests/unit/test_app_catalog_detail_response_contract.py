"""App catalog/detail routes expose desktop-safe app response shapes."""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from models.app import App  # noqa: E402
from routers.apps import AppCatalogResponse, AppSearchResponse  # noqa: E402


def _app_payload():
    return {
        'id': 'app1',
        'name': 'Catalog App',
        'description': 'Does things',
        'image': 'https://example.com/icon.png',
        'category': 'productivity',
        'author': 'Someone',
        'capabilities': {'chat', 'external_integration'},
        'approved': True,
        'private': False,
        'installs': 12,
        'rating_avg': 4,
        'rating_count': 2,
        'is_paid': False,
        'price': 0,
        'enabled': True,
        'twitter': {'handle': 'legacy-object'},
        'reviews': [{'uid': 'u1', 'rated_at': '2026-07-06T10:00:00Z', 'score': 5, 'review': 'nice'}],
        'chat_tools': [
            {
                'name': 'tool',
                'description': 'Runs a tool',
                'endpoint': 'https://example.com/tool',
            }
        ],
        'payment_product_id': 'prod_123',
    }


def test_v2_apps_catalog_response_uses_desktop_safe_app_items():
    response = AppCatalogResponse.model_validate(
        {
            'groups': [
                {
                    'capability': {'id': 'chat', 'title': 'Chat'},
                    'data': [_app_payload()],
                    'pagination': {
                        'total': 1,
                        'count': 1,
                        'offset': 0,
                        'limit': 20,
                        'hasNext': False,
                        'hasPrevious': False,
                    },
                }
            ],
            'meta': {'capabilities': [], 'groupCount': 1, 'limit': 20, 'offset': 0},
        }
    )

    app = response.model_dump()['groups'][0]['data'][0]
    assert app['capabilities'] == ['chat', 'external_integration'] or app['capabilities'] == [
        'external_integration',
        'chat',
    ]
    assert app['rating_avg'] == 4.0
    assert 'twitter' not in app
    assert 'reviews' not in app
    assert 'chat_tools' not in app
    assert 'payment_product_id' not in app


def test_v2_apps_search_response_uses_same_desktop_safe_app_items():
    response = AppSearchResponse.model_validate(
        {
            'data': [_app_payload()],
            'pagination': {'total': 1, 'count': 1, 'offset': 0, 'limit': 20, 'hasNext': False, 'hasPrevious': False},
            'filters': {'sort': 'name'},
        }
    )

    app = response.model_dump()['data'][0]
    assert app['id'] == 'app1'
    assert 'twitter' not in app
    assert 'reviews' not in app


def test_v1_app_detail_response_preserves_shared_client_fields():
    response = App.model_validate(
        {
            **_app_payload(),
            'uid': 'owner1',
            'status': 'approved',
            'chat_prompt': 'chat',
            'memory_prompt': 'memory',
            'persona_prompt': None,
            'payment_plan': None,
            'username': 'owner',
            'created_at': '2026-07-06T10:00:00Z',
            'external_integration': {'auth_steps': [{'name': 'Connect', 'url': 'https://example.com/oauth'}]},
        }
    )

    app = response.model_dump()
    assert app['id'] == 'app1'
    assert app['external_integration']['auth_steps'][0]['name'] == 'Connect'
    assert app['reviews'][0]['uid'] == 'u1'
    assert app['chat_tools'][0]['name'] == 'tool'
    assert app['payment_product_id'] == 'prod_123'
