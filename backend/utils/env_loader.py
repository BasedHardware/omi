"""Stage-aware backend environment loading.

Stages select committed template files (``backend/.env.<stage>``) for different
deployment contexts. Personal secrets live in ``backend/.env``, which always
loads last and overrides stage defaults.

Set ``OMI_ENV_STAGE`` to one of: ``prod``, ``dev``, ``local``, ``offline``.
When unset, only ``backend/.env`` is loaded (production / legacy behavior).
If ``OMI_ENV_STAGE`` is unset and ``PROVIDER_MODE=offline``, stage ``offline``
is inferred for harness compatibility.
"""

from __future__ import annotations

import logging
import os
import re
from enum import Enum
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

logger = logging.getLogger(__name__)

VALID_STAGES = frozenset({"prod", "dev", "local", "offline"})

# ``local`` uses the existing harness filename for backward compatibility.
STAGE_ENV_FILENAMES: dict[str, str] = {
    "prod": ".env.prod",
    "dev": ".env.dev",
    "local": ".env.local-dev",
    "offline": ".env.offline",
}

_PROVIDER_SECRET_RE = re.compile(
    r"(API_KEY|ACCESS_TOKEN|AUTH_TOKEN|SECRET|DEEPGRAM|OPENAI|ANTHROPIC|GROQ|ELEVENLABS|PINECONE)",
    re.IGNORECASE,
)


class EnvStage(str, Enum):
    PROD = "prod"
    DEV = "dev"
    LOCAL = "local"
    OFFLINE = "offline"


def backend_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def is_provider_secret_key(key: str) -> bool:
    return bool(_PROVIDER_SECRET_RE.search(key))


def firebase_admin_options(environ: dict[str, str] | None = None) -> dict[str, str] | None:
    """Return Firebase Admin options for the configured authentication project.

    Dev services intentionally validate production Firebase identities while
    their Google application credentials continue to select the dev data
    project. Firebase Admin therefore needs the explicit auth project; Google
    Cloud clients remain independently owned by ADC.
    """

    source = os.environ if environ is None else environ
    project_id = source.get("FIREBASE_AUTH_PROJECT_ID", "").strip()
    if not project_id:
        return None
    return {"projectId": project_id}


def stage_from_env(environ: dict[str, str] | None = None) -> str | None:
    """Return the active stage name, or ``None`` when only ``backend/.env`` applies."""

    source = os.environ if environ is None else environ
    raw = source.get("OMI_ENV_STAGE", "").strip().lower()
    if raw:
        if raw not in VALID_STAGES:
            raise ValueError(f"OMI_ENV_STAGE must be one of {sorted(VALID_STAGES)}, got {raw!r}")
        return raw
    if source.get("PROVIDER_MODE", "").strip().lower() == "offline":
        return EnvStage.OFFLINE.value
    return None


def resolve_stage_from_env(environ: dict[str, str] | None = None) -> str | None:
    """Like :func:`stage_from_env`, but invalid values fall back to legacy loading."""

    try:
        return stage_from_env(environ)
    except ValueError as exc:
        logger.warning("%s; falling back to legacy .env-only loading", exc)
        return None


def stage_env_filename(stage: str) -> str:
    if stage not in VALID_STAGES:
        raise ValueError(f"Unknown env stage {stage!r}")
    return STAGE_ENV_FILENAMES[stage]


def stage_env_path(stage: str, base: Path | None = None) -> Path:
    root = backend_dir() if base is None else base
    return root / stage_env_filename(stage)


_ADC_ENV_KEYS = frozenset({"GOOGLE_APPLICATION_CREDENTIALS", "SERVICE_ACCOUNT_JSON"})


def _skip_env_key_for_auth_emulator(key: str) -> bool:
    """Do not load production ADC when the Auth emulator is active."""

    if key not in _ADC_ENV_KEYS:
        return False
    return bool(os.environ.get("FIREBASE_AUTH_EMULATOR_HOST", "").strip())


def _apply_dotenv_file(
    path: Path,
    *,
    override: bool,
    exclude_provider_secrets: bool = False,
) -> None:
    for key, value in dotenv_values(path).items():
        if value is None:
            continue
        if exclude_provider_secrets and is_provider_secret_key(key):
            continue
        if _skip_env_key_for_auth_emulator(key):
            continue
        if override or key not in os.environ:
            os.environ[key] = value


def load_backend_env(base: Path | None = None) -> list[Path]:
    """Load stage defaults then personal ``backend/.env``. Returns loaded paths.

    Precedence (highest first): existing shell/process env, personal ``.env``,
    stage file defaults. Offline stage never loads provider credentials from disk.

    When ``OMI_HARNESS_INSTANCE`` is set, the local dev harness has already
    injected a complete child environment — skip all disk loading.
    """

    if os.environ.get("OMI_HARNESS_INSTANCE", "").strip():
        return []

    root = backend_dir() if base is None else base
    loaded: list[Path] = []
    preserved = dict(os.environ)

    stage = resolve_stage_from_env()
    offline_stage = stage == EnvStage.OFFLINE.value

    if stage is not None:
        stage_path = stage_env_path(stage, root)
        if stage_path.is_file():
            _apply_dotenv_file(stage_path, override=False)
            loaded.append(stage_path)

    personal = root / ".env"
    if personal.is_file():
        if stage is not None and loaded and not offline_stage:
            _apply_dotenv_file(personal, override=True)
            for key, value in preserved.items():
                os.environ[key] = value
        else:
            _apply_dotenv_file(
                personal,
                override=False,
                exclude_provider_secrets=offline_stage,
            )
        loaded.append(personal)
    elif stage is None:
        load_dotenv(personal)

    return loaded
