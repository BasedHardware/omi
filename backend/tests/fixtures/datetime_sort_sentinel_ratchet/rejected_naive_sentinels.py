from datetime import datetime


def newest_first(items):
    return sorted(items, key=lambda item: item.get("created_at") or datetime.min, reverse=True)


def oldest_first(items):
    items.sort(key=lambda item: item.get("expires_at") or datetime.max)
    return items
