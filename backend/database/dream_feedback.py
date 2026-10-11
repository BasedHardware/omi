"""Privacy gate and epoch-scoped k-anonymous developer patterns, without uid."""

import hashlib
import hmac
import json
import os
import re
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

from google.cloud import firestore

from database._client import get_firestore_client
from models.dream_agent import Feedback
from utils.dream_guards import feedback_rejection


def words(text):
    return re.findall(r'\w+', unicodedata.normalize('NFC', text).casefold())


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from strings(item)


def _name_terms(inputs, vocabulary):
    """Conservatively collect capitalized words and adjacent proper-noun runs."""
    names = set()

    def add_name(value):
        tokens = words(value)
        if tokens:
            names.add(tuple(tokens))

    for term in vocabulary:
        if isinstance(term, str):
            add_name(term)
            continue
        if isinstance(term, dict):
            aliases = term.get('aliases') or []
            for name in [term.get('spelling', ''), *aliases]:
                if isinstance(name, str):
                    add_name(name)

    token_pattern = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
    for text in strings(inputs):
        tokens = token_pattern.findall(unicodedata.normalize('NFC', text))
        run = []
        for token in tokens:
            normalized = words(token)
            if token.casefold().endswith(("'s", '’s')):
                normalized = words(token[:-2])
            if token[:1].isupper() and normalized:
                add_name(token)
                run.extend(normalized)
            else:
                if len(run) > 1:
                    names.add(tuple(run))
                run = []
        if len(run) > 1:
            names.add(tuple(run))
    return names


def validate(report: Feedback, inputs, vocabulary, *, uid='') -> None:
    reason = feedback_rejection(report)
    if reason:
        raise ValueError(reason)
    text = report.reproduction
    output = words(text)
    # References and storage IDs are private even when too short for the n-gram gate.
    identifiers = set()

    def collect(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if '/' in str(key):
                    identifiers.update((str(key), str(key).rsplit('/', 1)[-1]))
                if (key == 'id' or str(key).endswith('_id')) and isinstance(item, str):
                    identifiers.add(item)
                collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    collect(inputs)
    if uid:
        identifiers.add(uid)
    for identifier in identifiers:
        needle = words(identifier)
        if needle and any(output[i : i + len(needle)] == needle for i in range(len(output) - len(needle) + 1)):
            raise ValueError('feedback_record_reference')
    # Reject short quoted input too, across scripts and Unicode normalization forms.
    source_texts = list(strings(inputs))
    source_words = [words(source) for source in source_texts]
    for quoted in re.findall(r'["“«「‘\'](.*?)["”»」’\']', text, flags=re.DOTALL):
        needle = words(quoted)
        literal = unicodedata.normalize('NFC', quoted).casefold().strip()
        if needle and (
            any(literal in unicodedata.normalize('NFC', source).casefold() for source in source_texts)
            or any(
                any(source[i : i + len(needle)] == needle for i in range(len(source) - len(needle) + 1))
                for source in source_words
            )
        ):
            raise ValueError('feedback_input_overlap')
    for needle in source_words:
        if needle and any(output[i : i + len(needle)] == needle for i in range(len(output) - len(needle) + 1)):
            raise ValueError('feedback_input_overlap')
    grams = {tuple(output[i : i + 4]) for i in range(max(0, len(output) - 3))}
    # Also check across field boundaries: concatenation cannot evade the gate.
    source = words(' '.join(source_texts))
    if any(tuple(source[i : i + 4]) in grams for i in range(max(0, len(source) - 3))):
        raise ValueError('feedback_input_overlap')
    names = _name_terms(inputs, vocabulary)
    if uid:
        names.add(tuple(words(uid)))
    for needle in names:
        if needle and any(output[i : i + len(needle)] == list(needle) for i in range(len(output) - len(needle) + 1)):
            raise ValueError('feedback_vocabulary_overlap')


def store(uid, report: Feedback, inputs, vocabulary, *, now=None, firestore_client=None):
    validate(report, inputs, vocabulary, uid=uid)
    secret = os.getenv('DREAM_AGENT_FEEDBACK_SALT', '')
    if len(secret) < 32:
        raise ValueError('feedback_salt_unconfigured')
    now = now or datetime.now(timezone.utc)
    epoch = now.strftime('%G-W%V')
    distinct = hmac.new(secret.encode(), f'{epoch}:{uid}'.encode(), hashlib.sha256).hexdigest()
    pattern = hashlib.sha256(json.dumps([report.component, report.failure_class, report.severity]).encode()).hexdigest()
    database = firestore_client if firestore_client is not None else get_firestore_client()
    # uid never appears in the document path or stored payload.
    database.collection('dream_feedback').document(str(uuid4())).set(
        {
            'epoch': epoch,
            'distinct': distinct,
            'pattern': pattern,
            'created_at': now,
            **report.model_dump(),
        }
    )


def aggregate(rows, *, k=20):
    groups = {}
    for row in rows:
        key = (row['epoch'], row['pattern'])
        group = groups.setdefault(key, {'users': set(), 'reports': []})
        group['users'].add(row['distinct'])
        group['reports'].append(row)
    result = []
    for (epoch, _), group in groups.items():
        if len(group['users']) < max(2, k):
            continue
        reports = group['reports']
        result.append(
            {
                'epoch': epoch,
                'component': reports[0]['component'],
                'failure_class': reports[0]['failure_class'],
                'severity': reports[0]['severity'],
                'distinct_users': len(group['users']),
                'count': sum(r['count'] for r in reports),
                'mean_latency_ms': sum(r['latency_ms'] for r in reports) / len(reports),
                'mean_error_rate': sum(r['error_rate'] for r in reports) / len(reports),
            }
        )
    return result


def read_patterns(*, k=20, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    # Bound reads to the current rotation epoch, avoiding cross-epoch double counting.
    epoch = datetime.now(timezone.utc).strftime('%G-W%V')
    rows = (
        database.collection('dream_feedback')
        .where(filter=firestore.FieldFilter('epoch', '==', epoch))
        .limit(10000)
        .stream()
    )
    return aggregate([row.to_dict() for row in rows], k=k)
