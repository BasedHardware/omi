from types import SimpleNamespace

import pytest

from config.app_channel import APP_CHANNEL_HEADER, app_channel, is_testflight


def test_app_channel_is_bounded():
    assert app_channel(' Store ') == 'store'
    assert app_channel('BETA') == 'beta'
    assert app_channel('x' * 500) == 'unknown'
    assert app_channel(None) == 'unknown'


@pytest.mark.parametrize(
    ('headers', 'expected'),
    [
        ({APP_CHANNEL_HEADER: 'beta'}, True),
        ({APP_CHANNEL_HEADER: ' Beta '}, True),
        ({APP_CHANNEL_HEADER: 'store'}, False),
        ({APP_CHANNEL_HEADER: 'testflight'}, False),
        ({}, False),
    ],
)
def test_is_testflight_reads_only_the_beta_channel(headers, expected):
    assert is_testflight(SimpleNamespace(headers=headers)) is expected
