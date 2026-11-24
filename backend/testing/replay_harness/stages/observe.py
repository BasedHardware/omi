"""Observe real admission/drain boundaries without changing returns or exceptions."""

from contextlib import ExitStack
from contextvars import ContextVar
import re
from unittest.mock import patch

from testing.replay_harness.report import record_exception


def transaction_identity(body):
    name = f'{body.__module__}.{body.__qualname__}'.replace('.<locals>', '').replace('<lambda>', 'lambda')
    return name if re.fullmatch(r'[A-Za-z0-9_.]+', name) else 'unknown_transaction'


class AdmissionObserver:
    def __init__(self, live, store):
        self.live, self.store = live, store
        self.operation = ContextVar('replay_admission_operation', default=None)
        self.errors = []
        self.seen = {}
        self.transactions = {}
        self.stack = ExitStack()

    def record(self, error, operation, transaction=None):
        if id(error) not in self.seen:
            self.seen[id(error)] = error
            self.errors.append(record_exception(error, 'admission', operation=operation, transaction=transaction))

    def __enter__(self):
        original_admit, original_run, original_due = self.live.admit_recording, self.store.run, self.store.due

        async def admit(*args, **kwargs):
            token = self.operation.set('admit')
            try:
                return await original_admit(*args, **kwargs)
            except Exception as error:
                self.record(error, 'admit', self.transactions.get(id(error)))
                raise
            finally:
                self.operation.reset(token)

        def run(body):
            transaction = transaction_identity(body)
            try:
                return original_run(body)
            except Exception as error:
                if self.operation.get() == 'admit':
                    self.transactions[id(error)] = transaction
                else:
                    operation = 'defer' if body.__name__ == 'defer' else 'read_pending'
                    self.record(error, operation, transaction)
                raise

        def due(*args, **kwargs):
            try:
                return original_due(*args, **kwargs)
            except Exception as error:
                self.record(error, 'due')
                raise

        self.stack.enter_context(patch.object(self.live, 'admit_recording', admit))
        self.stack.enter_context(patch.object(self.store, 'run', run))
        self.stack.enter_context(patch.object(self.store, 'due', due))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)
