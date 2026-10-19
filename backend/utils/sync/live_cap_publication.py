"""One-use, process-owned source identity; retries cannot masquerade as fresh."""

from threading import RLock
from uuid import uuid4


class Publication:
    def __init__(self, uid: str) -> None:
        self._uid = uid
        self._identity = uuid4().hex
        self._attempted = False
        self.lock = RLock()
        self.fields: dict = {}
        self.put_started = False

    @property
    def uid(self) -> str:
        return self._uid

    @property
    def identity(self) -> str:
        return self._identity

    def is_retry(self, uid: str) -> bool:
        if uid != self.uid:
            raise ValueError('live publication owner changed')
        with self.lock:
            previous, self._attempted = self._attempted, True
            return previous
