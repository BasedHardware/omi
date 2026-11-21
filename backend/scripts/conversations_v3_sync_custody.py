"""Preview, apply, or roll back custody for one owner's nominated sync redirect."""

import argparse
import json

from database._client import get_data_plane_firestore_client
from database.conversations_v3_sync_repair import repair


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('preview', 'apply', 'rollback'))
    parser.add_argument('--uid', required=True)
    parser.add_argument('--donor', required=True)
    parser.add_argument('--receipt', help='Receipt from the reviewed preview, required for writes')
    args = parser.parse_args()
    if (args.mode == 'preview') == bool(args.receipt):
        parser.error('apply and rollback require --receipt from preview')
    result = repair(get_data_plane_firestore_client(), args.uid, args.donor, mode=args.mode, receipt=args.receipt)
    print(json.dumps(result, default=str, indent=2))
    return int(result['outcome'] == 'skipped')


if __name__ == '__main__':
    raise SystemExit(main())
