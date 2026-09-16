"""Unit tests for Twitter Omi Integration hardening."""
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from models import (
    ChatToolResponse,
    PostTweetRequest,
    GetUserProfileRequest,
    LikeTweetRequest,
)
from main import (
    _sanitize_username,
    _sanitize_tweet_id,
    _safe_int,
    format_tweet,
)


class TestInputSanitization(unittest.TestCase):
    def test_sanitize_username_variants(self):
        self.assertEqual(_sanitize_username("@elonmusk"), "elonmusk")
        self.assertEqual(_sanitize_username("  @jack  "), "jack")
        self.assertEqual(_sanitize_username("https://twitter.com/sama"), "sama")
        self.assertEqual(_sanitize_username("https://x.com/karpathy/"), "karpathy")
        self.assertEqual(_sanitize_username("plain_user"), "plain_user")
        self.assertIsNone(_sanitize_username(""))
        self.assertIsNone(_sanitize_username(None))
        self.assertIsNone(_sanitize_username("   "))

    def test_sanitize_tweet_id_variants(self):
        self.assertEqual(_sanitize_tweet_id("#1891234567890"), "1891234567890")
        self.assertEqual(_sanitize_tweet_id("  #987654321  "), "987654321")
        self.assertEqual(_sanitize_tweet_id("123456789"), "123456789")
        self.assertIsNone(_sanitize_tweet_id(""))
        self.assertIsNone(_sanitize_tweet_id(None))
        self.assertIsNone(_sanitize_tweet_id("   "))

    def test_safe_int(self):
        self.assertEqual(_safe_int("123"), 123)
        self.assertEqual(_safe_int(456), 456)
        self.assertEqual(_safe_int(None, 0), 0)
        self.assertEqual(_safe_int("not_a_num", 5), 5)
        self.assertEqual(_safe_int({}, 0), 0)


class TestModelValidation(unittest.TestCase):
    def test_post_tweet_request_validation(self):
        req = PostTweetRequest(text="  Hello World  ", reply_to="#12345")
        self.assertEqual(req.text, "Hello World")
        self.assertEqual(req.reply_to, "12345")

    def test_get_user_profile_request_validation(self):
        req = GetUserProfileRequest(username="  @BasedHardware ")
        self.assertEqual(req.username, "BasedHardware")

    def test_tweet_action_request_validation(self):
        req = LikeTweetRequest(tweet_id=" #999000111 ")
        self.assertEqual(req.tweet_id, "999000111")


class TestFormatTweetResilience(unittest.TestCase):
    def test_format_tweet_empty_or_non_dict(self):
        self.assertEqual(format_tweet(None), "")
        self.assertEqual(format_tweet("invalid"), "")
        self.assertEqual(format_tweet(123), "")

    def test_format_tweet_missing_optional_fields(self):
        tweet = {
            "id": "1001",
            "text": "Testing tweet without metrics or created_at",
        }
        res = format_tweet(tweet)
        self.assertIn("Testing tweet without metrics", res)
        self.assertIn("ID: `1001`", res)

    def test_format_tweet_null_fields(self):
        tweet = {
            "id": "1002",
            "text": "Tweet with nulls",
            "created_at": None,
            "public_metrics": None,
            "author_id": "auth123",
        }
        includes = {
            "users": [
                None,
                {"id": "auth123", "name": "Author", "username": "auth_user"},
            ]
        }
        res = format_tweet(tweet, includes)
        self.assertIn("@auth_user", res)
        self.assertIn("Tweet with nulls", res)

    def test_format_tweet_corrupt_metrics(self):
        tweet = {
            "id": "1003",
            "text": "Metrics corrupted",
            "public_metrics": {
                "like_count": "invalid",
                "retweet_count": None,
                "reply_count": "15",
            },
        }
        res = format_tweet(tweet)
        self.assertIn("Replies: 15", res)


class TestChatToolResponse(unittest.TestCase):
    def test_chat_tool_response_error(self):
        resp = ChatToolResponse(error="Something failed")
        self.assertEqual(resp.error, "Something failed")
        self.assertIsNone(resp.result)

    def test_chat_tool_response_success(self):
        resp = ChatToolResponse(result="Success message")
        self.assertEqual(resp.result, "Success message")
        self.assertIsNone(resp.error)


if __name__ == "__main__":
    unittest.main()
