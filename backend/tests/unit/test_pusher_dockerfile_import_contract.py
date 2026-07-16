"""Static import contract for the pusher runtime image.

`backend/pusher/Dockerfile` whitelist-copies only the first-party packages the
pusher reaches. When a pusher-reachable module gains a `from <pkg> import ...`
against a first-party package that the Dockerfile does not copy, the runtime
image crashes at import time with `ModuleNotFoundError` (dev pusher
CrashLoopBackOff — issue #9857; the earlier `jsonschema`/`services` gaps in
#9140/#9141/#9704 were the same class).

An in-process `import routers.pusher` cannot catch this: the full `backend/`
tree is present under pytest, so the import always succeeds. The only hermetic
guard is to reconcile the Dockerfile's copy whitelist against the first-party
packages that pusher's entrypoints statically reach.

# omi-test-quality: source-inspection -- static contract: the packaging gap only
# exists in the trimmed Docker image, which cannot be imported in-process.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
DOCKERFILE = BACKEND_DIR / "pusher" / "Dockerfile"

# Modules that are the pusher runtime entrypoints. Traversal follows their
# first-party imports transitively.
ENTRYPOINTS = ["pusher.main", "routers.pusher"]

# First-party top-level packages = importable directories under backend/ (those
# containing Python source). A same-named directory without any `.py` (e.g.
# `typesense/`, which only holds a schema file) is data, not a package — the
# matching `import typesense` resolves to the third-party pip client instead.
FIRST_PARTY = {p.name for p in BACKEND_DIR.iterdir() if p.is_dir() and any(p.rglob("*.py"))}


def _copied_packages() -> set[str]:
    """Top-level packages copied into the runtime image via `COPY backend/<pkg>/`."""
    text = DOCKERFILE.read_text()
    return set(re.findall(r"^COPY\s+backend/(\w+)/", text, re.MULTILINE))


def _resolve(module: str) -> Path | None:
    """Resolve a dotted first-party module to a parseable .py file, if any."""
    rel = module.replace(".", "/")
    for candidate in (BACKEND_DIR / f"{rel}.py", BACKEND_DIR / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _reachable_top_level_packages() -> set[str]:
    """BFS from the entrypoints, following absolute first-party imports."""
    referenced: set[str] = set()
    visited: set[str] = set()
    queue = list(ENTRYPOINTS)

    while queue:
        module = queue.pop()
        if module in visited:
            continue
        visited.add(module)

        top = module.split(".")[0]
        if top in FIRST_PARTY:
            referenced.add(top)

        path = _resolve(module)
        if path is None:
            continue

        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    queue.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                # Relative imports (level > 0) stay within an already-copied
                # package, so only absolute imports can introduce a new top-level.
                queue.append(node.module)

    return {pkg for pkg in referenced if pkg in FIRST_PARTY}


def test_pusher_dockerfile_copies_every_reachable_first_party_package():
    copied = _copied_packages()
    reachable = _reachable_top_level_packages()

    missing = sorted(reachable - copied)
    assert not missing, (
        "pusher/Dockerfile does not COPY first-party packages that pusher's "
        f"entrypoints import: {missing}. The runtime image will crash at import "
        "time with ModuleNotFoundError. Add `COPY backend/<pkg>/ ./<pkg>/`."
    )
