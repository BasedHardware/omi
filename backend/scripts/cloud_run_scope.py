"""Closed Cloud Run target set; a selector is never admission authority."""

SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


def selected(service: str = 'all') -> tuple[str, ...]:
    if service == 'all':
        return SERVICES
    if service not in SERVICES:
        raise ValueError('invalid cloud_run_service')
    return (service,)
