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


# A minimal transport module: the entry points are derived from which public
# functions call a primitive, so a fixture needs the module, not a name list.
_TRANSPORT_MODULE = '''
def _send_to_user(uid, tag, **kw): ...
async def _send_to_user_async(uid, tag, **kw): ...
def _send_messages(messages): ...

def send_notification(uid, title, body):
    _send_to_user(uid, "t")

async def send_notification_async(uid, title, body):
    await _send_to_user_async(uid, "t")

def send_client_displayed_notification(uid, title, body):
    _send_to_user(uid, "t")

async def send_client_displayed_notification_async(uid, title, body):
    await _send_to_user_async(uid, "t")

def send_credit_limit_notification(uid):
    send_notification(uid, "Credits", "low")
'''


def _write_transport(root: Path, source: str = _TRANSPORT_MODULE) -> None:
    _write(root, 'backend/utils/notifications.py', source)


class NotificationDispatchBoundaryTests(unittest.TestCase):
    def test_scanner_resolves_direct_alias_and_module_qualified_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_transport(root)
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

    def test_scanner_counts_every_transport_entry_point_not_only_send_notification(self) -> None:
        # `send_client_displayed_notification{,_async}` reach `_send_to_user` the same
        # way `send_notification` does (#13173). Leaving them off the list would let a
        # producer keep owning transport while the ratchet read it as a reduction.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_transport(root)
            _write(
                root,
                'backend/producer.py',
                '''
from utils.notifications import send_client_displayed_notification, send_client_displayed_notification_async

send_client_displayed_notification("u", "title", "body")


async def stream(uid):
    await send_client_displayed_notification_async(uid, "title", "body")
''',
            )

            self.assertEqual(guard.scan_direct_transport_calls(root), {'backend/producer.py': 2})

    def test_a_new_transport_entry_point_is_guarded_without_editing_the_checker(self) -> None:
        # A hand-maintained name list covered 7 of the module's direct senders, and the
        # first entry point added after it went unguarded until a merge exposed it.
        # Deriving from the module means a new sender is counted the day it lands.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_transport(
                root,
                _TRANSPORT_MODULE
                + '''
def send_brand_new_push(uid):
    _send_to_user(uid, "t")
''',
            )
            _write(
                root,
                'backend/producer.py',
                'from utils.notifications import send_brand_new_push\nsend_brand_new_push("u")\n',
            )

            self.assertIn('send_brand_new_push', guard.transport_entry_points(root))
            self.assertEqual(guard.scan_direct_transport_calls(root), {'backend/producer.py': 1})

    def test_only_functions_that_call_a_primitive_are_entry_points(self) -> None:
        # The stated limit: a wrapper delivering through another public function is not
        # itself an entry point, so a producer calling only the wrapper is not counted.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_transport(root)
            _write(
                root,
                'backend/producer.py',
                'from utils.notifications import send_credit_limit_notification\nsend_credit_limit_notification("u")\n',
            )

            entry_points = guard.transport_entry_points(root)
            self.assertNotIn('send_credit_limit_notification', entry_points)
            self.assertNotIn('_build_message', entry_points)
            self.assertEqual(guard.scan_direct_transport_calls(root), {})

    def test_a_missing_transport_module_fails_closed(self) -> None:
        # An unreadable module must not derive an empty guard list and pass as zero calls.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root, 'backend/producer.py', 'from utils.notifications import send_notification\n')

            with self.assertRaises(RuntimeError):
                guard.scan_direct_transport_calls(root)

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
