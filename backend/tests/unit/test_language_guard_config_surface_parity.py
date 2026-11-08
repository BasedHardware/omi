"""The config surface around the guard keeps its documented shapes.

The admission vocabulary, the language-class backstop, the inheritance default, and the disposition/safety flags define when the barrier can fire at all. This suite pins each flag grid cell and the admission-vs-barrier agreement so the classification change sits on a stable configuration surface.

Failure-Class: FC-language-guard-redrive-misclassified-as-worker-fault
"""

import pytest

from config.batch_pipeline import (
    known_unsupported_batch_language,
    language_inheritance_enabled,
    language_eligibility_enabled,
    worker_validation_disposition_enabled,
)
from config.batch_pipeline import worker_silence_disposition_enabled
from tests.unit.test_batch_pipeline_worker import item


def test_worker_validation_disposition_env_absent_is_True():
    """The disposition flag under absent."""
    import os
    import os
    from config.batch_pipeline import worker_validation_disposition_enabled

    assert worker_validation_disposition_enabled() is True


def test_worker_validation_disposition_env_true_is_True(monkeypatch):
    """The disposition flag under true."""
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'true')
    import os
    from config.batch_pipeline import worker_validation_disposition_enabled

    assert worker_validation_disposition_enabled() is True


def test_worker_validation_disposition_env_TRUE_is_True(monkeypatch):
    """The disposition flag under TRUE."""
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'TRUE')
    import os
    from config.batch_pipeline import worker_validation_disposition_enabled

    assert worker_validation_disposition_enabled() is True


def test_worker_validation_disposition_env_false_is_False(monkeypatch):
    """The disposition flag under false."""
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'false')
    import os
    from config.batch_pipeline import worker_validation_disposition_enabled

    assert worker_validation_disposition_enabled() is False


def test_worker_validation_disposition_env_yes_is_False(monkeypatch):
    """The disposition flag under yes."""
    monkeypatch.setenv('BATCH_PIPELINE_WORKER_VALIDATION_DISPOSITION_ENABLED', 'yes')
    import os
    from config.batch_pipeline import worker_validation_disposition_enabled

    assert worker_validation_disposition_enabled() is False


def test_safety_net_env_absent_is_True():
    """The safety-net flag under absent."""
    from config.batch_pipeline_empty_asr import safety_net_enabled
    import os

    assert safety_net_enabled() is True


def test_safety_net_env_false_is_False(monkeypatch):
    """The safety-net flag under false."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'false')
    from config.batch_pipeline_empty_asr import safety_net_enabled
    import os

    assert safety_net_enabled() is False


def test_safety_net_env_true_is_True(monkeypatch):
    """The safety-net flag under true."""
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_SAFETY_NET_ENABLED', 'true')
    from config.batch_pipeline_empty_asr import safety_net_enabled
    import os

    assert safety_net_enabled() is True


def test_language_inheritance_env_absent_is_True():
    """Inheritance under absent; malformed values stay safe/default."""
    import os

    assert language_inheritance_enabled() is True


def test_language_inheritance_env_false_is_False(monkeypatch):
    """Inheritance under false; malformed values stay safe/default."""
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'false')
    import os

    assert language_inheritance_enabled() is False


def test_language_inheritance_env_junk_is_True(monkeypatch):
    """Inheritance under junk; malformed values stay safe/default."""
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'junk')
    import os

    assert language_inheritance_enabled() is True


def test_language_eligibility_default_on():
    assert language_eligibility_enabled() is True


def test_known_unsupported_vi_is_True():
    """Admission vocabulary: 'vi'."""
    assert known_unsupported_batch_language('vi') is True


def test_known_unsupported_blank_is_False():
    """Admission vocabulary: ''."""
    assert known_unsupported_batch_language('') is False


def test_known_unsupported_und_is_False():
    """Admission vocabulary: 'und'."""
    assert known_unsupported_batch_language('und') is False


def test_known_unsupported_multi_is_False():
    """Admission vocabulary: 'multi'."""
    assert known_unsupported_batch_language('multi') is False


def test_known_unsupported_zz_is_False():
    """Admission vocabulary: 'zz'."""
    assert known_unsupported_batch_language('zz') is False


def test_known_unsupported_none_is_not_known():
    assert known_unsupported_batch_language(None) is False


def test_known_unsupported_int_is_not_known():
    assert known_unsupported_batch_language(42) is False


def test_admission_vocabulary_and_language_class_agree_on_vietnamese():
    """Both filters refuse Vietnamese: admission first, the GPU barrier as backstop."""
    from config.prerecorded_language import language_class

    assert known_unsupported_batch_language("vi") and language_class("vi") != "supported"


def test_admission_vocabulary_and_language_class_agree_on_english():
    from config.prerecorded_language import language_class

    assert not known_unsupported_batch_language("en") and language_class("en") == "supported"


def test_unknown_language_codes_are_admission_unknown_not_known_unsupported():
    """Unknown codes pass admission and only hit the GPU barrier later."""
    from config.prerecorded_language import language_class

    for code in ("", "und", "multi", "unknown"):
        assert not known_unsupported_batch_language(code)
        assert language_class(code) != "supported"
