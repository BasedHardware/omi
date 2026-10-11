#!/usr/bin/env python3
"""Validate the immutable identity of a mobile Codemagic release tag.

This module has no provider or network dependencies.  A platform-specific tag
is authoritative for its marketing version and build number; the historical
``-mobile-cm`` form remains valid for both mobile platforms.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import re

MAX_BUILD_NUMBER = 2_100_000_000
PLATFORMS = frozenset({"ios", "android"})
TAG_RE = re.compile(
    r"^v(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)\."
    r"(?P<patch>0|[1-9][0-9]*)\+"
    rf"(?P<build>[1-9][0-9]{{0,9}})-(?P<tag_platform>mobile|ios|android)-cm$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class ReleaseIdentityError(ValueError):
    """The release tag or its source identity violates the mobile contract."""


@dataclass(frozen=True)
class ReleaseIdentity:
    tag: str
    platform: str
    version: str
    build_number: int
    source_sha: str | None = None
    tag_source_sha: str | None = None

    @property
    def release_id(self) -> str:
        return self.tag


def _require_platform(platform: str) -> str:
    if platform not in PLATFORMS:
        raise ReleaseIdentityError("platform must be exactly ios or android")
    return platform


def require_sha(name: str, value: str) -> str:
    if not isinstance(value, str) or not SHA_RE.fullmatch(value):
        raise ReleaseIdentityError(f"{name} must be a lowercase 40-character Git SHA")
    return value


def parse_release_tag(tag: str) -> tuple[str, int, str]:
    """Return ``(version, build_number, tag_platform)`` for a strict tag."""
    if not isinstance(tag, str):
        raise ReleaseIdentityError("tag must be a string")
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ReleaseIdentityError(
            "tag must use v<major>.<minor>.<patch>+<positive-build>-"
            "<mobile|ios|android>-cm form"
        )

    build_number = int(match.group("build"))
    if build_number > MAX_BUILD_NUMBER:
        raise ReleaseIdentityError(f"build number must be <= {MAX_BUILD_NUMBER}")
    version = ".".join(match.group(name) for name in ("major", "minor", "patch"))
    return version, build_number, match.group("tag_platform")


def resolve_release_identity(
    tag: str,
    platform: str,
    *,
    source_sha: str | None = None,
    tag_source_sha: str | None = None,
) -> ReleaseIdentity:
    """Resolve a tag for a target platform and optionally bind its source.

    ``tag_source_sha`` is the commit resolved from an annotated or lightweight
    Git tag (for example, ``git rev-parse TAG^{commit}``).  If both source
    values are supplied they must match exactly; supplying only one still
    validates its shape and records it for downstream provenance.
    """
    platform = _require_platform(platform)
    version, build_number, tag_platform = parse_release_tag(tag)
    if tag_platform != "mobile" and tag_platform != platform:
        raise ReleaseIdentityError(
            f"tag platform {tag_platform} does not match requested platform {platform}"
        )

    if source_sha is not None:
        source_sha = require_sha("source_sha", source_sha)
    if tag_source_sha is not None:
        tag_source_sha = require_sha("tag_source_sha", tag_source_sha)
    if source_sha is not None and tag_source_sha is not None and source_sha != tag_source_sha:
        raise ReleaseIdentityError("source_sha does not match the commit resolved from the tag")

    return ReleaseIdentity(
        tag=tag,
        platform=platform,
        version=version,
        build_number=build_number,
        source_sha=source_sha,
        tag_source_sha=tag_source_sha,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--platform", required=True, choices=sorted(PLATFORMS))
    parser.add_argument("--source-sha")
    parser.add_argument("--tag-source-sha")
    parser.add_argument("--format", choices=("json", "shell"), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        identity = resolve_release_identity(
            args.tag,
            args.platform,
            source_sha=args.source_sha,
            tag_source_sha=args.tag_source_sha,
        )
    except ReleaseIdentityError as error:
        parser.error(str(error))

    if args.format == "shell":
        # Every value was validated above and is safe as a plain env assignment.
        print(f"BUILD_NAME={identity.version}")
        print(f"BUILD_NUMBER={identity.build_number}")
        print(f"OMI_RELEASE_PLATFORM={identity.platform}")
        print(f"OMI_RELEASE_TAG={identity.tag}")
    else:
        print(json.dumps(asdict(identity), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
