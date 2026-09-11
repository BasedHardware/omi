import unittest
from omi_cli.json_input import load_json_input


class TestRecursionErrorFix(unittest.TestCase):
    def test_deeply_nested_json_raises_value_error(self):
        raw = '{"child":' * 10_000 + '0' + '}' * 10_000
        with self.assertRaises(ValueError) as ctx:
            load_json_input(raw)
        self.assertIn("nested too deeply", str(ctx.exception))

    def test_normal_nested_json_still_works(self):
        raw = '{"a":{"b":{"c":1}}}'
        result = load_json_input(raw)
        self.assertEqual(result["a"]["b"]["c"], 1)

    def test_malformed_json_still_raises_value_error(self):
        with self.assertRaises(ValueError):
            load_json_input('{"unclosed"}')

    def test_non_finite_number_still_raises_value_error(self):
        with self.assertRaises(ValueError):
            load_json_input('{"x": Infinity}')


if __name__ == "__main__":
    unittest.main()
