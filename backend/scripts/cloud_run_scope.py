"""Closed Cloud Run target set; a selector is never admission authority."""

SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')
# SCA-3120: the dedicated projection pump is a fifth, explicit-only target. `all`
# never includes it; only a manual prod cloud-run-only singleton selects it.
PROJECTION_PUMP = 'backend-projection-pump'
SELECTABLE = (*SERVICES, PROJECTION_PUMP)


def selected(service: str = 'all') -> tuple[str, ...]:
    if service == 'all':
        return SERVICES
    if service not in SELECTABLE:
        raise ValueError('invalid cloud_run_service')
    return (service,)
