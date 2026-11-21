"""Execute the PostgreSQL selector builders against a recording connection."""

import ast
from contextlib import contextmanager, nullcontext
import re

from config.batch_census_selectors import DUE_FIELDS, STATE_FIELDS

_TABLES = re.compile(r'\bFROM\s+(jobs|results|docs|outbox)\b', re.IGNORECASE)
_STATES = re.compile(r'\b(?:' + '|'.join(sorted(STATE_FIELDS | {'done_at'})) + r')\b', re.IGNORECASE)
_LIMIT = re.compile(r'\blimit\s+(%s|\d+)\b', re.IGNORECASE)
_KEYED = re.compile(r'\b(?:key|id|dedupe_key|next_id)\s*=\s*%s\b', re.IGNORECASE)
_DUE = re.compile(
    r'\b(?:' + '|'.join(sorted(DUE_FIELDS)) + r''')\b["']?(?:\)::(?:float8|double precision))?\s*<=?\s*%s''',
    re.IGNORECASE,
)


def _functions(nodes, prefix=''):
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield prefix + node.name, node
        elif isinstance(node, ast.ClassDef):
            yield from _functions(node.body, prefix + node.name + '.')


def source_sites(source):
    """Find SQL-building sites that need an executable profile, including split predicates."""
    for name, function in _functions(ast.parse(source).body):
        literals = [
            node.value for node in ast.walk(function) if isinstance(node, ast.Constant) and type(node.value) is str
        ]
        text = ' '.join(literals)
        if any(re.match(r'\s*SELECT\s', item, re.IGNORECASE) for item in literals) and _TABLES.search(text):
            if _STATES.search(text):
                yield name


class RecordingConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement, parameters=()):
        text = statement if isinstance(statement, str) else statement.as_string()
        self.statements.append((text, parameters))
        return self

    def fetchone(self):
        statement = self.statements[-1][0].lower()
        if statement.startswith(('select count(', 'select min(')):
            return (0,)
        if statement.startswith('select id, available_at from outbox '):
            return (1, 2.0)
        return None

    def fetchall(self):
        return []

    def transaction(self):
        return nullcontext()


class RecordingPool:
    def __init__(self, connection):
        self.conn = connection

    @contextmanager
    def connection(self, *args, **kwargs):
        yield self.conn


def state_page(text, parameters):
    """Return the requested row limit for a state page that needs an exception."""
    normalized = ' '.join(text.lower().split())
    if not normalized.startswith('select ') or not _TABLES.search(normalized):
        return False, None
    if normalized.startswith(('select count(', 'select min(')):
        return False, None
    clause = normalized.partition(' where ')[2].split(' order by ')[0]
    if not _STATES.search(clause):
        return False, None
    # With alternatives every branch needs a due operand. An enqueue clock and
    # a cursor predicate remain chronology even if other profiles are due.
    if all(_DUE.search(branch) or _KEYED.search(branch) for branch in re.split(r'\bor\b', clause)):
        return False, None
    match = _LIMIT.search(normalized)
    if match is None:
        return True, None
    token = match[1]
    return True, parameters[normalized[: match.start()].count('%s')] if token == '%s' else int(token)
