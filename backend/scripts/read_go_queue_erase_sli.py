"""Emit aggregate Go queue erasure readback from authoritative deletion markers."""

from datetime import datetime, timezone
import json

from database.account_deletion_marker import account_deletion_collection
from database.go_queue_erase import readback


def main() -> None:
    result = readback(datetime.now(timezone.utc), account_deletion_collection())
    eligible = result['eligible']
    print(
        json.dumps(
            {
                'event': 'go_queue_erase_readback',
                'severity': 'ERROR' if result['overdue_pending'] or result['met'] < eligible else 'INFO',
                **result,
                'success_ratio': result['met'] / eligible if eligible else None,
            },
            sort_keys=True,
        )
    )


if __name__ == '__main__':
    main()
