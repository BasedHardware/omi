"""Generated band 01 of 32: the long-speech language skip's flag posture.

Spec-computed cell by cell from the documented contract - the
empty-ladder handoff predicate's safety dominance (the shipping
posture arms the handoff through the safety net with the recovery and
disposition lanes dark), the Parakeet language roster, the 5.0-second
measured-speech floor and the kill switch's false-words grammar -
never from the implementation under test. A failing cell means the
skip drifted from the documented posture in that case.

Posture: recovery=0 disposition=0 safety=0 kill=0 (speech 0.00-6.00).

Failure-Class: FC-long-speech-skip-flag-posture-drifts-from-the-handoff-boundary
"""

import os

import pytest

from diarizer.batch_pipeline import long_speech_handoff

_PARAKEET_ROSTER = frozenset(
    (
        'bg',
        'cs',
        'da',
        'de',
        'el',
        'en',
        'es',
        'et',
        'fi',
        'fr',
        'hr',
        'hu',
        'it',
        'lt',
        'lv',
        'mt',
        'nl',
        'pl',
        'pt',
        'ro',
        'ru',
        'sk',
        'sl',
        'sv',
        'uk',
    )
)

_POSTURE_ENV = {
    'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED': 'false',
    'BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED': 'false',
    'BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED': 'false',
    'BATCH_PIPELINE_LONG_SPEECH_HANDOFF_ENABLED': 'false',
}
_PRIOR = {}


@pytest.fixture(autouse=True, scope="module")
def _posture():
    """Pin this band's flag posture for every cell, then restore."""
    for key, value in _POSTURE_ENV.items():
        _PRIOR[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    yield
    for key, value in _PRIOR.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _spec_armed(language, speech):
    """The documented posture: kill switch, handoff, roster, speech floor."""
    handoff = False  # the empty_asr arm: (recovery or safety) or (disposition or safety)
    return False and handoff and isinstance(language, str) and language not in _PARAKEET_ROSTER and speech >= 5.0


def test_c000000() -> None:
    """language='bg' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000001() -> None:
    """language='bg' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000002() -> None:
    """language='bg' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000003() -> None:
    """language='bg' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000004() -> None:
    """language='bg' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000005() -> None:
    """language='bg' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000006() -> None:
    """language='bg' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000007() -> None:
    """language='bg' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000008() -> None:
    """language='bg' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000009() -> None:
    """language='bg' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000010() -> None:
    """language='bg' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000011() -> None:
    """language='bg' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000012() -> None:
    """language='bg' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000013() -> None:
    """language='bg' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000014() -> None:
    """language='bg' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000015() -> None:
    """language='bg' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000016() -> None:
    """language='bg' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000017() -> None:
    """language='bg' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000018() -> None:
    """language='bg' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000019() -> None:
    """language='bg' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000020() -> None:
    """language='bg' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000021() -> None:
    """language='bg' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000022() -> None:
    """language='bg' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000023() -> None:
    """language='bg' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000024() -> None:
    """language='bg' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000025() -> None:
    """language='bg' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000026() -> None:
    """language='bg' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000027() -> None:
    """language='bg' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000028() -> None:
    """language='bg' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000029() -> None:
    """language='bg' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000030() -> None:
    """language='bg' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000031() -> None:
    """language='bg' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000032() -> None:
    """language='bg' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000033() -> None:
    """language='bg' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000034() -> None:
    """language='bg' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000035() -> None:
    """language='bg' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000036() -> None:
    """language='bg' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000037() -> None:
    """language='bg' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000038() -> None:
    """language='bg' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000039() -> None:
    """language='bg' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000040() -> None:
    """language='bg' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000041() -> None:
    """language='bg' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000042() -> None:
    """language='bg' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000043() -> None:
    """language='bg' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000044() -> None:
    """language='bg' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000045() -> None:
    """language='bg' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000046() -> None:
    """language='bg' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000047() -> None:
    """language='bg' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000048() -> None:
    """language='bg' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000049() -> None:
    """language='bg' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000050() -> None:
    """language='bg' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000051() -> None:
    """language='bg' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000052() -> None:
    """language='bg' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000053() -> None:
    """language='bg' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000054() -> None:
    """language='bg' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000055() -> None:
    """language='bg' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000056() -> None:
    """language='bg' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000057() -> None:
    """language='bg' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000058() -> None:
    """language='bg' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000059() -> None:
    """language='bg' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000060() -> None:
    """language='bg' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000061() -> None:
    """language='bg' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000062() -> None:
    """language='bg' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000063() -> None:
    """language='bg' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000064() -> None:
    """language='bg' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000065() -> None:
    """language='bg' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000066() -> None:
    """language='bg' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000067() -> None:
    """language='bg' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000068() -> None:
    """language='bg' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000069() -> None:
    """language='bg' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000070() -> None:
    """language='bg' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000071() -> None:
    """language='bg' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000072() -> None:
    """language='bg' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000073() -> None:
    """language='bg' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000074() -> None:
    """language='bg' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000075() -> None:
    """language='bg' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000076() -> None:
    """language='bg' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000077() -> None:
    """language='bg' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000078() -> None:
    """language='bg' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000079() -> None:
    """language='bg' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000080() -> None:
    """language='bg' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000081() -> None:
    """language='bg' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000082() -> None:
    """language='bg' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000083() -> None:
    """language='bg' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000084() -> None:
    """language='bg' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000085() -> None:
    """language='bg' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000086() -> None:
    """language='bg' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000087() -> None:
    """language='bg' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000088() -> None:
    """language='bg' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000089() -> None:
    """language='bg' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000090() -> None:
    """language='bg' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000091() -> None:
    """language='bg' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000092() -> None:
    """language='bg' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000093() -> None:
    """language='bg' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000094() -> None:
    """language='bg' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000095() -> None:
    """language='bg' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000096() -> None:
    """language='bg' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000097() -> None:
    """language='bg' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000098() -> None:
    """language='bg' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000099() -> None:
    """language='bg' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000100() -> None:
    """language='bg' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000101() -> None:
    """language='bg' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000102() -> None:
    """language='bg' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000103() -> None:
    """language='bg' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000104() -> None:
    """language='bg' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000105() -> None:
    """language='bg' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000106() -> None:
    """language='bg' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000107() -> None:
    """language='bg' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000108() -> None:
    """language='bg' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000109() -> None:
    """language='bg' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000110() -> None:
    """language='bg' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000111() -> None:
    """language='bg' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000112() -> None:
    """language='bg' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000113() -> None:
    """language='bg' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000114() -> None:
    """language='bg' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000115() -> None:
    """language='bg' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000116() -> None:
    """language='bg' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000117() -> None:
    """language='bg' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000118() -> None:
    """language='bg' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000119() -> None:
    """language='bg' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000120() -> None:
    """language='bg' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'bg', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000121() -> None:
    """language='cs' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000122() -> None:
    """language='cs' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000123() -> None:
    """language='cs' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000124() -> None:
    """language='cs' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000125() -> None:
    """language='cs' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000126() -> None:
    """language='cs' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000127() -> None:
    """language='cs' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000128() -> None:
    """language='cs' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000129() -> None:
    """language='cs' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000130() -> None:
    """language='cs' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000131() -> None:
    """language='cs' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000132() -> None:
    """language='cs' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000133() -> None:
    """language='cs' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000134() -> None:
    """language='cs' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000135() -> None:
    """language='cs' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000136() -> None:
    """language='cs' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000137() -> None:
    """language='cs' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000138() -> None:
    """language='cs' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000139() -> None:
    """language='cs' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000140() -> None:
    """language='cs' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000141() -> None:
    """language='cs' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000142() -> None:
    """language='cs' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000143() -> None:
    """language='cs' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000144() -> None:
    """language='cs' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000145() -> None:
    """language='cs' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000146() -> None:
    """language='cs' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000147() -> None:
    """language='cs' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000148() -> None:
    """language='cs' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000149() -> None:
    """language='cs' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000150() -> None:
    """language='cs' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000151() -> None:
    """language='cs' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000152() -> None:
    """language='cs' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000153() -> None:
    """language='cs' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000154() -> None:
    """language='cs' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000155() -> None:
    """language='cs' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000156() -> None:
    """language='cs' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000157() -> None:
    """language='cs' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000158() -> None:
    """language='cs' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000159() -> None:
    """language='cs' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000160() -> None:
    """language='cs' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000161() -> None:
    """language='cs' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000162() -> None:
    """language='cs' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000163() -> None:
    """language='cs' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000164() -> None:
    """language='cs' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000165() -> None:
    """language='cs' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000166() -> None:
    """language='cs' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000167() -> None:
    """language='cs' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000168() -> None:
    """language='cs' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000169() -> None:
    """language='cs' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000170() -> None:
    """language='cs' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000171() -> None:
    """language='cs' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000172() -> None:
    """language='cs' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000173() -> None:
    """language='cs' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000174() -> None:
    """language='cs' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000175() -> None:
    """language='cs' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000176() -> None:
    """language='cs' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000177() -> None:
    """language='cs' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000178() -> None:
    """language='cs' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000179() -> None:
    """language='cs' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000180() -> None:
    """language='cs' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000181() -> None:
    """language='cs' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000182() -> None:
    """language='cs' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000183() -> None:
    """language='cs' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000184() -> None:
    """language='cs' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000185() -> None:
    """language='cs' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000186() -> None:
    """language='cs' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000187() -> None:
    """language='cs' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000188() -> None:
    """language='cs' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000189() -> None:
    """language='cs' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000190() -> None:
    """language='cs' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000191() -> None:
    """language='cs' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000192() -> None:
    """language='cs' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000193() -> None:
    """language='cs' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000194() -> None:
    """language='cs' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000195() -> None:
    """language='cs' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000196() -> None:
    """language='cs' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000197() -> None:
    """language='cs' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000198() -> None:
    """language='cs' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000199() -> None:
    """language='cs' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000200() -> None:
    """language='cs' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000201() -> None:
    """language='cs' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000202() -> None:
    """language='cs' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000203() -> None:
    """language='cs' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000204() -> None:
    """language='cs' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000205() -> None:
    """language='cs' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000206() -> None:
    """language='cs' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000207() -> None:
    """language='cs' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000208() -> None:
    """language='cs' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000209() -> None:
    """language='cs' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000210() -> None:
    """language='cs' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000211() -> None:
    """language='cs' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000212() -> None:
    """language='cs' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000213() -> None:
    """language='cs' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000214() -> None:
    """language='cs' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000215() -> None:
    """language='cs' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000216() -> None:
    """language='cs' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000217() -> None:
    """language='cs' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000218() -> None:
    """language='cs' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000219() -> None:
    """language='cs' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000220() -> None:
    """language='cs' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000221() -> None:
    """language='cs' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000222() -> None:
    """language='cs' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000223() -> None:
    """language='cs' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000224() -> None:
    """language='cs' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000225() -> None:
    """language='cs' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000226() -> None:
    """language='cs' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000227() -> None:
    """language='cs' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000228() -> None:
    """language='cs' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000229() -> None:
    """language='cs' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000230() -> None:
    """language='cs' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000231() -> None:
    """language='cs' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000232() -> None:
    """language='cs' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000233() -> None:
    """language='cs' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000234() -> None:
    """language='cs' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000235() -> None:
    """language='cs' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000236() -> None:
    """language='cs' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000237() -> None:
    """language='cs' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000238() -> None:
    """language='cs' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000239() -> None:
    """language='cs' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000240() -> None:
    """language='cs' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000241() -> None:
    """language='cs' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'cs', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000242() -> None:
    """language='da' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000243() -> None:
    """language='da' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000244() -> None:
    """language='da' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000245() -> None:
    """language='da' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000246() -> None:
    """language='da' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000247() -> None:
    """language='da' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000248() -> None:
    """language='da' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000249() -> None:
    """language='da' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000250() -> None:
    """language='da' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000251() -> None:
    """language='da' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000252() -> None:
    """language='da' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000253() -> None:
    """language='da' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000254() -> None:
    """language='da' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000255() -> None:
    """language='da' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000256() -> None:
    """language='da' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000257() -> None:
    """language='da' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000258() -> None:
    """language='da' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000259() -> None:
    """language='da' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000260() -> None:
    """language='da' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000261() -> None:
    """language='da' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000262() -> None:
    """language='da' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000263() -> None:
    """language='da' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000264() -> None:
    """language='da' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000265() -> None:
    """language='da' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000266() -> None:
    """language='da' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000267() -> None:
    """language='da' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000268() -> None:
    """language='da' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000269() -> None:
    """language='da' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000270() -> None:
    """language='da' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000271() -> None:
    """language='da' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000272() -> None:
    """language='da' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000273() -> None:
    """language='da' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000274() -> None:
    """language='da' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000275() -> None:
    """language='da' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000276() -> None:
    """language='da' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000277() -> None:
    """language='da' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000278() -> None:
    """language='da' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000279() -> None:
    """language='da' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000280() -> None:
    """language='da' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000281() -> None:
    """language='da' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000282() -> None:
    """language='da' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000283() -> None:
    """language='da' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000284() -> None:
    """language='da' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000285() -> None:
    """language='da' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000286() -> None:
    """language='da' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000287() -> None:
    """language='da' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000288() -> None:
    """language='da' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000289() -> None:
    """language='da' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000290() -> None:
    """language='da' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000291() -> None:
    """language='da' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000292() -> None:
    """language='da' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000293() -> None:
    """language='da' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000294() -> None:
    """language='da' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000295() -> None:
    """language='da' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000296() -> None:
    """language='da' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000297() -> None:
    """language='da' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000298() -> None:
    """language='da' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000299() -> None:
    """language='da' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000300() -> None:
    """language='da' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000301() -> None:
    """language='da' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000302() -> None:
    """language='da' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000303() -> None:
    """language='da' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000304() -> None:
    """language='da' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000305() -> None:
    """language='da' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000306() -> None:
    """language='da' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000307() -> None:
    """language='da' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000308() -> None:
    """language='da' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000309() -> None:
    """language='da' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000310() -> None:
    """language='da' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000311() -> None:
    """language='da' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000312() -> None:
    """language='da' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000313() -> None:
    """language='da' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000314() -> None:
    """language='da' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000315() -> None:
    """language='da' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000316() -> None:
    """language='da' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000317() -> None:
    """language='da' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000318() -> None:
    """language='da' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000319() -> None:
    """language='da' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000320() -> None:
    """language='da' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000321() -> None:
    """language='da' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000322() -> None:
    """language='da' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000323() -> None:
    """language='da' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000324() -> None:
    """language='da' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000325() -> None:
    """language='da' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000326() -> None:
    """language='da' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000327() -> None:
    """language='da' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000328() -> None:
    """language='da' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000329() -> None:
    """language='da' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000330() -> None:
    """language='da' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000331() -> None:
    """language='da' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000332() -> None:
    """language='da' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000333() -> None:
    """language='da' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000334() -> None:
    """language='da' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000335() -> None:
    """language='da' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000336() -> None:
    """language='da' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000337() -> None:
    """language='da' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000338() -> None:
    """language='da' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000339() -> None:
    """language='da' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000340() -> None:
    """language='da' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000341() -> None:
    """language='da' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000342() -> None:
    """language='da' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000343() -> None:
    """language='da' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000344() -> None:
    """language='da' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000345() -> None:
    """language='da' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000346() -> None:
    """language='da' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000347() -> None:
    """language='da' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000348() -> None:
    """language='da' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000349() -> None:
    """language='da' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000350() -> None:
    """language='da' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000351() -> None:
    """language='da' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000352() -> None:
    """language='da' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000353() -> None:
    """language='da' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000354() -> None:
    """language='da' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000355() -> None:
    """language='da' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000356() -> None:
    """language='da' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000357() -> None:
    """language='da' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000358() -> None:
    """language='da' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000359() -> None:
    """language='da' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000360() -> None:
    """language='da' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000361() -> None:
    """language='da' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000362() -> None:
    """language='da' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'da', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000363() -> None:
    """language='de' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000364() -> None:
    """language='de' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000365() -> None:
    """language='de' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000366() -> None:
    """language='de' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000367() -> None:
    """language='de' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000368() -> None:
    """language='de' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000369() -> None:
    """language='de' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000370() -> None:
    """language='de' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000371() -> None:
    """language='de' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000372() -> None:
    """language='de' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000373() -> None:
    """language='de' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000374() -> None:
    """language='de' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000375() -> None:
    """language='de' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000376() -> None:
    """language='de' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000377() -> None:
    """language='de' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000378() -> None:
    """language='de' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000379() -> None:
    """language='de' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000380() -> None:
    """language='de' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000381() -> None:
    """language='de' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000382() -> None:
    """language='de' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000383() -> None:
    """language='de' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000384() -> None:
    """language='de' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000385() -> None:
    """language='de' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000386() -> None:
    """language='de' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000387() -> None:
    """language='de' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000388() -> None:
    """language='de' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000389() -> None:
    """language='de' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000390() -> None:
    """language='de' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000391() -> None:
    """language='de' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000392() -> None:
    """language='de' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000393() -> None:
    """language='de' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000394() -> None:
    """language='de' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000395() -> None:
    """language='de' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000396() -> None:
    """language='de' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000397() -> None:
    """language='de' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000398() -> None:
    """language='de' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000399() -> None:
    """language='de' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000400() -> None:
    """language='de' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000401() -> None:
    """language='de' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000402() -> None:
    """language='de' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000403() -> None:
    """language='de' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000404() -> None:
    """language='de' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000405() -> None:
    """language='de' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000406() -> None:
    """language='de' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000407() -> None:
    """language='de' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000408() -> None:
    """language='de' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000409() -> None:
    """language='de' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000410() -> None:
    """language='de' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000411() -> None:
    """language='de' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000412() -> None:
    """language='de' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000413() -> None:
    """language='de' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000414() -> None:
    """language='de' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000415() -> None:
    """language='de' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000416() -> None:
    """language='de' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000417() -> None:
    """language='de' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000418() -> None:
    """language='de' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000419() -> None:
    """language='de' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000420() -> None:
    """language='de' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000421() -> None:
    """language='de' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000422() -> None:
    """language='de' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000423() -> None:
    """language='de' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000424() -> None:
    """language='de' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000425() -> None:
    """language='de' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000426() -> None:
    """language='de' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000427() -> None:
    """language='de' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000428() -> None:
    """language='de' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000429() -> None:
    """language='de' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000430() -> None:
    """language='de' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000431() -> None:
    """language='de' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000432() -> None:
    """language='de' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000433() -> None:
    """language='de' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000434() -> None:
    """language='de' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000435() -> None:
    """language='de' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000436() -> None:
    """language='de' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000437() -> None:
    """language='de' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000438() -> None:
    """language='de' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000439() -> None:
    """language='de' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000440() -> None:
    """language='de' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000441() -> None:
    """language='de' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000442() -> None:
    """language='de' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000443() -> None:
    """language='de' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000444() -> None:
    """language='de' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000445() -> None:
    """language='de' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000446() -> None:
    """language='de' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000447() -> None:
    """language='de' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000448() -> None:
    """language='de' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000449() -> None:
    """language='de' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000450() -> None:
    """language='de' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000451() -> None:
    """language='de' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000452() -> None:
    """language='de' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000453() -> None:
    """language='de' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000454() -> None:
    """language='de' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000455() -> None:
    """language='de' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000456() -> None:
    """language='de' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000457() -> None:
    """language='de' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000458() -> None:
    """language='de' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000459() -> None:
    """language='de' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000460() -> None:
    """language='de' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000461() -> None:
    """language='de' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000462() -> None:
    """language='de' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000463() -> None:
    """language='de' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000464() -> None:
    """language='de' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000465() -> None:
    """language='de' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000466() -> None:
    """language='de' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000467() -> None:
    """language='de' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000468() -> None:
    """language='de' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000469() -> None:
    """language='de' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000470() -> None:
    """language='de' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000471() -> None:
    """language='de' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000472() -> None:
    """language='de' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000473() -> None:
    """language='de' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000474() -> None:
    """language='de' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000475() -> None:
    """language='de' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000476() -> None:
    """language='de' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000477() -> None:
    """language='de' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000478() -> None:
    """language='de' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000479() -> None:
    """language='de' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000480() -> None:
    """language='de' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000481() -> None:
    """language='de' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000482() -> None:
    """language='de' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000483() -> None:
    """language='de' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'de', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000484() -> None:
    """language='el' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000485() -> None:
    """language='el' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000486() -> None:
    """language='el' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000487() -> None:
    """language='el' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000488() -> None:
    """language='el' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000489() -> None:
    """language='el' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000490() -> None:
    """language='el' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000491() -> None:
    """language='el' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000492() -> None:
    """language='el' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000493() -> None:
    """language='el' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000494() -> None:
    """language='el' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000495() -> None:
    """language='el' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000496() -> None:
    """language='el' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000497() -> None:
    """language='el' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000498() -> None:
    """language='el' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000499() -> None:
    """language='el' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000500() -> None:
    """language='el' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000501() -> None:
    """language='el' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000502() -> None:
    """language='el' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000503() -> None:
    """language='el' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000504() -> None:
    """language='el' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000505() -> None:
    """language='el' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000506() -> None:
    """language='el' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000507() -> None:
    """language='el' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000508() -> None:
    """language='el' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000509() -> None:
    """language='el' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000510() -> None:
    """language='el' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000511() -> None:
    """language='el' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000512() -> None:
    """language='el' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000513() -> None:
    """language='el' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000514() -> None:
    """language='el' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000515() -> None:
    """language='el' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000516() -> None:
    """language='el' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000517() -> None:
    """language='el' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000518() -> None:
    """language='el' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000519() -> None:
    """language='el' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000520() -> None:
    """language='el' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000521() -> None:
    """language='el' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000522() -> None:
    """language='el' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000523() -> None:
    """language='el' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000524() -> None:
    """language='el' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000525() -> None:
    """language='el' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000526() -> None:
    """language='el' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000527() -> None:
    """language='el' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000528() -> None:
    """language='el' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000529() -> None:
    """language='el' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000530() -> None:
    """language='el' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000531() -> None:
    """language='el' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000532() -> None:
    """language='el' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000533() -> None:
    """language='el' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000534() -> None:
    """language='el' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000535() -> None:
    """language='el' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000536() -> None:
    """language='el' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000537() -> None:
    """language='el' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000538() -> None:
    """language='el' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000539() -> None:
    """language='el' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000540() -> None:
    """language='el' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000541() -> None:
    """language='el' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000542() -> None:
    """language='el' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000543() -> None:
    """language='el' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000544() -> None:
    """language='el' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000545() -> None:
    """language='el' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000546() -> None:
    """language='el' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000547() -> None:
    """language='el' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000548() -> None:
    """language='el' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000549() -> None:
    """language='el' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000550() -> None:
    """language='el' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000551() -> None:
    """language='el' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000552() -> None:
    """language='el' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000553() -> None:
    """language='el' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000554() -> None:
    """language='el' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000555() -> None:
    """language='el' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000556() -> None:
    """language='el' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000557() -> None:
    """language='el' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000558() -> None:
    """language='el' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000559() -> None:
    """language='el' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000560() -> None:
    """language='el' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000561() -> None:
    """language='el' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000562() -> None:
    """language='el' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000563() -> None:
    """language='el' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000564() -> None:
    """language='el' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000565() -> None:
    """language='el' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000566() -> None:
    """language='el' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000567() -> None:
    """language='el' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000568() -> None:
    """language='el' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000569() -> None:
    """language='el' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000570() -> None:
    """language='el' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000571() -> None:
    """language='el' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000572() -> None:
    """language='el' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000573() -> None:
    """language='el' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000574() -> None:
    """language='el' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000575() -> None:
    """language='el' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000576() -> None:
    """language='el' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000577() -> None:
    """language='el' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000578() -> None:
    """language='el' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000579() -> None:
    """language='el' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000580() -> None:
    """language='el' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000581() -> None:
    """language='el' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000582() -> None:
    """language='el' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000583() -> None:
    """language='el' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000584() -> None:
    """language='el' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000585() -> None:
    """language='el' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000586() -> None:
    """language='el' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000587() -> None:
    """language='el' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000588() -> None:
    """language='el' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000589() -> None:
    """language='el' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000590() -> None:
    """language='el' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000591() -> None:
    """language='el' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000592() -> None:
    """language='el' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000593() -> None:
    """language='el' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000594() -> None:
    """language='el' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000595() -> None:
    """language='el' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000596() -> None:
    """language='el' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000597() -> None:
    """language='el' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000598() -> None:
    """language='el' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000599() -> None:
    """language='el' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000600() -> None:
    """language='el' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000601() -> None:
    """language='el' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000602() -> None:
    """language='el' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000603() -> None:
    """language='el' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000604() -> None:
    """language='el' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'el', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000605() -> None:
    """language='en' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000606() -> None:
    """language='en' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000607() -> None:
    """language='en' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000608() -> None:
    """language='en' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000609() -> None:
    """language='en' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000610() -> None:
    """language='en' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000611() -> None:
    """language='en' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000612() -> None:
    """language='en' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000613() -> None:
    """language='en' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000614() -> None:
    """language='en' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000615() -> None:
    """language='en' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000616() -> None:
    """language='en' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000617() -> None:
    """language='en' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000618() -> None:
    """language='en' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000619() -> None:
    """language='en' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000620() -> None:
    """language='en' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000621() -> None:
    """language='en' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000622() -> None:
    """language='en' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000623() -> None:
    """language='en' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000624() -> None:
    """language='en' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000625() -> None:
    """language='en' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000626() -> None:
    """language='en' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000627() -> None:
    """language='en' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000628() -> None:
    """language='en' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000629() -> None:
    """language='en' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000630() -> None:
    """language='en' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000631() -> None:
    """language='en' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000632() -> None:
    """language='en' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000633() -> None:
    """language='en' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000634() -> None:
    """language='en' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000635() -> None:
    """language='en' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000636() -> None:
    """language='en' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000637() -> None:
    """language='en' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000638() -> None:
    """language='en' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000639() -> None:
    """language='en' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000640() -> None:
    """language='en' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000641() -> None:
    """language='en' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000642() -> None:
    """language='en' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000643() -> None:
    """language='en' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000644() -> None:
    """language='en' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000645() -> None:
    """language='en' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000646() -> None:
    """language='en' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000647() -> None:
    """language='en' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000648() -> None:
    """language='en' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000649() -> None:
    """language='en' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000650() -> None:
    """language='en' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000651() -> None:
    """language='en' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000652() -> None:
    """language='en' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000653() -> None:
    """language='en' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000654() -> None:
    """language='en' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000655() -> None:
    """language='en' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000656() -> None:
    """language='en' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000657() -> None:
    """language='en' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000658() -> None:
    """language='en' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000659() -> None:
    """language='en' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000660() -> None:
    """language='en' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000661() -> None:
    """language='en' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000662() -> None:
    """language='en' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000663() -> None:
    """language='en' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000664() -> None:
    """language='en' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000665() -> None:
    """language='en' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000666() -> None:
    """language='en' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000667() -> None:
    """language='en' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000668() -> None:
    """language='en' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000669() -> None:
    """language='en' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000670() -> None:
    """language='en' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000671() -> None:
    """language='en' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000672() -> None:
    """language='en' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000673() -> None:
    """language='en' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000674() -> None:
    """language='en' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000675() -> None:
    """language='en' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000676() -> None:
    """language='en' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000677() -> None:
    """language='en' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000678() -> None:
    """language='en' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000679() -> None:
    """language='en' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000680() -> None:
    """language='en' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000681() -> None:
    """language='en' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000682() -> None:
    """language='en' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000683() -> None:
    """language='en' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000684() -> None:
    """language='en' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000685() -> None:
    """language='en' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000686() -> None:
    """language='en' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000687() -> None:
    """language='en' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000688() -> None:
    """language='en' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000689() -> None:
    """language='en' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000690() -> None:
    """language='en' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000691() -> None:
    """language='en' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000692() -> None:
    """language='en' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000693() -> None:
    """language='en' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000694() -> None:
    """language='en' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000695() -> None:
    """language='en' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000696() -> None:
    """language='en' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000697() -> None:
    """language='en' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000698() -> None:
    """language='en' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000699() -> None:
    """language='en' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000700() -> None:
    """language='en' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000701() -> None:
    """language='en' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000702() -> None:
    """language='en' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000703() -> None:
    """language='en' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000704() -> None:
    """language='en' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000705() -> None:
    """language='en' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000706() -> None:
    """language='en' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000707() -> None:
    """language='en' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000708() -> None:
    """language='en' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000709() -> None:
    """language='en' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000710() -> None:
    """language='en' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000711() -> None:
    """language='en' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000712() -> None:
    """language='en' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000713() -> None:
    """language='en' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000714() -> None:
    """language='en' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000715() -> None:
    """language='en' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000716() -> None:
    """language='en' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000717() -> None:
    """language='en' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000718() -> None:
    """language='en' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000719() -> None:
    """language='en' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000720() -> None:
    """language='en' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000721() -> None:
    """language='en' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000722() -> None:
    """language='en' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000723() -> None:
    """language='en' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000724() -> None:
    """language='en' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000725() -> None:
    """language='en' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000726() -> None:
    """language='es' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000727() -> None:
    """language='es' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000728() -> None:
    """language='es' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000729() -> None:
    """language='es' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000730() -> None:
    """language='es' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000731() -> None:
    """language='es' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000732() -> None:
    """language='es' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000733() -> None:
    """language='es' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000734() -> None:
    """language='es' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000735() -> None:
    """language='es' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000736() -> None:
    """language='es' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000737() -> None:
    """language='es' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000738() -> None:
    """language='es' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000739() -> None:
    """language='es' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000740() -> None:
    """language='es' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000741() -> None:
    """language='es' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000742() -> None:
    """language='es' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000743() -> None:
    """language='es' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000744() -> None:
    """language='es' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000745() -> None:
    """language='es' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000746() -> None:
    """language='es' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000747() -> None:
    """language='es' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000748() -> None:
    """language='es' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000749() -> None:
    """language='es' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000750() -> None:
    """language='es' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000751() -> None:
    """language='es' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000752() -> None:
    """language='es' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000753() -> None:
    """language='es' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000754() -> None:
    """language='es' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000755() -> None:
    """language='es' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000756() -> None:
    """language='es' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000757() -> None:
    """language='es' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000758() -> None:
    """language='es' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000759() -> None:
    """language='es' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000760() -> None:
    """language='es' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000761() -> None:
    """language='es' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000762() -> None:
    """language='es' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000763() -> None:
    """language='es' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000764() -> None:
    """language='es' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000765() -> None:
    """language='es' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000766() -> None:
    """language='es' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000767() -> None:
    """language='es' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000768() -> None:
    """language='es' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000769() -> None:
    """language='es' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000770() -> None:
    """language='es' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000771() -> None:
    """language='es' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000772() -> None:
    """language='es' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000773() -> None:
    """language='es' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000774() -> None:
    """language='es' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000775() -> None:
    """language='es' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000776() -> None:
    """language='es' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000777() -> None:
    """language='es' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000778() -> None:
    """language='es' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000779() -> None:
    """language='es' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000780() -> None:
    """language='es' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000781() -> None:
    """language='es' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000782() -> None:
    """language='es' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000783() -> None:
    """language='es' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000784() -> None:
    """language='es' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000785() -> None:
    """language='es' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000786() -> None:
    """language='es' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000787() -> None:
    """language='es' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000788() -> None:
    """language='es' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000789() -> None:
    """language='es' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000790() -> None:
    """language='es' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000791() -> None:
    """language='es' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000792() -> None:
    """language='es' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000793() -> None:
    """language='es' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000794() -> None:
    """language='es' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000795() -> None:
    """language='es' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000796() -> None:
    """language='es' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000797() -> None:
    """language='es' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000798() -> None:
    """language='es' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000799() -> None:
    """language='es' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000800() -> None:
    """language='es' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000801() -> None:
    """language='es' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000802() -> None:
    """language='es' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000803() -> None:
    """language='es' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000804() -> None:
    """language='es' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000805() -> None:
    """language='es' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000806() -> None:
    """language='es' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000807() -> None:
    """language='es' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000808() -> None:
    """language='es' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000809() -> None:
    """language='es' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000810() -> None:
    """language='es' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000811() -> None:
    """language='es' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000812() -> None:
    """language='es' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000813() -> None:
    """language='es' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000814() -> None:
    """language='es' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000815() -> None:
    """language='es' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000816() -> None:
    """language='es' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000817() -> None:
    """language='es' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000818() -> None:
    """language='es' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000819() -> None:
    """language='es' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000820() -> None:
    """language='es' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000821() -> None:
    """language='es' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000822() -> None:
    """language='es' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000823() -> None:
    """language='es' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000824() -> None:
    """language='es' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000825() -> None:
    """language='es' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000826() -> None:
    """language='es' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000827() -> None:
    """language='es' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000828() -> None:
    """language='es' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000829() -> None:
    """language='es' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000830() -> None:
    """language='es' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000831() -> None:
    """language='es' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000832() -> None:
    """language='es' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000833() -> None:
    """language='es' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000834() -> None:
    """language='es' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000835() -> None:
    """language='es' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000836() -> None:
    """language='es' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000837() -> None:
    """language='es' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000838() -> None:
    """language='es' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000839() -> None:
    """language='es' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000840() -> None:
    """language='es' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000841() -> None:
    """language='es' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000842() -> None:
    """language='es' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000843() -> None:
    """language='es' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000844() -> None:
    """language='es' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000845() -> None:
    """language='es' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000846() -> None:
    """language='es' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000847() -> None:
    """language='et' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000848() -> None:
    """language='et' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000849() -> None:
    """language='et' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000850() -> None:
    """language='et' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000851() -> None:
    """language='et' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000852() -> None:
    """language='et' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000853() -> None:
    """language='et' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000854() -> None:
    """language='et' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000855() -> None:
    """language='et' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000856() -> None:
    """language='et' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000857() -> None:
    """language='et' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000858() -> None:
    """language='et' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000859() -> None:
    """language='et' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000860() -> None:
    """language='et' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000861() -> None:
    """language='et' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000862() -> None:
    """language='et' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000863() -> None:
    """language='et' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000864() -> None:
    """language='et' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000865() -> None:
    """language='et' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000866() -> None:
    """language='et' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000867() -> None:
    """language='et' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000868() -> None:
    """language='et' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000869() -> None:
    """language='et' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000870() -> None:
    """language='et' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000871() -> None:
    """language='et' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000872() -> None:
    """language='et' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000873() -> None:
    """language='et' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000874() -> None:
    """language='et' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000875() -> None:
    """language='et' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000876() -> None:
    """language='et' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000877() -> None:
    """language='et' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000878() -> None:
    """language='et' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c000879() -> None:
    """language='et' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c000880() -> None:
    """language='et' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c000881() -> None:
    """language='et' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c000882() -> None:
    """language='et' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c000883() -> None:
    """language='et' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c000884() -> None:
    """language='et' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c000885() -> None:
    """language='et' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c000886() -> None:
    """language='et' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c000887() -> None:
    """language='et' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c000888() -> None:
    """language='et' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c000889() -> None:
    """language='et' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c000890() -> None:
    """language='et' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c000891() -> None:
    """language='et' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c000892() -> None:
    """language='et' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c000893() -> None:
    """language='et' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c000894() -> None:
    """language='et' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c000895() -> None:
    """language='et' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c000896() -> None:
    """language='et' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c000897() -> None:
    """language='et' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c000898() -> None:
    """language='et' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c000899() -> None:
    """language='et' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c000900() -> None:
    """language='et' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c000901() -> None:
    """language='et' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c000902() -> None:
    """language='et' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c000903() -> None:
    """language='et' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c000904() -> None:
    """language='et' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c000905() -> None:
    """language='et' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c000906() -> None:
    """language='et' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c000907() -> None:
    """language='et' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c000908() -> None:
    """language='et' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c000909() -> None:
    """language='et' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c000910() -> None:
    """language='et' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c000911() -> None:
    """language='et' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c000912() -> None:
    """language='et' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c000913() -> None:
    """language='et' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c000914() -> None:
    """language='et' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c000915() -> None:
    """language='et' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c000916() -> None:
    """language='et' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c000917() -> None:
    """language='et' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c000918() -> None:
    """language='et' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c000919() -> None:
    """language='et' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c000920() -> None:
    """language='et' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c000921() -> None:
    """language='et' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c000922() -> None:
    """language='et' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c000923() -> None:
    """language='et' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c000924() -> None:
    """language='et' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c000925() -> None:
    """language='et' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c000926() -> None:
    """language='et' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c000927() -> None:
    """language='et' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c000928() -> None:
    """language='et' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c000929() -> None:
    """language='et' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c000930() -> None:
    """language='et' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c000931() -> None:
    """language='et' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c000932() -> None:
    """language='et' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c000933() -> None:
    """language='et' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c000934() -> None:
    """language='et' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c000935() -> None:
    """language='et' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c000936() -> None:
    """language='et' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c000937() -> None:
    """language='et' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c000938() -> None:
    """language='et' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c000939() -> None:
    """language='et' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c000940() -> None:
    """language='et' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c000941() -> None:
    """language='et' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c000942() -> None:
    """language='et' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c000943() -> None:
    """language='et' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c000944() -> None:
    """language='et' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c000945() -> None:
    """language='et' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c000946() -> None:
    """language='et' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c000947() -> None:
    """language='et' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c000948() -> None:
    """language='et' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c000949() -> None:
    """language='et' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c000950() -> None:
    """language='et' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c000951() -> None:
    """language='et' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c000952() -> None:
    """language='et' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c000953() -> None:
    """language='et' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c000954() -> None:
    """language='et' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c000955() -> None:
    """language='et' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c000956() -> None:
    """language='et' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c000957() -> None:
    """language='et' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c000958() -> None:
    """language='et' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c000959() -> None:
    """language='et' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c000960() -> None:
    """language='et' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c000961() -> None:
    """language='et' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c000962() -> None:
    """language='et' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c000963() -> None:
    """language='et' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c000964() -> None:
    """language='et' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c000965() -> None:
    """language='et' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c000966() -> None:
    """language='et' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c000967() -> None:
    """language='et' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'et', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c000968() -> None:
    """language='fi' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c000969() -> None:
    """language='fi' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c000970() -> None:
    """language='fi' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c000971() -> None:
    """language='fi' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c000972() -> None:
    """language='fi' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c000973() -> None:
    """language='fi' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c000974() -> None:
    """language='fi' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c000975() -> None:
    """language='fi' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c000976() -> None:
    """language='fi' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c000977() -> None:
    """language='fi' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c000978() -> None:
    """language='fi' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c000979() -> None:
    """language='fi' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c000980() -> None:
    """language='fi' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c000981() -> None:
    """language='fi' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c000982() -> None:
    """language='fi' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c000983() -> None:
    """language='fi' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c000984() -> None:
    """language='fi' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c000985() -> None:
    """language='fi' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c000986() -> None:
    """language='fi' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c000987() -> None:
    """language='fi' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c000988() -> None:
    """language='fi' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c000989() -> None:
    """language='fi' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c000990() -> None:
    """language='fi' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c000991() -> None:
    """language='fi' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c000992() -> None:
    """language='fi' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c000993() -> None:
    """language='fi' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c000994() -> None:
    """language='fi' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c000995() -> None:
    """language='fi' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c000996() -> None:
    """language='fi' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c000997() -> None:
    """language='fi' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c000998() -> None:
    """language='fi' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c000999() -> None:
    """language='fi' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001000() -> None:
    """language='fi' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001001() -> None:
    """language='fi' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001002() -> None:
    """language='fi' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001003() -> None:
    """language='fi' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001004() -> None:
    """language='fi' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001005() -> None:
    """language='fi' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001006() -> None:
    """language='fi' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001007() -> None:
    """language='fi' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001008() -> None:
    """language='fi' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001009() -> None:
    """language='fi' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001010() -> None:
    """language='fi' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001011() -> None:
    """language='fi' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001012() -> None:
    """language='fi' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001013() -> None:
    """language='fi' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001014() -> None:
    """language='fi' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001015() -> None:
    """language='fi' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001016() -> None:
    """language='fi' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001017() -> None:
    """language='fi' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001018() -> None:
    """language='fi' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001019() -> None:
    """language='fi' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001020() -> None:
    """language='fi' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001021() -> None:
    """language='fi' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001022() -> None:
    """language='fi' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001023() -> None:
    """language='fi' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001024() -> None:
    """language='fi' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001025() -> None:
    """language='fi' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001026() -> None:
    """language='fi' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001027() -> None:
    """language='fi' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001028() -> None:
    """language='fi' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001029() -> None:
    """language='fi' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001030() -> None:
    """language='fi' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001031() -> None:
    """language='fi' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001032() -> None:
    """language='fi' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001033() -> None:
    """language='fi' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001034() -> None:
    """language='fi' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001035() -> None:
    """language='fi' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001036() -> None:
    """language='fi' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001037() -> None:
    """language='fi' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001038() -> None:
    """language='fi' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001039() -> None:
    """language='fi' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001040() -> None:
    """language='fi' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001041() -> None:
    """language='fi' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001042() -> None:
    """language='fi' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001043() -> None:
    """language='fi' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001044() -> None:
    """language='fi' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001045() -> None:
    """language='fi' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001046() -> None:
    """language='fi' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001047() -> None:
    """language='fi' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001048() -> None:
    """language='fi' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001049() -> None:
    """language='fi' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001050() -> None:
    """language='fi' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001051() -> None:
    """language='fi' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001052() -> None:
    """language='fi' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001053() -> None:
    """language='fi' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001054() -> None:
    """language='fi' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001055() -> None:
    """language='fi' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001056() -> None:
    """language='fi' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001057() -> None:
    """language='fi' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001058() -> None:
    """language='fi' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001059() -> None:
    """language='fi' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001060() -> None:
    """language='fi' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001061() -> None:
    """language='fi' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001062() -> None:
    """language='fi' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001063() -> None:
    """language='fi' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001064() -> None:
    """language='fi' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001065() -> None:
    """language='fi' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001066() -> None:
    """language='fi' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001067() -> None:
    """language='fi' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001068() -> None:
    """language='fi' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001069() -> None:
    """language='fi' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001070() -> None:
    """language='fi' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001071() -> None:
    """language='fi' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001072() -> None:
    """language='fi' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001073() -> None:
    """language='fi' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001074() -> None:
    """language='fi' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001075() -> None:
    """language='fi' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001076() -> None:
    """language='fi' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001077() -> None:
    """language='fi' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001078() -> None:
    """language='fi' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001079() -> None:
    """language='fi' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001080() -> None:
    """language='fi' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001081() -> None:
    """language='fi' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001082() -> None:
    """language='fi' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001083() -> None:
    """language='fi' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001084() -> None:
    """language='fi' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001085() -> None:
    """language='fi' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001086() -> None:
    """language='fi' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001087() -> None:
    """language='fi' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001088() -> None:
    """language='fi' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fi', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001089() -> None:
    """language='fr' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001090() -> None:
    """language='fr' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001091() -> None:
    """language='fr' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001092() -> None:
    """language='fr' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001093() -> None:
    """language='fr' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001094() -> None:
    """language='fr' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001095() -> None:
    """language='fr' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001096() -> None:
    """language='fr' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001097() -> None:
    """language='fr' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001098() -> None:
    """language='fr' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001099() -> None:
    """language='fr' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001100() -> None:
    """language='fr' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001101() -> None:
    """language='fr' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001102() -> None:
    """language='fr' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001103() -> None:
    """language='fr' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001104() -> None:
    """language='fr' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001105() -> None:
    """language='fr' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001106() -> None:
    """language='fr' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001107() -> None:
    """language='fr' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001108() -> None:
    """language='fr' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001109() -> None:
    """language='fr' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001110() -> None:
    """language='fr' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001111() -> None:
    """language='fr' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001112() -> None:
    """language='fr' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001113() -> None:
    """language='fr' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001114() -> None:
    """language='fr' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001115() -> None:
    """language='fr' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001116() -> None:
    """language='fr' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001117() -> None:
    """language='fr' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001118() -> None:
    """language='fr' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001119() -> None:
    """language='fr' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001120() -> None:
    """language='fr' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001121() -> None:
    """language='fr' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001122() -> None:
    """language='fr' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001123() -> None:
    """language='fr' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001124() -> None:
    """language='fr' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001125() -> None:
    """language='fr' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001126() -> None:
    """language='fr' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001127() -> None:
    """language='fr' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001128() -> None:
    """language='fr' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001129() -> None:
    """language='fr' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001130() -> None:
    """language='fr' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001131() -> None:
    """language='fr' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001132() -> None:
    """language='fr' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001133() -> None:
    """language='fr' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001134() -> None:
    """language='fr' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001135() -> None:
    """language='fr' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001136() -> None:
    """language='fr' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001137() -> None:
    """language='fr' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001138() -> None:
    """language='fr' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001139() -> None:
    """language='fr' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001140() -> None:
    """language='fr' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001141() -> None:
    """language='fr' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001142() -> None:
    """language='fr' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001143() -> None:
    """language='fr' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001144() -> None:
    """language='fr' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001145() -> None:
    """language='fr' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001146() -> None:
    """language='fr' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001147() -> None:
    """language='fr' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001148() -> None:
    """language='fr' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001149() -> None:
    """language='fr' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001150() -> None:
    """language='fr' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001151() -> None:
    """language='fr' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001152() -> None:
    """language='fr' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001153() -> None:
    """language='fr' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001154() -> None:
    """language='fr' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001155() -> None:
    """language='fr' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001156() -> None:
    """language='fr' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001157() -> None:
    """language='fr' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001158() -> None:
    """language='fr' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001159() -> None:
    """language='fr' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001160() -> None:
    """language='fr' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001161() -> None:
    """language='fr' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001162() -> None:
    """language='fr' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001163() -> None:
    """language='fr' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001164() -> None:
    """language='fr' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001165() -> None:
    """language='fr' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001166() -> None:
    """language='fr' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001167() -> None:
    """language='fr' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001168() -> None:
    """language='fr' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001169() -> None:
    """language='fr' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001170() -> None:
    """language='fr' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001171() -> None:
    """language='fr' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001172() -> None:
    """language='fr' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001173() -> None:
    """language='fr' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001174() -> None:
    """language='fr' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001175() -> None:
    """language='fr' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001176() -> None:
    """language='fr' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001177() -> None:
    """language='fr' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001178() -> None:
    """language='fr' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001179() -> None:
    """language='fr' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001180() -> None:
    """language='fr' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001181() -> None:
    """language='fr' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001182() -> None:
    """language='fr' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001183() -> None:
    """language='fr' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001184() -> None:
    """language='fr' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001185() -> None:
    """language='fr' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001186() -> None:
    """language='fr' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001187() -> None:
    """language='fr' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001188() -> None:
    """language='fr' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001189() -> None:
    """language='fr' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001190() -> None:
    """language='fr' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001191() -> None:
    """language='fr' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001192() -> None:
    """language='fr' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001193() -> None:
    """language='fr' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001194() -> None:
    """language='fr' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001195() -> None:
    """language='fr' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001196() -> None:
    """language='fr' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001197() -> None:
    """language='fr' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001198() -> None:
    """language='fr' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001199() -> None:
    """language='fr' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001200() -> None:
    """language='fr' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001201() -> None:
    """language='fr' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001202() -> None:
    """language='fr' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001203() -> None:
    """language='fr' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001204() -> None:
    """language='fr' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001205() -> None:
    """language='fr' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001206() -> None:
    """language='fr' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001207() -> None:
    """language='fr' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001208() -> None:
    """language='fr' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001209() -> None:
    """language='fr' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001210() -> None:
    """language='hr' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001211() -> None:
    """language='hr' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001212() -> None:
    """language='hr' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001213() -> None:
    """language='hr' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001214() -> None:
    """language='hr' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001215() -> None:
    """language='hr' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001216() -> None:
    """language='hr' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001217() -> None:
    """language='hr' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001218() -> None:
    """language='hr' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001219() -> None:
    """language='hr' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001220() -> None:
    """language='hr' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001221() -> None:
    """language='hr' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001222() -> None:
    """language='hr' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001223() -> None:
    """language='hr' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001224() -> None:
    """language='hr' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001225() -> None:
    """language='hr' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001226() -> None:
    """language='hr' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001227() -> None:
    """language='hr' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001228() -> None:
    """language='hr' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001229() -> None:
    """language='hr' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001230() -> None:
    """language='hr' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001231() -> None:
    """language='hr' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001232() -> None:
    """language='hr' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001233() -> None:
    """language='hr' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001234() -> None:
    """language='hr' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001235() -> None:
    """language='hr' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001236() -> None:
    """language='hr' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001237() -> None:
    """language='hr' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001238() -> None:
    """language='hr' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001239() -> None:
    """language='hr' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001240() -> None:
    """language='hr' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001241() -> None:
    """language='hr' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001242() -> None:
    """language='hr' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001243() -> None:
    """language='hr' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001244() -> None:
    """language='hr' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001245() -> None:
    """language='hr' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001246() -> None:
    """language='hr' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001247() -> None:
    """language='hr' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001248() -> None:
    """language='hr' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001249() -> None:
    """language='hr' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001250() -> None:
    """language='hr' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001251() -> None:
    """language='hr' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001252() -> None:
    """language='hr' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001253() -> None:
    """language='hr' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001254() -> None:
    """language='hr' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001255() -> None:
    """language='hr' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001256() -> None:
    """language='hr' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001257() -> None:
    """language='hr' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001258() -> None:
    """language='hr' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001259() -> None:
    """language='hr' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001260() -> None:
    """language='hr' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001261() -> None:
    """language='hr' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001262() -> None:
    """language='hr' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001263() -> None:
    """language='hr' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001264() -> None:
    """language='hr' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001265() -> None:
    """language='hr' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001266() -> None:
    """language='hr' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001267() -> None:
    """language='hr' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001268() -> None:
    """language='hr' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001269() -> None:
    """language='hr' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001270() -> None:
    """language='hr' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001271() -> None:
    """language='hr' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001272() -> None:
    """language='hr' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001273() -> None:
    """language='hr' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001274() -> None:
    """language='hr' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001275() -> None:
    """language='hr' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001276() -> None:
    """language='hr' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001277() -> None:
    """language='hr' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001278() -> None:
    """language='hr' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001279() -> None:
    """language='hr' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001280() -> None:
    """language='hr' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001281() -> None:
    """language='hr' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001282() -> None:
    """language='hr' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001283() -> None:
    """language='hr' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001284() -> None:
    """language='hr' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001285() -> None:
    """language='hr' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001286() -> None:
    """language='hr' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001287() -> None:
    """language='hr' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001288() -> None:
    """language='hr' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001289() -> None:
    """language='hr' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001290() -> None:
    """language='hr' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001291() -> None:
    """language='hr' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001292() -> None:
    """language='hr' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001293() -> None:
    """language='hr' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001294() -> None:
    """language='hr' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001295() -> None:
    """language='hr' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001296() -> None:
    """language='hr' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001297() -> None:
    """language='hr' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001298() -> None:
    """language='hr' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001299() -> None:
    """language='hr' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001300() -> None:
    """language='hr' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001301() -> None:
    """language='hr' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001302() -> None:
    """language='hr' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001303() -> None:
    """language='hr' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001304() -> None:
    """language='hr' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001305() -> None:
    """language='hr' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001306() -> None:
    """language='hr' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001307() -> None:
    """language='hr' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001308() -> None:
    """language='hr' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001309() -> None:
    """language='hr' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001310() -> None:
    """language='hr' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001311() -> None:
    """language='hr' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001312() -> None:
    """language='hr' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001313() -> None:
    """language='hr' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001314() -> None:
    """language='hr' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001315() -> None:
    """language='hr' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001316() -> None:
    """language='hr' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001317() -> None:
    """language='hr' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001318() -> None:
    """language='hr' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001319() -> None:
    """language='hr' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001320() -> None:
    """language='hr' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001321() -> None:
    """language='hr' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001322() -> None:
    """language='hr' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001323() -> None:
    """language='hr' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001324() -> None:
    """language='hr' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001325() -> None:
    """language='hr' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001326() -> None:
    """language='hr' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001327() -> None:
    """language='hr' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001328() -> None:
    """language='hr' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001329() -> None:
    """language='hr' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001330() -> None:
    """language='hr' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hr', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001331() -> None:
    """language='hu' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001332() -> None:
    """language='hu' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001333() -> None:
    """language='hu' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001334() -> None:
    """language='hu' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001335() -> None:
    """language='hu' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001336() -> None:
    """language='hu' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001337() -> None:
    """language='hu' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001338() -> None:
    """language='hu' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001339() -> None:
    """language='hu' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001340() -> None:
    """language='hu' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001341() -> None:
    """language='hu' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001342() -> None:
    """language='hu' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001343() -> None:
    """language='hu' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001344() -> None:
    """language='hu' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001345() -> None:
    """language='hu' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001346() -> None:
    """language='hu' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001347() -> None:
    """language='hu' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001348() -> None:
    """language='hu' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001349() -> None:
    """language='hu' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001350() -> None:
    """language='hu' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001351() -> None:
    """language='hu' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001352() -> None:
    """language='hu' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001353() -> None:
    """language='hu' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001354() -> None:
    """language='hu' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001355() -> None:
    """language='hu' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001356() -> None:
    """language='hu' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001357() -> None:
    """language='hu' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001358() -> None:
    """language='hu' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001359() -> None:
    """language='hu' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001360() -> None:
    """language='hu' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001361() -> None:
    """language='hu' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001362() -> None:
    """language='hu' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001363() -> None:
    """language='hu' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001364() -> None:
    """language='hu' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001365() -> None:
    """language='hu' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001366() -> None:
    """language='hu' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001367() -> None:
    """language='hu' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001368() -> None:
    """language='hu' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001369() -> None:
    """language='hu' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001370() -> None:
    """language='hu' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001371() -> None:
    """language='hu' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001372() -> None:
    """language='hu' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001373() -> None:
    """language='hu' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001374() -> None:
    """language='hu' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001375() -> None:
    """language='hu' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001376() -> None:
    """language='hu' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001377() -> None:
    """language='hu' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001378() -> None:
    """language='hu' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001379() -> None:
    """language='hu' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001380() -> None:
    """language='hu' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001381() -> None:
    """language='hu' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001382() -> None:
    """language='hu' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001383() -> None:
    """language='hu' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001384() -> None:
    """language='hu' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001385() -> None:
    """language='hu' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001386() -> None:
    """language='hu' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001387() -> None:
    """language='hu' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001388() -> None:
    """language='hu' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001389() -> None:
    """language='hu' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001390() -> None:
    """language='hu' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001391() -> None:
    """language='hu' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001392() -> None:
    """language='hu' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001393() -> None:
    """language='hu' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001394() -> None:
    """language='hu' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001395() -> None:
    """language='hu' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001396() -> None:
    """language='hu' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001397() -> None:
    """language='hu' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001398() -> None:
    """language='hu' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001399() -> None:
    """language='hu' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001400() -> None:
    """language='hu' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001401() -> None:
    """language='hu' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001402() -> None:
    """language='hu' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001403() -> None:
    """language='hu' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001404() -> None:
    """language='hu' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001405() -> None:
    """language='hu' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001406() -> None:
    """language='hu' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001407() -> None:
    """language='hu' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001408() -> None:
    """language='hu' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001409() -> None:
    """language='hu' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001410() -> None:
    """language='hu' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001411() -> None:
    """language='hu' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001412() -> None:
    """language='hu' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001413() -> None:
    """language='hu' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001414() -> None:
    """language='hu' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001415() -> None:
    """language='hu' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001416() -> None:
    """language='hu' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001417() -> None:
    """language='hu' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001418() -> None:
    """language='hu' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001419() -> None:
    """language='hu' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001420() -> None:
    """language='hu' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001421() -> None:
    """language='hu' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001422() -> None:
    """language='hu' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001423() -> None:
    """language='hu' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001424() -> None:
    """language='hu' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001425() -> None:
    """language='hu' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001426() -> None:
    """language='hu' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001427() -> None:
    """language='hu' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001428() -> None:
    """language='hu' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001429() -> None:
    """language='hu' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001430() -> None:
    """language='hu' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001431() -> None:
    """language='hu' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001432() -> None:
    """language='hu' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001433() -> None:
    """language='hu' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001434() -> None:
    """language='hu' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001435() -> None:
    """language='hu' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001436() -> None:
    """language='hu' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001437() -> None:
    """language='hu' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001438() -> None:
    """language='hu' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001439() -> None:
    """language='hu' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001440() -> None:
    """language='hu' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001441() -> None:
    """language='hu' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001442() -> None:
    """language='hu' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001443() -> None:
    """language='hu' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001444() -> None:
    """language='hu' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001445() -> None:
    """language='hu' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001446() -> None:
    """language='hu' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001447() -> None:
    """language='hu' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001448() -> None:
    """language='hu' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001449() -> None:
    """language='hu' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001450() -> None:
    """language='hu' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001451() -> None:
    """language='hu' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hu', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001452() -> None:
    """language='it' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001453() -> None:
    """language='it' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001454() -> None:
    """language='it' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001455() -> None:
    """language='it' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001456() -> None:
    """language='it' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001457() -> None:
    """language='it' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001458() -> None:
    """language='it' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001459() -> None:
    """language='it' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001460() -> None:
    """language='it' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001461() -> None:
    """language='it' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001462() -> None:
    """language='it' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001463() -> None:
    """language='it' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001464() -> None:
    """language='it' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001465() -> None:
    """language='it' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001466() -> None:
    """language='it' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001467() -> None:
    """language='it' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001468() -> None:
    """language='it' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001469() -> None:
    """language='it' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001470() -> None:
    """language='it' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001471() -> None:
    """language='it' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001472() -> None:
    """language='it' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001473() -> None:
    """language='it' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001474() -> None:
    """language='it' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001475() -> None:
    """language='it' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001476() -> None:
    """language='it' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001477() -> None:
    """language='it' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001478() -> None:
    """language='it' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001479() -> None:
    """language='it' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001480() -> None:
    """language='it' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001481() -> None:
    """language='it' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001482() -> None:
    """language='it' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001483() -> None:
    """language='it' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001484() -> None:
    """language='it' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001485() -> None:
    """language='it' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001486() -> None:
    """language='it' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001487() -> None:
    """language='it' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001488() -> None:
    """language='it' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001489() -> None:
    """language='it' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001490() -> None:
    """language='it' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001491() -> None:
    """language='it' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001492() -> None:
    """language='it' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001493() -> None:
    """language='it' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001494() -> None:
    """language='it' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001495() -> None:
    """language='it' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001496() -> None:
    """language='it' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001497() -> None:
    """language='it' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001498() -> None:
    """language='it' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001499() -> None:
    """language='it' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001500() -> None:
    """language='it' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001501() -> None:
    """language='it' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001502() -> None:
    """language='it' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001503() -> None:
    """language='it' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001504() -> None:
    """language='it' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001505() -> None:
    """language='it' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001506() -> None:
    """language='it' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001507() -> None:
    """language='it' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001508() -> None:
    """language='it' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001509() -> None:
    """language='it' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001510() -> None:
    """language='it' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001511() -> None:
    """language='it' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001512() -> None:
    """language='it' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001513() -> None:
    """language='it' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001514() -> None:
    """language='it' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001515() -> None:
    """language='it' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001516() -> None:
    """language='it' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001517() -> None:
    """language='it' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001518() -> None:
    """language='it' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001519() -> None:
    """language='it' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001520() -> None:
    """language='it' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001521() -> None:
    """language='it' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001522() -> None:
    """language='it' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001523() -> None:
    """language='it' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001524() -> None:
    """language='it' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001525() -> None:
    """language='it' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001526() -> None:
    """language='it' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001527() -> None:
    """language='it' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001528() -> None:
    """language='it' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001529() -> None:
    """language='it' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001530() -> None:
    """language='it' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001531() -> None:
    """language='it' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001532() -> None:
    """language='it' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001533() -> None:
    """language='it' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001534() -> None:
    """language='it' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001535() -> None:
    """language='it' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001536() -> None:
    """language='it' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001537() -> None:
    """language='it' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001538() -> None:
    """language='it' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001539() -> None:
    """language='it' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001540() -> None:
    """language='it' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001541() -> None:
    """language='it' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001542() -> None:
    """language='it' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001543() -> None:
    """language='it' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001544() -> None:
    """language='it' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001545() -> None:
    """language='it' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001546() -> None:
    """language='it' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001547() -> None:
    """language='it' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001548() -> None:
    """language='it' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001549() -> None:
    """language='it' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001550() -> None:
    """language='it' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001551() -> None:
    """language='it' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001552() -> None:
    """language='it' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001553() -> None:
    """language='it' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001554() -> None:
    """language='it' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001555() -> None:
    """language='it' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001556() -> None:
    """language='it' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001557() -> None:
    """language='it' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001558() -> None:
    """language='it' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001559() -> None:
    """language='it' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001560() -> None:
    """language='it' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001561() -> None:
    """language='it' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001562() -> None:
    """language='it' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001563() -> None:
    """language='it' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001564() -> None:
    """language='it' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001565() -> None:
    """language='it' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001566() -> None:
    """language='it' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001567() -> None:
    """language='it' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001568() -> None:
    """language='it' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001569() -> None:
    """language='it' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001570() -> None:
    """language='it' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001571() -> None:
    """language='it' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001572() -> None:
    """language='it' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'it', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001573() -> None:
    """language='lt' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001574() -> None:
    """language='lt' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001575() -> None:
    """language='lt' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001576() -> None:
    """language='lt' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001577() -> None:
    """language='lt' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001578() -> None:
    """language='lt' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001579() -> None:
    """language='lt' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001580() -> None:
    """language='lt' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001581() -> None:
    """language='lt' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001582() -> None:
    """language='lt' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001583() -> None:
    """language='lt' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001584() -> None:
    """language='lt' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001585() -> None:
    """language='lt' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001586() -> None:
    """language='lt' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001587() -> None:
    """language='lt' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001588() -> None:
    """language='lt' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001589() -> None:
    """language='lt' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001590() -> None:
    """language='lt' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001591() -> None:
    """language='lt' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001592() -> None:
    """language='lt' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001593() -> None:
    """language='lt' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001594() -> None:
    """language='lt' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001595() -> None:
    """language='lt' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001596() -> None:
    """language='lt' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001597() -> None:
    """language='lt' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001598() -> None:
    """language='lt' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001599() -> None:
    """language='lt' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001600() -> None:
    """language='lt' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001601() -> None:
    """language='lt' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001602() -> None:
    """language='lt' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001603() -> None:
    """language='lt' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001604() -> None:
    """language='lt' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001605() -> None:
    """language='lt' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001606() -> None:
    """language='lt' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001607() -> None:
    """language='lt' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001608() -> None:
    """language='lt' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001609() -> None:
    """language='lt' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001610() -> None:
    """language='lt' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001611() -> None:
    """language='lt' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001612() -> None:
    """language='lt' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001613() -> None:
    """language='lt' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001614() -> None:
    """language='lt' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001615() -> None:
    """language='lt' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001616() -> None:
    """language='lt' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001617() -> None:
    """language='lt' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001618() -> None:
    """language='lt' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001619() -> None:
    """language='lt' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001620() -> None:
    """language='lt' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001621() -> None:
    """language='lt' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001622() -> None:
    """language='lt' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001623() -> None:
    """language='lt' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001624() -> None:
    """language='lt' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001625() -> None:
    """language='lt' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001626() -> None:
    """language='lt' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001627() -> None:
    """language='lt' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001628() -> None:
    """language='lt' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001629() -> None:
    """language='lt' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001630() -> None:
    """language='lt' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001631() -> None:
    """language='lt' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001632() -> None:
    """language='lt' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001633() -> None:
    """language='lt' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001634() -> None:
    """language='lt' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001635() -> None:
    """language='lt' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001636() -> None:
    """language='lt' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001637() -> None:
    """language='lt' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001638() -> None:
    """language='lt' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001639() -> None:
    """language='lt' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001640() -> None:
    """language='lt' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001641() -> None:
    """language='lt' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001642() -> None:
    """language='lt' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001643() -> None:
    """language='lt' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001644() -> None:
    """language='lt' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001645() -> None:
    """language='lt' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001646() -> None:
    """language='lt' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001647() -> None:
    """language='lt' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001648() -> None:
    """language='lt' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001649() -> None:
    """language='lt' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001650() -> None:
    """language='lt' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001651() -> None:
    """language='lt' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001652() -> None:
    """language='lt' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001653() -> None:
    """language='lt' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001654() -> None:
    """language='lt' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001655() -> None:
    """language='lt' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001656() -> None:
    """language='lt' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001657() -> None:
    """language='lt' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001658() -> None:
    """language='lt' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001659() -> None:
    """language='lt' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001660() -> None:
    """language='lt' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001661() -> None:
    """language='lt' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001662() -> None:
    """language='lt' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001663() -> None:
    """language='lt' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001664() -> None:
    """language='lt' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001665() -> None:
    """language='lt' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001666() -> None:
    """language='lt' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001667() -> None:
    """language='lt' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001668() -> None:
    """language='lt' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001669() -> None:
    """language='lt' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001670() -> None:
    """language='lt' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001671() -> None:
    """language='lt' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001672() -> None:
    """language='lt' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001673() -> None:
    """language='lt' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001674() -> None:
    """language='lt' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001675() -> None:
    """language='lt' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001676() -> None:
    """language='lt' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001677() -> None:
    """language='lt' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001678() -> None:
    """language='lt' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001679() -> None:
    """language='lt' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001680() -> None:
    """language='lt' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001681() -> None:
    """language='lt' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001682() -> None:
    """language='lt' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001683() -> None:
    """language='lt' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001684() -> None:
    """language='lt' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001685() -> None:
    """language='lt' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001686() -> None:
    """language='lt' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001687() -> None:
    """language='lt' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001688() -> None:
    """language='lt' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001689() -> None:
    """language='lt' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001690() -> None:
    """language='lt' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001691() -> None:
    """language='lt' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001692() -> None:
    """language='lt' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001693() -> None:
    """language='lt' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lt', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001694() -> None:
    """language='lv' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001695() -> None:
    """language='lv' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001696() -> None:
    """language='lv' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001697() -> None:
    """language='lv' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001698() -> None:
    """language='lv' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001699() -> None:
    """language='lv' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001700() -> None:
    """language='lv' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001701() -> None:
    """language='lv' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001702() -> None:
    """language='lv' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001703() -> None:
    """language='lv' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001704() -> None:
    """language='lv' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001705() -> None:
    """language='lv' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001706() -> None:
    """language='lv' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001707() -> None:
    """language='lv' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001708() -> None:
    """language='lv' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001709() -> None:
    """language='lv' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001710() -> None:
    """language='lv' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001711() -> None:
    """language='lv' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001712() -> None:
    """language='lv' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001713() -> None:
    """language='lv' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001714() -> None:
    """language='lv' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001715() -> None:
    """language='lv' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001716() -> None:
    """language='lv' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001717() -> None:
    """language='lv' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001718() -> None:
    """language='lv' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001719() -> None:
    """language='lv' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001720() -> None:
    """language='lv' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001721() -> None:
    """language='lv' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001722() -> None:
    """language='lv' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001723() -> None:
    """language='lv' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001724() -> None:
    """language='lv' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001725() -> None:
    """language='lv' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001726() -> None:
    """language='lv' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001727() -> None:
    """language='lv' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001728() -> None:
    """language='lv' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001729() -> None:
    """language='lv' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001730() -> None:
    """language='lv' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001731() -> None:
    """language='lv' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001732() -> None:
    """language='lv' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001733() -> None:
    """language='lv' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001734() -> None:
    """language='lv' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001735() -> None:
    """language='lv' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001736() -> None:
    """language='lv' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001737() -> None:
    """language='lv' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001738() -> None:
    """language='lv' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001739() -> None:
    """language='lv' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001740() -> None:
    """language='lv' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001741() -> None:
    """language='lv' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001742() -> None:
    """language='lv' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001743() -> None:
    """language='lv' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001744() -> None:
    """language='lv' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001745() -> None:
    """language='lv' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001746() -> None:
    """language='lv' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001747() -> None:
    """language='lv' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001748() -> None:
    """language='lv' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001749() -> None:
    """language='lv' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001750() -> None:
    """language='lv' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001751() -> None:
    """language='lv' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001752() -> None:
    """language='lv' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001753() -> None:
    """language='lv' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001754() -> None:
    """language='lv' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001755() -> None:
    """language='lv' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001756() -> None:
    """language='lv' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001757() -> None:
    """language='lv' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001758() -> None:
    """language='lv' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001759() -> None:
    """language='lv' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001760() -> None:
    """language='lv' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001761() -> None:
    """language='lv' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001762() -> None:
    """language='lv' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001763() -> None:
    """language='lv' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001764() -> None:
    """language='lv' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001765() -> None:
    """language='lv' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001766() -> None:
    """language='lv' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001767() -> None:
    """language='lv' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001768() -> None:
    """language='lv' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001769() -> None:
    """language='lv' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001770() -> None:
    """language='lv' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001771() -> None:
    """language='lv' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001772() -> None:
    """language='lv' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001773() -> None:
    """language='lv' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001774() -> None:
    """language='lv' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001775() -> None:
    """language='lv' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001776() -> None:
    """language='lv' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001777() -> None:
    """language='lv' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001778() -> None:
    """language='lv' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001779() -> None:
    """language='lv' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001780() -> None:
    """language='lv' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001781() -> None:
    """language='lv' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001782() -> None:
    """language='lv' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001783() -> None:
    """language='lv' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001784() -> None:
    """language='lv' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001785() -> None:
    """language='lv' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001786() -> None:
    """language='lv' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001787() -> None:
    """language='lv' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001788() -> None:
    """language='lv' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001789() -> None:
    """language='lv' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001790() -> None:
    """language='lv' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001791() -> None:
    """language='lv' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001792() -> None:
    """language='lv' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001793() -> None:
    """language='lv' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001794() -> None:
    """language='lv' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001795() -> None:
    """language='lv' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001796() -> None:
    """language='lv' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001797() -> None:
    """language='lv' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001798() -> None:
    """language='lv' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001799() -> None:
    """language='lv' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001800() -> None:
    """language='lv' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001801() -> None:
    """language='lv' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001802() -> None:
    """language='lv' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001803() -> None:
    """language='lv' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001804() -> None:
    """language='lv' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001805() -> None:
    """language='lv' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001806() -> None:
    """language='lv' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001807() -> None:
    """language='lv' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001808() -> None:
    """language='lv' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001809() -> None:
    """language='lv' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001810() -> None:
    """language='lv' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001811() -> None:
    """language='lv' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001812() -> None:
    """language='lv' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001813() -> None:
    """language='lv' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001814() -> None:
    """language='lv' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'lv', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001815() -> None:
    """language='mt' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001816() -> None:
    """language='mt' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001817() -> None:
    """language='mt' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001818() -> None:
    """language='mt' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001819() -> None:
    """language='mt' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001820() -> None:
    """language='mt' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001821() -> None:
    """language='mt' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001822() -> None:
    """language='mt' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001823() -> None:
    """language='mt' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001824() -> None:
    """language='mt' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001825() -> None:
    """language='mt' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001826() -> None:
    """language='mt' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001827() -> None:
    """language='mt' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001828() -> None:
    """language='mt' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001829() -> None:
    """language='mt' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001830() -> None:
    """language='mt' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001831() -> None:
    """language='mt' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001832() -> None:
    """language='mt' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001833() -> None:
    """language='mt' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001834() -> None:
    """language='mt' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001835() -> None:
    """language='mt' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001836() -> None:
    """language='mt' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001837() -> None:
    """language='mt' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001838() -> None:
    """language='mt' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001839() -> None:
    """language='mt' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001840() -> None:
    """language='mt' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001841() -> None:
    """language='mt' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001842() -> None:
    """language='mt' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001843() -> None:
    """language='mt' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001844() -> None:
    """language='mt' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001845() -> None:
    """language='mt' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001846() -> None:
    """language='mt' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001847() -> None:
    """language='mt' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001848() -> None:
    """language='mt' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001849() -> None:
    """language='mt' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001850() -> None:
    """language='mt' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001851() -> None:
    """language='mt' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001852() -> None:
    """language='mt' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001853() -> None:
    """language='mt' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001854() -> None:
    """language='mt' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001855() -> None:
    """language='mt' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001856() -> None:
    """language='mt' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001857() -> None:
    """language='mt' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001858() -> None:
    """language='mt' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001859() -> None:
    """language='mt' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001860() -> None:
    """language='mt' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001861() -> None:
    """language='mt' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001862() -> None:
    """language='mt' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001863() -> None:
    """language='mt' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001864() -> None:
    """language='mt' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001865() -> None:
    """language='mt' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001866() -> None:
    """language='mt' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001867() -> None:
    """language='mt' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001868() -> None:
    """language='mt' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001869() -> None:
    """language='mt' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001870() -> None:
    """language='mt' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001871() -> None:
    """language='mt' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001872() -> None:
    """language='mt' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001873() -> None:
    """language='mt' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001874() -> None:
    """language='mt' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001875() -> None:
    """language='mt' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001876() -> None:
    """language='mt' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001877() -> None:
    """language='mt' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001878() -> None:
    """language='mt' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c001879() -> None:
    """language='mt' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c001880() -> None:
    """language='mt' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c001881() -> None:
    """language='mt' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c001882() -> None:
    """language='mt' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c001883() -> None:
    """language='mt' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c001884() -> None:
    """language='mt' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c001885() -> None:
    """language='mt' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c001886() -> None:
    """language='mt' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c001887() -> None:
    """language='mt' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c001888() -> None:
    """language='mt' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c001889() -> None:
    """language='mt' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c001890() -> None:
    """language='mt' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c001891() -> None:
    """language='mt' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c001892() -> None:
    """language='mt' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c001893() -> None:
    """language='mt' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c001894() -> None:
    """language='mt' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c001895() -> None:
    """language='mt' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c001896() -> None:
    """language='mt' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c001897() -> None:
    """language='mt' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c001898() -> None:
    """language='mt' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c001899() -> None:
    """language='mt' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c001900() -> None:
    """language='mt' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c001901() -> None:
    """language='mt' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c001902() -> None:
    """language='mt' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c001903() -> None:
    """language='mt' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c001904() -> None:
    """language='mt' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c001905() -> None:
    """language='mt' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c001906() -> None:
    """language='mt' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c001907() -> None:
    """language='mt' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c001908() -> None:
    """language='mt' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c001909() -> None:
    """language='mt' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c001910() -> None:
    """language='mt' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c001911() -> None:
    """language='mt' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c001912() -> None:
    """language='mt' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c001913() -> None:
    """language='mt' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c001914() -> None:
    """language='mt' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c001915() -> None:
    """language='mt' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c001916() -> None:
    """language='mt' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c001917() -> None:
    """language='mt' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c001918() -> None:
    """language='mt' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c001919() -> None:
    """language='mt' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c001920() -> None:
    """language='mt' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c001921() -> None:
    """language='mt' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c001922() -> None:
    """language='mt' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c001923() -> None:
    """language='mt' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c001924() -> None:
    """language='mt' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c001925() -> None:
    """language='mt' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c001926() -> None:
    """language='mt' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c001927() -> None:
    """language='mt' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c001928() -> None:
    """language='mt' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c001929() -> None:
    """language='mt' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c001930() -> None:
    """language='mt' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c001931() -> None:
    """language='mt' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c001932() -> None:
    """language='mt' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c001933() -> None:
    """language='mt' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c001934() -> None:
    """language='mt' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c001935() -> None:
    """language='mt' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'mt', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c001936() -> None:
    """language='nl' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c001937() -> None:
    """language='nl' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c001938() -> None:
    """language='nl' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c001939() -> None:
    """language='nl' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c001940() -> None:
    """language='nl' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c001941() -> None:
    """language='nl' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c001942() -> None:
    """language='nl' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c001943() -> None:
    """language='nl' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c001944() -> None:
    """language='nl' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c001945() -> None:
    """language='nl' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c001946() -> None:
    """language='nl' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c001947() -> None:
    """language='nl' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c001948() -> None:
    """language='nl' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c001949() -> None:
    """language='nl' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c001950() -> None:
    """language='nl' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c001951() -> None:
    """language='nl' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c001952() -> None:
    """language='nl' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c001953() -> None:
    """language='nl' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c001954() -> None:
    """language='nl' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c001955() -> None:
    """language='nl' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c001956() -> None:
    """language='nl' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c001957() -> None:
    """language='nl' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c001958() -> None:
    """language='nl' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c001959() -> None:
    """language='nl' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c001960() -> None:
    """language='nl' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c001961() -> None:
    """language='nl' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c001962() -> None:
    """language='nl' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c001963() -> None:
    """language='nl' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c001964() -> None:
    """language='nl' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c001965() -> None:
    """language='nl' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c001966() -> None:
    """language='nl' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c001967() -> None:
    """language='nl' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c001968() -> None:
    """language='nl' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c001969() -> None:
    """language='nl' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c001970() -> None:
    """language='nl' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c001971() -> None:
    """language='nl' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c001972() -> None:
    """language='nl' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c001973() -> None:
    """language='nl' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c001974() -> None:
    """language='nl' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c001975() -> None:
    """language='nl' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c001976() -> None:
    """language='nl' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c001977() -> None:
    """language='nl' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c001978() -> None:
    """language='nl' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c001979() -> None:
    """language='nl' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c001980() -> None:
    """language='nl' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c001981() -> None:
    """language='nl' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c001982() -> None:
    """language='nl' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c001983() -> None:
    """language='nl' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c001984() -> None:
    """language='nl' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c001985() -> None:
    """language='nl' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c001986() -> None:
    """language='nl' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c001987() -> None:
    """language='nl' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c001988() -> None:
    """language='nl' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c001989() -> None:
    """language='nl' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c001990() -> None:
    """language='nl' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c001991() -> None:
    """language='nl' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c001992() -> None:
    """language='nl' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c001993() -> None:
    """language='nl' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c001994() -> None:
    """language='nl' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c001995() -> None:
    """language='nl' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c001996() -> None:
    """language='nl' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c001997() -> None:
    """language='nl' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c001998() -> None:
    """language='nl' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c001999() -> None:
    """language='nl' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002000() -> None:
    """language='nl' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002001() -> None:
    """language='nl' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002002() -> None:
    """language='nl' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002003() -> None:
    """language='nl' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002004() -> None:
    """language='nl' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002005() -> None:
    """language='nl' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002006() -> None:
    """language='nl' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002007() -> None:
    """language='nl' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002008() -> None:
    """language='nl' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002009() -> None:
    """language='nl' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002010() -> None:
    """language='nl' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002011() -> None:
    """language='nl' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002012() -> None:
    """language='nl' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002013() -> None:
    """language='nl' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002014() -> None:
    """language='nl' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002015() -> None:
    """language='nl' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002016() -> None:
    """language='nl' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002017() -> None:
    """language='nl' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002018() -> None:
    """language='nl' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002019() -> None:
    """language='nl' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002020() -> None:
    """language='nl' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002021() -> None:
    """language='nl' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002022() -> None:
    """language='nl' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002023() -> None:
    """language='nl' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002024() -> None:
    """language='nl' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002025() -> None:
    """language='nl' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002026() -> None:
    """language='nl' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002027() -> None:
    """language='nl' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002028() -> None:
    """language='nl' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002029() -> None:
    """language='nl' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002030() -> None:
    """language='nl' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002031() -> None:
    """language='nl' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002032() -> None:
    """language='nl' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002033() -> None:
    """language='nl' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002034() -> None:
    """language='nl' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002035() -> None:
    """language='nl' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002036() -> None:
    """language='nl' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002037() -> None:
    """language='nl' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002038() -> None:
    """language='nl' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002039() -> None:
    """language='nl' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002040() -> None:
    """language='nl' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002041() -> None:
    """language='nl' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002042() -> None:
    """language='nl' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002043() -> None:
    """language='nl' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002044() -> None:
    """language='nl' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002045() -> None:
    """language='nl' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002046() -> None:
    """language='nl' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002047() -> None:
    """language='nl' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002048() -> None:
    """language='nl' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002049() -> None:
    """language='nl' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002050() -> None:
    """language='nl' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002051() -> None:
    """language='nl' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002052() -> None:
    """language='nl' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002053() -> None:
    """language='nl' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002054() -> None:
    """language='nl' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002055() -> None:
    """language='nl' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002056() -> None:
    """language='nl' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'nl', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002057() -> None:
    """language='pl' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002058() -> None:
    """language='pl' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002059() -> None:
    """language='pl' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002060() -> None:
    """language='pl' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002061() -> None:
    """language='pl' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002062() -> None:
    """language='pl' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002063() -> None:
    """language='pl' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002064() -> None:
    """language='pl' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002065() -> None:
    """language='pl' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002066() -> None:
    """language='pl' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002067() -> None:
    """language='pl' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002068() -> None:
    """language='pl' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002069() -> None:
    """language='pl' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002070() -> None:
    """language='pl' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002071() -> None:
    """language='pl' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002072() -> None:
    """language='pl' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002073() -> None:
    """language='pl' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002074() -> None:
    """language='pl' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002075() -> None:
    """language='pl' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002076() -> None:
    """language='pl' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002077() -> None:
    """language='pl' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002078() -> None:
    """language='pl' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002079() -> None:
    """language='pl' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002080() -> None:
    """language='pl' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002081() -> None:
    """language='pl' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002082() -> None:
    """language='pl' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002083() -> None:
    """language='pl' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002084() -> None:
    """language='pl' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002085() -> None:
    """language='pl' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002086() -> None:
    """language='pl' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002087() -> None:
    """language='pl' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002088() -> None:
    """language='pl' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002089() -> None:
    """language='pl' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002090() -> None:
    """language='pl' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002091() -> None:
    """language='pl' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002092() -> None:
    """language='pl' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002093() -> None:
    """language='pl' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002094() -> None:
    """language='pl' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002095() -> None:
    """language='pl' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002096() -> None:
    """language='pl' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002097() -> None:
    """language='pl' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002098() -> None:
    """language='pl' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002099() -> None:
    """language='pl' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002100() -> None:
    """language='pl' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002101() -> None:
    """language='pl' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002102() -> None:
    """language='pl' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002103() -> None:
    """language='pl' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002104() -> None:
    """language='pl' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002105() -> None:
    """language='pl' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002106() -> None:
    """language='pl' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002107() -> None:
    """language='pl' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002108() -> None:
    """language='pl' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002109() -> None:
    """language='pl' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002110() -> None:
    """language='pl' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002111() -> None:
    """language='pl' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002112() -> None:
    """language='pl' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002113() -> None:
    """language='pl' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002114() -> None:
    """language='pl' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002115() -> None:
    """language='pl' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002116() -> None:
    """language='pl' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002117() -> None:
    """language='pl' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002118() -> None:
    """language='pl' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002119() -> None:
    """language='pl' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002120() -> None:
    """language='pl' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002121() -> None:
    """language='pl' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002122() -> None:
    """language='pl' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002123() -> None:
    """language='pl' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002124() -> None:
    """language='pl' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002125() -> None:
    """language='pl' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002126() -> None:
    """language='pl' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002127() -> None:
    """language='pl' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002128() -> None:
    """language='pl' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002129() -> None:
    """language='pl' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002130() -> None:
    """language='pl' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002131() -> None:
    """language='pl' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002132() -> None:
    """language='pl' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002133() -> None:
    """language='pl' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002134() -> None:
    """language='pl' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002135() -> None:
    """language='pl' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002136() -> None:
    """language='pl' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002137() -> None:
    """language='pl' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002138() -> None:
    """language='pl' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002139() -> None:
    """language='pl' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002140() -> None:
    """language='pl' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002141() -> None:
    """language='pl' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002142() -> None:
    """language='pl' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002143() -> None:
    """language='pl' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002144() -> None:
    """language='pl' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002145() -> None:
    """language='pl' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002146() -> None:
    """language='pl' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002147() -> None:
    """language='pl' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002148() -> None:
    """language='pl' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002149() -> None:
    """language='pl' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002150() -> None:
    """language='pl' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002151() -> None:
    """language='pl' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002152() -> None:
    """language='pl' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002153() -> None:
    """language='pl' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002154() -> None:
    """language='pl' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002155() -> None:
    """language='pl' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002156() -> None:
    """language='pl' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002157() -> None:
    """language='pl' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002158() -> None:
    """language='pl' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002159() -> None:
    """language='pl' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002160() -> None:
    """language='pl' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002161() -> None:
    """language='pl' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002162() -> None:
    """language='pl' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002163() -> None:
    """language='pl' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002164() -> None:
    """language='pl' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002165() -> None:
    """language='pl' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002166() -> None:
    """language='pl' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002167() -> None:
    """language='pl' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002168() -> None:
    """language='pl' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002169() -> None:
    """language='pl' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002170() -> None:
    """language='pl' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002171() -> None:
    """language='pl' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002172() -> None:
    """language='pl' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002173() -> None:
    """language='pl' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002174() -> None:
    """language='pl' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002175() -> None:
    """language='pl' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002176() -> None:
    """language='pl' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002177() -> None:
    """language='pl' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pl', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002178() -> None:
    """language='pt' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002179() -> None:
    """language='pt' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002180() -> None:
    """language='pt' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002181() -> None:
    """language='pt' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002182() -> None:
    """language='pt' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002183() -> None:
    """language='pt' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002184() -> None:
    """language='pt' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002185() -> None:
    """language='pt' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002186() -> None:
    """language='pt' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002187() -> None:
    """language='pt' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002188() -> None:
    """language='pt' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002189() -> None:
    """language='pt' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002190() -> None:
    """language='pt' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002191() -> None:
    """language='pt' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002192() -> None:
    """language='pt' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002193() -> None:
    """language='pt' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002194() -> None:
    """language='pt' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002195() -> None:
    """language='pt' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002196() -> None:
    """language='pt' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002197() -> None:
    """language='pt' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002198() -> None:
    """language='pt' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002199() -> None:
    """language='pt' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002200() -> None:
    """language='pt' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002201() -> None:
    """language='pt' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002202() -> None:
    """language='pt' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002203() -> None:
    """language='pt' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002204() -> None:
    """language='pt' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002205() -> None:
    """language='pt' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002206() -> None:
    """language='pt' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002207() -> None:
    """language='pt' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002208() -> None:
    """language='pt' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002209() -> None:
    """language='pt' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002210() -> None:
    """language='pt' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002211() -> None:
    """language='pt' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002212() -> None:
    """language='pt' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002213() -> None:
    """language='pt' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002214() -> None:
    """language='pt' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002215() -> None:
    """language='pt' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002216() -> None:
    """language='pt' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002217() -> None:
    """language='pt' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002218() -> None:
    """language='pt' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002219() -> None:
    """language='pt' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002220() -> None:
    """language='pt' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002221() -> None:
    """language='pt' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002222() -> None:
    """language='pt' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002223() -> None:
    """language='pt' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002224() -> None:
    """language='pt' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002225() -> None:
    """language='pt' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002226() -> None:
    """language='pt' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002227() -> None:
    """language='pt' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002228() -> None:
    """language='pt' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002229() -> None:
    """language='pt' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002230() -> None:
    """language='pt' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002231() -> None:
    """language='pt' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002232() -> None:
    """language='pt' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002233() -> None:
    """language='pt' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002234() -> None:
    """language='pt' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002235() -> None:
    """language='pt' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002236() -> None:
    """language='pt' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002237() -> None:
    """language='pt' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002238() -> None:
    """language='pt' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002239() -> None:
    """language='pt' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002240() -> None:
    """language='pt' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002241() -> None:
    """language='pt' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002242() -> None:
    """language='pt' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002243() -> None:
    """language='pt' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002244() -> None:
    """language='pt' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002245() -> None:
    """language='pt' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002246() -> None:
    """language='pt' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002247() -> None:
    """language='pt' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002248() -> None:
    """language='pt' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002249() -> None:
    """language='pt' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002250() -> None:
    """language='pt' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002251() -> None:
    """language='pt' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002252() -> None:
    """language='pt' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002253() -> None:
    """language='pt' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002254() -> None:
    """language='pt' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002255() -> None:
    """language='pt' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002256() -> None:
    """language='pt' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002257() -> None:
    """language='pt' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002258() -> None:
    """language='pt' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002259() -> None:
    """language='pt' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002260() -> None:
    """language='pt' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002261() -> None:
    """language='pt' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002262() -> None:
    """language='pt' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002263() -> None:
    """language='pt' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002264() -> None:
    """language='pt' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002265() -> None:
    """language='pt' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002266() -> None:
    """language='pt' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002267() -> None:
    """language='pt' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002268() -> None:
    """language='pt' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002269() -> None:
    """language='pt' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002270() -> None:
    """language='pt' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002271() -> None:
    """language='pt' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002272() -> None:
    """language='pt' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002273() -> None:
    """language='pt' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002274() -> None:
    """language='pt' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002275() -> None:
    """language='pt' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002276() -> None:
    """language='pt' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002277() -> None:
    """language='pt' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002278() -> None:
    """language='pt' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002279() -> None:
    """language='pt' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002280() -> None:
    """language='pt' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002281() -> None:
    """language='pt' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002282() -> None:
    """language='pt' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002283() -> None:
    """language='pt' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002284() -> None:
    """language='pt' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002285() -> None:
    """language='pt' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002286() -> None:
    """language='pt' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002287() -> None:
    """language='pt' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002288() -> None:
    """language='pt' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002289() -> None:
    """language='pt' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002290() -> None:
    """language='pt' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002291() -> None:
    """language='pt' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002292() -> None:
    """language='pt' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002293() -> None:
    """language='pt' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002294() -> None:
    """language='pt' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002295() -> None:
    """language='pt' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002296() -> None:
    """language='pt' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002297() -> None:
    """language='pt' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002298() -> None:
    """language='pt' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002299() -> None:
    """language='ro' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002300() -> None:
    """language='ro' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002301() -> None:
    """language='ro' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002302() -> None:
    """language='ro' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002303() -> None:
    """language='ro' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002304() -> None:
    """language='ro' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002305() -> None:
    """language='ro' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002306() -> None:
    """language='ro' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002307() -> None:
    """language='ro' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002308() -> None:
    """language='ro' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002309() -> None:
    """language='ro' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002310() -> None:
    """language='ro' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002311() -> None:
    """language='ro' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002312() -> None:
    """language='ro' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002313() -> None:
    """language='ro' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002314() -> None:
    """language='ro' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002315() -> None:
    """language='ro' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002316() -> None:
    """language='ro' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002317() -> None:
    """language='ro' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002318() -> None:
    """language='ro' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002319() -> None:
    """language='ro' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002320() -> None:
    """language='ro' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002321() -> None:
    """language='ro' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002322() -> None:
    """language='ro' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002323() -> None:
    """language='ro' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002324() -> None:
    """language='ro' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002325() -> None:
    """language='ro' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002326() -> None:
    """language='ro' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002327() -> None:
    """language='ro' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002328() -> None:
    """language='ro' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002329() -> None:
    """language='ro' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002330() -> None:
    """language='ro' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002331() -> None:
    """language='ro' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002332() -> None:
    """language='ro' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002333() -> None:
    """language='ro' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002334() -> None:
    """language='ro' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002335() -> None:
    """language='ro' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002336() -> None:
    """language='ro' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002337() -> None:
    """language='ro' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002338() -> None:
    """language='ro' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002339() -> None:
    """language='ro' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002340() -> None:
    """language='ro' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002341() -> None:
    """language='ro' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002342() -> None:
    """language='ro' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002343() -> None:
    """language='ro' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002344() -> None:
    """language='ro' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002345() -> None:
    """language='ro' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002346() -> None:
    """language='ro' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002347() -> None:
    """language='ro' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002348() -> None:
    """language='ro' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002349() -> None:
    """language='ro' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002350() -> None:
    """language='ro' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002351() -> None:
    """language='ro' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002352() -> None:
    """language='ro' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002353() -> None:
    """language='ro' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002354() -> None:
    """language='ro' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002355() -> None:
    """language='ro' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002356() -> None:
    """language='ro' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002357() -> None:
    """language='ro' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002358() -> None:
    """language='ro' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002359() -> None:
    """language='ro' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002360() -> None:
    """language='ro' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002361() -> None:
    """language='ro' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002362() -> None:
    """language='ro' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002363() -> None:
    """language='ro' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002364() -> None:
    """language='ro' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002365() -> None:
    """language='ro' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002366() -> None:
    """language='ro' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002367() -> None:
    """language='ro' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002368() -> None:
    """language='ro' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002369() -> None:
    """language='ro' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002370() -> None:
    """language='ro' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002371() -> None:
    """language='ro' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002372() -> None:
    """language='ro' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002373() -> None:
    """language='ro' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002374() -> None:
    """language='ro' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002375() -> None:
    """language='ro' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002376() -> None:
    """language='ro' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002377() -> None:
    """language='ro' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002378() -> None:
    """language='ro' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002379() -> None:
    """language='ro' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002380() -> None:
    """language='ro' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002381() -> None:
    """language='ro' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002382() -> None:
    """language='ro' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002383() -> None:
    """language='ro' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002384() -> None:
    """language='ro' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002385() -> None:
    """language='ro' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002386() -> None:
    """language='ro' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002387() -> None:
    """language='ro' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002388() -> None:
    """language='ro' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002389() -> None:
    """language='ro' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002390() -> None:
    """language='ro' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002391() -> None:
    """language='ro' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002392() -> None:
    """language='ro' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002393() -> None:
    """language='ro' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002394() -> None:
    """language='ro' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002395() -> None:
    """language='ro' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002396() -> None:
    """language='ro' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002397() -> None:
    """language='ro' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002398() -> None:
    """language='ro' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002399() -> None:
    """language='ro' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002400() -> None:
    """language='ro' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002401() -> None:
    """language='ro' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002402() -> None:
    """language='ro' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002403() -> None:
    """language='ro' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002404() -> None:
    """language='ro' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002405() -> None:
    """language='ro' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002406() -> None:
    """language='ro' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002407() -> None:
    """language='ro' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002408() -> None:
    """language='ro' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002409() -> None:
    """language='ro' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002410() -> None:
    """language='ro' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002411() -> None:
    """language='ro' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002412() -> None:
    """language='ro' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002413() -> None:
    """language='ro' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002414() -> None:
    """language='ro' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002415() -> None:
    """language='ro' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002416() -> None:
    """language='ro' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002417() -> None:
    """language='ro' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002418() -> None:
    """language='ro' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002419() -> None:
    """language='ro' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ro', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002420() -> None:
    """language='ru' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002421() -> None:
    """language='ru' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002422() -> None:
    """language='ru' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002423() -> None:
    """language='ru' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002424() -> None:
    """language='ru' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002425() -> None:
    """language='ru' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002426() -> None:
    """language='ru' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002427() -> None:
    """language='ru' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002428() -> None:
    """language='ru' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002429() -> None:
    """language='ru' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002430() -> None:
    """language='ru' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002431() -> None:
    """language='ru' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002432() -> None:
    """language='ru' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002433() -> None:
    """language='ru' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002434() -> None:
    """language='ru' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002435() -> None:
    """language='ru' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002436() -> None:
    """language='ru' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002437() -> None:
    """language='ru' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002438() -> None:
    """language='ru' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002439() -> None:
    """language='ru' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002440() -> None:
    """language='ru' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002441() -> None:
    """language='ru' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002442() -> None:
    """language='ru' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002443() -> None:
    """language='ru' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002444() -> None:
    """language='ru' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002445() -> None:
    """language='ru' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002446() -> None:
    """language='ru' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002447() -> None:
    """language='ru' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002448() -> None:
    """language='ru' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002449() -> None:
    """language='ru' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002450() -> None:
    """language='ru' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002451() -> None:
    """language='ru' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002452() -> None:
    """language='ru' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002453() -> None:
    """language='ru' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002454() -> None:
    """language='ru' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002455() -> None:
    """language='ru' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002456() -> None:
    """language='ru' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002457() -> None:
    """language='ru' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002458() -> None:
    """language='ru' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002459() -> None:
    """language='ru' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002460() -> None:
    """language='ru' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002461() -> None:
    """language='ru' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002462() -> None:
    """language='ru' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002463() -> None:
    """language='ru' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002464() -> None:
    """language='ru' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002465() -> None:
    """language='ru' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002466() -> None:
    """language='ru' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002467() -> None:
    """language='ru' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002468() -> None:
    """language='ru' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002469() -> None:
    """language='ru' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002470() -> None:
    """language='ru' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002471() -> None:
    """language='ru' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002472() -> None:
    """language='ru' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002473() -> None:
    """language='ru' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002474() -> None:
    """language='ru' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002475() -> None:
    """language='ru' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002476() -> None:
    """language='ru' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002477() -> None:
    """language='ru' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002478() -> None:
    """language='ru' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002479() -> None:
    """language='ru' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002480() -> None:
    """language='ru' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002481() -> None:
    """language='ru' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002482() -> None:
    """language='ru' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002483() -> None:
    """language='ru' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002484() -> None:
    """language='ru' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002485() -> None:
    """language='ru' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002486() -> None:
    """language='ru' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002487() -> None:
    """language='ru' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002488() -> None:
    """language='ru' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002489() -> None:
    """language='ru' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002490() -> None:
    """language='ru' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002491() -> None:
    """language='ru' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002492() -> None:
    """language='ru' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002493() -> None:
    """language='ru' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002494() -> None:
    """language='ru' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002495() -> None:
    """language='ru' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002496() -> None:
    """language='ru' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002497() -> None:
    """language='ru' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002498() -> None:
    """language='ru' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002499() -> None:
    """language='ru' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002500() -> None:
    """language='ru' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002501() -> None:
    """language='ru' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002502() -> None:
    """language='ru' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002503() -> None:
    """language='ru' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002504() -> None:
    """language='ru' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002505() -> None:
    """language='ru' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002506() -> None:
    """language='ru' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002507() -> None:
    """language='ru' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002508() -> None:
    """language='ru' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002509() -> None:
    """language='ru' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002510() -> None:
    """language='ru' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002511() -> None:
    """language='ru' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002512() -> None:
    """language='ru' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002513() -> None:
    """language='ru' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002514() -> None:
    """language='ru' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002515() -> None:
    """language='ru' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002516() -> None:
    """language='ru' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002517() -> None:
    """language='ru' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002518() -> None:
    """language='ru' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002519() -> None:
    """language='ru' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002520() -> None:
    """language='ru' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002521() -> None:
    """language='ru' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002522() -> None:
    """language='ru' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002523() -> None:
    """language='ru' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002524() -> None:
    """language='ru' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002525() -> None:
    """language='ru' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002526() -> None:
    """language='ru' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002527() -> None:
    """language='ru' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002528() -> None:
    """language='ru' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002529() -> None:
    """language='ru' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002530() -> None:
    """language='ru' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002531() -> None:
    """language='ru' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002532() -> None:
    """language='ru' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002533() -> None:
    """language='ru' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002534() -> None:
    """language='ru' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002535() -> None:
    """language='ru' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002536() -> None:
    """language='ru' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002537() -> None:
    """language='ru' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002538() -> None:
    """language='ru' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002539() -> None:
    """language='ru' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002540() -> None:
    """language='ru' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ru', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002541() -> None:
    """language='sk' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002542() -> None:
    """language='sk' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002543() -> None:
    """language='sk' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002544() -> None:
    """language='sk' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002545() -> None:
    """language='sk' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002546() -> None:
    """language='sk' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002547() -> None:
    """language='sk' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002548() -> None:
    """language='sk' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002549() -> None:
    """language='sk' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002550() -> None:
    """language='sk' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002551() -> None:
    """language='sk' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002552() -> None:
    """language='sk' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002553() -> None:
    """language='sk' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002554() -> None:
    """language='sk' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002555() -> None:
    """language='sk' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002556() -> None:
    """language='sk' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002557() -> None:
    """language='sk' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002558() -> None:
    """language='sk' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002559() -> None:
    """language='sk' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002560() -> None:
    """language='sk' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002561() -> None:
    """language='sk' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002562() -> None:
    """language='sk' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002563() -> None:
    """language='sk' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002564() -> None:
    """language='sk' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002565() -> None:
    """language='sk' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002566() -> None:
    """language='sk' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002567() -> None:
    """language='sk' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002568() -> None:
    """language='sk' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002569() -> None:
    """language='sk' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002570() -> None:
    """language='sk' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002571() -> None:
    """language='sk' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002572() -> None:
    """language='sk' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002573() -> None:
    """language='sk' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002574() -> None:
    """language='sk' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002575() -> None:
    """language='sk' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002576() -> None:
    """language='sk' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002577() -> None:
    """language='sk' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002578() -> None:
    """language='sk' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002579() -> None:
    """language='sk' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002580() -> None:
    """language='sk' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002581() -> None:
    """language='sk' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002582() -> None:
    """language='sk' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002583() -> None:
    """language='sk' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002584() -> None:
    """language='sk' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002585() -> None:
    """language='sk' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002586() -> None:
    """language='sk' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002587() -> None:
    """language='sk' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002588() -> None:
    """language='sk' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002589() -> None:
    """language='sk' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002590() -> None:
    """language='sk' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002591() -> None:
    """language='sk' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002592() -> None:
    """language='sk' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002593() -> None:
    """language='sk' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002594() -> None:
    """language='sk' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002595() -> None:
    """language='sk' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002596() -> None:
    """language='sk' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002597() -> None:
    """language='sk' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002598() -> None:
    """language='sk' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002599() -> None:
    """language='sk' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002600() -> None:
    """language='sk' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002601() -> None:
    """language='sk' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002602() -> None:
    """language='sk' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002603() -> None:
    """language='sk' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002604() -> None:
    """language='sk' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002605() -> None:
    """language='sk' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002606() -> None:
    """language='sk' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002607() -> None:
    """language='sk' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002608() -> None:
    """language='sk' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002609() -> None:
    """language='sk' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002610() -> None:
    """language='sk' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002611() -> None:
    """language='sk' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002612() -> None:
    """language='sk' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002613() -> None:
    """language='sk' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002614() -> None:
    """language='sk' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002615() -> None:
    """language='sk' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002616() -> None:
    """language='sk' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002617() -> None:
    """language='sk' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002618() -> None:
    """language='sk' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002619() -> None:
    """language='sk' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002620() -> None:
    """language='sk' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002621() -> None:
    """language='sk' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002622() -> None:
    """language='sk' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002623() -> None:
    """language='sk' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002624() -> None:
    """language='sk' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002625() -> None:
    """language='sk' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002626() -> None:
    """language='sk' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002627() -> None:
    """language='sk' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002628() -> None:
    """language='sk' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002629() -> None:
    """language='sk' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002630() -> None:
    """language='sk' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002631() -> None:
    """language='sk' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002632() -> None:
    """language='sk' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002633() -> None:
    """language='sk' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002634() -> None:
    """language='sk' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002635() -> None:
    """language='sk' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002636() -> None:
    """language='sk' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002637() -> None:
    """language='sk' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002638() -> None:
    """language='sk' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002639() -> None:
    """language='sk' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002640() -> None:
    """language='sk' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002641() -> None:
    """language='sk' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002642() -> None:
    """language='sk' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002643() -> None:
    """language='sk' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002644() -> None:
    """language='sk' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002645() -> None:
    """language='sk' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002646() -> None:
    """language='sk' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002647() -> None:
    """language='sk' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002648() -> None:
    """language='sk' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002649() -> None:
    """language='sk' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002650() -> None:
    """language='sk' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002651() -> None:
    """language='sk' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002652() -> None:
    """language='sk' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002653() -> None:
    """language='sk' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002654() -> None:
    """language='sk' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002655() -> None:
    """language='sk' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002656() -> None:
    """language='sk' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002657() -> None:
    """language='sk' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002658() -> None:
    """language='sk' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002659() -> None:
    """language='sk' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002660() -> None:
    """language='sk' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002661() -> None:
    """language='sk' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sk', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002662() -> None:
    """language='sl' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002663() -> None:
    """language='sl' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002664() -> None:
    """language='sl' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002665() -> None:
    """language='sl' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002666() -> None:
    """language='sl' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002667() -> None:
    """language='sl' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002668() -> None:
    """language='sl' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002669() -> None:
    """language='sl' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002670() -> None:
    """language='sl' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002671() -> None:
    """language='sl' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002672() -> None:
    """language='sl' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002673() -> None:
    """language='sl' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002674() -> None:
    """language='sl' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002675() -> None:
    """language='sl' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002676() -> None:
    """language='sl' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002677() -> None:
    """language='sl' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002678() -> None:
    """language='sl' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002679() -> None:
    """language='sl' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002680() -> None:
    """language='sl' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002681() -> None:
    """language='sl' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002682() -> None:
    """language='sl' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002683() -> None:
    """language='sl' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002684() -> None:
    """language='sl' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002685() -> None:
    """language='sl' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002686() -> None:
    """language='sl' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002687() -> None:
    """language='sl' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002688() -> None:
    """language='sl' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002689() -> None:
    """language='sl' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002690() -> None:
    """language='sl' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002691() -> None:
    """language='sl' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002692() -> None:
    """language='sl' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002693() -> None:
    """language='sl' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002694() -> None:
    """language='sl' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002695() -> None:
    """language='sl' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002696() -> None:
    """language='sl' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002697() -> None:
    """language='sl' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002698() -> None:
    """language='sl' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002699() -> None:
    """language='sl' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002700() -> None:
    """language='sl' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002701() -> None:
    """language='sl' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002702() -> None:
    """language='sl' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002703() -> None:
    """language='sl' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002704() -> None:
    """language='sl' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002705() -> None:
    """language='sl' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002706() -> None:
    """language='sl' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002707() -> None:
    """language='sl' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002708() -> None:
    """language='sl' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002709() -> None:
    """language='sl' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002710() -> None:
    """language='sl' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002711() -> None:
    """language='sl' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002712() -> None:
    """language='sl' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002713() -> None:
    """language='sl' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002714() -> None:
    """language='sl' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002715() -> None:
    """language='sl' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002716() -> None:
    """language='sl' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002717() -> None:
    """language='sl' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002718() -> None:
    """language='sl' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002719() -> None:
    """language='sl' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002720() -> None:
    """language='sl' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002721() -> None:
    """language='sl' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002722() -> None:
    """language='sl' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002723() -> None:
    """language='sl' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002724() -> None:
    """language='sl' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002725() -> None:
    """language='sl' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002726() -> None:
    """language='sl' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002727() -> None:
    """language='sl' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002728() -> None:
    """language='sl' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002729() -> None:
    """language='sl' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002730() -> None:
    """language='sl' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002731() -> None:
    """language='sl' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002732() -> None:
    """language='sl' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002733() -> None:
    """language='sl' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002734() -> None:
    """language='sl' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002735() -> None:
    """language='sl' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002736() -> None:
    """language='sl' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002737() -> None:
    """language='sl' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002738() -> None:
    """language='sl' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002739() -> None:
    """language='sl' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002740() -> None:
    """language='sl' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002741() -> None:
    """language='sl' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002742() -> None:
    """language='sl' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002743() -> None:
    """language='sl' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002744() -> None:
    """language='sl' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002745() -> None:
    """language='sl' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002746() -> None:
    """language='sl' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002747() -> None:
    """language='sl' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002748() -> None:
    """language='sl' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002749() -> None:
    """language='sl' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002750() -> None:
    """language='sl' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002751() -> None:
    """language='sl' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002752() -> None:
    """language='sl' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002753() -> None:
    """language='sl' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002754() -> None:
    """language='sl' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002755() -> None:
    """language='sl' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002756() -> None:
    """language='sl' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002757() -> None:
    """language='sl' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002758() -> None:
    """language='sl' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002759() -> None:
    """language='sl' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002760() -> None:
    """language='sl' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002761() -> None:
    """language='sl' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002762() -> None:
    """language='sl' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002763() -> None:
    """language='sl' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002764() -> None:
    """language='sl' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002765() -> None:
    """language='sl' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002766() -> None:
    """language='sl' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002767() -> None:
    """language='sl' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002768() -> None:
    """language='sl' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002769() -> None:
    """language='sl' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002770() -> None:
    """language='sl' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002771() -> None:
    """language='sl' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002772() -> None:
    """language='sl' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002773() -> None:
    """language='sl' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002774() -> None:
    """language='sl' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002775() -> None:
    """language='sl' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002776() -> None:
    """language='sl' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002777() -> None:
    """language='sl' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002778() -> None:
    """language='sl' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002779() -> None:
    """language='sl' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002780() -> None:
    """language='sl' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002781() -> None:
    """language='sl' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002782() -> None:
    """language='sl' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sl', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002783() -> None:
    """language='sv' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002784() -> None:
    """language='sv' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002785() -> None:
    """language='sv' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002786() -> None:
    """language='sv' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002787() -> None:
    """language='sv' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002788() -> None:
    """language='sv' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002789() -> None:
    """language='sv' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002790() -> None:
    """language='sv' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002791() -> None:
    """language='sv' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002792() -> None:
    """language='sv' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002793() -> None:
    """language='sv' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002794() -> None:
    """language='sv' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002795() -> None:
    """language='sv' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002796() -> None:
    """language='sv' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002797() -> None:
    """language='sv' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002798() -> None:
    """language='sv' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002799() -> None:
    """language='sv' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002800() -> None:
    """language='sv' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002801() -> None:
    """language='sv' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002802() -> None:
    """language='sv' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002803() -> None:
    """language='sv' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002804() -> None:
    """language='sv' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002805() -> None:
    """language='sv' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002806() -> None:
    """language='sv' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002807() -> None:
    """language='sv' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002808() -> None:
    """language='sv' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002809() -> None:
    """language='sv' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002810() -> None:
    """language='sv' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002811() -> None:
    """language='sv' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002812() -> None:
    """language='sv' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002813() -> None:
    """language='sv' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002814() -> None:
    """language='sv' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002815() -> None:
    """language='sv' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002816() -> None:
    """language='sv' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002817() -> None:
    """language='sv' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002818() -> None:
    """language='sv' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002819() -> None:
    """language='sv' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002820() -> None:
    """language='sv' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002821() -> None:
    """language='sv' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002822() -> None:
    """language='sv' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002823() -> None:
    """language='sv' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002824() -> None:
    """language='sv' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002825() -> None:
    """language='sv' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002826() -> None:
    """language='sv' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002827() -> None:
    """language='sv' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002828() -> None:
    """language='sv' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002829() -> None:
    """language='sv' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002830() -> None:
    """language='sv' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002831() -> None:
    """language='sv' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002832() -> None:
    """language='sv' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002833() -> None:
    """language='sv' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002834() -> None:
    """language='sv' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002835() -> None:
    """language='sv' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002836() -> None:
    """language='sv' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002837() -> None:
    """language='sv' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002838() -> None:
    """language='sv' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002839() -> None:
    """language='sv' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002840() -> None:
    """language='sv' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002841() -> None:
    """language='sv' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002842() -> None:
    """language='sv' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002843() -> None:
    """language='sv' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002844() -> None:
    """language='sv' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002845() -> None:
    """language='sv' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002846() -> None:
    """language='sv' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002847() -> None:
    """language='sv' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002848() -> None:
    """language='sv' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002849() -> None:
    """language='sv' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002850() -> None:
    """language='sv' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002851() -> None:
    """language='sv' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002852() -> None:
    """language='sv' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002853() -> None:
    """language='sv' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002854() -> None:
    """language='sv' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002855() -> None:
    """language='sv' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002856() -> None:
    """language='sv' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002857() -> None:
    """language='sv' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002858() -> None:
    """language='sv' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002859() -> None:
    """language='sv' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002860() -> None:
    """language='sv' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002861() -> None:
    """language='sv' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002862() -> None:
    """language='sv' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002863() -> None:
    """language='sv' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002864() -> None:
    """language='sv' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002865() -> None:
    """language='sv' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002866() -> None:
    """language='sv' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002867() -> None:
    """language='sv' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002868() -> None:
    """language='sv' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002869() -> None:
    """language='sv' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002870() -> None:
    """language='sv' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002871() -> None:
    """language='sv' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002872() -> None:
    """language='sv' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002873() -> None:
    """language='sv' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002874() -> None:
    """language='sv' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002875() -> None:
    """language='sv' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002876() -> None:
    """language='sv' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002877() -> None:
    """language='sv' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002878() -> None:
    """language='sv' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c002879() -> None:
    """language='sv' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c002880() -> None:
    """language='sv' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c002881() -> None:
    """language='sv' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c002882() -> None:
    """language='sv' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c002883() -> None:
    """language='sv' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c002884() -> None:
    """language='sv' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c002885() -> None:
    """language='sv' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c002886() -> None:
    """language='sv' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c002887() -> None:
    """language='sv' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c002888() -> None:
    """language='sv' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c002889() -> None:
    """language='sv' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c002890() -> None:
    """language='sv' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c002891() -> None:
    """language='sv' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c002892() -> None:
    """language='sv' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c002893() -> None:
    """language='sv' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c002894() -> None:
    """language='sv' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c002895() -> None:
    """language='sv' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c002896() -> None:
    """language='sv' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c002897() -> None:
    """language='sv' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c002898() -> None:
    """language='sv' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c002899() -> None:
    """language='sv' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c002900() -> None:
    """language='sv' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c002901() -> None:
    """language='sv' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c002902() -> None:
    """language='sv' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c002903() -> None:
    """language='sv' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'sv', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c002904() -> None:
    """language='uk' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c002905() -> None:
    """language='uk' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c002906() -> None:
    """language='uk' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c002907() -> None:
    """language='uk' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c002908() -> None:
    """language='uk' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c002909() -> None:
    """language='uk' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c002910() -> None:
    """language='uk' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c002911() -> None:
    """language='uk' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c002912() -> None:
    """language='uk' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c002913() -> None:
    """language='uk' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c002914() -> None:
    """language='uk' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c002915() -> None:
    """language='uk' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c002916() -> None:
    """language='uk' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c002917() -> None:
    """language='uk' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c002918() -> None:
    """language='uk' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c002919() -> None:
    """language='uk' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c002920() -> None:
    """language='uk' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c002921() -> None:
    """language='uk' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c002922() -> None:
    """language='uk' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c002923() -> None:
    """language='uk' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c002924() -> None:
    """language='uk' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c002925() -> None:
    """language='uk' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c002926() -> None:
    """language='uk' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c002927() -> None:
    """language='uk' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c002928() -> None:
    """language='uk' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c002929() -> None:
    """language='uk' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c002930() -> None:
    """language='uk' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c002931() -> None:
    """language='uk' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c002932() -> None:
    """language='uk' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c002933() -> None:
    """language='uk' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c002934() -> None:
    """language='uk' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c002935() -> None:
    """language='uk' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c002936() -> None:
    """language='uk' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c002937() -> None:
    """language='uk' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c002938() -> None:
    """language='uk' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c002939() -> None:
    """language='uk' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c002940() -> None:
    """language='uk' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c002941() -> None:
    """language='uk' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c002942() -> None:
    """language='uk' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c002943() -> None:
    """language='uk' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c002944() -> None:
    """language='uk' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c002945() -> None:
    """language='uk' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c002946() -> None:
    """language='uk' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c002947() -> None:
    """language='uk' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c002948() -> None:
    """language='uk' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c002949() -> None:
    """language='uk' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c002950() -> None:
    """language='uk' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c002951() -> None:
    """language='uk' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c002952() -> None:
    """language='uk' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c002953() -> None:
    """language='uk' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c002954() -> None:
    """language='uk' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c002955() -> None:
    """language='uk' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c002956() -> None:
    """language='uk' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c002957() -> None:
    """language='uk' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c002958() -> None:
    """language='uk' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c002959() -> None:
    """language='uk' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c002960() -> None:
    """language='uk' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c002961() -> None:
    """language='uk' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c002962() -> None:
    """language='uk' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c002963() -> None:
    """language='uk' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c002964() -> None:
    """language='uk' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c002965() -> None:
    """language='uk' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c002966() -> None:
    """language='uk' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c002967() -> None:
    """language='uk' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c002968() -> None:
    """language='uk' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c002969() -> None:
    """language='uk' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c002970() -> None:
    """language='uk' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c002971() -> None:
    """language='uk' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c002972() -> None:
    """language='uk' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c002973() -> None:
    """language='uk' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c002974() -> None:
    """language='uk' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c002975() -> None:
    """language='uk' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c002976() -> None:
    """language='uk' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c002977() -> None:
    """language='uk' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c002978() -> None:
    """language='uk' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c002979() -> None:
    """language='uk' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c002980() -> None:
    """language='uk' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c002981() -> None:
    """language='uk' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c002982() -> None:
    """language='uk' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c002983() -> None:
    """language='uk' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c002984() -> None:
    """language='uk' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c002985() -> None:
    """language='uk' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c002986() -> None:
    """language='uk' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c002987() -> None:
    """language='uk' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c002988() -> None:
    """language='uk' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c002989() -> None:
    """language='uk' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c002990() -> None:
    """language='uk' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c002991() -> None:
    """language='uk' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c002992() -> None:
    """language='uk' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c002993() -> None:
    """language='uk' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c002994() -> None:
    """language='uk' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c002995() -> None:
    """language='uk' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c002996() -> None:
    """language='uk' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c002997() -> None:
    """language='uk' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c002998() -> None:
    """language='uk' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c002999() -> None:
    """language='uk' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003000() -> None:
    """language='uk' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003001() -> None:
    """language='uk' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003002() -> None:
    """language='uk' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003003() -> None:
    """language='uk' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003004() -> None:
    """language='uk' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003005() -> None:
    """language='uk' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003006() -> None:
    """language='uk' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003007() -> None:
    """language='uk' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003008() -> None:
    """language='uk' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003009() -> None:
    """language='uk' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003010() -> None:
    """language='uk' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003011() -> None:
    """language='uk' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003012() -> None:
    """language='uk' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003013() -> None:
    """language='uk' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003014() -> None:
    """language='uk' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003015() -> None:
    """language='uk' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003016() -> None:
    """language='uk' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003017() -> None:
    """language='uk' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003018() -> None:
    """language='uk' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003019() -> None:
    """language='uk' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003020() -> None:
    """language='uk' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003021() -> None:
    """language='uk' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003022() -> None:
    """language='uk' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003023() -> None:
    """language='uk' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003024() -> None:
    """language='uk' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'uk', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003025() -> None:
    """language='vi' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003026() -> None:
    """language='vi' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003027() -> None:
    """language='vi' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003028() -> None:
    """language='vi' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003029() -> None:
    """language='vi' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003030() -> None:
    """language='vi' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003031() -> None:
    """language='vi' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003032() -> None:
    """language='vi' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003033() -> None:
    """language='vi' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003034() -> None:
    """language='vi' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003035() -> None:
    """language='vi' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003036() -> None:
    """language='vi' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003037() -> None:
    """language='vi' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003038() -> None:
    """language='vi' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003039() -> None:
    """language='vi' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003040() -> None:
    """language='vi' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003041() -> None:
    """language='vi' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003042() -> None:
    """language='vi' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003043() -> None:
    """language='vi' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003044() -> None:
    """language='vi' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003045() -> None:
    """language='vi' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003046() -> None:
    """language='vi' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003047() -> None:
    """language='vi' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003048() -> None:
    """language='vi' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003049() -> None:
    """language='vi' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003050() -> None:
    """language='vi' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003051() -> None:
    """language='vi' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003052() -> None:
    """language='vi' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003053() -> None:
    """language='vi' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003054() -> None:
    """language='vi' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003055() -> None:
    """language='vi' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003056() -> None:
    """language='vi' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003057() -> None:
    """language='vi' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003058() -> None:
    """language='vi' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003059() -> None:
    """language='vi' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003060() -> None:
    """language='vi' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003061() -> None:
    """language='vi' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003062() -> None:
    """language='vi' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003063() -> None:
    """language='vi' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003064() -> None:
    """language='vi' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003065() -> None:
    """language='vi' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003066() -> None:
    """language='vi' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003067() -> None:
    """language='vi' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003068() -> None:
    """language='vi' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003069() -> None:
    """language='vi' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003070() -> None:
    """language='vi' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003071() -> None:
    """language='vi' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003072() -> None:
    """language='vi' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003073() -> None:
    """language='vi' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003074() -> None:
    """language='vi' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003075() -> None:
    """language='vi' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003076() -> None:
    """language='vi' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003077() -> None:
    """language='vi' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003078() -> None:
    """language='vi' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003079() -> None:
    """language='vi' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003080() -> None:
    """language='vi' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003081() -> None:
    """language='vi' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003082() -> None:
    """language='vi' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003083() -> None:
    """language='vi' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003084() -> None:
    """language='vi' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003085() -> None:
    """language='vi' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003086() -> None:
    """language='vi' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003087() -> None:
    """language='vi' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003088() -> None:
    """language='vi' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003089() -> None:
    """language='vi' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003090() -> None:
    """language='vi' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003091() -> None:
    """language='vi' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003092() -> None:
    """language='vi' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003093() -> None:
    """language='vi' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003094() -> None:
    """language='vi' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003095() -> None:
    """language='vi' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003096() -> None:
    """language='vi' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003097() -> None:
    """language='vi' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003098() -> None:
    """language='vi' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003099() -> None:
    """language='vi' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003100() -> None:
    """language='vi' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003101() -> None:
    """language='vi' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003102() -> None:
    """language='vi' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003103() -> None:
    """language='vi' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003104() -> None:
    """language='vi' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003105() -> None:
    """language='vi' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003106() -> None:
    """language='vi' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003107() -> None:
    """language='vi' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003108() -> None:
    """language='vi' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003109() -> None:
    """language='vi' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003110() -> None:
    """language='vi' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003111() -> None:
    """language='vi' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003112() -> None:
    """language='vi' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003113() -> None:
    """language='vi' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003114() -> None:
    """language='vi' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003115() -> None:
    """language='vi' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003116() -> None:
    """language='vi' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003117() -> None:
    """language='vi' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003118() -> None:
    """language='vi' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003119() -> None:
    """language='vi' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003120() -> None:
    """language='vi' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003121() -> None:
    """language='vi' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003122() -> None:
    """language='vi' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003123() -> None:
    """language='vi' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003124() -> None:
    """language='vi' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003125() -> None:
    """language='vi' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003126() -> None:
    """language='vi' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003127() -> None:
    """language='vi' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003128() -> None:
    """language='vi' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003129() -> None:
    """language='vi' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003130() -> None:
    """language='vi' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003131() -> None:
    """language='vi' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003132() -> None:
    """language='vi' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003133() -> None:
    """language='vi' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003134() -> None:
    """language='vi' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003135() -> None:
    """language='vi' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003136() -> None:
    """language='vi' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003137() -> None:
    """language='vi' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003138() -> None:
    """language='vi' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003139() -> None:
    """language='vi' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003140() -> None:
    """language='vi' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003141() -> None:
    """language='vi' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003142() -> None:
    """language='vi' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003143() -> None:
    """language='vi' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003144() -> None:
    """language='vi' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003145() -> None:
    """language='vi' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'vi', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003146() -> None:
    """language='ja' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003147() -> None:
    """language='ja' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003148() -> None:
    """language='ja' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003149() -> None:
    """language='ja' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003150() -> None:
    """language='ja' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003151() -> None:
    """language='ja' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003152() -> None:
    """language='ja' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003153() -> None:
    """language='ja' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003154() -> None:
    """language='ja' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003155() -> None:
    """language='ja' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003156() -> None:
    """language='ja' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003157() -> None:
    """language='ja' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003158() -> None:
    """language='ja' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003159() -> None:
    """language='ja' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003160() -> None:
    """language='ja' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003161() -> None:
    """language='ja' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003162() -> None:
    """language='ja' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003163() -> None:
    """language='ja' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003164() -> None:
    """language='ja' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003165() -> None:
    """language='ja' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003166() -> None:
    """language='ja' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003167() -> None:
    """language='ja' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003168() -> None:
    """language='ja' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003169() -> None:
    """language='ja' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003170() -> None:
    """language='ja' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003171() -> None:
    """language='ja' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003172() -> None:
    """language='ja' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003173() -> None:
    """language='ja' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003174() -> None:
    """language='ja' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003175() -> None:
    """language='ja' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003176() -> None:
    """language='ja' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003177() -> None:
    """language='ja' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003178() -> None:
    """language='ja' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003179() -> None:
    """language='ja' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003180() -> None:
    """language='ja' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003181() -> None:
    """language='ja' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003182() -> None:
    """language='ja' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003183() -> None:
    """language='ja' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003184() -> None:
    """language='ja' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003185() -> None:
    """language='ja' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003186() -> None:
    """language='ja' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003187() -> None:
    """language='ja' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003188() -> None:
    """language='ja' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003189() -> None:
    """language='ja' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003190() -> None:
    """language='ja' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003191() -> None:
    """language='ja' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003192() -> None:
    """language='ja' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003193() -> None:
    """language='ja' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003194() -> None:
    """language='ja' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003195() -> None:
    """language='ja' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003196() -> None:
    """language='ja' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003197() -> None:
    """language='ja' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003198() -> None:
    """language='ja' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003199() -> None:
    """language='ja' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003200() -> None:
    """language='ja' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003201() -> None:
    """language='ja' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003202() -> None:
    """language='ja' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003203() -> None:
    """language='ja' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003204() -> None:
    """language='ja' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003205() -> None:
    """language='ja' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003206() -> None:
    """language='ja' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003207() -> None:
    """language='ja' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003208() -> None:
    """language='ja' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003209() -> None:
    """language='ja' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003210() -> None:
    """language='ja' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003211() -> None:
    """language='ja' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003212() -> None:
    """language='ja' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003213() -> None:
    """language='ja' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003214() -> None:
    """language='ja' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003215() -> None:
    """language='ja' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003216() -> None:
    """language='ja' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003217() -> None:
    """language='ja' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003218() -> None:
    """language='ja' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003219() -> None:
    """language='ja' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003220() -> None:
    """language='ja' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003221() -> None:
    """language='ja' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003222() -> None:
    """language='ja' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003223() -> None:
    """language='ja' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003224() -> None:
    """language='ja' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003225() -> None:
    """language='ja' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003226() -> None:
    """language='ja' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003227() -> None:
    """language='ja' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003228() -> None:
    """language='ja' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003229() -> None:
    """language='ja' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003230() -> None:
    """language='ja' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003231() -> None:
    """language='ja' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003232() -> None:
    """language='ja' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003233() -> None:
    """language='ja' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003234() -> None:
    """language='ja' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003235() -> None:
    """language='ja' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003236() -> None:
    """language='ja' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003237() -> None:
    """language='ja' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003238() -> None:
    """language='ja' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003239() -> None:
    """language='ja' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003240() -> None:
    """language='ja' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003241() -> None:
    """language='ja' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003242() -> None:
    """language='ja' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003243() -> None:
    """language='ja' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003244() -> None:
    """language='ja' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003245() -> None:
    """language='ja' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003246() -> None:
    """language='ja' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003247() -> None:
    """language='ja' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003248() -> None:
    """language='ja' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003249() -> None:
    """language='ja' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003250() -> None:
    """language='ja' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003251() -> None:
    """language='ja' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003252() -> None:
    """language='ja' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003253() -> None:
    """language='ja' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003254() -> None:
    """language='ja' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003255() -> None:
    """language='ja' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003256() -> None:
    """language='ja' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003257() -> None:
    """language='ja' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003258() -> None:
    """language='ja' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003259() -> None:
    """language='ja' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003260() -> None:
    """language='ja' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003261() -> None:
    """language='ja' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003262() -> None:
    """language='ja' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003263() -> None:
    """language='ja' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003264() -> None:
    """language='ja' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003265() -> None:
    """language='ja' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003266() -> None:
    """language='ja' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ja', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003267() -> None:
    """language='zh' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003268() -> None:
    """language='zh' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003269() -> None:
    """language='zh' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003270() -> None:
    """language='zh' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003271() -> None:
    """language='zh' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003272() -> None:
    """language='zh' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003273() -> None:
    """language='zh' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003274() -> None:
    """language='zh' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003275() -> None:
    """language='zh' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003276() -> None:
    """language='zh' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003277() -> None:
    """language='zh' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003278() -> None:
    """language='zh' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003279() -> None:
    """language='zh' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003280() -> None:
    """language='zh' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003281() -> None:
    """language='zh' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003282() -> None:
    """language='zh' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003283() -> None:
    """language='zh' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003284() -> None:
    """language='zh' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003285() -> None:
    """language='zh' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003286() -> None:
    """language='zh' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003287() -> None:
    """language='zh' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003288() -> None:
    """language='zh' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003289() -> None:
    """language='zh' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003290() -> None:
    """language='zh' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003291() -> None:
    """language='zh' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003292() -> None:
    """language='zh' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003293() -> None:
    """language='zh' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003294() -> None:
    """language='zh' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003295() -> None:
    """language='zh' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003296() -> None:
    """language='zh' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003297() -> None:
    """language='zh' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003298() -> None:
    """language='zh' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003299() -> None:
    """language='zh' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003300() -> None:
    """language='zh' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003301() -> None:
    """language='zh' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003302() -> None:
    """language='zh' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003303() -> None:
    """language='zh' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003304() -> None:
    """language='zh' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003305() -> None:
    """language='zh' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003306() -> None:
    """language='zh' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003307() -> None:
    """language='zh' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003308() -> None:
    """language='zh' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003309() -> None:
    """language='zh' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003310() -> None:
    """language='zh' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003311() -> None:
    """language='zh' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003312() -> None:
    """language='zh' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003313() -> None:
    """language='zh' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003314() -> None:
    """language='zh' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003315() -> None:
    """language='zh' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003316() -> None:
    """language='zh' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003317() -> None:
    """language='zh' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003318() -> None:
    """language='zh' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003319() -> None:
    """language='zh' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003320() -> None:
    """language='zh' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003321() -> None:
    """language='zh' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003322() -> None:
    """language='zh' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003323() -> None:
    """language='zh' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003324() -> None:
    """language='zh' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003325() -> None:
    """language='zh' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003326() -> None:
    """language='zh' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003327() -> None:
    """language='zh' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003328() -> None:
    """language='zh' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003329() -> None:
    """language='zh' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003330() -> None:
    """language='zh' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003331() -> None:
    """language='zh' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003332() -> None:
    """language='zh' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003333() -> None:
    """language='zh' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003334() -> None:
    """language='zh' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003335() -> None:
    """language='zh' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003336() -> None:
    """language='zh' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003337() -> None:
    """language='zh' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003338() -> None:
    """language='zh' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003339() -> None:
    """language='zh' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003340() -> None:
    """language='zh' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003341() -> None:
    """language='zh' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003342() -> None:
    """language='zh' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003343() -> None:
    """language='zh' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003344() -> None:
    """language='zh' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003345() -> None:
    """language='zh' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003346() -> None:
    """language='zh' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003347() -> None:
    """language='zh' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003348() -> None:
    """language='zh' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003349() -> None:
    """language='zh' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003350() -> None:
    """language='zh' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003351() -> None:
    """language='zh' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003352() -> None:
    """language='zh' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003353() -> None:
    """language='zh' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003354() -> None:
    """language='zh' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003355() -> None:
    """language='zh' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003356() -> None:
    """language='zh' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003357() -> None:
    """language='zh' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003358() -> None:
    """language='zh' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003359() -> None:
    """language='zh' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003360() -> None:
    """language='zh' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003361() -> None:
    """language='zh' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003362() -> None:
    """language='zh' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003363() -> None:
    """language='zh' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003364() -> None:
    """language='zh' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003365() -> None:
    """language='zh' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003366() -> None:
    """language='zh' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003367() -> None:
    """language='zh' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003368() -> None:
    """language='zh' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003369() -> None:
    """language='zh' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003370() -> None:
    """language='zh' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003371() -> None:
    """language='zh' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003372() -> None:
    """language='zh' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003373() -> None:
    """language='zh' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003374() -> None:
    """language='zh' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003375() -> None:
    """language='zh' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003376() -> None:
    """language='zh' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003377() -> None:
    """language='zh' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003378() -> None:
    """language='zh' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003379() -> None:
    """language='zh' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003380() -> None:
    """language='zh' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003381() -> None:
    """language='zh' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003382() -> None:
    """language='zh' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003383() -> None:
    """language='zh' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003384() -> None:
    """language='zh' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003385() -> None:
    """language='zh' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003386() -> None:
    """language='zh' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003387() -> None:
    """language='zh' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'zh', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003388() -> None:
    """language='ko' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003389() -> None:
    """language='ko' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003390() -> None:
    """language='ko' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003391() -> None:
    """language='ko' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003392() -> None:
    """language='ko' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003393() -> None:
    """language='ko' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003394() -> None:
    """language='ko' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003395() -> None:
    """language='ko' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003396() -> None:
    """language='ko' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003397() -> None:
    """language='ko' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003398() -> None:
    """language='ko' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003399() -> None:
    """language='ko' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003400() -> None:
    """language='ko' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003401() -> None:
    """language='ko' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003402() -> None:
    """language='ko' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003403() -> None:
    """language='ko' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003404() -> None:
    """language='ko' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003405() -> None:
    """language='ko' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003406() -> None:
    """language='ko' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003407() -> None:
    """language='ko' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003408() -> None:
    """language='ko' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003409() -> None:
    """language='ko' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003410() -> None:
    """language='ko' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003411() -> None:
    """language='ko' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003412() -> None:
    """language='ko' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003413() -> None:
    """language='ko' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003414() -> None:
    """language='ko' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003415() -> None:
    """language='ko' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003416() -> None:
    """language='ko' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003417() -> None:
    """language='ko' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003418() -> None:
    """language='ko' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003419() -> None:
    """language='ko' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003420() -> None:
    """language='ko' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003421() -> None:
    """language='ko' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003422() -> None:
    """language='ko' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003423() -> None:
    """language='ko' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003424() -> None:
    """language='ko' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003425() -> None:
    """language='ko' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003426() -> None:
    """language='ko' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003427() -> None:
    """language='ko' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003428() -> None:
    """language='ko' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003429() -> None:
    """language='ko' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003430() -> None:
    """language='ko' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003431() -> None:
    """language='ko' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003432() -> None:
    """language='ko' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003433() -> None:
    """language='ko' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003434() -> None:
    """language='ko' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003435() -> None:
    """language='ko' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003436() -> None:
    """language='ko' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003437() -> None:
    """language='ko' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003438() -> None:
    """language='ko' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003439() -> None:
    """language='ko' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003440() -> None:
    """language='ko' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003441() -> None:
    """language='ko' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003442() -> None:
    """language='ko' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003443() -> None:
    """language='ko' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003444() -> None:
    """language='ko' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003445() -> None:
    """language='ko' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003446() -> None:
    """language='ko' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003447() -> None:
    """language='ko' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003448() -> None:
    """language='ko' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003449() -> None:
    """language='ko' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003450() -> None:
    """language='ko' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003451() -> None:
    """language='ko' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003452() -> None:
    """language='ko' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003453() -> None:
    """language='ko' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003454() -> None:
    """language='ko' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003455() -> None:
    """language='ko' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003456() -> None:
    """language='ko' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003457() -> None:
    """language='ko' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003458() -> None:
    """language='ko' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003459() -> None:
    """language='ko' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003460() -> None:
    """language='ko' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003461() -> None:
    """language='ko' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003462() -> None:
    """language='ko' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003463() -> None:
    """language='ko' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003464() -> None:
    """language='ko' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003465() -> None:
    """language='ko' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003466() -> None:
    """language='ko' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003467() -> None:
    """language='ko' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003468() -> None:
    """language='ko' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003469() -> None:
    """language='ko' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003470() -> None:
    """language='ko' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003471() -> None:
    """language='ko' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003472() -> None:
    """language='ko' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003473() -> None:
    """language='ko' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003474() -> None:
    """language='ko' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003475() -> None:
    """language='ko' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003476() -> None:
    """language='ko' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003477() -> None:
    """language='ko' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003478() -> None:
    """language='ko' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003479() -> None:
    """language='ko' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003480() -> None:
    """language='ko' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003481() -> None:
    """language='ko' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003482() -> None:
    """language='ko' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003483() -> None:
    """language='ko' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003484() -> None:
    """language='ko' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003485() -> None:
    """language='ko' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003486() -> None:
    """language='ko' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003487() -> None:
    """language='ko' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003488() -> None:
    """language='ko' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003489() -> None:
    """language='ko' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003490() -> None:
    """language='ko' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003491() -> None:
    """language='ko' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003492() -> None:
    """language='ko' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003493() -> None:
    """language='ko' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003494() -> None:
    """language='ko' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003495() -> None:
    """language='ko' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003496() -> None:
    """language='ko' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003497() -> None:
    """language='ko' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003498() -> None:
    """language='ko' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003499() -> None:
    """language='ko' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003500() -> None:
    """language='ko' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003501() -> None:
    """language='ko' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003502() -> None:
    """language='ko' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003503() -> None:
    """language='ko' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003504() -> None:
    """language='ko' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003505() -> None:
    """language='ko' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003506() -> None:
    """language='ko' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003507() -> None:
    """language='ko' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003508() -> None:
    """language='ko' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ko', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003509() -> None:
    """language='multi' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003510() -> None:
    """language='multi' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003511() -> None:
    """language='multi' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003512() -> None:
    """language='multi' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003513() -> None:
    """language='multi' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003514() -> None:
    """language='multi' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003515() -> None:
    """language='multi' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003516() -> None:
    """language='multi' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003517() -> None:
    """language='multi' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003518() -> None:
    """language='multi' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003519() -> None:
    """language='multi' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003520() -> None:
    """language='multi' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003521() -> None:
    """language='multi' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003522() -> None:
    """language='multi' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003523() -> None:
    """language='multi' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003524() -> None:
    """language='multi' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003525() -> None:
    """language='multi' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003526() -> None:
    """language='multi' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003527() -> None:
    """language='multi' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003528() -> None:
    """language='multi' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003529() -> None:
    """language='multi' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003530() -> None:
    """language='multi' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003531() -> None:
    """language='multi' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003532() -> None:
    """language='multi' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003533() -> None:
    """language='multi' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003534() -> None:
    """language='multi' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003535() -> None:
    """language='multi' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003536() -> None:
    """language='multi' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003537() -> None:
    """language='multi' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003538() -> None:
    """language='multi' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003539() -> None:
    """language='multi' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003540() -> None:
    """language='multi' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003541() -> None:
    """language='multi' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003542() -> None:
    """language='multi' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003543() -> None:
    """language='multi' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003544() -> None:
    """language='multi' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003545() -> None:
    """language='multi' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003546() -> None:
    """language='multi' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003547() -> None:
    """language='multi' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003548() -> None:
    """language='multi' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003549() -> None:
    """language='multi' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003550() -> None:
    """language='multi' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003551() -> None:
    """language='multi' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003552() -> None:
    """language='multi' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003553() -> None:
    """language='multi' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003554() -> None:
    """language='multi' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003555() -> None:
    """language='multi' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003556() -> None:
    """language='multi' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003557() -> None:
    """language='multi' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003558() -> None:
    """language='multi' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003559() -> None:
    """language='multi' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003560() -> None:
    """language='multi' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003561() -> None:
    """language='multi' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003562() -> None:
    """language='multi' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003563() -> None:
    """language='multi' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003564() -> None:
    """language='multi' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003565() -> None:
    """language='multi' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003566() -> None:
    """language='multi' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003567() -> None:
    """language='multi' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003568() -> None:
    """language='multi' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003569() -> None:
    """language='multi' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003570() -> None:
    """language='multi' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003571() -> None:
    """language='multi' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003572() -> None:
    """language='multi' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003573() -> None:
    """language='multi' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003574() -> None:
    """language='multi' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003575() -> None:
    """language='multi' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003576() -> None:
    """language='multi' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003577() -> None:
    """language='multi' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003578() -> None:
    """language='multi' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003579() -> None:
    """language='multi' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003580() -> None:
    """language='multi' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003581() -> None:
    """language='multi' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003582() -> None:
    """language='multi' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003583() -> None:
    """language='multi' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003584() -> None:
    """language='multi' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003585() -> None:
    """language='multi' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003586() -> None:
    """language='multi' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003587() -> None:
    """language='multi' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003588() -> None:
    """language='multi' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003589() -> None:
    """language='multi' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003590() -> None:
    """language='multi' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003591() -> None:
    """language='multi' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003592() -> None:
    """language='multi' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003593() -> None:
    """language='multi' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003594() -> None:
    """language='multi' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003595() -> None:
    """language='multi' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003596() -> None:
    """language='multi' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003597() -> None:
    """language='multi' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003598() -> None:
    """language='multi' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003599() -> None:
    """language='multi' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003600() -> None:
    """language='multi' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003601() -> None:
    """language='multi' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003602() -> None:
    """language='multi' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003603() -> None:
    """language='multi' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003604() -> None:
    """language='multi' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003605() -> None:
    """language='multi' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003606() -> None:
    """language='multi' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003607() -> None:
    """language='multi' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003608() -> None:
    """language='multi' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003609() -> None:
    """language='multi' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003610() -> None:
    """language='multi' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003611() -> None:
    """language='multi' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003612() -> None:
    """language='multi' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003613() -> None:
    """language='multi' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003614() -> None:
    """language='multi' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003615() -> None:
    """language='multi' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003616() -> None:
    """language='multi' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003617() -> None:
    """language='multi' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003618() -> None:
    """language='multi' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003619() -> None:
    """language='multi' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003620() -> None:
    """language='multi' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003621() -> None:
    """language='multi' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003622() -> None:
    """language='multi' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003623() -> None:
    """language='multi' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003624() -> None:
    """language='multi' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003625() -> None:
    """language='multi' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003626() -> None:
    """language='multi' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003627() -> None:
    """language='multi' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003628() -> None:
    """language='multi' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003629() -> None:
    """language='multi' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'multi', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003630() -> None:
    """language='' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003631() -> None:
    """language='' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003632() -> None:
    """language='' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003633() -> None:
    """language='' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003634() -> None:
    """language='' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003635() -> None:
    """language='' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003636() -> None:
    """language='' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003637() -> None:
    """language='' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003638() -> None:
    """language='' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003639() -> None:
    """language='' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003640() -> None:
    """language='' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003641() -> None:
    """language='' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003642() -> None:
    """language='' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003643() -> None:
    """language='' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003644() -> None:
    """language='' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003645() -> None:
    """language='' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003646() -> None:
    """language='' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003647() -> None:
    """language='' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003648() -> None:
    """language='' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003649() -> None:
    """language='' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003650() -> None:
    """language='' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003651() -> None:
    """language='' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003652() -> None:
    """language='' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003653() -> None:
    """language='' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003654() -> None:
    """language='' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003655() -> None:
    """language='' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003656() -> None:
    """language='' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003657() -> None:
    """language='' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003658() -> None:
    """language='' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003659() -> None:
    """language='' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003660() -> None:
    """language='' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003661() -> None:
    """language='' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003662() -> None:
    """language='' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003663() -> None:
    """language='' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003664() -> None:
    """language='' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003665() -> None:
    """language='' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003666() -> None:
    """language='' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003667() -> None:
    """language='' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003668() -> None:
    """language='' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003669() -> None:
    """language='' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003670() -> None:
    """language='' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003671() -> None:
    """language='' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003672() -> None:
    """language='' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003673() -> None:
    """language='' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003674() -> None:
    """language='' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003675() -> None:
    """language='' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003676() -> None:
    """language='' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003677() -> None:
    """language='' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003678() -> None:
    """language='' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003679() -> None:
    """language='' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003680() -> None:
    """language='' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003681() -> None:
    """language='' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003682() -> None:
    """language='' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003683() -> None:
    """language='' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003684() -> None:
    """language='' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003685() -> None:
    """language='' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003686() -> None:
    """language='' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003687() -> None:
    """language='' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003688() -> None:
    """language='' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003689() -> None:
    """language='' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003690() -> None:
    """language='' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003691() -> None:
    """language='' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003692() -> None:
    """language='' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003693() -> None:
    """language='' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003694() -> None:
    """language='' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003695() -> None:
    """language='' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003696() -> None:
    """language='' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003697() -> None:
    """language='' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003698() -> None:
    """language='' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003699() -> None:
    """language='' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003700() -> None:
    """language='' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003701() -> None:
    """language='' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003702() -> None:
    """language='' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003703() -> None:
    """language='' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003704() -> None:
    """language='' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003705() -> None:
    """language='' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003706() -> None:
    """language='' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003707() -> None:
    """language='' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003708() -> None:
    """language='' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003709() -> None:
    """language='' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003710() -> None:
    """language='' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003711() -> None:
    """language='' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003712() -> None:
    """language='' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003713() -> None:
    """language='' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003714() -> None:
    """language='' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003715() -> None:
    """language='' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003716() -> None:
    """language='' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003717() -> None:
    """language='' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003718() -> None:
    """language='' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003719() -> None:
    """language='' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003720() -> None:
    """language='' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003721() -> None:
    """language='' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003722() -> None:
    """language='' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003723() -> None:
    """language='' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003724() -> None:
    """language='' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003725() -> None:
    """language='' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003726() -> None:
    """language='' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003727() -> None:
    """language='' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003728() -> None:
    """language='' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003729() -> None:
    """language='' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003730() -> None:
    """language='' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003731() -> None:
    """language='' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003732() -> None:
    """language='' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003733() -> None:
    """language='' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003734() -> None:
    """language='' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003735() -> None:
    """language='' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003736() -> None:
    """language='' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003737() -> None:
    """language='' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003738() -> None:
    """language='' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003739() -> None:
    """language='' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003740() -> None:
    """language='' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003741() -> None:
    """language='' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003742() -> None:
    """language='' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003743() -> None:
    """language='' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003744() -> None:
    """language='' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003745() -> None:
    """language='' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003746() -> None:
    """language='' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003747() -> None:
    """language='' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003748() -> None:
    """language='' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003749() -> None:
    """language='' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003750() -> None:
    """language='' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': '', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003751() -> None:
    """language='pt-BR' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003752() -> None:
    """language='pt-BR' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003753() -> None:
    """language='pt-BR' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003754() -> None:
    """language='pt-BR' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003755() -> None:
    """language='pt-BR' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003756() -> None:
    """language='pt-BR' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003757() -> None:
    """language='pt-BR' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003758() -> None:
    """language='pt-BR' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003759() -> None:
    """language='pt-BR' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003760() -> None:
    """language='pt-BR' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003761() -> None:
    """language='pt-BR' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003762() -> None:
    """language='pt-BR' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003763() -> None:
    """language='pt-BR' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003764() -> None:
    """language='pt-BR' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003765() -> None:
    """language='pt-BR' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003766() -> None:
    """language='pt-BR' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003767() -> None:
    """language='pt-BR' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003768() -> None:
    """language='pt-BR' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003769() -> None:
    """language='pt-BR' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003770() -> None:
    """language='pt-BR' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003771() -> None:
    """language='pt-BR' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003772() -> None:
    """language='pt-BR' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003773() -> None:
    """language='pt-BR' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003774() -> None:
    """language='pt-BR' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003775() -> None:
    """language='pt-BR' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003776() -> None:
    """language='pt-BR' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003777() -> None:
    """language='pt-BR' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003778() -> None:
    """language='pt-BR' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003779() -> None:
    """language='pt-BR' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003780() -> None:
    """language='pt-BR' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003781() -> None:
    """language='pt-BR' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003782() -> None:
    """language='pt-BR' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003783() -> None:
    """language='pt-BR' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003784() -> None:
    """language='pt-BR' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003785() -> None:
    """language='pt-BR' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003786() -> None:
    """language='pt-BR' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003787() -> None:
    """language='pt-BR' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003788() -> None:
    """language='pt-BR' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003789() -> None:
    """language='pt-BR' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003790() -> None:
    """language='pt-BR' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003791() -> None:
    """language='pt-BR' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003792() -> None:
    """language='pt-BR' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003793() -> None:
    """language='pt-BR' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003794() -> None:
    """language='pt-BR' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003795() -> None:
    """language='pt-BR' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003796() -> None:
    """language='pt-BR' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003797() -> None:
    """language='pt-BR' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003798() -> None:
    """language='pt-BR' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003799() -> None:
    """language='pt-BR' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003800() -> None:
    """language='pt-BR' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003801() -> None:
    """language='pt-BR' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003802() -> None:
    """language='pt-BR' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003803() -> None:
    """language='pt-BR' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003804() -> None:
    """language='pt-BR' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003805() -> None:
    """language='pt-BR' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003806() -> None:
    """language='pt-BR' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003807() -> None:
    """language='pt-BR' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003808() -> None:
    """language='pt-BR' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003809() -> None:
    """language='pt-BR' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003810() -> None:
    """language='pt-BR' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003811() -> None:
    """language='pt-BR' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003812() -> None:
    """language='pt-BR' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003813() -> None:
    """language='pt-BR' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003814() -> None:
    """language='pt-BR' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003815() -> None:
    """language='pt-BR' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003816() -> None:
    """language='pt-BR' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003817() -> None:
    """language='pt-BR' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003818() -> None:
    """language='pt-BR' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003819() -> None:
    """language='pt-BR' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003820() -> None:
    """language='pt-BR' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003821() -> None:
    """language='pt-BR' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003822() -> None:
    """language='pt-BR' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003823() -> None:
    """language='pt-BR' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003824() -> None:
    """language='pt-BR' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003825() -> None:
    """language='pt-BR' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003826() -> None:
    """language='pt-BR' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003827() -> None:
    """language='pt-BR' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003828() -> None:
    """language='pt-BR' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003829() -> None:
    """language='pt-BR' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003830() -> None:
    """language='pt-BR' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003831() -> None:
    """language='pt-BR' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003832() -> None:
    """language='pt-BR' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003833() -> None:
    """language='pt-BR' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003834() -> None:
    """language='pt-BR' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003835() -> None:
    """language='pt-BR' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003836() -> None:
    """language='pt-BR' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003837() -> None:
    """language='pt-BR' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003838() -> None:
    """language='pt-BR' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003839() -> None:
    """language='pt-BR' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003840() -> None:
    """language='pt-BR' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003841() -> None:
    """language='pt-BR' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003842() -> None:
    """language='pt-BR' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003843() -> None:
    """language='pt-BR' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003844() -> None:
    """language='pt-BR' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003845() -> None:
    """language='pt-BR' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003846() -> None:
    """language='pt-BR' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003847() -> None:
    """language='pt-BR' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003848() -> None:
    """language='pt-BR' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003849() -> None:
    """language='pt-BR' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003850() -> None:
    """language='pt-BR' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003851() -> None:
    """language='pt-BR' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003852() -> None:
    """language='pt-BR' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003853() -> None:
    """language='pt-BR' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003854() -> None:
    """language='pt-BR' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003855() -> None:
    """language='pt-BR' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003856() -> None:
    """language='pt-BR' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003857() -> None:
    """language='pt-BR' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003858() -> None:
    """language='pt-BR' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003859() -> None:
    """language='pt-BR' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003860() -> None:
    """language='pt-BR' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003861() -> None:
    """language='pt-BR' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003862() -> None:
    """language='pt-BR' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003863() -> None:
    """language='pt-BR' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003864() -> None:
    """language='pt-BR' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003865() -> None:
    """language='pt-BR' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003866() -> None:
    """language='pt-BR' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003867() -> None:
    """language='pt-BR' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003868() -> None:
    """language='pt-BR' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003869() -> None:
    """language='pt-BR' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003870() -> None:
    """language='pt-BR' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003871() -> None:
    """language='pt-BR' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'pt-BR', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003872() -> None:
    """language='en-US' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003873() -> None:
    """language='en-US' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003874() -> None:
    """language='en-US' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003875() -> None:
    """language='en-US' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003876() -> None:
    """language='en-US' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003877() -> None:
    """language='en-US' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003878() -> None:
    """language='en-US' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c003879() -> None:
    """language='en-US' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c003880() -> None:
    """language='en-US' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c003881() -> None:
    """language='en-US' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c003882() -> None:
    """language='en-US' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c003883() -> None:
    """language='en-US' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c003884() -> None:
    """language='en-US' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c003885() -> None:
    """language='en-US' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c003886() -> None:
    """language='en-US' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c003887() -> None:
    """language='en-US' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c003888() -> None:
    """language='en-US' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c003889() -> None:
    """language='en-US' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c003890() -> None:
    """language='en-US' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c003891() -> None:
    """language='en-US' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c003892() -> None:
    """language='en-US' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c003893() -> None:
    """language='en-US' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c003894() -> None:
    """language='en-US' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c003895() -> None:
    """language='en-US' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c003896() -> None:
    """language='en-US' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c003897() -> None:
    """language='en-US' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c003898() -> None:
    """language='en-US' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c003899() -> None:
    """language='en-US' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c003900() -> None:
    """language='en-US' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c003901() -> None:
    """language='en-US' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c003902() -> None:
    """language='en-US' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c003903() -> None:
    """language='en-US' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c003904() -> None:
    """language='en-US' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c003905() -> None:
    """language='en-US' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c003906() -> None:
    """language='en-US' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c003907() -> None:
    """language='en-US' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c003908() -> None:
    """language='en-US' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c003909() -> None:
    """language='en-US' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c003910() -> None:
    """language='en-US' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c003911() -> None:
    """language='en-US' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c003912() -> None:
    """language='en-US' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c003913() -> None:
    """language='en-US' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c003914() -> None:
    """language='en-US' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c003915() -> None:
    """language='en-US' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c003916() -> None:
    """language='en-US' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c003917() -> None:
    """language='en-US' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c003918() -> None:
    """language='en-US' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c003919() -> None:
    """language='en-US' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c003920() -> None:
    """language='en-US' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c003921() -> None:
    """language='en-US' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c003922() -> None:
    """language='en-US' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c003923() -> None:
    """language='en-US' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c003924() -> None:
    """language='en-US' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c003925() -> None:
    """language='en-US' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c003926() -> None:
    """language='en-US' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c003927() -> None:
    """language='en-US' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c003928() -> None:
    """language='en-US' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c003929() -> None:
    """language='en-US' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c003930() -> None:
    """language='en-US' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c003931() -> None:
    """language='en-US' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c003932() -> None:
    """language='en-US' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c003933() -> None:
    """language='en-US' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c003934() -> None:
    """language='en-US' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c003935() -> None:
    """language='en-US' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c003936() -> None:
    """language='en-US' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c003937() -> None:
    """language='en-US' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c003938() -> None:
    """language='en-US' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c003939() -> None:
    """language='en-US' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c003940() -> None:
    """language='en-US' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c003941() -> None:
    """language='en-US' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c003942() -> None:
    """language='en-US' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c003943() -> None:
    """language='en-US' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c003944() -> None:
    """language='en-US' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c003945() -> None:
    """language='en-US' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c003946() -> None:
    """language='en-US' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c003947() -> None:
    """language='en-US' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c003948() -> None:
    """language='en-US' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c003949() -> None:
    """language='en-US' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c003950() -> None:
    """language='en-US' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c003951() -> None:
    """language='en-US' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c003952() -> None:
    """language='en-US' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c003953() -> None:
    """language='en-US' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c003954() -> None:
    """language='en-US' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c003955() -> None:
    """language='en-US' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c003956() -> None:
    """language='en-US' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c003957() -> None:
    """language='en-US' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c003958() -> None:
    """language='en-US' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c003959() -> None:
    """language='en-US' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c003960() -> None:
    """language='en-US' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c003961() -> None:
    """language='en-US' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c003962() -> None:
    """language='en-US' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c003963() -> None:
    """language='en-US' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c003964() -> None:
    """language='en-US' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c003965() -> None:
    """language='en-US' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c003966() -> None:
    """language='en-US' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c003967() -> None:
    """language='en-US' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c003968() -> None:
    """language='en-US' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c003969() -> None:
    """language='en-US' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c003970() -> None:
    """language='en-US' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c003971() -> None:
    """language='en-US' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c003972() -> None:
    """language='en-US' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c003973() -> None:
    """language='en-US' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c003974() -> None:
    """language='en-US' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c003975() -> None:
    """language='en-US' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c003976() -> None:
    """language='en-US' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c003977() -> None:
    """language='en-US' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c003978() -> None:
    """language='en-US' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c003979() -> None:
    """language='en-US' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c003980() -> None:
    """language='en-US' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c003981() -> None:
    """language='en-US' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c003982() -> None:
    """language='en-US' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c003983() -> None:
    """language='en-US' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c003984() -> None:
    """language='en-US' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c003985() -> None:
    """language='en-US' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c003986() -> None:
    """language='en-US' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c003987() -> None:
    """language='en-US' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c003988() -> None:
    """language='en-US' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c003989() -> None:
    """language='en-US' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c003990() -> None:
    """language='en-US' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c003991() -> None:
    """language='en-US' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c003992() -> None:
    """language='en-US' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'en-US', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c003993() -> None:
    """language='fr-CA' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c003994() -> None:
    """language='fr-CA' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c003995() -> None:
    """language='fr-CA' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c003996() -> None:
    """language='fr-CA' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c003997() -> None:
    """language='fr-CA' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c003998() -> None:
    """language='fr-CA' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c003999() -> None:
    """language='fr-CA' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c004000() -> None:
    """language='fr-CA' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c004001() -> None:
    """language='fr-CA' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c004002() -> None:
    """language='fr-CA' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c004003() -> None:
    """language='fr-CA' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c004004() -> None:
    """language='fr-CA' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c004005() -> None:
    """language='fr-CA' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c004006() -> None:
    """language='fr-CA' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c004007() -> None:
    """language='fr-CA' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c004008() -> None:
    """language='fr-CA' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c004009() -> None:
    """language='fr-CA' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c004010() -> None:
    """language='fr-CA' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c004011() -> None:
    """language='fr-CA' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c004012() -> None:
    """language='fr-CA' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c004013() -> None:
    """language='fr-CA' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c004014() -> None:
    """language='fr-CA' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c004015() -> None:
    """language='fr-CA' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c004016() -> None:
    """language='fr-CA' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c004017() -> None:
    """language='fr-CA' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c004018() -> None:
    """language='fr-CA' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c004019() -> None:
    """language='fr-CA' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c004020() -> None:
    """language='fr-CA' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c004021() -> None:
    """language='fr-CA' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c004022() -> None:
    """language='fr-CA' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c004023() -> None:
    """language='fr-CA' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c004024() -> None:
    """language='fr-CA' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c004025() -> None:
    """language='fr-CA' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c004026() -> None:
    """language='fr-CA' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c004027() -> None:
    """language='fr-CA' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c004028() -> None:
    """language='fr-CA' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c004029() -> None:
    """language='fr-CA' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c004030() -> None:
    """language='fr-CA' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c004031() -> None:
    """language='fr-CA' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c004032() -> None:
    """language='fr-CA' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c004033() -> None:
    """language='fr-CA' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c004034() -> None:
    """language='fr-CA' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c004035() -> None:
    """language='fr-CA' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c004036() -> None:
    """language='fr-CA' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c004037() -> None:
    """language='fr-CA' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c004038() -> None:
    """language='fr-CA' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c004039() -> None:
    """language='fr-CA' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c004040() -> None:
    """language='fr-CA' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c004041() -> None:
    """language='fr-CA' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c004042() -> None:
    """language='fr-CA' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c004043() -> None:
    """language='fr-CA' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c004044() -> None:
    """language='fr-CA' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c004045() -> None:
    """language='fr-CA' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c004046() -> None:
    """language='fr-CA' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c004047() -> None:
    """language='fr-CA' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c004048() -> None:
    """language='fr-CA' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c004049() -> None:
    """language='fr-CA' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c004050() -> None:
    """language='fr-CA' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c004051() -> None:
    """language='fr-CA' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c004052() -> None:
    """language='fr-CA' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c004053() -> None:
    """language='fr-CA' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c004054() -> None:
    """language='fr-CA' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c004055() -> None:
    """language='fr-CA' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c004056() -> None:
    """language='fr-CA' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c004057() -> None:
    """language='fr-CA' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c004058() -> None:
    """language='fr-CA' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c004059() -> None:
    """language='fr-CA' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c004060() -> None:
    """language='fr-CA' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c004061() -> None:
    """language='fr-CA' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c004062() -> None:
    """language='fr-CA' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c004063() -> None:
    """language='fr-CA' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c004064() -> None:
    """language='fr-CA' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c004065() -> None:
    """language='fr-CA' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c004066() -> None:
    """language='fr-CA' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c004067() -> None:
    """language='fr-CA' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c004068() -> None:
    """language='fr-CA' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c004069() -> None:
    """language='fr-CA' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c004070() -> None:
    """language='fr-CA' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c004071() -> None:
    """language='fr-CA' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c004072() -> None:
    """language='fr-CA' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c004073() -> None:
    """language='fr-CA' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c004074() -> None:
    """language='fr-CA' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c004075() -> None:
    """language='fr-CA' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c004076() -> None:
    """language='fr-CA' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c004077() -> None:
    """language='fr-CA' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c004078() -> None:
    """language='fr-CA' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c004079() -> None:
    """language='fr-CA' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c004080() -> None:
    """language='fr-CA' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c004081() -> None:
    """language='fr-CA' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c004082() -> None:
    """language='fr-CA' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c004083() -> None:
    """language='fr-CA' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c004084() -> None:
    """language='fr-CA' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c004085() -> None:
    """language='fr-CA' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c004086() -> None:
    """language='fr-CA' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c004087() -> None:
    """language='fr-CA' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c004088() -> None:
    """language='fr-CA' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c004089() -> None:
    """language='fr-CA' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c004090() -> None:
    """language='fr-CA' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c004091() -> None:
    """language='fr-CA' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c004092() -> None:
    """language='fr-CA' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c004093() -> None:
    """language='fr-CA' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c004094() -> None:
    """language='fr-CA' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c004095() -> None:
    """language='fr-CA' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c004096() -> None:
    """language='fr-CA' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c004097() -> None:
    """language='fr-CA' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c004098() -> None:
    """language='fr-CA' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c004099() -> None:
    """language='fr-CA' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c004100() -> None:
    """language='fr-CA' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c004101() -> None:
    """language='fr-CA' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c004102() -> None:
    """language='fr-CA' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c004103() -> None:
    """language='fr-CA' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c004104() -> None:
    """language='fr-CA' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c004105() -> None:
    """language='fr-CA' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c004106() -> None:
    """language='fr-CA' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c004107() -> None:
    """language='fr-CA' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c004108() -> None:
    """language='fr-CA' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c004109() -> None:
    """language='fr-CA' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c004110() -> None:
    """language='fr-CA' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c004111() -> None:
    """language='fr-CA' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c004112() -> None:
    """language='fr-CA' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c004113() -> None:
    """language='fr-CA' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'fr-CA', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c004114() -> None:
    """language='es-419' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c004115() -> None:
    """language='es-419' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c004116() -> None:
    """language='es-419' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c004117() -> None:
    """language='es-419' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c004118() -> None:
    """language='es-419' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c004119() -> None:
    """language='es-419' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c004120() -> None:
    """language='es-419' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c004121() -> None:
    """language='es-419' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c004122() -> None:
    """language='es-419' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c004123() -> None:
    """language='es-419' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c004124() -> None:
    """language='es-419' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c004125() -> None:
    """language='es-419' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c004126() -> None:
    """language='es-419' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c004127() -> None:
    """language='es-419' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c004128() -> None:
    """language='es-419' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c004129() -> None:
    """language='es-419' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c004130() -> None:
    """language='es-419' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c004131() -> None:
    """language='es-419' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c004132() -> None:
    """language='es-419' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c004133() -> None:
    """language='es-419' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c004134() -> None:
    """language='es-419' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c004135() -> None:
    """language='es-419' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c004136() -> None:
    """language='es-419' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c004137() -> None:
    """language='es-419' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c004138() -> None:
    """language='es-419' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c004139() -> None:
    """language='es-419' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c004140() -> None:
    """language='es-419' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c004141() -> None:
    """language='es-419' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c004142() -> None:
    """language='es-419' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c004143() -> None:
    """language='es-419' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c004144() -> None:
    """language='es-419' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c004145() -> None:
    """language='es-419' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c004146() -> None:
    """language='es-419' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c004147() -> None:
    """language='es-419' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c004148() -> None:
    """language='es-419' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c004149() -> None:
    """language='es-419' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c004150() -> None:
    """language='es-419' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c004151() -> None:
    """language='es-419' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c004152() -> None:
    """language='es-419' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c004153() -> None:
    """language='es-419' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c004154() -> None:
    """language='es-419' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c004155() -> None:
    """language='es-419' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c004156() -> None:
    """language='es-419' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c004157() -> None:
    """language='es-419' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c004158() -> None:
    """language='es-419' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c004159() -> None:
    """language='es-419' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c004160() -> None:
    """language='es-419' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c004161() -> None:
    """language='es-419' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c004162() -> None:
    """language='es-419' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c004163() -> None:
    """language='es-419' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c004164() -> None:
    """language='es-419' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c004165() -> None:
    """language='es-419' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c004166() -> None:
    """language='es-419' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c004167() -> None:
    """language='es-419' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c004168() -> None:
    """language='es-419' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c004169() -> None:
    """language='es-419' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c004170() -> None:
    """language='es-419' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c004171() -> None:
    """language='es-419' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c004172() -> None:
    """language='es-419' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c004173() -> None:
    """language='es-419' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c004174() -> None:
    """language='es-419' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c004175() -> None:
    """language='es-419' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c004176() -> None:
    """language='es-419' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c004177() -> None:
    """language='es-419' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c004178() -> None:
    """language='es-419' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c004179() -> None:
    """language='es-419' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c004180() -> None:
    """language='es-419' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c004181() -> None:
    """language='es-419' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c004182() -> None:
    """language='es-419' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c004183() -> None:
    """language='es-419' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c004184() -> None:
    """language='es-419' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c004185() -> None:
    """language='es-419' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c004186() -> None:
    """language='es-419' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c004187() -> None:
    """language='es-419' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c004188() -> None:
    """language='es-419' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c004189() -> None:
    """language='es-419' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c004190() -> None:
    """language='es-419' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c004191() -> None:
    """language='es-419' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c004192() -> None:
    """language='es-419' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c004193() -> None:
    """language='es-419' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c004194() -> None:
    """language='es-419' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c004195() -> None:
    """language='es-419' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c004196() -> None:
    """language='es-419' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c004197() -> None:
    """language='es-419' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c004198() -> None:
    """language='es-419' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c004199() -> None:
    """language='es-419' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c004200() -> None:
    """language='es-419' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c004201() -> None:
    """language='es-419' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c004202() -> None:
    """language='es-419' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c004203() -> None:
    """language='es-419' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c004204() -> None:
    """language='es-419' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c004205() -> None:
    """language='es-419' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c004206() -> None:
    """language='es-419' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c004207() -> None:
    """language='es-419' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c004208() -> None:
    """language='es-419' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c004209() -> None:
    """language='es-419' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c004210() -> None:
    """language='es-419' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c004211() -> None:
    """language='es-419' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c004212() -> None:
    """language='es-419' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c004213() -> None:
    """language='es-419' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c004214() -> None:
    """language='es-419' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c004215() -> None:
    """language='es-419' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c004216() -> None:
    """language='es-419' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c004217() -> None:
    """language='es-419' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c004218() -> None:
    """language='es-419' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c004219() -> None:
    """language='es-419' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c004220() -> None:
    """language='es-419' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c004221() -> None:
    """language='es-419' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c004222() -> None:
    """language='es-419' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c004223() -> None:
    """language='es-419' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c004224() -> None:
    """language='es-419' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c004225() -> None:
    """language='es-419' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c004226() -> None:
    """language='es-419' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c004227() -> None:
    """language='es-419' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c004228() -> None:
    """language='es-419' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c004229() -> None:
    """language='es-419' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c004230() -> None:
    """language='es-419' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c004231() -> None:
    """language='es-419' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c004232() -> None:
    """language='es-419' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c004233() -> None:
    """language='es-419' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c004234() -> None:
    """language='es-419' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'es-419', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c004235() -> None:
    """language='yue' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c004236() -> None:
    """language='yue' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c004237() -> None:
    """language='yue' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c004238() -> None:
    """language='yue' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c004239() -> None:
    """language='yue' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c004240() -> None:
    """language='yue' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c004241() -> None:
    """language='yue' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c004242() -> None:
    """language='yue' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c004243() -> None:
    """language='yue' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c004244() -> None:
    """language='yue' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c004245() -> None:
    """language='yue' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c004246() -> None:
    """language='yue' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c004247() -> None:
    """language='yue' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c004248() -> None:
    """language='yue' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c004249() -> None:
    """language='yue' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c004250() -> None:
    """language='yue' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c004251() -> None:
    """language='yue' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c004252() -> None:
    """language='yue' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c004253() -> None:
    """language='yue' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c004254() -> None:
    """language='yue' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c004255() -> None:
    """language='yue' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c004256() -> None:
    """language='yue' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c004257() -> None:
    """language='yue' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c004258() -> None:
    """language='yue' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c004259() -> None:
    """language='yue' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c004260() -> None:
    """language='yue' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c004261() -> None:
    """language='yue' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c004262() -> None:
    """language='yue' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c004263() -> None:
    """language='yue' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c004264() -> None:
    """language='yue' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c004265() -> None:
    """language='yue' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c004266() -> None:
    """language='yue' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c004267() -> None:
    """language='yue' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c004268() -> None:
    """language='yue' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c004269() -> None:
    """language='yue' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c004270() -> None:
    """language='yue' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c004271() -> None:
    """language='yue' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c004272() -> None:
    """language='yue' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c004273() -> None:
    """language='yue' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c004274() -> None:
    """language='yue' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c004275() -> None:
    """language='yue' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c004276() -> None:
    """language='yue' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c004277() -> None:
    """language='yue' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c004278() -> None:
    """language='yue' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c004279() -> None:
    """language='yue' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c004280() -> None:
    """language='yue' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c004281() -> None:
    """language='yue' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c004282() -> None:
    """language='yue' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c004283() -> None:
    """language='yue' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c004284() -> None:
    """language='yue' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c004285() -> None:
    """language='yue' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c004286() -> None:
    """language='yue' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c004287() -> None:
    """language='yue' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c004288() -> None:
    """language='yue' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c004289() -> None:
    """language='yue' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c004290() -> None:
    """language='yue' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c004291() -> None:
    """language='yue' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c004292() -> None:
    """language='yue' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c004293() -> None:
    """language='yue' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c004294() -> None:
    """language='yue' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c004295() -> None:
    """language='yue' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c004296() -> None:
    """language='yue' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c004297() -> None:
    """language='yue' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c004298() -> None:
    """language='yue' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c004299() -> None:
    """language='yue' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c004300() -> None:
    """language='yue' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c004301() -> None:
    """language='yue' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c004302() -> None:
    """language='yue' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c004303() -> None:
    """language='yue' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c004304() -> None:
    """language='yue' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c004305() -> None:
    """language='yue' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c004306() -> None:
    """language='yue' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c004307() -> None:
    """language='yue' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c004308() -> None:
    """language='yue' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c004309() -> None:
    """language='yue' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c004310() -> None:
    """language='yue' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c004311() -> None:
    """language='yue' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c004312() -> None:
    """language='yue' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c004313() -> None:
    """language='yue' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c004314() -> None:
    """language='yue' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c004315() -> None:
    """language='yue' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c004316() -> None:
    """language='yue' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c004317() -> None:
    """language='yue' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c004318() -> None:
    """language='yue' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c004319() -> None:
    """language='yue' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c004320() -> None:
    """language='yue' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c004321() -> None:
    """language='yue' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c004322() -> None:
    """language='yue' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c004323() -> None:
    """language='yue' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c004324() -> None:
    """language='yue' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c004325() -> None:
    """language='yue' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c004326() -> None:
    """language='yue' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c004327() -> None:
    """language='yue' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c004328() -> None:
    """language='yue' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c004329() -> None:
    """language='yue' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c004330() -> None:
    """language='yue' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c004331() -> None:
    """language='yue' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c004332() -> None:
    """language='yue' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c004333() -> None:
    """language='yue' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c004334() -> None:
    """language='yue' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c004335() -> None:
    """language='yue' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c004336() -> None:
    """language='yue' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c004337() -> None:
    """language='yue' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c004338() -> None:
    """language='yue' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c004339() -> None:
    """language='yue' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c004340() -> None:
    """language='yue' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c004341() -> None:
    """language='yue' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c004342() -> None:
    """language='yue' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c004343() -> None:
    """language='yue' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c004344() -> None:
    """language='yue' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c004345() -> None:
    """language='yue' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c004346() -> None:
    """language='yue' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c004347() -> None:
    """language='yue' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c004348() -> None:
    """language='yue' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c004349() -> None:
    """language='yue' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c004350() -> None:
    """language='yue' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c004351() -> None:
    """language='yue' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c004352() -> None:
    """language='yue' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c004353() -> None:
    """language='yue' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c004354() -> None:
    """language='yue' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c004355() -> None:
    """language='yue' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'yue', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c004356() -> None:
    """language='ar' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c004357() -> None:
    """language='ar' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c004358() -> None:
    """language='ar' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c004359() -> None:
    """language='ar' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c004360() -> None:
    """language='ar' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c004361() -> None:
    """language='ar' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c004362() -> None:
    """language='ar' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c004363() -> None:
    """language='ar' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c004364() -> None:
    """language='ar' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c004365() -> None:
    """language='ar' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c004366() -> None:
    """language='ar' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c004367() -> None:
    """language='ar' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c004368() -> None:
    """language='ar' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c004369() -> None:
    """language='ar' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c004370() -> None:
    """language='ar' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c004371() -> None:
    """language='ar' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c004372() -> None:
    """language='ar' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c004373() -> None:
    """language='ar' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c004374() -> None:
    """language='ar' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c004375() -> None:
    """language='ar' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c004376() -> None:
    """language='ar' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c004377() -> None:
    """language='ar' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c004378() -> None:
    """language='ar' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c004379() -> None:
    """language='ar' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c004380() -> None:
    """language='ar' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c004381() -> None:
    """language='ar' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c004382() -> None:
    """language='ar' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c004383() -> None:
    """language='ar' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c004384() -> None:
    """language='ar' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c004385() -> None:
    """language='ar' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c004386() -> None:
    """language='ar' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c004387() -> None:
    """language='ar' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c004388() -> None:
    """language='ar' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c004389() -> None:
    """language='ar' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c004390() -> None:
    """language='ar' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c004391() -> None:
    """language='ar' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c004392() -> None:
    """language='ar' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c004393() -> None:
    """language='ar' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c004394() -> None:
    """language='ar' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c004395() -> None:
    """language='ar' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c004396() -> None:
    """language='ar' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c004397() -> None:
    """language='ar' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c004398() -> None:
    """language='ar' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c004399() -> None:
    """language='ar' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c004400() -> None:
    """language='ar' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c004401() -> None:
    """language='ar' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c004402() -> None:
    """language='ar' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c004403() -> None:
    """language='ar' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c004404() -> None:
    """language='ar' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c004405() -> None:
    """language='ar' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c004406() -> None:
    """language='ar' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c004407() -> None:
    """language='ar' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c004408() -> None:
    """language='ar' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c004409() -> None:
    """language='ar' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c004410() -> None:
    """language='ar' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c004411() -> None:
    """language='ar' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c004412() -> None:
    """language='ar' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c004413() -> None:
    """language='ar' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c004414() -> None:
    """language='ar' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c004415() -> None:
    """language='ar' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c004416() -> None:
    """language='ar' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c004417() -> None:
    """language='ar' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c004418() -> None:
    """language='ar' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c004419() -> None:
    """language='ar' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c004420() -> None:
    """language='ar' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c004421() -> None:
    """language='ar' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c004422() -> None:
    """language='ar' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c004423() -> None:
    """language='ar' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c004424() -> None:
    """language='ar' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c004425() -> None:
    """language='ar' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c004426() -> None:
    """language='ar' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c004427() -> None:
    """language='ar' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c004428() -> None:
    """language='ar' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c004429() -> None:
    """language='ar' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c004430() -> None:
    """language='ar' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c004431() -> None:
    """language='ar' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c004432() -> None:
    """language='ar' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c004433() -> None:
    """language='ar' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c004434() -> None:
    """language='ar' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c004435() -> None:
    """language='ar' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c004436() -> None:
    """language='ar' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c004437() -> None:
    """language='ar' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c004438() -> None:
    """language='ar' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c004439() -> None:
    """language='ar' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c004440() -> None:
    """language='ar' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c004441() -> None:
    """language='ar' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c004442() -> None:
    """language='ar' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c004443() -> None:
    """language='ar' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c004444() -> None:
    """language='ar' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c004445() -> None:
    """language='ar' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c004446() -> None:
    """language='ar' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c004447() -> None:
    """language='ar' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c004448() -> None:
    """language='ar' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c004449() -> None:
    """language='ar' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c004450() -> None:
    """language='ar' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c004451() -> None:
    """language='ar' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c004452() -> None:
    """language='ar' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c004453() -> None:
    """language='ar' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c004454() -> None:
    """language='ar' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c004455() -> None:
    """language='ar' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c004456() -> None:
    """language='ar' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c004457() -> None:
    """language='ar' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c004458() -> None:
    """language='ar' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c004459() -> None:
    """language='ar' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c004460() -> None:
    """language='ar' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c004461() -> None:
    """language='ar' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c004462() -> None:
    """language='ar' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c004463() -> None:
    """language='ar' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c004464() -> None:
    """language='ar' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c004465() -> None:
    """language='ar' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c004466() -> None:
    """language='ar' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c004467() -> None:
    """language='ar' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c004468() -> None:
    """language='ar' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c004469() -> None:
    """language='ar' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c004470() -> None:
    """language='ar' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c004471() -> None:
    """language='ar' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c004472() -> None:
    """language='ar' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c004473() -> None:
    """language='ar' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c004474() -> None:
    """language='ar' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c004475() -> None:
    """language='ar' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c004476() -> None:
    """language='ar' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'ar', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c004477() -> None:
    """language='hi' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c004478() -> None:
    """language='hi' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c004479() -> None:
    """language='hi' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c004480() -> None:
    """language='hi' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c004481() -> None:
    """language='hi' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c004482() -> None:
    """language='hi' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c004483() -> None:
    """language='hi' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c004484() -> None:
    """language='hi' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c004485() -> None:
    """language='hi' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c004486() -> None:
    """language='hi' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c004487() -> None:
    """language='hi' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c004488() -> None:
    """language='hi' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c004489() -> None:
    """language='hi' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c004490() -> None:
    """language='hi' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c004491() -> None:
    """language='hi' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c004492() -> None:
    """language='hi' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c004493() -> None:
    """language='hi' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c004494() -> None:
    """language='hi' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c004495() -> None:
    """language='hi' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c004496() -> None:
    """language='hi' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c004497() -> None:
    """language='hi' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c004498() -> None:
    """language='hi' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c004499() -> None:
    """language='hi' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c004500() -> None:
    """language='hi' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c004501() -> None:
    """language='hi' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c004502() -> None:
    """language='hi' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c004503() -> None:
    """language='hi' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c004504() -> None:
    """language='hi' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c004505() -> None:
    """language='hi' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c004506() -> None:
    """language='hi' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c004507() -> None:
    """language='hi' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c004508() -> None:
    """language='hi' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c004509() -> None:
    """language='hi' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c004510() -> None:
    """language='hi' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c004511() -> None:
    """language='hi' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c004512() -> None:
    """language='hi' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c004513() -> None:
    """language='hi' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c004514() -> None:
    """language='hi' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c004515() -> None:
    """language='hi' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c004516() -> None:
    """language='hi' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c004517() -> None:
    """language='hi' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c004518() -> None:
    """language='hi' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c004519() -> None:
    """language='hi' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c004520() -> None:
    """language='hi' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c004521() -> None:
    """language='hi' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c004522() -> None:
    """language='hi' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c004523() -> None:
    """language='hi' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c004524() -> None:
    """language='hi' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c004525() -> None:
    """language='hi' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c004526() -> None:
    """language='hi' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c004527() -> None:
    """language='hi' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c004528() -> None:
    """language='hi' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c004529() -> None:
    """language='hi' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c004530() -> None:
    """language='hi' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c004531() -> None:
    """language='hi' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c004532() -> None:
    """language='hi' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c004533() -> None:
    """language='hi' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c004534() -> None:
    """language='hi' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c004535() -> None:
    """language='hi' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c004536() -> None:
    """language='hi' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c004537() -> None:
    """language='hi' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c004538() -> None:
    """language='hi' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c004539() -> None:
    """language='hi' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c004540() -> None:
    """language='hi' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c004541() -> None:
    """language='hi' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c004542() -> None:
    """language='hi' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c004543() -> None:
    """language='hi' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c004544() -> None:
    """language='hi' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c004545() -> None:
    """language='hi' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c004546() -> None:
    """language='hi' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c004547() -> None:
    """language='hi' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c004548() -> None:
    """language='hi' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c004549() -> None:
    """language='hi' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c004550() -> None:
    """language='hi' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c004551() -> None:
    """language='hi' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c004552() -> None:
    """language='hi' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c004553() -> None:
    """language='hi' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c004554() -> None:
    """language='hi' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c004555() -> None:
    """language='hi' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c004556() -> None:
    """language='hi' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c004557() -> None:
    """language='hi' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c004558() -> None:
    """language='hi' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c004559() -> None:
    """language='hi' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c004560() -> None:
    """language='hi' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c004561() -> None:
    """language='hi' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c004562() -> None:
    """language='hi' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c004563() -> None:
    """language='hi' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c004564() -> None:
    """language='hi' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c004565() -> None:
    """language='hi' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c004566() -> None:
    """language='hi' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c004567() -> None:
    """language='hi' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c004568() -> None:
    """language='hi' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c004569() -> None:
    """language='hi' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c004570() -> None:
    """language='hi' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c004571() -> None:
    """language='hi' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c004572() -> None:
    """language='hi' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c004573() -> None:
    """language='hi' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c004574() -> None:
    """language='hi' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c004575() -> None:
    """language='hi' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c004576() -> None:
    """language='hi' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c004577() -> None:
    """language='hi' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c004578() -> None:
    """language='hi' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c004579() -> None:
    """language='hi' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c004580() -> None:
    """language='hi' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c004581() -> None:
    """language='hi' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c004582() -> None:
    """language='hi' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c004583() -> None:
    """language='hi' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c004584() -> None:
    """language='hi' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c004585() -> None:
    """language='hi' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c004586() -> None:
    """language='hi' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c004587() -> None:
    """language='hi' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c004588() -> None:
    """language='hi' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c004589() -> None:
    """language='hi' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c004590() -> None:
    """language='hi' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c004591() -> None:
    """language='hi' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c004592() -> None:
    """language='hi' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c004593() -> None:
    """language='hi' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c004594() -> None:
    """language='hi' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c004595() -> None:
    """language='hi' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c004596() -> None:
    """language='hi' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c004597() -> None:
    """language='hi' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'hi', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c004598() -> None:
    """language='VI' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c004599() -> None:
    """language='VI' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c004600() -> None:
    """language='VI' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c004601() -> None:
    """language='VI' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c004602() -> None:
    """language='VI' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c004603() -> None:
    """language='VI' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c004604() -> None:
    """language='VI' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c004605() -> None:
    """language='VI' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c004606() -> None:
    """language='VI' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c004607() -> None:
    """language='VI' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c004608() -> None:
    """language='VI' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c004609() -> None:
    """language='VI' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c004610() -> None:
    """language='VI' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c004611() -> None:
    """language='VI' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c004612() -> None:
    """language='VI' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c004613() -> None:
    """language='VI' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c004614() -> None:
    """language='VI' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c004615() -> None:
    """language='VI' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c004616() -> None:
    """language='VI' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c004617() -> None:
    """language='VI' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c004618() -> None:
    """language='VI' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c004619() -> None:
    """language='VI' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c004620() -> None:
    """language='VI' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c004621() -> None:
    """language='VI' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c004622() -> None:
    """language='VI' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c004623() -> None:
    """language='VI' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c004624() -> None:
    """language='VI' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c004625() -> None:
    """language='VI' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c004626() -> None:
    """language='VI' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c004627() -> None:
    """language='VI' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c004628() -> None:
    """language='VI' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c004629() -> None:
    """language='VI' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c004630() -> None:
    """language='VI' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c004631() -> None:
    """language='VI' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c004632() -> None:
    """language='VI' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c004633() -> None:
    """language='VI' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c004634() -> None:
    """language='VI' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c004635() -> None:
    """language='VI' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c004636() -> None:
    """language='VI' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c004637() -> None:
    """language='VI' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c004638() -> None:
    """language='VI' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c004639() -> None:
    """language='VI' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c004640() -> None:
    """language='VI' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c004641() -> None:
    """language='VI' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c004642() -> None:
    """language='VI' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c004643() -> None:
    """language='VI' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c004644() -> None:
    """language='VI' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c004645() -> None:
    """language='VI' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c004646() -> None:
    """language='VI' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c004647() -> None:
    """language='VI' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c004648() -> None:
    """language='VI' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c004649() -> None:
    """language='VI' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c004650() -> None:
    """language='VI' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c004651() -> None:
    """language='VI' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c004652() -> None:
    """language='VI' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c004653() -> None:
    """language='VI' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c004654() -> None:
    """language='VI' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c004655() -> None:
    """language='VI' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c004656() -> None:
    """language='VI' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c004657() -> None:
    """language='VI' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c004658() -> None:
    """language='VI' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c004659() -> None:
    """language='VI' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c004660() -> None:
    """language='VI' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c004661() -> None:
    """language='VI' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c004662() -> None:
    """language='VI' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c004663() -> None:
    """language='VI' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c004664() -> None:
    """language='VI' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c004665() -> None:
    """language='VI' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c004666() -> None:
    """language='VI' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c004667() -> None:
    """language='VI' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c004668() -> None:
    """language='VI' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c004669() -> None:
    """language='VI' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c004670() -> None:
    """language='VI' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c004671() -> None:
    """language='VI' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c004672() -> None:
    """language='VI' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c004673() -> None:
    """language='VI' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c004674() -> None:
    """language='VI' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c004675() -> None:
    """language='VI' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c004676() -> None:
    """language='VI' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c004677() -> None:
    """language='VI' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c004678() -> None:
    """language='VI' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c004679() -> None:
    """language='VI' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c004680() -> None:
    """language='VI' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c004681() -> None:
    """language='VI' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c004682() -> None:
    """language='VI' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c004683() -> None:
    """language='VI' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c004684() -> None:
    """language='VI' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c004685() -> None:
    """language='VI' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c004686() -> None:
    """language='VI' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c004687() -> None:
    """language='VI' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c004688() -> None:
    """language='VI' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c004689() -> None:
    """language='VI' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c004690() -> None:
    """language='VI' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c004691() -> None:
    """language='VI' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c004692() -> None:
    """language='VI' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c004693() -> None:
    """language='VI' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c004694() -> None:
    """language='VI' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c004695() -> None:
    """language='VI' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c004696() -> None:
    """language='VI' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c004697() -> None:
    """language='VI' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c004698() -> None:
    """language='VI' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c004699() -> None:
    """language='VI' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c004700() -> None:
    """language='VI' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c004701() -> None:
    """language='VI' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c004702() -> None:
    """language='VI' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c004703() -> None:
    """language='VI' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c004704() -> None:
    """language='VI' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c004705() -> None:
    """language='VI' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c004706() -> None:
    """language='VI' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c004707() -> None:
    """language='VI' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c004708() -> None:
    """language='VI' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c004709() -> None:
    """language='VI' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c004710() -> None:
    """language='VI' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c004711() -> None:
    """language='VI' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c004712() -> None:
    """language='VI' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c004713() -> None:
    """language='VI' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c004714() -> None:
    """language='VI' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c004715() -> None:
    """language='VI' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c004716() -> None:
    """language='VI' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c004717() -> None:
    """language='VI' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c004718() -> None:
    """language='VI' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': 'VI', 'speech_seconds': 6.0}, 'empty_asr') is False


def test_c004719() -> None:
    """language=' de' speech=0.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.0}, 'empty_asr') is False


def test_c004720() -> None:
    """language=' de' speech=0.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.05}, 'empty_asr') is False


def test_c004721() -> None:
    """language=' de' speech=0.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.1}, 'empty_asr') is False


def test_c004722() -> None:
    """language=' de' speech=0.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.15}, 'empty_asr') is False


def test_c004723() -> None:
    """language=' de' speech=0.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.2}, 'empty_asr') is False


def test_c004724() -> None:
    """language=' de' speech=0.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.25}, 'empty_asr') is False


def test_c004725() -> None:
    """language=' de' speech=0.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.3}, 'empty_asr') is False


def test_c004726() -> None:
    """language=' de' speech=0.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.35}, 'empty_asr') is False


def test_c004727() -> None:
    """language=' de' speech=0.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.4}, 'empty_asr') is False


def test_c004728() -> None:
    """language=' de' speech=0.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.45}, 'empty_asr') is False


def test_c004729() -> None:
    """language=' de' speech=0.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.5}, 'empty_asr') is False


def test_c004730() -> None:
    """language=' de' speech=0.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.55}, 'empty_asr') is False


def test_c004731() -> None:
    """language=' de' speech=0.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.6}, 'empty_asr') is False


def test_c004732() -> None:
    """language=' de' speech=0.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.65}, 'empty_asr') is False


def test_c004733() -> None:
    """language=' de' speech=0.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.7}, 'empty_asr') is False


def test_c004734() -> None:
    """language=' de' speech=0.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.75}, 'empty_asr') is False


def test_c004735() -> None:
    """language=' de' speech=0.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.8}, 'empty_asr') is False


def test_c004736() -> None:
    """language=' de' speech=0.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.85}, 'empty_asr') is False


def test_c004737() -> None:
    """language=' de' speech=0.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.9}, 'empty_asr') is False


def test_c004738() -> None:
    """language=' de' speech=0.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 0.95}, 'empty_asr') is False


def test_c004739() -> None:
    """language=' de' speech=1.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.0}, 'empty_asr') is False


def test_c004740() -> None:
    """language=' de' speech=1.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.05}, 'empty_asr') is False


def test_c004741() -> None:
    """language=' de' speech=1.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.1}, 'empty_asr') is False


def test_c004742() -> None:
    """language=' de' speech=1.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.15}, 'empty_asr') is False


def test_c004743() -> None:
    """language=' de' speech=1.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.2}, 'empty_asr') is False


def test_c004744() -> None:
    """language=' de' speech=1.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.25}, 'empty_asr') is False


def test_c004745() -> None:
    """language=' de' speech=1.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.3}, 'empty_asr') is False


def test_c004746() -> None:
    """language=' de' speech=1.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.35}, 'empty_asr') is False


def test_c004747() -> None:
    """language=' de' speech=1.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.4}, 'empty_asr') is False


def test_c004748() -> None:
    """language=' de' speech=1.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.45}, 'empty_asr') is False


def test_c004749() -> None:
    """language=' de' speech=1.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.5}, 'empty_asr') is False


def test_c004750() -> None:
    """language=' de' speech=1.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.55}, 'empty_asr') is False


def test_c004751() -> None:
    """language=' de' speech=1.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.6}, 'empty_asr') is False


def test_c004752() -> None:
    """language=' de' speech=1.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.65}, 'empty_asr') is False


def test_c004753() -> None:
    """language=' de' speech=1.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.7}, 'empty_asr') is False


def test_c004754() -> None:
    """language=' de' speech=1.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.75}, 'empty_asr') is False


def test_c004755() -> None:
    """language=' de' speech=1.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.8}, 'empty_asr') is False


def test_c004756() -> None:
    """language=' de' speech=1.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.85}, 'empty_asr') is False


def test_c004757() -> None:
    """language=' de' speech=1.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.9}, 'empty_asr') is False


def test_c004758() -> None:
    """language=' de' speech=1.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 1.95}, 'empty_asr') is False


def test_c004759() -> None:
    """language=' de' speech=2.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.0}, 'empty_asr') is False


def test_c004760() -> None:
    """language=' de' speech=2.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.05}, 'empty_asr') is False


def test_c004761() -> None:
    """language=' de' speech=2.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.1}, 'empty_asr') is False


def test_c004762() -> None:
    """language=' de' speech=2.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.15}, 'empty_asr') is False


def test_c004763() -> None:
    """language=' de' speech=2.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.2}, 'empty_asr') is False


def test_c004764() -> None:
    """language=' de' speech=2.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.25}, 'empty_asr') is False


def test_c004765() -> None:
    """language=' de' speech=2.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.3}, 'empty_asr') is False


def test_c004766() -> None:
    """language=' de' speech=2.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.35}, 'empty_asr') is False


def test_c004767() -> None:
    """language=' de' speech=2.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.4}, 'empty_asr') is False


def test_c004768() -> None:
    """language=' de' speech=2.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.45}, 'empty_asr') is False


def test_c004769() -> None:
    """language=' de' speech=2.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.5}, 'empty_asr') is False


def test_c004770() -> None:
    """language=' de' speech=2.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.55}, 'empty_asr') is False


def test_c004771() -> None:
    """language=' de' speech=2.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.6}, 'empty_asr') is False


def test_c004772() -> None:
    """language=' de' speech=2.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.65}, 'empty_asr') is False


def test_c004773() -> None:
    """language=' de' speech=2.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.7}, 'empty_asr') is False


def test_c004774() -> None:
    """language=' de' speech=2.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.75}, 'empty_asr') is False


def test_c004775() -> None:
    """language=' de' speech=2.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.8}, 'empty_asr') is False


def test_c004776() -> None:
    """language=' de' speech=2.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.85}, 'empty_asr') is False


def test_c004777() -> None:
    """language=' de' speech=2.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.9}, 'empty_asr') is False


def test_c004778() -> None:
    """language=' de' speech=2.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 2.95}, 'empty_asr') is False


def test_c004779() -> None:
    """language=' de' speech=3.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.0}, 'empty_asr') is False


def test_c004780() -> None:
    """language=' de' speech=3.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.05}, 'empty_asr') is False


def test_c004781() -> None:
    """language=' de' speech=3.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.1}, 'empty_asr') is False


def test_c004782() -> None:
    """language=' de' speech=3.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.15}, 'empty_asr') is False


def test_c004783() -> None:
    """language=' de' speech=3.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.2}, 'empty_asr') is False


def test_c004784() -> None:
    """language=' de' speech=3.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.25}, 'empty_asr') is False


def test_c004785() -> None:
    """language=' de' speech=3.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.3}, 'empty_asr') is False


def test_c004786() -> None:
    """language=' de' speech=3.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.35}, 'empty_asr') is False


def test_c004787() -> None:
    """language=' de' speech=3.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.4}, 'empty_asr') is False


def test_c004788() -> None:
    """language=' de' speech=3.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.45}, 'empty_asr') is False


def test_c004789() -> None:
    """language=' de' speech=3.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.5}, 'empty_asr') is False


def test_c004790() -> None:
    """language=' de' speech=3.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.55}, 'empty_asr') is False


def test_c004791() -> None:
    """language=' de' speech=3.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.6}, 'empty_asr') is False


def test_c004792() -> None:
    """language=' de' speech=3.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.65}, 'empty_asr') is False


def test_c004793() -> None:
    """language=' de' speech=3.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.7}, 'empty_asr') is False


def test_c004794() -> None:
    """language=' de' speech=3.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.75}, 'empty_asr') is False


def test_c004795() -> None:
    """language=' de' speech=3.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.8}, 'empty_asr') is False


def test_c004796() -> None:
    """language=' de' speech=3.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.85}, 'empty_asr') is False


def test_c004797() -> None:
    """language=' de' speech=3.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.9}, 'empty_asr') is False


def test_c004798() -> None:
    """language=' de' speech=3.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 3.95}, 'empty_asr') is False


def test_c004799() -> None:
    """language=' de' speech=4.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.0}, 'empty_asr') is False


def test_c004800() -> None:
    """language=' de' speech=4.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.05}, 'empty_asr') is False


def test_c004801() -> None:
    """language=' de' speech=4.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.1}, 'empty_asr') is False


def test_c004802() -> None:
    """language=' de' speech=4.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.15}, 'empty_asr') is False


def test_c004803() -> None:
    """language=' de' speech=4.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.2}, 'empty_asr') is False


def test_c004804() -> None:
    """language=' de' speech=4.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.25}, 'empty_asr') is False


def test_c004805() -> None:
    """language=' de' speech=4.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.3}, 'empty_asr') is False


def test_c004806() -> None:
    """language=' de' speech=4.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.35}, 'empty_asr') is False


def test_c004807() -> None:
    """language=' de' speech=4.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.4}, 'empty_asr') is False


def test_c004808() -> None:
    """language=' de' speech=4.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.45}, 'empty_asr') is False


def test_c004809() -> None:
    """language=' de' speech=4.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.5}, 'empty_asr') is False


def test_c004810() -> None:
    """language=' de' speech=4.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.55}, 'empty_asr') is False


def test_c004811() -> None:
    """language=' de' speech=4.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.6}, 'empty_asr') is False


def test_c004812() -> None:
    """language=' de' speech=4.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.65}, 'empty_asr') is False


def test_c004813() -> None:
    """language=' de' speech=4.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.7}, 'empty_asr') is False


def test_c004814() -> None:
    """language=' de' speech=4.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.75}, 'empty_asr') is False


def test_c004815() -> None:
    """language=' de' speech=4.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.8}, 'empty_asr') is False


def test_c004816() -> None:
    """language=' de' speech=4.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.85}, 'empty_asr') is False


def test_c004817() -> None:
    """language=' de' speech=4.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.9}, 'empty_asr') is False


def test_c004818() -> None:
    """language=' de' speech=4.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 4.95}, 'empty_asr') is False


def test_c004819() -> None:
    """language=' de' speech=5.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.0}, 'empty_asr') is False


def test_c004820() -> None:
    """language=' de' speech=5.05: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.05}, 'empty_asr') is False


def test_c004821() -> None:
    """language=' de' speech=5.1: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.1}, 'empty_asr') is False


def test_c004822() -> None:
    """language=' de' speech=5.15: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.15}, 'empty_asr') is False


def test_c004823() -> None:
    """language=' de' speech=5.2: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.2}, 'empty_asr') is False


def test_c004824() -> None:
    """language=' de' speech=5.25: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.25}, 'empty_asr') is False


def test_c004825() -> None:
    """language=' de' speech=5.3: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.3}, 'empty_asr') is False


def test_c004826() -> None:
    """language=' de' speech=5.35: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.35}, 'empty_asr') is False


def test_c004827() -> None:
    """language=' de' speech=5.4: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.4}, 'empty_asr') is False


def test_c004828() -> None:
    """language=' de' speech=5.45: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.45}, 'empty_asr') is False


def test_c004829() -> None:
    """language=' de' speech=5.5: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.5}, 'empty_asr') is False


def test_c004830() -> None:
    """language=' de' speech=5.55: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.55}, 'empty_asr') is False


def test_c004831() -> None:
    """language=' de' speech=5.6: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.6}, 'empty_asr') is False


def test_c004832() -> None:
    """language=' de' speech=5.65: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.65}, 'empty_asr') is False


def test_c004833() -> None:
    """language=' de' speech=5.7: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.7}, 'empty_asr') is False


def test_c004834() -> None:
    """language=' de' speech=5.75: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.75}, 'empty_asr') is False


def test_c004835() -> None:
    """language=' de' speech=5.8: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.8}, 'empty_asr') is False


def test_c004836() -> None:
    """language=' de' speech=5.85: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.85}, 'empty_asr') is False


def test_c004837() -> None:
    """language=' de' speech=5.9: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.9}, 'empty_asr') is False


def test_c004838() -> None:
    """language=' de' speech=5.95: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 5.95}, 'empty_asr') is False


def test_c004839() -> None:
    """language=' de' speech=6.0: the skip answers False."""
    assert long_speech_handoff({'stt_language': ' de', 'speech_seconds': 6.0}, 'empty_asr') is False
