"""Exact task identity shared by replacement and preservation; no IO or fuzzy matching."""

import unicodedata
from typing import List


def identity_key(description: object) -> str:
    """Exact canonical form of a task description; empty means "never the same task"."""
    if not isinstance(description, str):
        return ''
    # NFKC turns x² into x2 and Ⅳ into IV. Keep numeric compatibility symbols;
    # width folding (including full-width digits) and composed accents are safe.
    normalized = unicodedata.normalize(
        'NFC',
        ''.join(
            char if unicodedata.category(char) in ('No', 'Nl') else unicodedata.normalize('NFKC', char)
            for char in description
        ),
    )
    words = normalized.split()
    code_bearing = any(
        word.casefold().strip('.,:;!?') in {'code', 'password', 'token', 'identifier', 'secret'} for word in words
    )
    code_bearing = code_bearing or any(
        any(char.isalpha() for char in word) and any(char.isnumeric() for char in word) for word in words
    )
    folded = unicodedata.normalize('NFC', normalized if code_bearing else normalized.casefold())
    chars: List[str] = []
    for index, char in enumerate(folded):
        category = unicodedata.category(char)
        if char in ('\u200b', '\ufeff'):
            continue
        # Curly apostrophes are typography; signs, decimal separators, identifiers
        # and emoji/script joiners are content. Never erase all Unicode punctuation.
        if char in ('\u2018', '\u2019'):
            char = "'"
        next_char = folded[index + 1 : index + 2]
        previous_char = folded[index - 1 : index] if index else ''
        sentence_separator = char in '.,!?;' and (not next_char or next_char.isspace() or next_char in '.,!?;')
        if sentence_separator and not previous_char.isdigit():
            char = ' '
        chars.append(' ' if category == 'Cc' else char)
    key = ' '.join(''.join(chars).split())
    return key if any(not unicodedata.category(char).startswith(('P', 'Z', 'C')) for char in key) else ''
