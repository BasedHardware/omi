"""Render arguments the worker deploy passes for the record token lease (SCA-3748).

Prod worker values leave ``recordTokenLease`` empty: gcp_diarizer.yml binds all
four from ``vars.RECORD_TOKEN_LEASE_*`` and the chart refuses to render without
them. Tests that render the prod chart pass the serve vector the same way.
``--set`` (not ``--set-string``) keeps a later per-test ``--set`` authoritative:
Helm applies every ``--set-string`` after every ``--set``.
"""

WORKER_LEASE_SET_ARGS = (
    '--set',
    'recordTokenLease.mode=serve,recordTokenLease.servePercent=100,'
    'recordTokenLease.seconds=3600,recordTokenLease.deployedAt=1795662310',
)
