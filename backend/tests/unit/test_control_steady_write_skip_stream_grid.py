"""Control steady-write skip: admission-stream grid over the shared helpers."""

from tests.unit.control_steady_skip_fleet_helpers import *  # noqa: F401,F403
import pytest  # noqa: F401
from config.batch_pipeline import scheduler_control_key
from tests.unit.control_steady_skip_fleet_helpers import _force_legacy, control_doc, queue_doc  # noqa: F401


def test_stream_1_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0',))
    assert_count(store, 1)


def test_stream_1_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0',))
    killed = legacy_stream(('s0',))
    assert_pair(store, killed, ('s0',))
    assert_count(store, 1)
    assert_count(killed, 1)


def test_stream_1_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0',))
    assert queue_doc(store)["items"] == list(('s0',))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s0"


def test_stream_1_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0',))
    assert len(store.ledgers) == 1
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_1_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0',))
    killed = legacy_stream(('s0',))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_2_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1'))
    assert_count(store, 1)


def test_stream_2_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1'))
    killed = legacy_stream(('s0', 's1'))
    assert_pair(store, killed, ('s0', 's1'))
    assert_count(store, 1)
    assert_count(killed, 2)


def test_stream_2_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1'))
    assert queue_doc(store)["items"] == list(('s0', 's1'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s1"


def test_stream_2_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1'))
    assert len(store.ledgers) == 2
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_2_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1'))
    killed = legacy_stream(('s0', 's1'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_3_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2'))
    assert_count(store, 1)


def test_stream_3_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2'))
    killed = legacy_stream(('s0', 's1', 's2'))
    assert_pair(store, killed, ('s0', 's1', 's2'))
    assert_count(store, 1)
    assert_count(killed, 3)


def test_stream_3_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s2"


def test_stream_3_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2'))
    assert len(store.ledgers) == 3
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_3_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2'))
    killed = legacy_stream(('s0', 's1', 's2'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_4_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3'))
    assert_count(store, 1)


def test_stream_4_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3'))
    killed = legacy_stream(('s0', 's1', 's2', 's3'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3'))
    assert_count(store, 1)
    assert_count(killed, 4)


def test_stream_4_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s3"


def test_stream_4_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3'))
    assert len(store.ledgers) == 4
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_4_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3'))
    killed = legacy_stream(('s0', 's1', 's2', 's3'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_5_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4'))
    assert_count(store, 1)


def test_stream_5_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4'))
    assert_count(store, 1)
    assert_count(killed, 5)


def test_stream_5_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s4"


def test_stream_5_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4'))
    assert len(store.ledgers) == 5
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_5_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_6_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5'))
    assert_count(store, 1)


def test_stream_6_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5'))
    assert_count(store, 1)
    assert_count(killed, 6)


def test_stream_6_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4', 's5'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s5"


def test_stream_6_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5'))
    assert len(store.ledgers) == 6
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_6_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_7_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    assert_count(store, 1)


def test_stream_7_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    assert_count(store, 1)
    assert_count(killed, 7)


def test_stream_7_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s6"


def test_stream_7_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    assert len(store.ledgers) == 7
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_7_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_8_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    assert_count(store, 1)


def test_stream_8_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    assert_count(store, 1)
    assert_count(killed, 8)


def test_stream_8_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s7"


def test_stream_8_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    assert len(store.ledgers) == 8
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_8_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_9_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    assert_count(store, 1)


def test_stream_9_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    assert_count(store, 1)
    assert_count(killed, 9)


def test_stream_9_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s8"


def test_stream_9_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    assert len(store.ledgers) == 9
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_9_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_10_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    assert_count(store, 1)


def test_stream_10_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    assert_count(store, 1)
    assert_count(killed, 10)


def test_stream_10_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s9"


def test_stream_10_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    assert len(store.ledgers) == 10
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_10_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_11_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    assert_count(store, 1)


def test_stream_11_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    assert_count(store, 1)
    assert_count(killed, 11)


def test_stream_11_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s10"


def test_stream_11_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    assert len(store.ledgers) == 11
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_11_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_12_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    assert_count(store, 1)


def test_stream_12_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    assert_count(store, 1)
    assert_count(killed, 12)


def test_stream_12_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    assert queue_doc(store)["items"] == list(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s11"


def test_stream_12_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    assert len(store.ledgers) == 12
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_12_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_13_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    assert_count(store, 1)


def test_stream_13_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    assert_count(store, 1)
    assert_count(killed, 13)


def test_stream_13_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    assert queue_doc(store)["items"] == list(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12')
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s12"


def test_stream_13_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    assert len(store.ledgers) == 13
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_13_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_14_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    assert_count(store, 1)


def test_stream_14_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    assert_pair(store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    assert_count(store, 1)
    assert_count(killed, 14)


def test_stream_14_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    assert queue_doc(store)["items"] == list(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13')
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s13"


def test_stream_14_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    assert len(store.ledgers) == 14
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_14_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    killed = legacy_stream(('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13'))
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_15_writes_control_once():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14'))
    assert_count(store, 1)


def test_stream_15_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14'))
    killed = legacy_stream(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14')
    )
    assert_pair(
        store, killed, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14')
    )
    assert_count(store, 1)
    assert_count(killed, 15)


def test_stream_15_queue_order_survives():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14'))
    assert queue_doc(store)["items"] == list(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14')
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s14"


def test_stream_15_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14'))
    assert len(store.ledgers) == 15
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_15_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14'))
    killed = legacy_stream(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14')
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_16_writes_control_once():
    store = LedgerStore()
    run_stream(
        store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    assert_count(store, 1)


def test_stream_16_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    killed = legacy_stream(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    assert_pair(
        store,
        killed,
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15'),
    )
    assert_count(store, 1)
    assert_count(killed, 16)


def test_stream_16_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    assert queue_doc(store)["items"] == list(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s15"


def test_stream_16_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    assert len(store.ledgers) == 16
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_16_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store, ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    killed = legacy_stream(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15')
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_17_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16'),
    )
    assert_count(store, 1)


def test_stream_17_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16'),
    )
    killed = legacy_stream(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16')
    )
    assert_pair(
        store,
        killed,
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16'),
    )
    assert_count(store, 1)
    assert_count(killed, 17)


def test_stream_17_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16'),
    )
    assert queue_doc(store)["items"] == list(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16')
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s16"


def test_stream_17_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16'),
    )
    assert len(store.ledgers) == 17
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_17_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16'),
    )
    killed = legacy_stream(
        ('s0', 's1', 's2', 's3', 's4', 's5', 's6', 's7', 's8', 's9', 's10', 's11', 's12', 's13', 's14', 's15', 's16')
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_18_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        ),
    )
    assert_count(store, 1)


def test_stream_18_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 18)


def test_stream_18_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s17"


def test_stream_18_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        ),
    )
    assert len(store.ledgers) == 18
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_18_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_19_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        ),
    )
    assert_count(store, 1)


def test_stream_19_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 19)


def test_stream_19_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s18"


def test_stream_19_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        ),
    )
    assert len(store.ledgers) == 19
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_19_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_20_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        ),
    )
    assert_count(store, 1)


def test_stream_20_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 20)


def test_stream_20_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s19"


def test_stream_20_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        ),
    )
    assert len(store.ledgers) == 20
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_20_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_21_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        ),
    )
    assert_count(store, 1)


def test_stream_21_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 21)


def test_stream_21_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s20"


def test_stream_21_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        ),
    )
    assert len(store.ledgers) == 21
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_21_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_22_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        ),
    )
    assert_count(store, 1)


def test_stream_22_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 22)


def test_stream_22_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s21"


def test_stream_22_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        ),
    )
    assert len(store.ledgers) == 22
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_22_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_23_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        ),
    )
    assert_count(store, 1)


def test_stream_23_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 23)


def test_stream_23_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s22"


def test_stream_23_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        ),
    )
    assert len(store.ledgers) == 23
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_23_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_24_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        ),
    )
    assert_count(store, 1)


def test_stream_24_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 24)


def test_stream_24_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s23"


def test_stream_24_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        ),
    )
    assert len(store.ledgers) == 24
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_24_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_25_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        ),
    )
    assert_count(store, 1)


def test_stream_25_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 25)


def test_stream_25_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s24"


def test_stream_25_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        ),
    )
    assert len(store.ledgers) == 25
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_25_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_26_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        ),
    )
    assert_count(store, 1)


def test_stream_26_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 26)


def test_stream_26_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s25"


def test_stream_26_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        ),
    )
    assert len(store.ledgers) == 26
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_26_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_27_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        ),
    )
    assert_count(store, 1)


def test_stream_27_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 27)


def test_stream_27_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s26"


def test_stream_27_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        ),
    )
    assert len(store.ledgers) == 27
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_27_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_28_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        ),
    )
    assert_count(store, 1)


def test_stream_28_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 28)


def test_stream_28_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s27"


def test_stream_28_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        ),
    )
    assert len(store.ledgers) == 28
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_28_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_29_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        ),
    )
    assert_count(store, 1)


def test_stream_29_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 29)


def test_stream_29_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s28"


def test_stream_29_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        ),
    )
    assert len(store.ledgers) == 29
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_29_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_stream_30_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        ),
    )
    assert_count(store, 1)


def test_stream_30_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 30)


def test_stream_30_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        ),
    )
    assert queue_doc(store)["items"] == list(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        )
    )
    assert queue_doc(store)["head"] == "s0"
    assert queue_doc(store)["tail"] == "s29"


def test_stream_30_ledgers_stay_in_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        ),
    )
    assert len(store.ledgers) == 30
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(("control", CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ("control", CONTROL) in store.ledgers[0]


def test_stream_30_control_content_freezes_after_the_first_write():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
        )
    )
    assert control_doc(store) == control_doc(killed)
    doc = control_doc(store)
    assert doc["p2_active"] is True
    assert doc["p2_service"] == 0.0


def test_owner_mix_heavy_heavy_heavy_writes_one_control_per_owner():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(zip(('a0', 'a1', 'a2'), ('heavy', 'heavy', 'heavy'))):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    assert_count(store, 1)
    for owner in set(('heavy', 'heavy', 'heavy')):
        assert_count(store, 1, scheduler_control_key(owner_key(owner)))


def test_owner_mix_heavy_heavy_heavy_documents_match_the_kill_switch():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(zip(('a0', 'a1', 'a2'), ('heavy', 'heavy', 'heavy'))):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    with _force_legacy():
        killed = LedgerStore()
        scheduler_k = Scheduler(killed)
        for index, (segment, owner) in enumerate(zip(('a0', 'a1', 'a2'), ('heavy', 'heavy', 'heavy'))):
            assert scheduler_k.enqueue(item(segment, owner=owner), index * 70.0)
    for owner in set(('heavy', 'heavy', 'heavy')):
        assert control_doc(store, owner_key(owner)) == control_doc(killed, owner_key(owner))
        assert queue_doc(store, owner_key(owner)) == queue_doc(killed, owner_key(owner))


def test_owner_mix_heavy_light_heavy_light_writes_one_control_per_owner():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(zip(('a0', 'b0', 'a1', 'b1'), ('heavy', 'light', 'heavy', 'light'))):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    assert_count(store, 1)
    for owner in set(('heavy', 'light', 'heavy', 'light')):
        assert_count(store, 1, scheduler_control_key(owner_key(owner)))


def test_owner_mix_heavy_light_heavy_light_documents_match_the_kill_switch():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(zip(('a0', 'b0', 'a1', 'b1'), ('heavy', 'light', 'heavy', 'light'))):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    with _force_legacy():
        killed = LedgerStore()
        scheduler_k = Scheduler(killed)
        for index, (segment, owner) in enumerate(zip(('a0', 'b0', 'a1', 'b1'), ('heavy', 'light', 'heavy', 'light'))):
            assert scheduler_k.enqueue(item(segment, owner=owner), index * 70.0)
    for owner in set(('heavy', 'light', 'heavy', 'light')):
        assert control_doc(store, owner_key(owner)) == control_doc(killed, owner_key(owner))
        assert queue_doc(store, owner_key(owner)) == queue_doc(killed, owner_key(owner))


def test_owner_mix_heavy_light_three_heavy_writes_one_control_per_owner():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(zip(('a0', 'b0', 'c0', 'a1'), ('heavy', 'light', 'three', 'heavy'))):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    assert_count(store, 1)
    for owner in set(('heavy', 'light', 'three', 'heavy')):
        assert_count(store, 1, scheduler_control_key(owner_key(owner)))


def test_owner_mix_heavy_light_three_heavy_documents_match_the_kill_switch():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(zip(('a0', 'b0', 'c0', 'a1'), ('heavy', 'light', 'three', 'heavy'))):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    with _force_legacy():
        killed = LedgerStore()
        scheduler_k = Scheduler(killed)
        for index, (segment, owner) in enumerate(zip(('a0', 'b0', 'c0', 'a1'), ('heavy', 'light', 'three', 'heavy'))):
            assert scheduler_k.enqueue(item(segment, owner=owner), index * 70.0)
    for owner in set(('heavy', 'light', 'three', 'heavy')):
        assert control_doc(store, owner_key(owner)) == control_doc(killed, owner_key(owner))
        assert queue_doc(store, owner_key(owner)) == queue_doc(killed, owner_key(owner))


def test_owner_mix_light_three_light_three_light_writes_one_control_per_owner():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(
        zip(('b0', 'c0', 'b1', 'c1', 'b2'), ('light', 'three', 'light', 'three', 'light'))
    ):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    assert_count(store, 0)
    for owner in set(('light', 'three', 'light', 'three', 'light')):
        assert_count(store, 1, scheduler_control_key(owner_key(owner)))


def test_owner_mix_light_three_light_three_light_documents_match_the_kill_switch():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, owner) in enumerate(
        zip(('b0', 'c0', 'b1', 'c1', 'b2'), ('light', 'three', 'light', 'three', 'light'))
    ):
        assert scheduler.enqueue(item(segment, owner=owner), index * 70.0)
    with _force_legacy():
        killed = LedgerStore()
        scheduler_k = Scheduler(killed)
        for index, (segment, owner) in enumerate(
            zip(('b0', 'c0', 'b1', 'c1', 'b2'), ('light', 'three', 'light', 'three', 'light'))
        ):
            assert scheduler_k.enqueue(item(segment, owner=owner), index * 70.0)
    for owner in set(('light', 'three', 'light', 'three', 'light')):
        assert control_doc(store, owner_key(owner)) == control_doc(killed, owner_key(owner))
        assert queue_doc(store, owner_key(owner)) == queue_doc(killed, owner_key(owner))


def test_priority_mix_ddf_writes_on_first_touch_per_priority():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, priority) in enumerate(zip(('d0', 'd1', 'f0'), (2, 2, 0))):
        assert scheduler.enqueue(item(segment, owner=OWNER, priority=Priority(priority)), index * 70.0)
    assert_count(store, 2)
    doc = control_doc(store)
    assert queue_doc(store)["tail"] == "d1"


def test_priority_mix_dff_writes_on_first_touch_per_priority():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, priority) in enumerate(zip(('d0', 'f0', 'f1'), (2, 0, 0))):
        assert scheduler.enqueue(item(segment, owner=OWNER, priority=Priority(priority)), index * 70.0)
    assert_count(store, 2)
    doc = control_doc(store)
    assert queue_doc(store)["tail"] == "d0"


def test_priority_mix_ffddf_writes_on_first_touch_per_priority():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, priority) in enumerate(zip(('f0', 'f1', 'd0', 'd1', 'f2'), (0, 0, 2, 2, 0))):
        assert scheduler.enqueue(item(segment, owner=OWNER, priority=Priority(priority)), index * 70.0)
    assert_count(store, 2)
    doc = control_doc(store)
    assert queue_doc(store)["tail"] == "d1"


def test_priority_mix_dfdfdf_writes_on_first_touch_per_priority():
    store = LedgerStore()
    scheduler = Scheduler(store)
    for index, (segment, priority) in enumerate(zip(('d0', 'f0', 'd1', 'f1', 'd2', 'f2'), (2, 0, 2, 0, 2, 0))):
        assert scheduler.enqueue(item(segment, owner=OWNER, priority=Priority(priority)), index * 70.0)
    assert_count(store, 2)
    doc = control_doc(store)
    assert queue_doc(store)["tail"] == "d2"


def test_stream_31_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
        ),
    )
    assert_count(store, 1)


def test_stream_31_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 31)


def test_stream_31_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's30'


def test_stream_31_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
        ),
    )
    assert len(store.ledgers) == 31
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_32_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
        ),
    )
    assert_count(store, 1)


def test_stream_32_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 32)


def test_stream_32_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's31'


def test_stream_32_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
        ),
    )
    assert len(store.ledgers) == 32
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_33_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
        ),
    )
    assert_count(store, 1)


def test_stream_33_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 33)


def test_stream_33_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's32'


def test_stream_33_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
        ),
    )
    assert len(store.ledgers) == 33
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_34_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
        ),
    )
    assert_count(store, 1)


def test_stream_34_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 34)


def test_stream_34_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
        's33',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's33'


def test_stream_34_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
        ),
    )
    assert len(store.ledgers) == 34
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_35_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
        ),
    )
    assert_count(store, 1)


def test_stream_35_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 35)


def test_stream_35_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
        's33',
        's34',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's34'


def test_stream_35_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
        ),
    )
    assert len(store.ledgers) == 35
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_36_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
        ),
    )
    assert_count(store, 1)


def test_stream_36_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 36)


def test_stream_36_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
        's33',
        's34',
        's35',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's35'


def test_stream_36_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
        ),
    )
    assert len(store.ledgers) == 36
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_37_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
        ),
    )
    assert_count(store, 1)


def test_stream_37_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 37)


def test_stream_37_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
        's33',
        's34',
        's35',
        's36',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's36'


def test_stream_37_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
        ),
    )
    assert len(store.ledgers) == 37
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_38_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
        ),
    )
    assert_count(store, 1)


def test_stream_38_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 38)


def test_stream_38_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
        's33',
        's34',
        's35',
        's36',
        's37',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's37'


def test_stream_38_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
        ),
    )
    assert len(store.ledgers) == 38
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_39_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
        ),
    )
    assert_count(store, 1)


def test_stream_39_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 39)


def test_stream_39_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
        's33',
        's34',
        's35',
        's36',
        's37',
        's38',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's38'


def test_stream_39_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
        ),
    )
    assert len(store.ledgers) == 39
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]


def test_stream_40_writes_control_once():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
            's39',
        ),
    )
    assert_count(store, 1)


def test_stream_40_matches_the_kill_switch_documents():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
            's39',
        ),
    )
    killed = legacy_stream(
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
            's39',
        )
    )
    assert_pair(
        store,
        killed,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
            's39',
        ),
    )
    assert_count(store, 1)
    assert_count(killed, 40)


def test_stream_40_queue_order_survives():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
            's39',
        ),
    )
    row = store.rows.get(('queues', QUEUE)) or {}
    assert row.get('items') == [
        's0',
        's1',
        's2',
        's3',
        's4',
        's5',
        's6',
        's7',
        's8',
        's9',
        's10',
        's11',
        's12',
        's13',
        's14',
        's15',
        's16',
        's17',
        's18',
        's19',
        's20',
        's21',
        's22',
        's23',
        's24',
        's25',
        's26',
        's27',
        's28',
        's29',
        's30',
        's31',
        's32',
        's33',
        's34',
        's35',
        's36',
        's37',
        's38',
        's39',
    ]
    assert row.get('head') == 's0'
    assert row.get('tail') == 's39'


def test_stream_40_ledgers_stay_within_the_write_bound():
    store = LedgerStore()
    run_stream(
        store,
        (
            's0',
            's1',
            's2',
            's3',
            's4',
            's5',
            's6',
            's7',
            's8',
            's9',
            's10',
            's11',
            's12',
            's13',
            's14',
            's15',
            's16',
            's17',
            's18',
            's19',
            's20',
            's21',
            's22',
            's23',
            's24',
            's25',
            's26',
            's27',
            's28',
            's29',
            's30',
            's31',
            's32',
            's33',
            's34',
            's35',
            's36',
            's37',
            's38',
            's39',
        ),
    )
    assert len(store.ledgers) == 40
    assert all(len(puts) <= 4 for puts in store.ledgers)
    assert all(('control', CONTROL) not in puts[1:] for puts in store.ledgers)
    assert ('control', CONTROL) in store.ledgers[0]
