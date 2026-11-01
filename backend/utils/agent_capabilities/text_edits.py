"""Pure exact-term text replacement shared by projections and edit validation."""

import re


def replace_term(text, before, after):
    return re.sub(r'(?<!\w)' + re.escape(before) + r'(?!\w)', lambda _: after, text)
