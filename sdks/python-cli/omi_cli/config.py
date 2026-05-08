"""Configuration store for omi-cli.

State lives at ``~/.omi/config.toml`` (overridable via ``$OMI_CONFIG``). The file
holds one or more named profiles; each profile carries one auth method (api_key
or oauth) plus an API base URL.

The schema is intentionally small and forward-compatible: unknown keys are
preserved on round-trip so future versions can add fields without breaking
older installs.

Permissions: the config file is created with mode ``0600`` (owner-only) since it
holds bearer credentials.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import tomli_w

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — exercised only on 3.10
    import tomli as tomllib  # noqa: F401


DEFAULT_API_BASE = "https://api.omi.me"
DEFAULT_PROFILE_NAME = "default"
ENV_CONFIG_PATH = "OMI_CONFIG"
ENV_API_KEY = "OMI_API_KEY"
ENV_API_BASE = "OMI_API_BASE"
ENV_PROFILE = "OMI_PROFILE"


def default_config_path() -> Path:
    """Return the resolved config path, honoring ``$OMI_CONFIG``."""
    override = os.environ.get(ENV_CONFIG_PATH)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".omi" / "config.toml"


@dataclass
class Profile:
    """One auth context. A user may have several (e.g. personal vs work)."""

    name: str
    auth_method: Optional[str] = None  # "api_key" | "oauth" | None (unconfigured)
    api_key: Optional[str] = None
    id_token: Optional[str] = None
    refresh_token: Optional[str] = None
    id_token_expires_at: Optional[float] = None  # unix epoch seconds
    api_base: str = DEFAULT_API_BASE
    extra: dict[str, Any] = field(default_factory=dict)

    def is_authenticated(self) -> bool:
        if self.auth_method == "api_key":
            return bool(self.api_key)
        if self.auth_method == "oauth":
            return bool(self.id_token) or bool(self.refresh_token)
        return False

    def to_toml_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"api_base": self.api_base}
        if self.auth_method:
            out["auth_method"] = self.auth_method
        if self.api_key:
            out["api_key"] = self.api_key
        if self.id_token:
            out["id_token"] = self.id_token
        if self.refresh_token:
            out["refresh_token"] = self.refresh_token
        if self.id_token_expires_at is not None:
            out["id_token_expires_at"] = self.id_token_expires_at
        # Round-trip preserve unknown keys for forward compatibility.
        for k, v in self.extra.items():
            if k not in out:
                out[k] = v
        return out

    @classmethod
    def from_toml_dict(cls, name: str, data: dict[str, Any]) -> "Profile":
        known = {
            "auth_method",
            "api_key",
            "id_token",
            "refresh_token",
            "id_token_expires_at",
            "api_base",
        }
        extra = {k: v for k, v in data.items() if k not in known}
        return cls(
            name=name,
            auth_method=data.get("auth_method"),
            api_key=data.get("api_key"),
            id_token=data.get("id_token"),
            refresh_token=data.get("refresh_token"),
            id_token_expires_at=data.get("id_token_expires_at"),
            api_base=data.get("api_base", DEFAULT_API_BASE),
            extra=extra,
        )

    def masked_credential(self) -> str:
        """Return a redacted form of the active credential, for status displays."""
        if self.auth_method == "api_key" and self.api_key:
            return _mask_token(self.api_key)
        if self.auth_method == "oauth" and self.id_token:
            return _mask_token(self.id_token)
        return "(none)"


@dataclass
class Config:
    """In-memory representation of the on-disk config file."""

    path: Path
    active_profile: str = DEFAULT_PROFILE_NAME
    profiles: dict[str, Profile] = field(default_factory=dict)

    def get_profile(self, name: Optional[str] = None) -> Profile:
        target = name or self.active_profile
        if target not in self.profiles:
            self.profiles[target] = Profile(name=target)
        return self.profiles[target]

    def set_profile(self, profile: Profile) -> None:
        self.profiles[profile.name] = profile

    def delete_profile(self, name: str) -> None:
        self.profiles.pop(name, None)
        if self.active_profile == name:
            self.active_profile = DEFAULT_PROFILE_NAME

    def list_profiles(self) -> list[str]:
        return sorted(self.profiles.keys())


def load(path: Optional[Path] = None) -> Config:
    """Load the config from disk, returning an empty Config if the file is missing."""
    p = path or default_config_path()
    if not p.exists():
        return Config(path=p, active_profile=DEFAULT_PROFILE_NAME, profiles={})

    with p.open("rb") as fh:
        data = tomllib.load(fh)

    active = data.get("active_profile", DEFAULT_PROFILE_NAME)
    profiles_data = data.get("profiles", {})
    profiles = {name: Profile.from_toml_dict(name, raw) for name, raw in profiles_data.items()}

    return Config(path=p, active_profile=active, profiles=profiles)


def save(config: Config) -> None:
    """Persist the config to disk with secure (owner-only) permissions.

    The temp file is **created** with mode ``0o600`` via :func:`os.open`, not
    chmodded after the fact — this closes a TOCTOU window where another local
    user could read bearer credentials between file creation (default umask,
    typically ``0o644``) and the chmod call. We also temporarily clamp the
    process umask to ``0o077`` so any platform that ANDs the requested mode
    against the umask still ends up with owner-only perms.
    """
    config.path.parent.mkdir(parents=True, exist_ok=True)
    # Tighten parent dir perms too — credentials live underneath. Best-effort:
    # don't fail if the user has a custom mode they want to keep.
    try:
        os.chmod(config.path.parent, 0o700)
    except OSError:
        pass

    payload: dict[str, Any] = {
        "active_profile": config.active_profile,
        "profiles": {name: p.to_toml_dict() for name, p in config.profiles.items()},
    }

    tmp_path = config.path.with_suffix(config.path.suffix + ".tmp")
    # Belt-and-suspenders: clamp umask AND pass an explicit 0o600 mode to os.open.
    old_umask = os.umask(0o077)
    try:
        # O_EXCL guards against following an attacker-planted symlink at this path.
        try:
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # Stale temp from a previous interrupted save — remove and retry once.
            os.unlink(tmp_path)
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                tomli_w.dump(payload, fh)
        except Exception:
            # Best-effort cleanup if the dump itself failed mid-write.
            try:
                os.unlink(tmp_path)
            except FileNotFoundError:
                pass
            raise
    finally:
        os.umask(old_umask)

    # Atomic rename. The destination inherits the temp's 0o600 mode.
    os.replace(tmp_path, config.path)


def resolve_profile_name(cli_flag: Optional[str], config: Config) -> str:
    """Resolve which profile to use given the precedence: CLI flag > env > config default."""
    if cli_flag:
        return cli_flag
    env = os.environ.get(ENV_PROFILE)
    if env:
        return env
    return config.active_profile


def _mask_token(token: str) -> str:
    """Render a token as ``prefix…suffix`` (4+4 chars) for safe display."""
    if not token:
        return ""
    if len(token) <= 12:
        # Short token — show only the first 2 and last 2 chars.
        return f"{token[:2]}…{token[-2:]}"
    return f"{token[:6]}…{token[-4:]}"
