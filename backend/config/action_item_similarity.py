"""Cheap conservative similarity for automatic refresh only; no provider calls."""

import re

from config.action_item_identity_key import identity_key

_FILLER = {'a', 'an', 'the', 'please', 'to'}
_VERBS = {'email': 'send', 'share': 'send', 'deliver': 'send', 'purchase': 'buy', 'telephone': 'call'}
_SENSITIVE = {'not', 'never', 'without', 'and', 'or', 'from', 'before', 'after'}
_CODE_WORDS = {'code', 'password', 'token', 'identifier', 'secret'}
_ELABORATION = {'final', 'latest', 'updated', 'revised'}


def tokens(description: object) -> frozenset[str]:
    words = re.findall(r"[\w]+(?:[-'.][\w]+)*", identity_key(description))
    if words:
        words[0] = _VERBS.get(words[0], words[0])
    return frozenset(word for word in words if word not in _FILLER)


def near_duplicate(left: object, right: object) -> bool:
    if identity_key(left) and identity_key(left) == identity_key(right):
        return True
    a, b = tokens(left), tokens(right)
    return near_duplicate_tokens(a, b)


def near_duplicate_tokens(a: frozenset[str], b: frozenset[str]) -> bool:
    """Compare cached token sets; exact identities are checked separately by the planner."""
    if not a or not b:
        return False
    # Preserve numbers, codes, negation, conjunctions and directional/time qualifiers.
    # Task titles containing codes use exact identity only (case and punctuation matter).
    if (a | b) & _CODE_WORDS:
        return False
    guarded = lambda words: {w for w in words if w in _SENSITIVE or any(c.isdigit() for c in w)}
    if guarded(a) != guarded(b):
        return False
    # Substituting a recipient, object or action is not a paraphrase, even when
    # most words match. Only reordering, known verb variants and small additions
    # qualify. In particular token_set_ratio's subset=100 would be too permissive.
    if a - b and b - a:
        return False
    if (a ^ b) - _ELABORATION:
        return False
    return len(a & b) / len(a | b) >= 0.8
