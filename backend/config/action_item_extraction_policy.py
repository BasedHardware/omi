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


def clearly_other_owner(owner_name: object, profile_name: str | None) -> bool:
    name = normalized_name(owner_name)
    profile = normalized_name(profile_name)
    if name in UNKNOWN_OWNERS | OWNER_ALIASES or not profile:
        return False
    if re.fullmatch(r'(?:speaker|spk)\s*\d+', name):
        return False
    # Accept a first name or a full name, but not a different full name sharing it.
    return name not in {profile, profile.split()[0]}


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
