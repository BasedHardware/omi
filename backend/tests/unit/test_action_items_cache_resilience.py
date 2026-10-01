import json
import unittest

import redis as redis_pkg

import database.action_items_cache as ai_cache
from database import redis_db


class _FakeRedis:
    def __init__(self):
        self.store = {}
        self.expires = {}
        self.should_raise = False

    def get(self, key):
        if self.should_raise:
            raise redis_pkg.exceptions.RedisError("Simulated Redis Failure")
        val = self.store.get(key)
        return val.encode() if isinstance(val, str) else val

    def set(self, key, value, ex=None):
        if self.should_raise:
            raise redis_pkg.exceptions.RedisError("Simulated Redis Failure")
        self.store[key] = value
        if ex is not None:
            self.expires[key] = ex

    def incr(self, key):
        if self.should_raise:
            raise redis_pkg.exceptions.RedisError("Simulated Redis Failure")
        val = int(self.store.get(key, 0)) + 1
        self.store[key] = str(val)
        return val

    def expire(self, key, ttl):
        if self.should_raise:
            raise redis_pkg.exceptions.RedisError("Simulated Redis Failure")
        self.expires[key] = ttl
        return True

    def pipeline(self):
        if self.should_raise:
            raise redis_pkg.exceptions.RedisError("Simulated Redis Failure")
        outer = self

        class _Pipe:
            def __init__(self):
                self.ops = []

            def incr(self, k):
                self.ops.append(('incr', k))
                return self

            def expire(self, k, t):
                self.ops.append(('expire', k, t))
                return self

            def execute(self):
                if outer.should_raise:
                    raise redis_pkg.exceptions.RedisError("Pipeline execution failure")
                for op in self.ops:
                    if op[0] == 'incr':
                        outer.incr(op[1])
                    elif op[0] == 'expire':
                        outer.expire(op[1], op[2])
                self.ops = []

        return _Pipe()


class TestActionItemsCacheResilience(unittest.TestCase):
    def setUp(self):
        self.fake_redis = _FakeRedis()
        self.orig_r = getattr(redis_db, 'r', None)
        redis_db.r = self.fake_redis

    def tearDown(self):
        redis_db.r = self.orig_r

    def test_clean_uid_valid(self):
        self.assertEqual(ai_cache._clean_uid("user_12345"), "user_12345")
        self.assertEqual(ai_cache._clean_uid("  user_abc  "), "user_abc")

    def test_clean_uid_rejects_non_string(self):
        self.assertIsNone(ai_cache._clean_uid(None))
        self.assertIsNone(ai_cache._clean_uid(12345))
        self.assertIsNone(ai_cache._clean_uid(["user"]))
        self.assertIsNone(ai_cache._clean_uid({"uid": "123"}))

    def test_clean_uid_rejects_empty_or_whitespace(self):
        self.assertIsNone(ai_cache._clean_uid(""))
        self.assertIsNone(ai_cache._clean_uid("   "))
        self.assertIsNone(ai_cache._clean_uid("\t\n"))

    def test_clean_uid_rejects_oversized(self):
        oversized = "u" * 129
        self.assertIsNone(ai_cache._clean_uid(oversized))
        at_limit = "u" * 128
        self.assertEqual(ai_cache._clean_uid(at_limit), at_limit)

    def test_clean_uid_rejects_control_chars_and_null(self):
        self.assertIsNone(ai_cache._clean_uid("user\nname"))
        self.assertIsNone(ai_cache._clean_uid("user\rname"))
        self.assertIsNone(ai_cache._clean_uid("user\0name"))
        self.assertIsNone(ai_cache._clean_uid("user\x1bname"))

    def test_clean_uid_rejects_traversal(self):
        self.assertIsNone(ai_cache._clean_uid("../etc/passwd"))
        self.assertIsNone(ai_cache._clean_uid("user..name"))

    def test_clean_key_boundaries(self):
        self.assertEqual(ai_cache._clean_key("ail:u1:1:fingerprint"), "ail:u1:1:fingerprint")
        self.assertIsNone(ai_cache._clean_key(""))
        self.assertIsNone(ai_cache._clean_key("k" * 257))
        self.assertIsNone(ai_cache._clean_key("key\0bad"))
        self.assertIsNone(ai_cache._clean_key(1234))

    def test_version_key_generation(self):
        self.assertEqual(ai_cache._version_key("alice"), "ail:ver:alice")
        self.assertIsNone(ai_cache._version_key("../bad"))
        self.assertIsNone(ai_cache._version_key(""))

    def test_list_cache_key_deterministic_and_sanitized(self):
        k1 = ai_cache.list_cache_key("user1", 1, {"limit": 10, "offset": 0})
        k2 = ai_cache.list_cache_key("user1", 1, {"offset": 0, "limit": 10})
        self.assertEqual(k1, k2)
        self.assertTrue(k1.startswith("ail:user1:1:"))
        k_neg = ai_cache.list_cache_key("user1", -5, {})
        self.assertTrue(k_neg.startswith("ail:user1:0:"))
        self.assertEqual(ai_cache.list_cache_key("", 1, {}), "")
        self.assertEqual(ai_cache.list_cache_key(None, 1, {}), "")

    def test_etag_computation_and_weak_prefix(self):
        body = {"items": [1, 2, 3], "total": 3}
        etag = ai_cache.compute_etag(body)
        self.assertTrue(etag.startswith('W/"'))
        self.assertTrue(etag.endswith('"'))
        self.assertEqual(len(etag), 3 + 32 + 1)
        etag2 = ai_cache.compute_etag({"total": 3, "items": [1, 2, 3]})
        self.assertEqual(etag, etag2)

    def test_if_none_match_exact_and_weak_matching(self):
        etag = 'W/"12345abcdef"'
        self.assertTrue(ai_cache.if_none_match_matches('W/"12345abcdef"', etag))
        self.assertTrue(ai_cache.if_none_match_matches('"12345abcdef"', etag))
        self.assertTrue(ai_cache.if_none_match_matches('12345abcdef', etag))
        self.assertFalse(ai_cache.if_none_match_matches('W/"mismatched"', etag))
        self.assertFalse(ai_cache.if_none_match_matches(None, etag))
        self.assertFalse(ai_cache.if_none_match_matches("", etag))

    def test_if_none_match_wildcard(self):
        self.assertTrue(ai_cache.if_none_match_matches('*', 'W/"anyetag"'))
        self.assertTrue(ai_cache.if_none_match_matches(' "tag1", * ', 'W/"anyetag"'))

    def test_if_none_match_multi_token_header(self):
        etag = 'W/"match_me"'
        header = 'W/"prev_etag", "match_me", W/"next_etag"'
        self.assertTrue(ai_cache.if_none_match_matches(header, etag))
        header_no_match = 'W/"other1", "other2"'
        self.assertFalse(ai_cache.if_none_match_matches(header_no_match, etag))

    def test_write_cached_list_ttl_clamping(self):
        ai_cache.write_cached_list("valid_key", body={"ok": True}, etag='W/"123"', ttl=9999)
        self.assertEqual(self.fake_redis.expires.get("valid_key"), 300)
        ai_cache.write_cached_list("zero_key", body={"ok": True}, etag='W/"123"', ttl=0)
        self.assertNotIn("zero_key", self.fake_redis.store)
        ai_cache.write_cached_list("neg_key", body={"ok": True}, etag='W/"123"', ttl=-10)
        self.assertNotIn("neg_key", self.fake_redis.store)

    def test_read_cached_list_corrupted_payload_shapes(self):
        self.fake_redis.store["key1"] = json.dumps(["a", "b"])
        self.assertIsNone(ai_cache.read_cached_list("key1"))

        self.fake_redis.store["key2"] = json.dumps({"etag": 'W/"123"'})
        self.assertIsNone(ai_cache.read_cached_list("key2"))

        self.fake_redis.store["key3"] = json.dumps({"etag": 12345, "body": {}})
        self.assertIsNone(ai_cache.read_cached_list("key3"))

        self.fake_redis.store["key4"] = json.dumps({"etag": 'W/"123"', "body": "string_not_dict"})
        self.assertIsNone(ai_cache.read_cached_list("key4"))

        self.fake_redis.store["key5"] = json.dumps({"etag": 'W/"123"', "body": {"items": []}})
        res = ai_cache.read_cached_list("key5")
        self.assertIsNotNone(res)
        self.assertEqual(res["etag"], 'W/"123"')
        self.assertEqual(res["body"], {"items": []})

    def test_fail_open_when_redis_is_none(self):
        redis_db.r = None
        ai_cache.bump_action_items_list_version("user1")
        self.assertIsNone(ai_cache.get_action_items_list_version("user1"))
        self.assertIsNone(ai_cache.read_cached_list("any_key"))
        ai_cache.write_cached_list("any_key", body={"a": 1}, etag='W/"1"', ttl=30)

    def test_fail_open_on_redis_errors(self):
        self.fake_redis.should_raise = True
        ai_cache.bump_action_items_list_version("user1")
        self.assertIsNone(ai_cache.get_action_items_list_version("user1"))
        self.assertIsNone(ai_cache.read_cached_list("any_key"))
        ai_cache.write_cached_list("any_key", body={"a": 1}, etag='W/"1"', ttl=30)

    def test_bump_and_get_version_cycle(self):
        v0 = ai_cache.get_action_items_list_version("user_cycle")
        self.assertEqual(v0, 0)
        ai_cache.bump_action_items_list_version("user_cycle")
        v1 = ai_cache.get_action_items_list_version("user_cycle")
        self.assertEqual(v1, 1)
        ai_cache.bump_action_items_list_version("user_cycle")
        v2 = ai_cache.get_action_items_list_version("user_cycle")
        self.assertEqual(v2, 2)
        self.assertEqual(self.fake_redis.expires.get("ail:ver:user_cycle"), 7 * 24 * 3600)
