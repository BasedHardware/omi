import datetime as dt


def oldest_first(items):
    return sorted(items, key=lambda item: item.get("expires_at") or dt.datetime.max)
