"""Contention-classification grid for the publication re-strike lane.

Only the bounded contention budget may replay a lost publication transition: the exhausted
budget exception, its job-store subclass, and any cause chain that classifies as atomic
transaction contention. Everything else aborts the lane to the legacy catch site. Every
row here pins one exception shape and cross-checks it against the shared boundary helper
``database.firestore_transaction_retry.is_transaction_contention``, so the lane and the
budget can never drift apart.

Failure-Class: FC-publication-contention-discards-completed-gpu-results
"""

import asyncio

from google.api_core.exceptions import Aborted, InvalidArgument

from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    is_transaction_contention,
)
from utils.batch_pipeline.pump import publication_loss_is_contention


class _LocalExhausted(FirestoreContentionExhausted):
    pass


class _DeepExhausted(_LocalExhausted):
    pass


def chain(depth, leaf):
    inner = leaf
    for _ in range(depth):
        wrapper = RuntimeError('wrapper')
        wrapper.__cause__ = inner
        inner = wrapper
    return inner


def test_classification_exhausted_plain():
    error = FirestoreContentionExhausted("spent")
    assert publication_loss_is_contention(error) is True


def test_classification_exhausted_plain_lane_contract_matches_its_two_arms():
    error = FirestoreContentionExhausted("spent")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_exhausted_attempts_reason():
    error = FirestoreContentionExhausted("spent", reason="attempts_exhausted")
    assert publication_loss_is_contention(error) is True


def test_classification_exhausted_attempts_reason_lane_contract_matches_its_two_arms():
    error = FirestoreContentionExhausted("spent", reason="attempts_exhausted")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_exhausted_deadline_reason():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    assert publication_loss_is_contention(error) is True


def test_classification_exhausted_deadline_reason_lane_contract_matches_its_two_arms():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_local_subclass():
    error = _LocalExhausted("spent")
    assert publication_loss_is_contention(error) is True


def test_classification_local_subclass_lane_contract_matches_its_two_arms():
    error = _LocalExhausted("spent")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_deep_subclass():
    error = _DeepExhausted("spent")
    assert publication_loss_is_contention(error) is True


def test_classification_deep_subclass_lane_contract_matches_its_two_arms():
    error = _DeepExhausted("spent")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_wrapped_budget_exception():
    error = chain(1, FirestoreContentionExhausted("spent"))
    assert publication_loss_is_contention(error) is False


def test_classification_wrapped_budget_exception_lane_contract_matches_its_two_arms():
    error = chain(1, FirestoreContentionExhausted("spent"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_deeply_wrapped_budget_exception():
    error = chain(3, FirestoreContentionExhausted("spent"))
    assert publication_loss_is_contention(error) is False


def test_classification_deeply_wrapped_budget_exception_lane_contract_matches_its_two_arms():
    error = chain(3, FirestoreContentionExhausted("spent"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_direct_aborted():
    error = Aborted("commit race")
    assert publication_loss_is_contention(error) is True


def test_classification_direct_aborted_lane_contract_matches_its_two_arms():
    error = Aborted("commit race")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_aborted_under_runtimeerror():
    error = chain(1, Aborted("commit race"))
    assert publication_loss_is_contention(error) is True


def test_classification_aborted_under_runtimeerror_lane_contract_matches_its_two_arms():
    error = chain(1, Aborted("commit race"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_aborted_three_deep():
    error = chain(3, Aborted("commit race"))
    assert publication_loss_is_contention(error) is True


def test_classification_aborted_three_deep_lane_contract_matches_its_two_arms():
    error = chain(3, Aborted("commit race"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_aborted_six_deep():
    error = chain(6, Aborted("commit race"))
    assert publication_loss_is_contention(error) is True


def test_classification_aborted_six_deep_lane_contract_matches_its_two_arms():
    error = chain(6, Aborted("commit race"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_aborted_upper_message():
    error = Aborted("ABORTED: hot document")
    assert publication_loss_is_contention(error) is True


def test_classification_aborted_upper_message_lane_contract_matches_its_two_arms():
    error = Aborted("ABORTED: hot document")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_expired_invalid_argument():
    error = InvalidArgument("Transaction has expired")
    assert publication_loss_is_contention(error) is True


def test_classification_expired_invalid_argument_lane_contract_matches_its_two_arms():
    error = InvalidArgument("Transaction has expired")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_expired_lower_message():
    error = InvalidArgument("transaction has expired. span")
    assert publication_loss_is_contention(error) is True


def test_classification_expired_lower_message_lane_contract_matches_its_two_arms():
    error = InvalidArgument("transaction has expired. span")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_expired_under_oserror():
    error = chain(2, InvalidArgument("Transaction has expired"))
    assert publication_loss_is_contention(error) is True


def test_classification_expired_under_oserror_lane_contract_matches_its_two_arms():
    error = chain(2, InvalidArgument("Transaction has expired"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_expiring_aborted_marker():
    error = Aborted("the transaction has expired and was retired")
    assert publication_loss_is_contention(error) is True


def test_classification_expiring_aborted_marker_lane_contract_matches_its_two_arms():
    error = Aborted("the transaction has expired and was retired")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is True


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_valueerror():
    error = ValueError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_valueerror_lane_contract_matches_its_two_arms():
    error = ValueError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_keyerror():
    error = KeyError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_keyerror_lane_contract_matches_its_two_arms():
    error = KeyError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_runtimeerror():
    error = RuntimeError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_runtimeerror_lane_contract_matches_its_two_arms():
    error = RuntimeError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_timeouterror():
    error = TimeoutError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_timeouterror_lane_contract_matches_its_two_arms():
    error = TimeoutError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_stopiteration():
    error = StopIteration("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_stopiteration_lane_contract_matches_its_two_arms():
    error = StopIteration("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_zerodivisionerror():
    error = ZeroDivisionError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_zerodivisionerror_lane_contract_matches_its_two_arms():
    error = ZeroDivisionError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_oserror():
    error = OSError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_oserror_lane_contract_matches_its_two_arms():
    error = OSError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_permissionerror():
    error = PermissionError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_permissionerror_lane_contract_matches_its_two_arms():
    error = PermissionError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_unicodedecodeerror():
    error = UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_unicodedecodeerror_lane_contract_matches_its_two_arms():
    error = UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_typeerror():
    error = TypeError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_typeerror_lane_contract_matches_its_two_arms():
    error = TypeError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_indexerror():
    error = IndexError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_indexerror_lane_contract_matches_its_two_arms():
    error = IndexError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_plain_attributeerror():
    error = AttributeError("no")
    assert publication_loss_is_contention(error) is False


def test_classification_plain_attributeerror_lane_contract_matches_its_two_arms():
    error = AttributeError("no")
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_asyncio_timeout():
    error = asyncio.TimeoutError()
    assert publication_loss_is_contention(error) is False


def test_classification_asyncio_timeout_lane_contract_matches_its_two_arms():
    error = asyncio.TimeoutError()
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_noncontention_chain_one():
    error = chain(1, ValueError("no"))
    assert publication_loss_is_contention(error) is False


def test_classification_noncontention_chain_one_lane_contract_matches_its_two_arms():
    error = chain(1, ValueError("no"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_noncontention_chain_six():
    error = chain(6, ValueError("no"))
    assert publication_loss_is_contention(error) is False


def test_classification_noncontention_chain_six_lane_contract_matches_its_two_arms():
    error = chain(6, ValueError("no"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_noncontention_under_aborted_sibling():
    error = chain(2, ValueError("no"))
    assert publication_loss_is_contention(error) is False


def test_classification_noncontention_under_aborted_sibling_lane_contract_matches_its_two_arms():
    error = chain(2, ValueError("no"))
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_classification_none_input():
    error = None
    assert publication_loss_is_contention(error) is False


def test_classification_none_input_lane_contract_matches_its_two_arms():
    error = None
    budget_arm = isinstance(error, FirestoreContentionExhausted)
    chain_arm = is_transaction_contention(error)
    assert publication_loss_is_contention(error) == (budget_arm or chain_arm)
    assert publication_loss_is_contention(leaf(error)) is False


def leaf(error):
    while getattr(error, '__cause__', None) is not None:
        error = error.__cause__
    return error


def test_subclass_rows_are_instances_of_the_budget_exception():
    assert issubclass(_LocalExhausted, FirestoreContentionExhausted)
    assert issubclass(_DeepExhausted, FirestoreContentionExhausted)


def test_self_referential_cause_chain_is_safe():
    error = RuntimeError('loop')
    error.__cause__ = error
    assert publication_loss_is_contention(error) is False


def test_two_node_cause_cycle_is_safe():
    a = RuntimeError('a')
    b = RuntimeError('b')
    a.__cause__ = b
    b.__cause__ = a
    assert publication_loss_is_contention(a) is False


def test_contention_instance_keeps_its_closed_reason_token():
    assert FirestoreContentionExhausted('spent').reason == 'attempts_exhausted'


def test_deadline_instance_keeps_its_closed_reason_token():
    error = FirestoreContentionExhausted('spent', reason='deadline_exhausted')
    assert error.reason == 'deadline_exhausted'


def test_chained_budget_exception_preserves_its_reason():
    error = chain(3, FirestoreContentionExhausted('spent'))
    assert getattr(error.__cause__.__cause__.__cause__, 'reason', None) == 'attempts_exhausted'


from database.jobstore.postgres_store import JobStoreContentionExhausted


def test_classification_postgres_budget_exception():
    assert publication_loss_is_contention(JobStoreContentionExhausted("pg spent")) is True


def test_classification_postgres_budget_exception_lane_contract():
    error = JobStoreContentionExhausted("pg spent")
    assert publication_loss_is_contention(error) == (
        isinstance(error, FirestoreContentionExhausted) or is_transaction_contention(error)
    )


def test_classification_postgres_wrapped_is_not_restrikeable():
    assert publication_loss_is_contention(chain(1, JobStoreContentionExhausted("pg spent"))) is False


def test_classification_postgres_leaf_classifies():
    assert publication_loss_is_contention(chain(2, JobStoreContentionExhausted("pg spent")).__cause__.__cause__) is True


def test_classification_deep_aborted_chain_twelve():
    assert publication_loss_is_contention(chain(12, Aborted("commit race"))) is True


def test_classification_budget_exception_under_deadline_marker_chain():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    error.__cause__ = InvalidArgument("Transaction has expired")
    assert publication_loss_is_contention(error) is True


from database.jobstore.postgres_store import JobStoreContentionExhausted


def test_classification_postgres_budget_exception():
    assert publication_loss_is_contention(JobStoreContentionExhausted("pg spent")) is True


def test_classification_postgres_budget_exception_lane_contract():
    error = JobStoreContentionExhausted("pg spent")
    assert publication_loss_is_contention(error) == (
        isinstance(error, FirestoreContentionExhausted) or is_transaction_contention(error)
    )


def test_classification_postgres_wrapped_is_not_restrikeable():
    assert publication_loss_is_contention(chain(1, JobStoreContentionExhausted("pg spent"))) is False


def test_classification_postgres_leaf_classifies():
    assert publication_loss_is_contention(chain(2, JobStoreContentionExhausted("pg spent")).__cause__.__cause__) is True


def test_classification_deep_aborted_chain_twelve():
    assert publication_loss_is_contention(chain(12, Aborted("commit race"))) is True


def test_classification_budget_exception_under_deadline_marker_chain():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    error.__cause__ = InvalidArgument("Transaction has expired")
    assert publication_loss_is_contention(error) is True


from database.jobstore.postgres_store import JobStoreContentionExhausted


def test_classification_postgres_budget_exception():
    assert publication_loss_is_contention(JobStoreContentionExhausted("pg spent")) is True


def test_classification_postgres_budget_exception_lane_contract():
    error = JobStoreContentionExhausted("pg spent")
    assert publication_loss_is_contention(error) == (
        isinstance(error, FirestoreContentionExhausted) or is_transaction_contention(error)
    )


def test_classification_postgres_wrapped_is_not_restrikeable():
    assert publication_loss_is_contention(chain(1, JobStoreContentionExhausted("pg spent"))) is False


def test_classification_postgres_leaf_classifies():
    assert publication_loss_is_contention(chain(2, JobStoreContentionExhausted("pg spent")).__cause__.__cause__) is True


def test_classification_deep_aborted_chain_twelve():
    assert publication_loss_is_contention(chain(12, Aborted("commit race"))) is True


def test_classification_budget_exception_under_deadline_marker_chain():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    error.__cause__ = InvalidArgument("Transaction has expired")
    assert publication_loss_is_contention(error) is True


from database.jobstore.postgres_store import JobStoreContentionExhausted


def test_classification_postgres_budget_exception():
    assert publication_loss_is_contention(JobStoreContentionExhausted("pg spent")) is True


def test_classification_postgres_budget_exception_lane_contract():
    error = JobStoreContentionExhausted("pg spent")
    assert publication_loss_is_contention(error) == (
        isinstance(error, FirestoreContentionExhausted) or is_transaction_contention(error)
    )


def test_classification_postgres_wrapped_is_not_restrikeable():
    assert publication_loss_is_contention(chain(1, JobStoreContentionExhausted("pg spent"))) is False


def test_classification_postgres_leaf_classifies():
    assert publication_loss_is_contention(chain(2, JobStoreContentionExhausted("pg spent")).__cause__.__cause__) is True


def test_classification_deep_aborted_chain_twelve():
    assert publication_loss_is_contention(chain(12, Aborted("commit race"))) is True


def test_classification_budget_exception_under_deadline_marker_chain():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    error.__cause__ = InvalidArgument("Transaction has expired")
    assert publication_loss_is_contention(error) is True


from database.jobstore.postgres_store import JobStoreContentionExhausted


def test_classification_postgres_budget_exception():
    assert publication_loss_is_contention(JobStoreContentionExhausted("pg spent")) is True


def test_classification_postgres_budget_exception_lane_contract():
    error = JobStoreContentionExhausted("pg spent")
    assert publication_loss_is_contention(error) == (
        isinstance(error, FirestoreContentionExhausted) or is_transaction_contention(error)
    )


def test_classification_postgres_wrapped_is_not_restrikeable():
    assert publication_loss_is_contention(chain(1, JobStoreContentionExhausted("pg spent"))) is False


def test_classification_postgres_leaf_classifies():
    assert publication_loss_is_contention(chain(2, JobStoreContentionExhausted("pg spent")).__cause__.__cause__) is True


def test_classification_deep_aborted_chain_twelve():
    assert publication_loss_is_contention(chain(12, Aborted("commit race"))) is True


def test_classification_budget_exception_under_deadline_marker_chain():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    error.__cause__ = InvalidArgument("Transaction has expired")
    assert publication_loss_is_contention(error) is True


from database.jobstore.postgres_store import JobStoreContentionExhausted


def test_classification_postgres_budget_exception():
    assert publication_loss_is_contention(JobStoreContentionExhausted("pg spent")) is True


def test_classification_postgres_budget_exception_lane_contract():
    error = JobStoreContentionExhausted("pg spent")
    assert publication_loss_is_contention(error) == (
        isinstance(error, FirestoreContentionExhausted) or is_transaction_contention(error)
    )


def test_classification_postgres_wrapped_is_not_restrikeable():
    assert publication_loss_is_contention(chain(1, JobStoreContentionExhausted("pg spent"))) is False


def test_classification_postgres_leaf_classifies():
    assert publication_loss_is_contention(chain(2, JobStoreContentionExhausted("pg spent")).__cause__.__cause__) is True


def test_classification_deep_aborted_chain_twelve():
    assert publication_loss_is_contention(chain(12, Aborted("commit race"))) is True


def test_classification_budget_exception_under_deadline_marker_chain():
    error = FirestoreContentionExhausted("spent", reason="deadline_exhausted")
    error.__cause__ = InvalidArgument("Transaction has expired")
    assert publication_loss_is_contention(error) is True
