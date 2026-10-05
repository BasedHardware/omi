import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from utils.webhooks import (
    _append_query_params,
    _is_valid_audio_bytes_webhook_url,
    send_audio_bytes_developer_webhook,
)


class TestAudioBytesWebhookUrl(unittest.IsolatedAsyncioTestCase):
    """Regression test suite for #20666.

    Validates that configured developer audio-bytes webhook URLs (such as query-on-root
    without a trailing slash and bracketed IPv6 literals) are accepted by the sender
    validator and query appender rather than being discarded before delivery.
    """

    def test_query_on_root_without_trailing_slash_is_valid(self):
        url = 'https://hooks.example.com?token=synthetic'
        self.assertTrue(_is_valid_audio_bytes_webhook_url(url))

    def test_query_on_root_with_trailing_slash_is_valid(self):
        url = 'https://hooks.example.com/?token=synthetic'
        self.assertTrue(_is_valid_audio_bytes_webhook_url(url))

    def test_ipv6_literal_target_is_valid(self):
        url = 'https://[2606:4700:4700::1111]/audio'
        self.assertTrue(_is_valid_audio_bytes_webhook_url(url))

    def test_ipv4_mapped_ipv6_literal_target_is_valid(self):
        url = 'https://[::ffff:8.8.8.8]/audio'
        self.assertTrue(_is_valid_audio_bytes_webhook_url(url))

    def test_ipv6_literal_with_port_and_query_is_valid(self):
        url = 'https://[2606:4700:4700::1111]:8080?token=synthetic'
        self.assertTrue(_is_valid_audio_bytes_webhook_url(url))

    def test_standard_hostname_and_ipv4_urls_are_valid(self):
        self.assertTrue(_is_valid_audio_bytes_webhook_url('https://hooks.example.com/audio'))
        self.assertTrue(_is_valid_audio_bytes_webhook_url('http://localhost:8000'))
        self.assertTrue(_is_valid_audio_bytes_webhook_url('http://192.168.1.1:8080/audio'))

    def test_invalid_urls_rejected(self):
        self.assertFalse(_is_valid_audio_bytes_webhook_url(''))
        self.assertFalse(_is_valid_audio_bytes_webhook_url('   '))
        self.assertFalse(_is_valid_audio_bytes_webhook_url('ftp://example.com/audio'))
        self.assertFalse(_is_valid_audio_bytes_webhook_url('javascript:alert(1)'))
        self.assertFalse(_is_valid_audio_bytes_webhook_url('https://[bad::ipv6::literal]/audio'))
        self.assertFalse(_is_valid_audio_bytes_webhook_url('https://[zzz]/audio'))
        self.assertFalse(_is_valid_audio_bytes_webhook_url('https://example.com/audio with spaces'))

    def test_append_query_params_to_query_on_root(self):
        url = 'https://hooks.example.com?token=synthetic'
        appended = _append_query_params(url, {'sample_rate': 16000, 'uid': 'u1'})
        self.assertEqual(appended, 'https://hooks.example.com?token=synthetic&sample_rate=16000&uid=u1')

    def test_append_query_params_to_ipv6_literal(self):
        url = 'https://[2606:4700:4700::1111]/audio'
        appended = _append_query_params(url, {'sample_rate': 16000, 'uid': 'u1'})
        self.assertEqual(appended, 'https://[2606:4700:4700::1111]/audio?sample_rate=16000&uid=u1')

    async def test_send_audio_bytes_webhook_does_not_reject_valid_query_on_root(self):
        uid = 'test-uid'
        sample_rate = 16000
        data = bytearray(b'\x00\x00' * sample_rate)
        mock_response = MagicMock(status_code=200)

        with (
            patch('utils.webhooks.user_webhook_status_db', return_value=True),
            patch('utils.webhooks.get_user_webhook_db', return_value='https://hooks.example.com?token=synthetic'),
            patch('utils.webhooks.record_dev_webhook_success'),
            patch('utils.webhooks._post_dev_webhook', new_callable=AsyncMock, return_value=mock_response) as mock_post,
        ):
            await send_audio_bytes_developer_webhook(uid, sample_rate, data)

        mock_post.assert_awaited()
        call_url = mock_post.await_args[0][1]
        self.assertTrue(call_url.startswith('https://hooks.example.com?token=synthetic'))
        self.assertIn('sample_rate=16000', call_url)
        self.assertIn('uid=test-uid', call_url)

    async def test_send_audio_bytes_webhook_does_not_reject_ipv6_literal(self):
        uid = 'test-uid'
        sample_rate = 16000
        data = bytearray(b'\x00\x00' * sample_rate)
        mock_response = MagicMock(status_code=200)

        with (
            patch('utils.webhooks.user_webhook_status_db', return_value=True),
            patch('utils.webhooks.get_user_webhook_db', return_value='https://[2606:4700:4700::1111]/audio'),
            patch('utils.webhooks.record_dev_webhook_success'),
            patch('utils.webhooks._post_dev_webhook', new_callable=AsyncMock, return_value=mock_response) as mock_post,
        ):
            await send_audio_bytes_developer_webhook(uid, sample_rate, data)

        mock_post.assert_awaited()
        call_url = mock_post.await_args[0][1]
        self.assertTrue(call_url.startswith('https://[2606:4700:4700::1111]/audio'))
        self.assertIn('sample_rate=16000', call_url)
        self.assertIn('uid=test-uid', call_url)
