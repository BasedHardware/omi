"""Which phone line a new link texts: the one with the most room, read in small random samples.

A line's room is its tighter limit: new people in the last 24 hours, or people linked. Each
line row holds `users` and `starts`, a map of hashed uid to {at, linked}. Starts drop out of the
map after 24 hours, or after the proof's lifetime if nobody texted, so the map stays small and
an abandoned connect sheet gives its slot back.
"""

import random
from datetime import timedelta

from google.cloud import firestore

from database.firestore_transaction_retry import run_with_transaction_contention_retry
from utils.messaging.identity import key

_DAY = timedelta(hours=24)
# One transaction reads at most this many lines, so a wave of links does not contend on all of
# them. With this many lines or fewer, every line is compared.
_SAMPLE = 8


def _line_ref(db, channel, address):
    return db.collection('channel_capacity').document(channel).collection('lines').document(address)


def _placement_ref(db, uid, channel):
    return db.collection('users').document(uid).collection('channel_lines').document(channel)


def _live_starts(row, now, hold):
    return {
        who: start
        for who, start in (row.get('starts') or {}).items()
        if now - start['at'] < (_DAY if start.get('linked') else hold)
    }


def _room(line, row, starts, who, now):
    """Fraction of the tighter limit still free for this person; 0 means the line is full."""
    others = {name: start for name, start in starts.items() if name != who}
    new_limit = line.new_limit(now.date())
    if new_limit <= 0 or line.max_users <= 0:
        return 0
    pending = sum(not start.get('linked') for start in others.values())
    new_left = new_limit - len(others)
    users_left = line.max_users - row.get('users', 0) - pending
    return max(0, min(new_left / new_limit, users_left / line.max_users))


def assign_line(db, uid, channel, lines, *, now, hold):
    """The address this person should text, or None when no line has room.

    Someone who has linked keeps their line even past `max_users`, because their conversation is
    already there and Keiki advises against moving people. A new code while one is pending keeps
    the same line and slot.
    """
    by_address = {line.address: line for line in lines}
    who = key(uid)
    placement = _placement_ref(db, uid, channel)

    def from_sample(sample):
        @firestore.transactional
        def apply(tx):
            placed = placement.get(transaction=tx).to_dict() or {}
            current = by_address.get(placed.get('address'))
            if current and placed.get('linked'):
                return current.address
            candidates = list(sample) + ([current] if current and current not in sample else [])
            refs = {line.address: _line_ref(db, channel, line.address) for line in candidates}
            rows = {address: ref.get(transaction=tx).to_dict() or {} for address, ref in refs.items()}
            starts = {address: _live_starts(row, now, hold) for address, row in rows.items()}
            if current and who in starts[current.address]:
                chosen = current
            else:
                chosen = max(
                    candidates,
                    key=lambda line: _room(line, rows[line.address], starts[line.address], who, now),
                )
                if _room(chosen, rows[chosen.address], starts[chosen.address], who, now) <= 0:
                    return None
            address = chosen.address
            tx.set(refs[address], {**rows[address], 'starts': {**starts[address], who: {'at': now, 'linked': False}}})
            tx.set(placement, {'address': address, 'linked': False, 'updated_at': now})
            return address

        return run_with_transaction_contention_retry(db.transaction, apply, operation_name='messaging_line_assign')

    shuffled = random.sample(list(lines), len(lines))
    for start in range(0, len(shuffled), _SAMPLE):
        address = from_sample(shuffled[start : start + _SAMPLE])
        if address:
            return address
    return None


def read_line(db, tx, channel, address):
    ref = _line_ref(db, channel, address)
    return ref, ref.get(transaction=tx).to_dict() or {}


def record_link(db, tx, uid, channel, address, ref, row, now):
    """Count the person on the line. Call after every read in the transaction."""
    who = key(uid)
    starts = dict(row.get('starts') or {})
    if who in starts:
        starts[who] = {'at': now, 'linked': True}
    tx.set(ref, {**row, 'users': row.get('users', 0) + 1, 'starts': starts})
    tx.set(_placement_ref(db, uid, channel), {'address': address, 'linked': True, 'updated_at': now})


def release_link(tx, ref, row):
    """A slot in the last 24 hours stays spent: the line has still opened that conversation."""
    tx.set(ref, {'users': max(0, row.get('users', 0) - 1)}, merge=True)
