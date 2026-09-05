from __future__ import annotations

import pytest

from utils.jit_qa_admission import JITQAAdmissionError, enforce_jit_qa_uid


def _env(**overrides: str) -> dict[str, str]:
    values = {
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": "qa-user",
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
    }
    values.update(overrides)
    return values


def test_qa_admission_accepts_only_the_explicit_dev_uid():
    enforce_jit_qa_uid("qa-user", _env())
    with pytest.raises(JITQAAdmissionError):
        enforce_jit_qa_uid("other-user", _env())


def test_qa_admission_normalizes_stage_and_project():
    enforce_jit_qa_uid(
        "qa-user",
        _env(OMI_ENV_STAGE=" DEV ", GOOGLE_CLOUD_PROJECT=" based-hardware-dev "),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"OMI_JIT_QA_UID_ALLOWLIST": ""},
        {"OMI_JIT_QA_UID_ALLOWLIST": "qa-user,other-user"},
        {"GOOGLE_CLOUD_PROJECT": "based-hardware"},
        {"OMI_ENV_STAGE": "prod"},
    ],
)
def test_qa_admission_fails_closed_when_scope_is_not_exact(overrides):
    with pytest.raises(JITQAAdmissionError):
        enforce_jit_qa_uid("qa-user", _env(**overrides))


def test_qa_admission_is_inert_when_switch_is_absent():
    enforce_jit_qa_uid("any-normal-user", {"OMI_ENV_STAGE": "prod", "GOOGLE_CLOUD_PROJECT": "based-hardware"})
