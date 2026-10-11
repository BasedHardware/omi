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
        ('Phone Battery Sample', row['person_id'], row['timestamp'], json.dumps(row['properties'])),
    )

for name, fn in {
    'toInt': lambda v: None if v is None else int(v),
    'toFloat': lambda v: None if v is None else float(v),
    'fixtureIsNull': lambda v: v is None,
    'now': lambda: 100000,
    'dateDiff': lambda unit, start, end: end - start,
}.items():
    db.create_function(name, -1, fn)


class CountIf:
    def __init__(self):
        self.n = 0

    def step(self, condition):
        self.n += bool(condition)

    def finalize(self):
        return self.n


class UniqExactIf:
    def __init__(self):
        self.values = set()

    def step(self, value, condition):
        if condition:
            self.values.add(value)

    def finalize(self):
        return len(self.values)


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
db.create_aggregate('uniqExactIf', 2, UniqExactIf)
db.create_aggregate('fixtureQuantileIf', 3, QuantileIf)
query = payload['query']
query = re.sub(r'properties\.([\w$]+)', lambda m: f"json_extract(properties, '$.\"{m[1]}\"')", query)
query = re.sub(r'INTERVAL (\d+) DAY', lambda m: str(int(m[1]) * 86400), query)
query = query.replace('lagInFrame(', 'lag(').replace('isNull(', 'fixtureIsNull(')
query = re.sub(r'\bif\(', 'iif(', query)
query = re.sub(r'quantileIf\((0\.[59])\)\(', r'fixtureQuantileIf(\1, ', query)
# HogQL resolves output aliases before joined input columns; SQLite needs
# qualification where both joined CTEs contain os/build.
head, tail = query.rsplit('FROM intervals', 1)
tail = tail.replace('GROUP BY os, build', 'GROUP BY intervals.os, intervals.build')
tail = tail.replace('ORDER BY os, build', 'ORDER BY intervals.os, intervals.build')
query = head + 'FROM intervals' + tail
print(json.dumps(db.execute(query).fetchall()))
