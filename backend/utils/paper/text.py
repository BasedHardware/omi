"""Text primitives shared by the deterministic edition blocks.

Deliberately dependency-free and dumb. These decide whether a question got answered and
whether two questions are the same question, so they need to be inspectable and cheap —
an embedding call here would make every block untestable and non-deterministic.
"""

import re
from datetime import date

# Words that carry no topic signal. Kept small on purpose: an aggressive stop list
# makes short questions collapse into each other and wrongly dedupe.
_STOPWORDS = frozenset("""
    a an the and or but if then than that this these those there here
    is are was were be been being am do does did doing done
    have has had having will would shall should can could may might must
    i me my we us our you your he him his she her it its they them their
    of in on at to for from with without by about into over under again
    what when where who whom which why how whether
    not no nor so as just also very really actually still yet
    """.split())

_WORD_RE = re.compile(r"[a-z0-9']+")


def content_words(text: str) -> set[str]:
    """Lowercased topic-bearing words, naively singularised.

    Singularisation is a trailing-``s`` strip guarded on length so ``loops``/``loop``
    match while ``is``/``i`` and ``css``/``cs`` do not.
    """
    words = set()
    for raw in _WORD_RE.findall((text or '').lower()):
        if raw in _STOPWORDS:
            continue
        if len(raw) > 3 and raw.endswith('s') and not raw.endswith('ss'):
            raw = raw[:-1]
        if len(raw) > 2:
            words.add(raw)
    return words


def overlap(source: str, candidate: str) -> float:
    """Fraction of ``source``'s content words that also appear in ``candidate``.

    Asymmetric by design: a long answer that happens to contain every word of a short
    question should score 1.0, but not the reverse.
    """
    src = content_words(source)
    if not src:
        return 0.0
    return len(src & content_words(candidate)) / len(src)


def days_between(earlier: str, later: date) -> int:
    """Whole days from an ``yyyy-mm-dd`` string to a date. 0 if unparseable or future."""
    try:
        parsed = date.fromisoformat((earlier or '').strip()[:10])
    except (ValueError, TypeError):
        return 0
    return max(0, (later - parsed).days)
