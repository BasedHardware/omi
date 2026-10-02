To resolve the issue, we'll adjust the `collect_people_stats` function to use the scan-and-fill reader when `include_discarded=True` and ensure it skips `discarded` rows in `aggregate_people_stats`.

Here's the fixed code:

```python
def collect_people_stats(uid, batch=25):
    stats = []
    rows = []
    scan_cap = 250
    while len(rows) < scan_cap:
        request_size = min(batch, scan_cap - len(rows))
        page = fetch_page(request_size, len(rows))
        rows.extend(page)
        if len(page) < request_size:
            break
    stats = aggregate_people_stats(rows, uid)
    return stats
```

This adjustment ensures that the function fetches all relevant rows before aggregating the stats.