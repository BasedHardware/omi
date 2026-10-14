"""Conservative, IO-free guards for model-extracted tasks (never stored user tasks)."""

import re
import unicodedata


def normalized_name(value: object) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split()) if isinstance(value, str) else ''


UNKNOWN_OWNERS = {
    '',
    'unknown',
    'unknown owner',
    'unknown person',
    'unassigned',
    'unspecified',
    'not specified',
    'none',
    'n/a',
    '?',
    'someone',
    'one speaker',
    'another speaker',
}
OWNER_ALIASES = {'user', 'the user', 'me', 'myself', 'i', 'account owner'}


def _given_name(name: str) -> str:
    token = name.split()[0] if name else ''
    token = re.sub(r'^\W+|\W+$', '', token)
    token = re.sub(r"['’]s$", '', token)
    return ''.join(char for char in token if not unicodedata.category(char).startswith('P'))


def clearly_other_owner(owner_name: object, profile_name: str | None) -> bool:
    name = normalized_name(owner_name)
    profile = normalized_name(profile_name)
    if name in UNKNOWN_OWNERS | OWNER_ALIASES or not profile:
        return False
    if re.fullmatch(r'(?:speaker|spk)\s*\d+', name):
        return False
    # STT surnames and initials are unreliable. Prefer keeping a stray task over
    # losing the owner's commitment; only a different given name is a rejection.
    owner_given, profile_given = _given_name(name), _given_name(profile)
    return bool(owner_given and profile_given and owner_given != profile_given)


_STATUS = re.compile(
    r'^(?:User|The user|[A-Z][\w\'-]*(?: [A-Z][\w\'-]*){0,2}) '
    r'(?:is|are|was|were) (?:(?:currently|already|still) )?'
    r'(?:testing|working|using|trying|reviewing|waiting|checking|planning|considering|developing)\b'
)
_IMPERATIVES = {'check', 'ensure', 'confirm', 'verify', 'ask', 'tell', 'remind', 'see', 'find'}


def clearly_status(description: object) -> bool:
    if not isinstance(description, str):
        return False
    text = ' '.join(description.split())
    if not text or text.split()[0].casefold() in _IMPERATIVES:
        return False
    return bool(_STATUS.match(text))
