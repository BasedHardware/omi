"""Runtime mode contract for the Parakeet GPU service.

The image is shared by the batch and realtime deployments, but a GPU pod must
load only the model family it serves.  ``mixed`` preserves the historical
single-process behavior for deployments that do not set the mode explicitly.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

SERVICE_MODE_ENV = "PARAKEET_SERVICE_MODE"
DEFAULT_SERVICE_MODE = "mixed"
VALID_SERVICE_MODES = ("mixed", "batch", "stream")

# Keep the stream model default beside the service-mode contract.  The stream
# deployment is intentionally allowed to override this with the English-only
# RNNT checkpoint during a staged rollout, but an unset variable must select
# the multilingual TDT checkpoint that the official NeMo streaming example
# supports.
STREAM_MODEL_ENV = "PARAKEET_STREAM_MODEL"
DEFAULT_STREAM_MODEL_NAME = "nvidia/parakeet-tdt-0.6b-v3"
RNNT_STREAM_MODEL_NAME = "nvidia/parakeet-rnnt-1.1b"
DEFAULT_STREAM_MODEL_ARTIFACT = "parakeet-tdt-0.6b-v3.nemo"
DEFAULT_STREAM_MODEL_REVISION = "541d1f99c6b0c3cd0b11a95167540bb8edefd82b"


def get_stream_model_name(env: Mapping[str, str]) -> str:
    """Return the configured stream model, defaulting to multilingual TDT.

    An explicitly empty value remains a supported way to disable streaming
    model loading in mixed or batch-only test/dev processes.  This distinction
    lets the absence of deployment configuration select the safe production
    default without making test fixtures download a checkpoint.
    """

    configured = env.get(STREAM_MODEL_ENV)
    if configured is None:
        return DEFAULT_STREAM_MODEL_NAME
    return configured.strip()


def stream_model_identity(model_name: Optional[str], backend: str = "nemo") -> Dict[str, Any]:
    """Describe the stream model contract for readiness and health responses.

    The model family is later checked against the loaded NeMo decoder.  Model
    names alone are useful for observability, but are not accepted as proof of
    architecture compatibility by the runtime loader.
    """

    normalized = (model_name or "").strip()
    if normalized == DEFAULT_STREAM_MODEL_NAME:
        family = "tdt"
        language_support = "multilingual"
        model_revision: Optional[str] = DEFAULT_STREAM_MODEL_REVISION
        model_artifact: Optional[str] = DEFAULT_STREAM_MODEL_ARTIFACT
    elif normalized == RNNT_STREAM_MODEL_NAME:
        family = "rnnt"
        language_support = "en"
        model_revision = None
        model_artifact = None
    elif normalized:
        family = "unknown"
        language_support = "unknown"
        model_revision = None
        model_artifact = None
    else:
        family = "none"
        language_support = "none"
        model_revision = None
        model_artifact = None

    return {
        "backend": backend,
        "stream_model": normalized or None,
        "decoder_family": family,
        "language_support": language_support,
        "model_revision": model_revision,
        "model_artifact": model_artifact,
    }


def get_service_mode(env: Mapping[str, str]) -> str:
    """Return the normalized service mode or fail closed on bad configuration."""

    mode = env.get(SERVICE_MODE_ENV, DEFAULT_SERVICE_MODE).strip().lower()
    if mode not in VALID_SERVICE_MODES:
        allowed = ", ".join(VALID_SERVICE_MODES)
        raise ValueError(f"{SERVICE_MODE_ENV} must be one of {allowed}, got '{mode}'")
    return mode
