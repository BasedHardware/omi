"""Pack one owner's closed capture day. Flag defaults off; no legacy scans."""

import argparse

from database.legal_holds import destructive_operation_gate, external_write_fence
from utils.other.audio_packs import enabled, pack_owner_day
from utils.other.storage import get_canonical_audio_bucket


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--day', required=True)
    args = parser.parse_args()
    if not enabled():
        print('canonical packing disabled')
        return
    with external_write_fence(args.owner):
        pass
    with destructive_operation_gate(args.owner, kind='canonical_audio_packing'):
        count = pack_owner_day(get_canonical_audio_bucket(), args.owner, args.day)
    print(f'new shards: {count}')


if __name__ == '__main__':
    main()
