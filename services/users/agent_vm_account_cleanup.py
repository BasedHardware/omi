import math
import sys
from typing import Any, List


def _migration_reconcile_lease_active(
    vm: dict[str, Any], leases: List[dict[str, Any]], now: float
) -> bool:
    """
    Check if the VM's migration lease is still active.
    Raises RuntimeError if the lease is ambiguous or malformed.
    """
    reconcile = vm.get('reconcile', {})
    lease = reconcile.get('lease', {})
    raw_expires_at = lease.get('expiresAt')

    if not isinstance(raw_expires_at, (int, float, str)):
        raise RuntimeError('Agent VM migration reconcile lease is ambiguous')

    try:
        expires_at = float(raw_expires_at)
    except (TypeError, ValueError, OverflowError) as exc:
        raise RuntimeError('Agent VM migration reconcile lease is ambiguous') from exc

    if not math.isfinite(expires_at):
        raise RuntimeError('Agent VM migration reconcile lease is ambiguous')

    return expires_at > now