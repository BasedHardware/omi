"""Execute the route's query over fixtures using SQLite dialect adapters.

Only HogQL syntax/functions are adapted; selection, joins and guards come from
production SQL. This is a hermetic behavioral test, not a PostHog conformance test.
"""

import json
import re
import sqlite3
import sys

payload = json.load(sys.stdin)
db = sqlite3.connect(':memory:')
db.execute('CREATE TABLE events (event TEXT, person_id TEXT, timestamp INTEGER, properties TEXT)')
for row in payload['rows']:
    db.execute(
        'INSERT INTO events VALUES (?, ?, ?, ?)',
        (row.get('event', 'Phone Battery Sample'), row['person_id'], row['timestamp'], json.dumps(row['properties'])),
    )

for name, fn in {
    'toInt': lambda v: None if v is None else int(v),
    'toFloat': lambda v: None if v is None else float(v),
    'fixtureIsNull': lambda v: v is None,
    'now': lambda: 100000,
    'dateDiff': lambda unit, start, end: end - start,
    'greatest': lambda *values: max(v for v in values if v is not None),
    'fixtureMatch': lambda value, pattern: value is not None and re.search(pattern, value) is not None,
}.items():
    db.create_function(name, -1, fn)


class CountIf:
    def __init__(self):
        self.n = 0

    def step(self, condition):
        self.n += bool(condition)

    def finalize(self):
        return self.n


class SumIf:
    def __init__(self):
        self.total = 0

    def step(self, value, condition):
        if condition and value is not None:
            self.total += value

    def finalize(self):
        return self.total


class QuantileIf:
    def __init__(self):
        self.values = []
        self.q = 0

    def step(self, q, value, condition):
        self.q = q
        if condition and value is not None:
            self.values.append(value)

    def finalize(self):
        if not self.values:
            return None
        values = sorted(self.values)
        return values[round((len(values) - 1) * self.q)]


db.create_aggregate('countIf', 1, CountIf)
db.create_aggregate('sumIf', 2, SumIf)
db.create_aggregate('fixtureQuantileIf', 3, QuantileIf)
query = payload['query']
query = re.sub(r'properties\.([\w$]+)', lambda m: f"json_extract(properties, '$.\"{m[1]}\"')", query)
query = re.sub(r'INTERVAL (\d+) DAY', lambda m: str(int(m[1]) * 86400), query)
query = query.replace('lagInFrame(', 'lag(').replace('isNull(', 'fixtureIsNull(')
query = query.replace('match(', 'fixtureMatch(')
query = re.sub(r'\bif\(', 'iif(', query)
query = re.sub(r'quantileIf\((0\.[59])\)\(', r'fixtureQuantileIf(\1, ', query)
# The pendant fixture uses one model per firmware/OS group.
query = query.replace('any(model)', 'min(model)')
print(json.dumps(db.execute(query).fetchall()))
