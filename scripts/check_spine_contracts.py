#!/usr/bin/env python3
"""List pending contracts and allow only marker removal from spine originals."""
from __future__ import annotations

import hashlib
import argparse
from contextvars import ContextVar
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "contracts/spine/files.json"
ROOTS = ("scripts/dev-harness/tests/spine/", "app/test/spine/")
MARKER = re.compile(r'''^\s*(?:@pending\((?:"([A-Z][A-Z0-9-]*)"|'([A-Z][A-Z0-9-]*)')\)|pendingContract\((?:'([A-Z][A-Z0-9-]*)'|"([A-Z][A-Z0-9-]*)")\);)\s*$''')


_reads = ContextVar("spine_git_reads", default=None)


def git(*args: str, root: Path = ROOT) -> str:
    cache = _reads.get()
    key = (root, args)
    if cache is not None and key in cache:
        return cache[key]
    result = subprocess.check_output(["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL)
    if cache is not None:
        cache[key] = result
    return result


def allowed(original: str, current: str) -> bool:
    # A subsequence permits deletion only, never insertion/reordering of markers.
    lines = iter(original.splitlines(keepends=True))
    for wanted in current.splitlines(keepends=True):
        for line in lines:
            if line == wanted:
                break
            if not MARKER.fullmatch(line.rstrip("\n")):
                return False
        else:
            return False
    return all(MARKER.fullmatch(line.rstrip("\n")) for line in lines)


REVISIONS = "contracts/spine/revisions"
SCOPE = "contracts/spine/revision-scope.json"
RUNNERS = "contracts/spine/runners.json"
PREFIXES = "contracts/spine/shared-prefixes.json"


def introductions(root: Path, path: str) -> list[str]:
    # Default path history simplifies merges and can hide the PR parent's copy.
    return git("log", "--full-history", "--diff-filter=A", "--format=%H", "HEAD", "--", path, root=root).splitlines()


def pinned_text(root: Path, path: str, current: str) -> None:
    for commit in introductions(root, path):
        if git("show", f"{commit}:{path}", root=root) != current:
            raise ValueError(f"{path}: committed definition is immutable")


def direct_commands(source: str) -> list[list[str]]:
    """Constrained shell invocation tripwire, not an interpreter or sandbox.

    Only direct top-level commands count. Nested branches/functions, pipelines,
    short-circuit calls and comment-only copies cannot satisfy an invocation.
    """
    result, depth = [], 0
    for line in source.replace("\\\n", " ").splitlines():
        tokens = shlex.split(line, comments=True)
        if not tokens:
            continue
        first = tokens[0]
        if any("<<" in token for token in tokens):
            raise ValueError("heredocs require a reviewed invocation rule")
        if first in ("exec", "eval", "source", ".", "trap", "alias") or (first == "exit" and (len(tokens) != 2 or not tokens[1].isdigit() or int(tokens[1]) == 0)):
            raise ValueError("early success/indirect dispatch cannot replace the spine suite")
        if first == "set" and tokens not in (["set", "-euo", "pipefail"], ["set", "-x"]):
            raise ValueError("runner must preserve fail-fast options and caller arguments")
        if first in ("fi", "done", "esac", "}"):
            depth -= 1
            if depth < 0:
                raise ValueError("unbalanced shell dispatch")
            continue
        block = first in ("if", "for", "while", "until", "case", "select", "function") or bool(re.match(r"[A-Za-z_][A-Za-z_0-9]*\s*\(\)\s*\{", line.strip()))
        if block:
            depth += 1
            continue
        if depth == 0:
            result.append(tokens)
    if depth:
        raise ValueError("unbalanced shell dispatch")
    return result


def runner_contracts(root: Path, registry: dict) -> tuple[set[str], list[str]]:
    declaration = root / RUNNERS
    if not declaration.is_file():
        if introductions(root, RUNNERS):
            return set(), [f"{RUNNERS}: invocation contracts cannot be removed"]
        return set(), []  # older fixture/repository without runner adoption
    raw = declaration.read_text()
    pinned_text(root, RUNNERS, raw)
    runners, errors = set(), []
    for row in json.loads(raw)["runners"]:
        path = row["path"]
        if path in registry or path.startswith(ROOTS + ("app/test/support/spine/",)):
            raise ValueError(f"{path}: an oracle cannot be classified as a shared runner")
        required = [item["argv"] for item in row["invocations"]
                    if not item.get("when_registered") or item["when_registered"] in registry]
        try:
            source = (root / path).read_text()
            syntax = subprocess.run(["bash", "-n", str(root / path)], capture_output=True, text=True)
            if syntax.returncode:
                raise ValueError("shared runner must be valid Bash")
            commands = direct_commands(source)
            if ["set", "-euo", "pipefail"] not in commands:
                raise ValueError("must preserve fail-fast set -euo pipefail")
            for argv in required:
                if argv not in commands:
                    raise ValueError(f"missing direct unconditional suite invocation: {shlex.join(argv)}")
            names = {argv[0] for argv in required}
            if any(re.search(r"(?:^|\n)\s*(?:function\s+)?" + re.escape(name) + r"\s*(?:\(\)|\{)", source) for name in names):
                raise ValueError("suite command shadowed by a shell function")
            for command in commands:
                if command[0] in ("exit", "return", "exec", "eval", "source", ".", "trap", "alias") or command[:2] == ["set", "+e"]:
                    raise ValueError("runner dispatch must remain direct and fail-fast; early exit/indirection is not accepted")
            runners.add(path)
        except (OSError, ValueError) as exc:
            errors.append(f"{path}: {exc}; restore the declared spine invocation in {RUNNERS}")
    return runners, errors


def grandfathered_oracle(root: Path, path: str, current: str, policy: dict) -> bool:
    """A pinned pre-policy correction is already an accepted oracle, even if
    main squash-merged its older parent while the corrected child was open.
    New records cannot add to this immutable set.
    """
    for name, hashes in policy.get("grandfathered_revisions", {}).items():
        file = root / name
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() not in hashes:
            continue
        record = json.loads(file.read_text())
        if record["path"] != path:
            continue
        commits = introductions(root, name)
        for commit in commits:
            oracle = git("show", f"{commit}:{path}", root=root)
            if digest(oracle) == record["after"] and allowed(oracle, current):
                return True
    return False


def pinned_retired_rendering(root: Path, path: str, current: str) -> bool:
    # Record immutability and whole-proposal scope are checked independently.
    # A newly supplied pin still triggers scope through its changed record path.
    if any(MARKER.fullmatch(line) for line in current.splitlines()):
        return False
    return any(record.get("path") == path and record.get("retired_sha256") == digest(current)
               for record in (json.loads(file.read_text()) for file in (root / REVISIONS).glob("*.json")))


def shared_prefixes(root: Path, base: str, registry: dict, policy: dict, read, *, historical: bool = False) -> set[str]:
    """Exact frozen additions to a shared file; its remaining bytes equal target.

    Unlike a whole-file scaffold hash, an unchanged prefix survives unrelated
    accepted implementation updates. This never permits proposed body edits.
    """
    raw = read(PREFIXES)
    if raw is None:
        if not historical and introductions(root, PREFIXES):
            raise ValueError(f"{PREFIXES}: shared-prefix declarations cannot be removed")
        return set()
    pinned_text(root, PREFIXES, raw)
    accepted = set()
    for row in json.loads(raw)["prefixes"]:
        path, prefix, frozen = row["path"], row["prefix"], row["scaffold_sha256"]
        if path in registry or path.startswith(ROOTS + ("app/test/support/spine/",)):
            raise ValueError(f"{path}: an oracle cannot be a shared scaffold")
        if not prefix or frozen not in policy.get("scaffolding", {}).get(path, []):
            raise ValueError(f"{path}: shared prefix requires an existing frozen scaffold")
        # The immutable declaration pins the reviewed prefix itself. Do not
        # reconstruct an old shared-file body from history: a squash may erase
        # that payload while preserving both this declaration and target body.
        try:
            target = git("show", f"{base}:{path}", root=root)
        except subprocess.CalledProcessError:
            continue
        expected = target if target.startswith(prefix) else prefix + target
        if read(path) == expected:
            accepted.add(path)
    return accepted


def revision_scope(root: Path, base: str, registry: dict) -> list[str]:
    """A revision is an oracle-only PR, including unstaged/untracked edits.

    Frozen scaffolding permits existing stacked spine PRs, never subsequent
    implementation at those paths. The policy is pinned at introduction.
    """
    policy_file = root / SCOPE
    commits = introductions(root, SCOPE)
    policy = json.loads(policy_file.read_text()) if policy_file.is_file() else {}
    if commits:
        if not policy_file.is_file():
            return [f"{SCOPE}: the initial scope snapshot is immutable; it cannot authorize a builder's edit"]
        try:
            pinned_text(root, SCOPE, policy_file.read_text())
        except ValueError as exc:
            return [str(exc)]
    shared_runners, runner_errors = runner_contracts(root, registry)
    if runner_errors:
        return runner_errors
    read = lambda path: (root / path).read_text() if (root / path).is_file() else None
    prefixes = shared_prefixes(root, base, registry, policy, read)
    changed = set(git("diff", "--name-only", base, "--", root=root).splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard", root=root).splitlines())
    needs_revision = False
    for path in changed:
        if path.startswith(REVISIONS + "/"):
            file = root / path
            if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() not in policy.get("grandfathered_revisions", {}).get(path, []):
                needs_revision = True
        elif path in registry:
            try:
                old = git("show", f"{base}:{path}", root=root)
            except subprocess.CalledProcessError:
                continue  # introducing a new contract is not revising one
            file = root / path
            if not file.is_file():
                needs_revision = True
            elif (not allowed(old, file.read_text()) and not grandfathered_oracle(root, path, file.read_text(), policy)
                  and not pinned_retired_rendering(root, path, file.read_text())):
                needs_revision = True
    if not needs_revision:
        return []
    rejected = outside_oracle_scope(changed, policy, shared_runners | prefixes, read)
    if not rejected:
        return []
    return ["Spine revision mixed with implementation/non-oracle paths: " + ", ".join(rejected)
            + ". Restore the oracle and remove the revision record from the builder PR; send its reproduction to the spine. "
            "Land the oracle-only revision separately, then base the implementation on it. Separate commits in one PR do not satisfy this rule."]


def outside_oracle_scope(paths, policy, shared_runners, read):
    permitted = set(policy.get("oracle_paths", [])) | {"scripts/check_spine_contracts.py", "scripts/dev-harness/tests/test_spine_mechanism.py"}
    rejected = []
    for path in sorted(paths):
        if path.startswith(ROOTS + ("contracts/spine/", "app/test/support/spine/")) or path in permitted or path in shared_runners:
            continue
        source = read(path)
        if source is not None and digest(source) in policy.get("scaffolding", {}).get(path, []):
            continue
        rejected.append(path)
    return rejected


def authorized_revision_paths(root: Path, base_ref: str, registry: dict, present: set[str]) -> set[str]:
    """Accepted target content plus scope-eligible proposals, not every addition.

    Eligibility is the WHOLE proposal relative to its target, not one commit:
    splitting a self-authorization into two commits cannot make it append-only.
    A target that already accepted a rejected record's absence is authoritative.
    Review identity still belongs to the coordinator, not Git.
    """
    accepted = set(git("ls-tree", "-r", "--name-only", base_ref, "--", REVISIONS, root=root).splitlines())
    policy = json.loads((root / SCOPE).read_text()) if (root / SCOPE).is_file() else {}
    runners, _ = runner_contracts(root, registry)
    paths = set(git("log", "--full-history", "--diff-filter=A", "--name-only", "--format=", "HEAD", "--", REVISIONS, root=root).splitlines()) - {""}
    for path in paths - accepted - present:
        for commit in introductions(root, path):
            base = git("merge-base", commit, base_ref, root=root).strip()
            if base == commit:
                continue  # accepted target content already resolves this proposal
            def read(name):
                try:
                    return git("show", f"{commit}:{name}", root=root)
                except subprocess.CalledProcessError:
                    return None
            raw = read(path)
            try:
                record = json.loads(raw)
            except (ValueError, TypeError):
                continue  # malformed rejected proposals acquire no authority
            if not isinstance(record, dict) or not all(isinstance(value, str) for value in record.values()):
                continue
            if (set(record) - {"retired_sha256"} != {"path", "owner", "before", "after", "reason"}
                    or registry.get(record["path"]) != record["owner"]
                    or not record["reason"].strip()
                    or read(record["path"]) is None
                    or digest(read(record["path"])) != record["after"]):
                continue
            grandfathered = digest(raw) in policy.get("grandfathered_revisions", {}).get(path, [])
            changed = git("diff", "--name-only", base, commit, "--", root=root).splitlines()
            prefixes = shared_prefixes(root, base, registry, policy, read, historical=True)
            if grandfathered or not outside_oracle_scope(changed, policy, runners | prefixes, read):
                accepted.add(path)
                break
    return accepted


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def revisions(root: Path, registry: dict, base_ref: str) -> dict:
    """Reviewed, append-only exact replacements; never a builder rebaseline flag."""
    directory = root / REVISIONS
    present = {str(p.relative_to(root)) for p in directory.glob("*.json")}
    existing = authorized_revision_paths(root, base_ref, registry, present)
    if existing - present:
        raise ValueError("Spine revision records cannot be removed")
    result = {}
    for path in sorted(present):
        raw = (root / path).read_text()
        commits = introductions(root, path)
        pinned_text(root, path, raw)
        record = json.loads(raw)
        if set(record) - {"retired_sha256"} != {"path", "owner", "before", "after", "reason"} or not record["reason"].strip():
            raise ValueError(f"{path}: invalid spine revision record")
        if "retired_sha256" in record and not re.fullmatch(r"[0-9a-f]{64}", record["retired_sha256"]):
            raise ValueError(f"{path}: invalid exact retired-content digest")
        target = record["path"]
        if registry.get(target) != record["owner"]:
            raise ValueError(f"{path}: revision owner differs from registry")
        # Several introductions can coexist after a squash + PR merge. Find
        # the pinned payload, never whichever parent the history walk favours.
        candidates = [git("show", f"{commit}:{target}", root=root) for commit in commits]
        revised = next((text for text in candidates if digest(text) == record["after"]), "") if commits else (root / target).read_text()
        result.setdefault(target, []).append((record, revised))
    return result


def revised_original(original: str, records: list, *, absorbed: int | None = None) -> str:
    for (previous, _), (following, _) in zip(records, records[1:]):
        if previous["after"] != following["before"]:
            raise ValueError(f"{following['path']}: broken revision chain")
    # A squash introduces the corrected file and its review records together.
    # That introducing commit is already the accepted oracle. Absorb only a
    # prefix ending at its exact digest; later revisions still need exact bytes.
    if absorbed is None:
        absorbed = 0
        for index, (record, _) in enumerate(records):
            if record["after"] == digest(original):
                absorbed = index + 1
    for record, revised in records[absorbed:]:
        if digest(revised) != record["after"]:
            raise ValueError(f"{record['path']}: revised bytes do not match pinned digest")
        if digest(original) != record["before"]:
            raise ValueError(f"{record['path']}: broken revision chain")
        before = [line for line in original.splitlines() if MARKER.fullmatch(line)]
        after = [line for line in revised.splitlines() if MARKER.fullmatch(line)]
        if before != after:
            raise ValueError(f"{record['path']}: revision must preserve pending markers; retire separately")
        original = revised
    return original


def accepted_checkpoint(root: Path, path: str, records: list, base_ref: str) -> tuple[str, int] | None:
    """Recover an exact accepted prefix without replaying squash-erased blobs.

    Only records already on the target confer this authority. A matching PR
    payload or an unrelated ref cannot authorize skipping a new revision.
    """
    accepted = [json.loads(git("show", f"{base_ref}:{name}", root=root))
                for name in git("ls-tree", "-r", "--name-only", base_ref, "--", REVISIONS, root=root).splitlines()]
    prefix = []
    for record, _ in records:
        if record not in accepted:
            break
        prefix.append(record["after"])
    if not prefix:
        return None
    # Try the target tree first. If builders retired its markers, retain the
    # exact full oracle from target history, never from an arbitrary branch.
    versions = [base_ref] + git("log", "--full-history", "--format=%H", base_ref, "--", path, root=root).splitlines()
    checkpoint, rank = None, -1
    for version in versions:
        try:
            text = git("show", f"{version}:{path}", root=root)
        except subprocess.CalledProcessError:
            continue  # a deletion is not an oracle payload
        fingerprint = digest(text)
        if fingerprint in prefix and prefix.index(fingerprint) > rank:
            checkpoint, rank = text, prefix.index(fingerprint)
            if rank == len(prefix) - 1:
                break
    return (checkpoint, rank + 1) if checkpoint is not None else None


def marker_slots(original: str, current: str) -> set[int] | None:
    """Identify retained marker occurrences, not just their count/package."""
    if not allowed(original, current):
        return None
    wanted = iter(current.splitlines(keepends=True))
    next_line = next(wanted, None)
    kept, slot = set(), 0
    for line in original.splitlines(keepends=True):
        marker = bool(MARKER.fullmatch(line.rstrip("\n")))
        if line == next_line:
            if marker:
                kept.add(slot)
            next_line = next(wanted, None)
        slot += marker
    return kept


def retirement_allowed(anchors: list[str], base: str, current: str) -> bool:
    remaining = marker_slots(anchors[-1], current)
    for anchor in anchors:
        retired_base = marker_slots(anchor, base)
        if retired_base is not None:
            return remaining is not None and remaining <= retired_base
    return False


def check(root: Path = ROOT, base_ref: str = "origin/main") -> list[str]:
    # One read snapshot per invocation, never retained across edits/checks.
    token = _reads.set({})
    try:
        return _check(root, base_ref)
    finally:
        _reads.reset(token)


def _check(root: Path, base_ref: str) -> list[str]:
    errors = []
    registry = json.loads((root / REGISTRY).read_text())
    if git("rev-parse", "--is-shallow-repository", root=root).strip() == "true":
        return ["Spine protection needs full history: git fetch --unshallow origin"]
    base = git("merge-base", "HEAD", base_ref, root=root).strip()
    errors.extend(revision_scope(root, base, registry))
    try:
        previous = json.loads(git("show", f"{base}:{REGISTRY}", root=root))
    except subprocess.CalledProcessError:
        previous = {}
    registry_commits = git("log", "--full-history", "--format=%H", "HEAD", "--", REGISTRY, root=root).splitlines()
    for commit in registry_commits:
        introduced = json.loads(git("show", f"{commit}:{REGISTRY}", root=root))
        for path, owner in introduced.items():
            if path in previous and previous[path] != owner:
                errors.append(f"{path}: conflicting registry owners in reachable history")
            previous[path] = owner
    for path, owner in previous.items():
        if registry.get(path) != owner:
            errors.append(f"{path}: existing registry entry changed/deleted")
    discovered = {str(p.relative_to(root)) for prefix in ROOTS for p in (root / prefix).rglob("*")
                  if p.is_file() and p.suffix in (".py", ".dart", ".json") and "__pycache__" not in p.parts}
    for path in discovered - registry.keys():
        errors.append(f"{path}: unregistered spine file")
    amendments = revisions(root, registry, base_ref)
    count = 0
    for path, owner in registry.items():
        file = root / path
        if not file.is_file():
            errors.append(f"{path}: protected file missing")
            continue
        current = file.read_text()
        commits = introductions(root, path)
        if commits:
            introduced = {git("show", f"{commit}:{path}", root=root) for commit in commits}
            records = amendments.get(path, [])
            absorbed = None
            if records:
                accepted = [records[0][0]["before"]] + [record["after"] for record, _ in records]
                candidates = [text for text in introduced if digest(text) in accepted]
                if not candidates:
                    raise ValueError(f"{path}: no introduction matches the pinned revision chain")
                checkpoint = accepted_checkpoint(root, path, records, base_ref)
                if checkpoint is None:
                    initial = min(candidates, key=lambda text: accepted.index(digest(text)))
                else:
                    initial, absorbed = checkpoint
                anchors = candidates
            else:
                initial = max(introduced, key=lambda text: (len(text), text))
                anchors = [initial]
            original = revised_original(initial, records, absorbed=absorbed)
            anchors += [text for _, text in records if text] + [original]
            retired_digests = {record["retired_sha256"] for record, _ in records if "retired_sha256" in record}
            def exact_retired(text):
                return digest(text) in retired_digests and not any(MARKER.fullmatch(line) for line in text.splitlines())
            if any(not exact_retired(text) and not any(allowed(anchor, text) for anchor in anchors) for text in introduced):
                raise ValueError(f"{path}: conflicting oracle introductions in reachable history")
            if not allowed(original, current) and not exact_retired(current):
                errors.append(f"{path}: only pending-marker removal allowed (spine {commits[-1]})")
            # Also enforce monotonic retirement against current main.
            try:
                base_text = git("show", f"{base_ref}:{path}", root=root)
            except subprocess.CalledProcessError:
                base_text = original
            # Corrections preserve ordered marker slots. Retiring another test
            # cannot pay for restoring a marker already retired on main.
            # A reviewed exact marker-free rendering has zero remaining slots.
            retired = "".join(line for line in original.splitlines(keepends=True) if not MARKER.fullmatch(line.rstrip("\n")))
            comparable_base = retired if exact_retired(base_text) else base_text
            comparable_current = retired if exact_retired(current) else current
            monotonic = retirement_allowed(anchors, comparable_base, comparable_current) if amendments.get(path) else allowed(base_text, current)
            if not monotonic:
                errors.append(f"{path}: retired markers cannot be restored")
        else:
            try:
                git("cat-file", "-e", f"HEAD:{path}", root=root)
            except subprocess.CalledProcessError:
                pass  # new spine, not yet committed
            else:
                errors.append(f"{path}: introducing commit unavailable; fetch full history")
        for number, line in enumerate(current.splitlines(), 1):
            match = MARKER.fullmatch(line)
            if owner != "MECHANISM" and re.match(r"^\s*(?:@pending\b|pendingContract\s*\()", line) and not match:
                errors.append(f"{path}:{number}: pending markers must be a complete standalone literal call")
            if match:
                package = next(value for value in match.groups() if value)
                count += 1
                print(f"PENDING {package} {path}:{number}")
                if package != owner:
                    errors.append(f"{path}:{number}: marker owner {package} != registry {owner}")
    print(f"Spine contracts: {count} pending markers; {len(registry)} protected files")
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="actual PR target; supplied by the checks manifest")
    args = parser.parse_args()
    try:
        problems = check(base_ref=args.base)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        problems = [str(exc)]
    for problem in problems:
        print(problem, file=sys.stderr)
    raise SystemExit(1 if problems else 0)
