import time

# In-memory proactive notification sent cache: maps "<uid>:<app_id>" -> (sent_ts, expiry_ts).
proactive_noti_sent_at: dict[str, tuple[int, float]] = {}

# Safety cap: expired entries are only deleted when their own key is read again, so keys for churned
# users or uninstalled apps would otherwise accumulate on the long-lived process. Bound the map.
_MAX_PROACTIVE_NOTI_ENTRIES = 50000


def _prune_proactive_noti(now: float) -> None:
    # Sweep already-expired entries first (get() already treats them as gone), then, if still over the
    # cap, drop the entries nearest to expiry so the map stays bounded.
    for key in [k for k, (_ts, ex) in proactive_noti_sent_at.items() if ex < now]:
        del proactive_noti_sent_at[key]
    if len(proactive_noti_sent_at) > _MAX_PROACTIVE_NOTI_ENTRIES:
        overflow = len(proactive_noti_sent_at) - _MAX_PROACTIVE_NOTI_ENTRIES
        for key in sorted(proactive_noti_sent_at, key=lambda k: proactive_noti_sent_at[k][1])[:overflow]:
            del proactive_noti_sent_at[key]


def set_proactive_noti_sent_at(uid: str, *, app_id: str, ts: int, ttl: int = 30) -> None:
    k = f'{uid}:{app_id}'
    now = time.time()
    proactive_noti_sent_at[k] = (ts, ttl + now)
    if len(proactive_noti_sent_at) > _MAX_PROACTIVE_NOTI_ENTRIES:
        _prune_proactive_noti(now)


def get_proactive_noti_sent_at(uid: str, app_id: str) -> int | None:
    k = f'{uid}:{app_id}'
    if k not in proactive_noti_sent_at:
        return None

    ts, ex = proactive_noti_sent_at[k]
    if ex < time.time():
        del proactive_noti_sent_at[k]
        return None
    return ts
