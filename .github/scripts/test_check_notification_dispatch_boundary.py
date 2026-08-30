import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('check_notification_dispatch_boundary.py')
SPEC = importlib.util.spec_from_file_location('notification_dispatch_boundary', SCRIPT)
assert SPEC and SPEC.loader
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def _write(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')


class NotificationDispatchBoundaryTests(unittest.TestCase):
    def test_scanner_resolves_direct_alias_and_module_qualified_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root,
                'backend/producer.py',
                '''
from utils.notifications import send_notification as push
import utils.notifications as transport

push("u", "title", "body")
transport.send_notification_async("u", "title", "body")
delivery = push
''',
            )

            self.assertEqual(guard.scan_direct_transport_calls(root), {'backend/producer.py': 3})

    def test_scanner_excludes_transport_owner_dispatcher_and_tests(self) -> None:
        source = 'from utils.notifications import send_notification\nsend_notification("u", "t", "b")\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root, 'backend/utils/notifications.py', source)
            _write(root, 'backend/utils/notification_dispatch.py', source)
            _write(root, 'backend/tests/unit/test_notification.py', source)

            self.assertEqual(guard.scan_direct_transport_calls(root), {})

    def test_initial_baseline_must_exactly_describe_observed_calls(self) -> None:
        self.assertEqual(guard.validate_baseline({'backend/a.py': 2}, {'backend/a.py': 2}, None), [])
        self.assertTrue(guard.validate_baseline({'backend/a.py': 2}, {'backend/a.py': 1}, None))

    def test_existing_baseline_cannot_grow_even_if_updated_to_match(self) -> None:
        errors = guard.validate_baseline(
            {'backend/a.py': 3, 'backend/new.py': 1},
            {'backend/a.py': 3, 'backend/new.py': 1},
            {'backend/a.py': 2},
        )

        self.assertIn('backend/a.py: direct transport calls grew from 2 to 3', errors)
        self.assertIn('backend/new.py: direct transport calls grew from 0 to 1', errors)

    def test_reduction_requires_and_accepts_a_lower_exact_baseline(self) -> None:
        self.assertTrue(guard.validate_baseline({'backend/a.py': 1}, {'backend/a.py': 2}, {'backend/a.py': 2}))
        self.assertEqual(guard.validate_baseline({'backend/a.py': 1}, {'backend/a.py': 1}, {'backend/a.py': 2}), [])


if __name__ == '__main__':
    unittest.main()
