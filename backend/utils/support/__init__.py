"""Support operator commands behind ``scripts/support/ops.py``.

Module contract (one module per command group):

- ``register(groups)`` adds one subparser group to the CLI's
  ``add_subparsers`` object. Each leaf subparser sets ``action=<name>`` and
  ``handler=<callable>`` via ``set_defaults``.
- A handler is ``handler(args, ctx, record) -> dict``: ``ctx`` is a
  ``database.support_actions.ActionContext`` (``ctx.apply`` false means dry
  run: perform no writes), ``record`` is the ``ActionRecord`` to fill with a
  content-free ``summary`` and ``before_digest``/``after_digest`` for writes.
  The returned dict is printed for the operator and may contain customer
  data; ``record.summary`` must not.
- No IO or client construction at import time. Firestore and GCS clients are
  resolved at call time and every handler accepts injected clients through
  module-level ``_firestore_client()`` / ``_storage_client()`` seams that tests
  monkeypatch.
"""
