"""A managed leg's transport cleanup must not read as the client leaving."""

from types import SimpleNamespace

from utils.stt.resilient_stream import socket_is_finishing


def _managed(owner_closing: bool, raw_finishing: bool):
    raw = SimpleNamespace(_finishing=raw_finishing)
    return SimpleNamespace(leg_outcome=SimpleNamespace(owner_closing=owner_closing), raw=raw)


def test_raw_cleanup_after_failed_send_does_not_block_recovery():
    # LiveLegSocket.send calls raw.finish() after a rejected send (Soniox queue
    # overflow on replay), which sets the raw _finishing latch. The client is
    # still connected, so recovery must proceed.
    assert socket_is_finishing(_managed(owner_closing=False, raw_finishing=True)) is False


def test_owner_teardown_still_blocks_recovery():
    assert socket_is_finishing(_managed(owner_closing=True, raw_finishing=False)) is True
    assert socket_is_finishing(_managed(owner_closing=True, raw_finishing=True)) is True


def test_unmanaged_socket_keeps_its_finishing_latch():
    assert socket_is_finishing(SimpleNamespace(_finishing=True)) is True
    assert socket_is_finishing(SimpleNamespace(_finishing=False)) is False
    wrapper = SimpleNamespace(_conn=SimpleNamespace(_finishing=True))
    assert socket_is_finishing(wrapper) is True


def test_none_is_not_finishing():
    assert socket_is_finishing(None) is False
