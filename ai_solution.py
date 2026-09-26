```python
def persisted_started_seconds(value: typing.Optional[bool]) -> typing.Optional[int]:
    if isinstance(value, bool):
        return None
    return value

# In the test file:

class TestListenStartedSeconds(unittest.TestCase):
    def test_bool_case(self):
        self.assertIsNone(persisted_started_seconds(True))
        self.assertIsNone(persisted_started_seconds(False))
    def test_int_case(self):
        self.assertEqual(1, persisted_started_seconds(1))
        self.assertEqual(2, persisted_started_seconds(2))
    def test_none_case(self):
        self.assertIsNone(persisted_started_seconds(None))
    def test_float_case(self):
        self.assertEqual(1, persisted_started_seconds(1.0))
```