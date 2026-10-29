import pytest
from diarizer.admission import AdmissionQueue, CapacityExceeded, GPU_LOCK

def test_gpu_lock_exists():
    assert GPU_LOCK is not None
    assert hasattr(GPU_LOCK, "acquire")
    assert hasattr(GPU_LOCK, "release")

def test_admission_queue_reserve_release():
    queue = AdmissionQueue(capacity=2)
    assert queue.depth == 0

    queue.reserve()
    assert queue.depth == 1

    queue.reserve()
    assert queue.depth == 2

    with pytest.raises(CapacityExceeded):
        queue.reserve()

    queue.release()
    assert queue.depth == 1

    queue.release()
    assert queue.depth == 0

def test_admission_queue_admit_context_manager():
    queue = AdmissionQueue(capacity=1)

    with queue.admit():
        assert queue.depth == 1
        with pytest.raises(CapacityExceeded):
            queue.reserve()

    assert queue.depth == 0

def test_admission_queue_admit_context_manager_exception():
    queue = AdmissionQueue(capacity=1)

    class DummyException(Exception):
        pass

    with pytest.raises(DummyException):
        with queue.admit():
            assert queue.depth == 1
            raise DummyException()

    assert queue.depth == 0
