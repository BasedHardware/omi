from __future__ import annotations

ASSISTANT_VOICES: tuple[str, ...] = (
    'Zephyr',
    'Puck',
    'Charon',
    'Kore',
    'Fenrir',
    'Leda',
    'Orus',
    'Aoede',
    'Callirrhoe',
    'Autonoe',
    'Enceladus',
    'Iapetus',
    'Umbriel',
    'Algieba',
    'Despina',
    'Erinome',
    'Algenib',
    'Rasalgethi',
    'Laomedeia',
    'Achernar',
    'Alnilam',
    'Schedar',
    'Gacrux',
    'Pulcherrima',
    'Achird',
    'Zubenelgenubi',
    'Vindemiatrix',
    'Sadachbia',
    'Sadaltager',
    'Sulafat',
)

DEFAULT_ASSISTANT_VOICE = 'Charon'

ASSISTANT_VOICE_IDS = frozenset(ASSISTANT_VOICES)


def normalize_assistant_voice(value: str | None) -> str:
    if isinstance(value, str) and value in ASSISTANT_VOICE_IDS:
        return value
    return DEFAULT_ASSISTANT_VOICE
