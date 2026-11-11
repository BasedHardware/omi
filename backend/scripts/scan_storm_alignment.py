#!/usr/bin/env python3
"""Contention storm-alignment parity scanner for the batch contention family.

Property enforced: a function that re-offers work after a contention loss
must consume the measured storm window -- call one of the alignment helpers
(``contention_retry_after``, ``publication_restrike_storm_after``,
``_contention_storm_after``), reference the stamped ``retry_after``, or
consult the retry engine's ``inter_attempt_gate`` -- or re-offer with no
in-function wait at all (the cadence-aligned sweeps, which the store-level
damper and a >=5s cadence already space). A re-offer that sleeps on a bare
fixed ladder fires into the interior of the window the store's storm damper
armed for the label: the entry consult parks the lane's db-executor thread
on the residual sleep and a chain that still loses re-arms the very storm
the lane just re-entered. That lockstep burn is the root cause behind the
production ERROR family ``firestore_transaction_contention
operation=batch_pipeline_store attempt=5/5 outcome=exhausted`` and
``batch_merge`` / ``batch_completion`` ``outcome=retry
exception_type=FirestoreContentionExhausted``.

A surface is any function that (a) catches a contention exhaustion
(``FirestoreContentionExhausted`` / ``JobStoreContentionExhausted``), (b)
constructs or raises one by name, (c) classifies a loss as contention (a
call to ``publication_loss_is_contention``), (d) compares an error-type
string against a contention exhaustion name, or (e) passes the stamped
``retry_after=`` into a deferral contract. A wait is any ``sleep``-named
call (``asyncio.sleep``, ``time.sleep``, ``self._publication_sleep``, ...)
or a state-armed backoff: an assignment (``=``, ``+=``, ``:=``-style
annotated or augmented) to a ``*_backoff_until`` name holding a value that
is not a literal zero — the scheduler's shard pull lane parks its next
re-entry in ``_contention_backoff_until`` and sleeps on it at the entry
gate, so the arm IS the wait even though no ``sleep`` call sits in the
function. A finding is a surface + wait with no alignment reference
anywhere in the function body (nested helpers included, so moving the bare
ladder behind a closure is not an escape, mirroring the async-gate rule).

This property covers the shard pull lane directly: its contention handler
used to arm ``_contention_backoff_until`` from a bare ``2 ** failures``
ladder and discard the stamped window, so a shard that lost a chain
re-entered the armed window's interior, burned the next five-attempt chain
against a collision the damper had already measured, and re-armed the storm
it had just paid to leave — the lockstep burn behind the
``firestore_transaction_contention operation=... outcome=exhausted`` ERROR
family and the scheduler's ``event=batch_pull outcome=backoff`` lines.
``Scheduler.pull`` now consumes ``pull_contention_storm_after`` (the
stamped window raised to a floor under the lane's documented horizon), and
this scanner fails on any future arm that drops the measured window.

Ablation (--ablate, or ``ablate_source``): every alignment helper name is
rewritten to a dead ``__dealigned`` suffix and the source rescanned. The
parity fixture uses this to prove the scanner flags exactly the functions
whose alignment the landed source encodes through the helper names -- the
blackout regression surface for the re-strike collision class.

Usage:
  python3 scripts/scan_storm_alignment.py
  python3 scripts/scan_storm_alignment.py --json
  python3 scripts/scan_storm_alignment.py --ablate --json

Exit codes: 0 = clean; 1 = findings present; 2 = usage error.

Failure-Class: FC-publication-restrike-collides-inside-the-armed-storm-window
Failure-Class: FC-pull-backoff-collides-inside-the-armed-storm-window
"""

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# The scanner owns everything under backend/, resolved from this file's own
# location so the CLI, the test fixture and generated grids agree on one
# inventory regardless of the caller's working directory.
BACKEND_ROOT = Path(__file__).resolve().parents[1]

# The contention family this scanner owns: every module that re-offers
# batch work through or around the store's storm damper. Paths are relative
# to ``backend/``.
FAMILY_FILES: tuple = tuple(
    sorted(str(p.relative_to(BACKEND_ROOT)) for p in (BACKEND_ROOT / "utils" / "batch_pipeline").glob("*.py"))
    + [
        "database/batch_pipeline_store.py",
        "database/firestore_transaction_retry.py",
        "database/jobstore/postgres_store.py",
        "database/_client.py",
    ]
)

# Exception names whose catch, construction or raise marks a contention
# re-offer surface.
CONTENTION_EXHAUSTIONS = frozenset({"FirestoreContentionExhausted", "JobStoreContentionExhausted"})

# Calls that classify a loss as contention (the pump re-strike gate).
CONTENTION_CLASSIFIERS = frozenset({"publication_loss_is_contention"})

# Reference names that mark a function as a contention surface even without
# a typed catch (construction/raise sites, classifier calls).
SURFACE_REFERENCE_NAMES = CONTENTION_EXHAUSTIONS | CONTENTION_CLASSIFIERS

# Alignment helpers: calls to these consume the measured storm window.
ALIGNMENT_CALLS = frozenset(
    {
        "contention_retry_after",
        "publication_restrike_storm_after",
        "_contention_storm_after",
        "pull_contention_storm_after",
    }
)

# Ablation target: the helper names above, renamed to a dead suffix.
DEALIGNED_SUFFIX = "__dealigned"
_ABLATION_PATTERN = re.compile(
    r"\b(" + "|".join(sorted((re.escape(n) for n in ALIGNMENT_CALLS), key=len, reverse=True)) + r")\b"
)

# Call names that park the caller waiting (bare ladders all bottom out here).
WAIT_CALL_NAMES = frozenset({"sleep"})


def ablate_source(source: str) -> str:
    """Rename every alignment helper to its dead ``__dealigned`` form.

    Word-bounded, so ``contention_retry_after_default`` keeps its name and
    the rewrite is idempotent (an already-dealigned name no longer matches).
    """
    return _ABLATION_PATTERN.sub(lambda m: m.group(1) + DEALIGNED_SUFFIX, source)


def _handler_names(node) -> set:
    """The simple names an except clause catches (tuples flattened)."""
    names: set = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Attribute):
        names.add(node.attr)
    elif isinstance(node, ast.Tuple):
        for element in node.elts:
            names |= _handler_names(element)
    return names


def _backoff_target_names(targets: list) -> set:
    """The ``*_backoff_until`` deadline names among assignment targets (tuples flattened)."""
    names: set = set()
    for target in targets:
        if isinstance(target, ast.Name):
            if target.id.endswith('_backoff_until'):
                names.add(target.id)
        elif isinstance(target, ast.Attribute):
            if target.attr.endswith('_backoff_until'):
                names.add(target.attr)
        elif isinstance(target, (ast.Tuple, ast.List)):
            names |= _backoff_target_names(target.elts)
    return names


def _backoff_arm(targets: list, value) -> bool:
    """True when an assignment arms a ``*_backoff_until`` re-entry deadline.

    The scheduler's pull lane parks its next re-entry in
    ``_contention_backoff_until`` and sleeps on it at the entry gate, so the
    arm is the wait even though no ``sleep`` call sits in the arming
    function. Assigning a literal zero (int or float) is the clear, not an
    arm: the init and the clean-pull reset both store ``0.0`` and never park
    anything. Subscript and starred targets are not recognized deadline
    stores and count nothing. Never raises.
    """
    if isinstance(value, ast.Constant) and isinstance(value.value, (int, float)) and not value.value:
        return False
    return bool(_backoff_target_names(targets))


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _qualname(tree: ast.AST, node) -> str:
    """A stable per-module identity: ``Class.method`` / ``outer.inner``.

    Nested same-name functions stay distinct, so grid cells pin exactly the
    function they were generated against.
    """
    parents: dict = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    parts: list = []
    current = node
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            parts.append(current.name)
        current = parents.get(id(current))
    return ".".join(reversed(parts)) or node.name


class FunctionVerdict:
    """One function's storm-alignment posture, as the scanner sees it."""

    __slots__ = ("module", "name", "qualname", "order", "surface", "waits", "aligned")

    def __init__(self, module: str, name: str, qualname: str, order: int):
        self.module = module
        self.name = name
        self.qualname = qualname
        self.order = order
        self.surface = False
        self.waits = 0
        self.aligned = False

    @property
    def finding(self):
        """The scanner's verdict for this function, or None when clean.

        A finding is a contention surface that also waits without any
        alignment reference: the bare-ladder collision shape.
        """
        if self.surface and self.waits and not self.aligned:
            return (
                f"bare contention re-offer: {self.qualname} catches/classifies a contention "
                f"loss and waits {self.waits}x without consuming the measured storm window"
            )
        return None


def catalog_source(source: str, module: str) -> dict:
    """Scan one module's source; return {qualname: finding-or-None}.

    Every function gets an entry (None = clean), so a fixture can enumerate
    the full judged inventory rather than only the flagged surface. Nested
    defs are judged both on their own and as part of their parent (the
    parent's walk includes nested bodies), so a bare ladder cannot hide
    behind a closure the way the async gate forbids hiding behind a
    module-local helper.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        return {f"<module:{module}>": f"unparsable source: {error}"}

    verdicts: dict = {}
    order = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        qualname = _qualname(tree, node)
        verdict = verdicts.get(qualname)
        if verdict is None:
            verdict = FunctionVerdict(module, node.name, qualname, order)
            verdicts[qualname] = verdict
            order += 1
        for inner in ast.walk(node):
            if isinstance(inner, ast.ExceptHandler):
                if _handler_names(inner.type) & CONTENTION_EXHAUSTIONS:
                    verdict.surface = True
            elif isinstance(inner, ast.Assign):
                if _backoff_arm(inner.targets, inner.value):
                    verdict.waits += 1
            elif isinstance(inner, ast.AugAssign):
                if _backoff_arm([inner.target], inner.value):
                    verdict.waits += 1
            elif isinstance(inner, ast.AnnAssign):
                if inner.value is not None and _backoff_arm([inner.target], inner.value):
                    verdict.waits += 1
            elif isinstance(inner, ast.Call):
                name = _call_name(inner)
                if name in CONTENTION_CLASSIFIERS:
                    verdict.surface = True
                if name in WAIT_CALL_NAMES or name.endswith("_sleep"):
                    verdict.waits += 1
                for keyword in inner.keywords:
                    if keyword.arg == "retry_after":
                        # Passing the stamped window into a deferral
                        # contract is both a contention surface and the
                        # alignment act itself.
                        verdict.surface = True
                        verdict.aligned = True
            elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                if inner.value in CONTENTION_EXHAUSTIONS:
                    verdict.surface = True
            elif isinstance(inner, ast.Name) and inner.id in SURFACE_REFERENCE_NAMES:
                # Constructing, raising or classifying by name is contention
                # handling, not merely a mention.
                verdict.surface = True
            elif isinstance(inner, ast.Attribute) and inner.attr in ("retry_after", "inter_attempt_gate"):
                verdict.aligned = True
            elif isinstance(inner, ast.arg) and inner.arg in ("retry_after", "inter_attempt_gate"):
                verdict.aligned = True
            elif isinstance(inner, ast.Name) and inner.id in ALIGNMENT_CALLS:
                verdict.aligned = True
            elif isinstance(inner, ast.Name) and inner.id == "inter_attempt_gate":
                # The retry engine's caller-owned contention-shaping gate is
                # the alignment contract at the engine layer: the gate
                # returns the armed window's residual and the chain adds it
                # to the inter-attempt wait.
                verdict.aligned = True
    return {qualname: verdict.finding for qualname, verdict in verdicts.items()}


def scan_source(source: str, module: str) -> dict:
    """The flagged subset of ``catalog_source``: {qualname: [finding]}."""
    return {qualname: [finding] for qualname, finding in catalog_source(source, module).items() if finding}


def scan_tree(root=BACKEND_ROOT, files=FAMILY_FILES) -> dict:
    """Scan the family files under ``root`` (a backend/ directory)."""
    findings: dict = {}
    for rel in files:
        path = Path(root) / rel
        if not path.is_file():
            findings[f"<missing:{rel}>"] = ["family file missing from this checkout"]
            continue
        module_findings = scan_source(path.read_text(encoding="utf-8"), rel)
        for qualname, messages in module_findings.items():
            findings[f"{rel}::{qualname}"] = messages
    return findings


def scan_tree_catalog(root=BACKEND_ROOT, files=FAMILY_FILES) -> dict:
    """Full per-function catalog across the family: {'rel::qualname': verdict}."""
    catalog: dict = {}
    for rel in files:
        path = Path(root) / rel
        if not path.is_file():
            catalog[f"<missing:{rel}>"] = "family file missing from this checkout"
            continue
        for qualname, finding in catalog_source(path.read_text(encoding="utf-8"), rel).items():
            catalog[f"{rel}::{qualname}"] = finding
    return catalog


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Contention storm-alignment parity scanner")
    parser.add_argument("--root", default=str(BACKEND_ROOT), help="backend/ directory holding the family files")
    parser.add_argument("--ablate", action="store_true", help="scan the dealigned posture instead")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    findings: dict = {}
    for rel in FAMILY_FILES:
        path = Path(args.root) / rel
        if not path.is_file():
            findings[f"<missing:{rel}>"] = ["family file missing from this checkout"]
            continue
        source = path.read_text(encoding="utf-8")
        if args.ablate:
            source = ablate_source(source)
        for qualname, messages in scan_source(source, rel).items():
            findings[f"{rel}::{qualname}"] = messages

    if args.json:
        print(json.dumps({"ablated": args.ablate, "findings": findings}, indent=2, sort_keys=True))
    else:
        for key in sorted(findings):
            for message in findings[key]:
                print(f"{key}: {message}")
        print(f"{len(findings)} finding(s)" + (" (ablated posture)" if args.ablate else ""))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
