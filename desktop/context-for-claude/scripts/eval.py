#!/usr/bin/env python3
"""Quality eval for Context for Claude's MCP surface.

`swift test` proves the code does what it was written to do. It proves nothing about whether the
*answers* are any good — and the central claim of this product is epistemic: that a model reading a
tool result can tell "this did not happen" from "this was not captured". That claim can only be
checked by asking the shipping binary real questions against a known corpus and reading what comes
back.

So this drives the real `context-for-claude-mcp` over stdio, against a throwaway database it seeds
itself, and scores nine classes of behaviour. Most of them are about honesty under adversarial
conditions rather than recall.

    python3 scripts/eval.py                 # build if needed, run, print a summary
    python3 scripts/eval.py --only ranking  # one class
    python3 scripts/eval.py --floor 0.9     # stricter gate

Exit codes: 0 pass · 1 below the floor or a critical check failed · 2 the harness could not run
(build failure, or isolation could not be proven).

Hermetic by construction:

  * its own temp home, seeded from scratch, deleted afterwards;
  * `CFFIXED_USER_HOME` is what actually redirects an AppKit-less macOS binary — `HOME` alone does
    **not**: `FileManager.urls(for: .applicationSupportDirectory)` resolves the real home through
    the password database and cheerfully ignores `HOME`. That was verified the hard way, so the
    first thing this script does is make the binary *print* the database path it opened and refuse
    to score anything unless that path is inside the temp root;
  * the child process gets an explicitly built environment, never this one's, so no
    `CONTEXT_OMI_MCP_KEY` can leak in. With no credential reachable the Omi half never runs, which
    is what makes the run offline — and is itself the "one half could not be searched" condition
    several checks are about.

No dependencies beyond the standard library.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

PKG_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BINARY = PKG_ROOT / ".build" / "release" / "context-for-claude-mcp"
RESULTS_PATH = PKG_ROOT / "dist" / "eval-results.json"

# The overall gate. Set just under the score measured at the commit that introduced this file, so
# it catches a regression rather than blessing one. Ratchet it upward as classes are fixed; never
# lower it to make a build pass.
OVERALL_FLOOR = 0.93

# Checks that fail today, each with the defect behind it.
#
# A known failure still scores zero — the overall number tells the truth about the product and rises
# when one is fixed — but it does not turn the build red, so the gate stays usable while these are
# worked through. Anything failing that is *not* listed here is a new regression and does fail the
# build. `--strict` ignores this list. Delete an entry the moment its check passes; the run prints a
# nudge when one does.
KNOWN_FAILURES: dict[str, str] = {
    # Empty on purpose. Every entry here suppresses gating on a check that is genuinely failing,
    # so an entry that outlives its defect silently disarms the harness. Add one only with the
    # cause written down, and delete it in the same change that fixes the cause.
}

# Weights say what this product is for. Filter integrity and confabulation are doubled because both
# make a reader believe something false about the user's life; findability is only the price of
# admission.
CLASS_WEIGHTS = {
    "findability": 1.5,
    "no_confabulation": 2.0,
    "ranking": 1.0,
    "dedup": 1.0,
    "uncertainty": 1.0,
    "filter_integrity": 2.0,
    "bad_input": 1.0,
    "coherence": 1.0,
    "protocol": 0.75,
    "traceability": 0.75,
}

CLASS_ORDER = list(CLASS_WEIGHTS)

UNCERTAIN_MARKER = "(uncertain — may be background audio, not speech)"


# --------------------------------------------------------------------------------- corpus


def describe(epoch: float) -> str:
    """The Swift side's `ContextTime.describe`, so a check can assert the exact printed boundary."""
    return time.strftime("%a %-d %b %Y at %-I:%M %p", time.localtime(epoch))


def iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


LOREM = (
    "the roadmap review covered staffing latency and the migration order agenda items were "
    "carried over from the previous week nobody objected to the proposed sequencing and the "
    "owner of each workstream confirmed the dates before the meeting closed with a short "
    "discussion of hiring and the budget for the following quarter which remains unchanged"
).split()


def filler(seed: int, words: int) -> str:
    """Deterministic filler prose. Distinct per seed so two frames are never accidental duplicates."""
    out = []
    for i in range(words):
        out.append(LOREM[(seed * 7 + i * 3) % len(LOREM)])
    return " ".join(out)


@dataclass
class Corpus:
    """The seeded world, plus every fact a check needs to state its expectation exactly."""

    a0: float  # region A — the content corpus
    b0: float  # region B — the filter probes
    sessions: list[tuple[int, float, float, str]] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    frames: list[dict] = field(default_factory=list)

    def frame(self, at: float, app: str, window: str, ocr: str) -> None:
        self.frames.append({"at": at, "app": app, "window": window, "ocr": ocr})

    def segment(self, session: int, at: float, source: str, text: str, confidence) -> None:
        self.segments.append(
            {
                "session": session,
                "at": at,
                "source": source,
                "text": text,
                "confidence": confidence,
            }
        )

    def frames_at(self, lo: float, hi: float) -> list[dict]:
        return [f for f in self.frames if lo <= f["at"] <= hi]


# Nonces. Every filter probe carries one, so a range check is a set comparison against rows this
# script placed itself rather than a guess about what the renderer meant.
NONCE = {
    "a1": "nqxalphaone",
    "a2": "nqxalphatwo",
    "b1": "nqxbetaone",
    "b2": "nqxbetatwo",
    "g1": "nqxgammaone",
    "g2": "nqxgammatwo",
}
ALL_PROBE_NONCES = set(NONCE.values())

# Region A's distinctive terms, each seeded exactly once unless noted.
TERM_HALYARD = "Halyard"  # speech, one occurrence
TERM_PRIYANKA = "Priyanka"  # speech, one occurrence
TERM_ZEPHYRINE = "Zephyrine"  # speech, two occurrences
TERM_THERMOPYLAE = "Thermopylae"  # screen, window title only
TERM_BASILISK = "basilisk"  # screen, buried mid-OCR
TERM_WARP_NOVEL = "quicksilver"  # the frame that must not collapse
TERM_UNSEEN = "flibbertigibbet"  # never captured
TERM_NEAR_MISS = "basilica"  # lexically near `basilisk`, never captured
TERM_KESTREL = "Kestrel"  # ranking: full-coverage match, oldest, against partial matches
TERM_GAP = "tailwatcher"  # two identical frames either side of the moment gap


def build_corpus(now: float) -> Corpus:
    """Two disjoint time regions.

    Region A is the content corpus — findability, ranking, dedup, confidence — and its text is kept
    clean so nothing distorts bm25. Region B holds the filter probes, every row tagged with a nonce,
    so `since` / `until` / `app` can be scored as exact set equality instead of eyeballed.
    """
    t0 = math.floor(now / 60) * 60 - 8 * 3600
    c = Corpus(a0=t0, b0=t0 + 4 * 3600)
    a, b = c.a0, c.b0

    # -- speech ------------------------------------------------------------------
    c.sessions = [
        (1, a + 0, a + 600, "Zoom"),
        (2, a + 1200, a + 1400, "Slack"),
        (3, a + 2000, a + 2100, "Meet"),
    ]

    # Session 1 carries the confidence spread: high, low, unknown, very high.
    c.segment(1, a + 10, "mic", f"We agreed to ship the {TERM_HALYARD} migration on Friday.", 0.92)
    c.segment(1, a + 40, "system", "the invoice came to three thousand two hundred euros", 0.41)
    c.segment(1, a + 70, "mic", "Let us park the pricing discussion until next week.", None)
    c.segment(
        1, a + 100, "mic", f"Remind me to email {TERM_PRIYANKA} about the vendor contract.", 0.99
    )
    c.segment(2, a + 1210, "mic", f"The codename for the launch is {TERM_ZEPHYRINE}.", 0.88)
    c.segment(2, a + 1240, "system", f"I will send the {TERM_ZEPHYRINE} brief tonight.", 0.95)

    # Session 3 is the confidence boundary, one line per case. The floor is `<`, so a score sitting
    # exactly on it is certain enough; a score outside 0…1 is not a probability on this scale at all
    # and must say nothing rather than mark everything the day someone stores log-probabilities.
    c.segment(3, a + 2000, "mic", "Boundary sample exactlyatfloor please ignore.", 0.65)
    c.segment(3, a + 2010, "mic", "Boundary sample justunderfloor please ignore.", 0.649)
    c.segment(3, a + 2020, "mic", "Boundary sample zeroscore please ignore.", 0.0)
    c.segment(3, a + 2030, "mic", "Boundary sample perfectscore please ignore.", 1.0)
    c.segment(3, a + 2040, "mic", "Boundary sample negativelogprob please ignore.", -3.2)
    c.segment(3, a + 2050, "mic", "Boundary sample aboveone please ignore.", 5.0)

    # -- ranking: one genuine match, six incidental ones, all of them newer -------
    c.frame(
        a + 1500,
        "Cursor",
        "SCA-219: Parity Pack v0 — omi",
        "SCA-219 Parity Pack v0: one PR (dev whitelist capture). Reviewers asked for a smaller diff "
        "before the parity pack lands.",
    )
    decoys = [
        "Inbox (12) - Gmail",
        "Hacker News",
        "Amazon | Bulk pack deals",
        "Notion - Sprint board",
        "GitHub - pull requests",
        "YouTube",
    ]
    for i, title in enumerate(decoys):
        c.frame(
            a + 1600 + i * 60,
            "Arc",
            title,
            "Bookmarks Bar: Pack Tracker - Battery Pack - Pack Reviews - Vacation packing list "
            f"- Six Pack Fitness. {filler(i, 40)}",
        )

    # -- ranking, second shape: decoys strong enough to clear the relevance floor -
    #
    # The SCA-219 cluster is floored out entirely, so it tests the floor rather than the order.
    # Here the decoys share two of three query words and *do* survive, and the genuine match is the
    # oldest row in the corpus — so only relevance, not recency, can put it first.
    c.frame(
        a + 300,
        "Notion",
        f"{TERM_KESTREL} deployment checklist — Notion",
        f"{TERM_KESTREL} deployment checklist: rollback plan, canary window, alert owners.",
    )
    for i, title in enumerate(
        ["Deployment guide - docs", "Checklist template", "Deployment status", "Checklist archive"]
    ):
        c.frame(
            a + 3000 + i * 60,
            "Chrome",
            title,
            f"deployment checklist steps and deployment notes. {filler(i + 20, 40)}",
        )

    # -- findability: title-only, and buried mid-body ----------------------------
    c.frame(
        a + 2200,
        "Obsidian",
        f"{TERM_THERMOPYLAE} notes — Obsidian",
        "Meeting agenda. Follow up on the roadmap next week. No further detail recorded here.",
    )
    body = filler(3, 60) + f" the {TERM_BASILISK} is a legendary serpent " + filler(9, 60)
    c.frame(a + 2300, "Safari", "Mythology - Wikipedia", body)

    # -- dedup: twelve near-identical frames of one window, then a real change ----
    spinners = ["✳", "⠂", "⠐", "⠠", "⢀", "⡀", "⠄", "⠆", "⠇", "⠋", "⠙", "⠹"]
    base = filler(5, 60).split()
    for i in range(12):
        words = list(base)
        words[i % len(words)] = f"tick{i}"  # one word of churn, the way an OCR pass wobbles
        c.frame(a + 2500 + i * 3, "Warp", f"{spinners[i]} claude — omi", " ".join(words))
    c.frame(
        a + 2600,
        "Warp",
        "⠸ claude — omi",
        f"{TERM_WARP_NOVEL} " + filler(31, 60),
    )

    # -- dedup, the other direction: identical text either side of the moment gap -
    # Same window, same words; only the eleven-minute gap makes them two events.
    gap_ocr = f"{TERM_GAP} tail -f server.log waiting for the next line to arrive"
    c.frame(a + 3300, "Terminal", "logs — tail", gap_ocr)
    c.frame(a + 3300 + 700, "Terminal", "logs — tail", gap_ocr)

    # -- region B: filter probes -------------------------------------------------
    probes = [
        (b + 0, "ProbeAlpha", "Alpha One", NONCE["a1"]),
        (b + 300, "ProbeAlpha", "Alpha Two", NONCE["a2"]),
        (b + 1200, "ProbeBeta", "Beta One", NONCE["b1"]),
        (b + 1500, "ProbeBeta", "Beta Two", NONCE["b2"]),
        (b + 2400, "ProbeGamma", "Gamma One", NONCE["g1"]),
        (b + 2700, "ProbeGamma", "Gamma Two", NONCE["g2"]),
    ]
    for i, (at, app, window, nonce) in enumerate(probes):
        c.frame(at, app, window, f"probeword {nonce} filter probe row {filler(i + 40, 25)}")

    # Two dense runs, far enough apart to be separate activity blocks.
    for k in range(8):
        c.frame(b + 3300 + k * 30, "ProbeDelta", "Delta Work", f"deltaword {filler(k + 60, 20)}")
    for k in range(8):
        c.frame(b + 3900 + k * 30, "ProbeEpsilon", "Eps Work", f"epsilonword {filler(k + 70, 20)}")

    return c


# --------------------------------------------------------------------------------- seeding

# The schema of `Sources/ContextCore/Store.swift` (migrations v1, v3, v4), written directly rather
# than through a Swift shim so this script stays dependency-free. The FTS5 tables must keep their
# exact column order: `Queries.matchedFrames` passes positional bm25 weights to
# `frames_fts(ocrText, windowTitle, appName)`, and reordering them silently reweights the ranker.
SCHEMA = """
CREATE TABLE sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  startedAt DOUBLE NOT NULL,
  endedAt DOUBLE,
  appHint TEXT
);
CREATE INDEX idx_sessions_startedAt ON sessions(startedAt);

CREATE TABLE segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sessionId INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  startedAt DOUBLE NOT NULL,
  endedAt DOUBLE NOT NULL,
  source TEXT NOT NULL,
  speaker TEXT NOT NULL,
  text TEXT NOT NULL,
  confidence DOUBLE,
  speakerLabel TEXT,
  personId TEXT
);
CREATE INDEX idx_segments_startedAt ON segments(startedAt);
CREATE INDEX idx_segments_sessionId ON segments(sessionId, startedAt);

CREATE TABLE frames (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  capturedAt DOUBLE NOT NULL,
  appName TEXT,
  windowTitle TEXT,
  ocrText TEXT,
  imagePath TEXT
);
CREATE INDEX idx_frames_capturedAt ON frames(capturedAt);
CREATE INDEX idx_frames_app ON frames(appName, capturedAt);

CREATE VIRTUAL TABLE segments_fts USING fts5(
  text, content='segments', content_rowid='id', tokenize='porter unicode61'
);
CREATE VIRTUAL TABLE frames_fts USING fts5(
  ocrText, windowTitle, appName, content='frames', content_rowid='id',
  tokenize='porter unicode61'
);
"""


def seed_database(path: Path, corpus: Corpus | None) -> None:
    """Writes a fixture database.

    Left in rollback-journal mode on purpose. GRDB's reader opens read-only, and a WAL database with
    no live writer has no `-shm` file that a read-only connection is allowed to create — SQLite
    answers `error 14: unable to open database file`. In production the app is the writer holding
    those sidecars open; here there is no writer, so the fixture must not be in WAL.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    try:
        db.executescript(SCHEMA)
        if corpus:
            for sid, started, ended, hint in corpus.sessions:
                db.execute(
                    "INSERT INTO sessions(id, startedAt, endedAt, appHint) VALUES (?,?,?,?)",
                    (sid, started, ended, hint),
                )
            for s in corpus.segments:
                speaker = "me" if s["source"] == "mic" else "them"
                db.execute(
                    "INSERT INTO segments(sessionId, startedAt, endedAt, source, speaker, text,"
                    " confidence) VALUES (?,?,?,?,?,?,?)",
                    (
                        s["session"],
                        s["at"],
                        s["at"] + 5,
                        s["source"],
                        speaker,
                        s["text"],
                        s["confidence"],
                    ),
                )
            for f in corpus.frames:
                db.execute(
                    "INSERT INTO frames(capturedAt, appName, windowTitle, ocrText, imagePath)"
                    " VALUES (?,?,?,?,NULL)",
                    (f["at"], f["app"], f["window"], f["ocr"]),
                )
            # External-content FTS: the base tables stay the only copy of the text.
            db.execute("INSERT INTO segments_fts(rowid, text) SELECT id, text FROM segments")
            db.execute(
                "INSERT INTO frames_fts(rowid, ocrText, windowTitle, appName)"
                " SELECT id, ocrText, windowTitle, appName FROM frames"
            )
        db.commit()
    finally:
        db.close()


def write_heartbeat(home: Path, capturing: bool, capabilities: list[tuple[str, bool, str]]) -> None:
    state = {
        "capturing": capturing,
        "pausedReason": None if capturing else "Paused for the eval",
        "capabilities": [
            {"name": n, "granted": g, "detail": d} for n, g, d in capabilities
        ],
        "updatedAt": time.time(),
    }
    support = home / "Library" / "Application Support" / "ContextForClaude"
    support.mkdir(parents=True, exist_ok=True)
    (support / "capture-state.json").write_text(json.dumps(state))


GRANTED = [
    ("microphone", True, "Granted"),
    ("systemAudio", True, "Granted"),
    ("screen", True, "Granted"),
]
SCREEN_DENIED = [
    ("microphone", True, "Granted"),
    ("systemAudio", True, "Granted"),
    ("screen", False, "Screen Recording is off in System Settings"),
]


# --------------------------------------------------------------------------------- stdio client


class ProtocolViolation(RuntimeError):
    pass


class Server:
    """One `context-for-claude-mcp` process, spoken to over line-delimited JSON-RPC.

    Every line the server writes to stdout is recorded, because "stdout carries the protocol and
    nothing else" is itself one of the things under test: a stray `print` anywhere in the binary
    corrupts the stream and Claude drops the connection.
    """

    def __init__(self, binary: Path, home: Path):
        env = {
            # `CFFIXED_USER_HOME` is the one that works; `HOME` is set too so anything reading it
            # directly agrees. Nothing else is inherited — an inherited CONTEXT_OMI_MCP_KEY would
            # put this run on the network and against a real account.
            "HOME": str(home),
            "CFFIXED_USER_HOME": str(home),
            "TMPDIR": str(home / "tmp"),
            "PATH": "/usr/bin:/bin",
            "LANG": "en_US.UTF-8",
        }
        (home / "tmp").mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=str(home),
        )
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.raw_stdout: list[str] = []
        self.stderr: list[str] = []
        self._next_id = 1
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    def _pump_stdout(self) -> None:
        assert self.proc.stdout
        for raw in self.proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if not line:
                continue
            self.raw_stdout.append(line)
            self.lines.put(line)

    def _pump_stderr(self) -> None:
        assert self.proc.stderr
        for raw in self.proc.stderr:
            self.stderr.append(raw.decode("utf-8", "replace").rstrip("\n"))

    def send_raw(self, payload: bytes) -> None:
        assert self.proc.stdin
        self.proc.stdin.write(payload)
        self.proc.stdin.flush()

    def send(self, obj: dict) -> None:
        self.send_raw((json.dumps(obj) + "\n").encode("utf-8"))

    def read(self, timeout: float = 30.0) -> dict:
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty as exc:
            raise ProtocolViolation("no response within %.0fs" % timeout) from exc
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolViolation("stdout line is not JSON: %r" % line[:200]) from exc

    def request(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        rid = self._next_id
        self._next_id += 1
        frame = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            frame["params"] = params
        self.send(frame)
        response = self.read(timeout)
        if response.get("id") != rid:
            raise ProtocolViolation(f"id mismatch: asked {rid}, got {response.get('id')}")
        return response

    def initialize(self) -> dict:
        return self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "eval", "version": "0"},
            },
        )

    def call(self, tool: str, arguments: dict | None = None) -> "ToolResult":
        response = self.request("tools/call", {"name": tool, "arguments": arguments or {}})
        return ToolResult(tool, arguments or {}, response)

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()


@dataclass
class ToolResult:
    tool: str
    arguments: dict
    response: dict

    @property
    def text(self) -> str:
        content = self.response.get("result", {}).get("content") or []
        return "\n".join(part.get("text", "") for part in content)

    @property
    def is_error(self) -> bool:
        return bool(self.response.get("result", {}).get("isError"))

    @property
    def rpc_error(self) -> dict | None:
        return self.response.get("error")

    def label(self) -> str:
        return f"{self.tool}({json.dumps(self.arguments, ensure_ascii=False)})"


# --------------------------------------------------------------------------------- parsing

HIT_RE = re.compile(
    r"^- \*\*(?P<time>[^*]+)\*\* · \*(?P<kind>[a-z ]+)\*"
    r"(?: · (?P<origin>live|omi))?"
    r"(?: \((?P<ctx>.*?)\))?"
    r"(?:: (?P<body>.*))?$"
)
FRAMES_RE = re.compile(r"^\[(\d+) frames · ")


@dataclass
class Hit:
    raw: str
    kind: str
    origin: str | None
    app: str | None
    window: str | None
    body: str
    uncertain: bool
    frames: int


def parse_hits(text: str) -> list[Hit]:
    hits = []
    for line in text.splitlines():
        m = HIT_RE.match(line.strip())
        if not m:
            continue
        ctx = m.group("ctx") or ""
        uncertain = UNCERTAIN_MARKER in line
        app = window = None
        if m.group("kind") == "screen" and ctx:
            if " — " in ctx:
                app, window = ctx.split(" — ", 1)
                window = window.strip('"')
            else:
                app = ctx
        body = m.group("body") or ""
        fm = FRAMES_RE.match(body)
        hits.append(
            Hit(
                raw=line.strip(),
                kind=m.group("kind"),
                origin=m.group("origin"),
                app=app,
                window=window,
                body=body,
                uncertain=uncertain,
                frames=int(fm.group(1)) if fm else 1,
            )
        )
    return hits


def nonces_in(text: str) -> set[str]:
    lowered = text.lower()
    return {n for n in ALL_PROBE_NONCES if n in lowered}


def stem_prefix(term: str) -> str:
    """A crude stem, only ever used to ask 'does this hit contain any query word at all'."""
    term = re.sub(r"[^a-z0-9]", "", term.lower())
    return term[: max(4, len(term) - 3)]


def contains_any_term(hit_text: str, query: str) -> bool:
    lowered = re.sub(r"[^a-z0-9 ]", " ", hit_text.lower())
    for word in query.split():
        stem = stem_prefix(word)
        if len(stem) >= 3 and stem in lowered:
            return True
    return False


def has_any(text: str, phrases: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(p.lower() in lowered for p in phrases)


# --------------------------------------------------------------------------------- reporting


@dataclass
class Check:
    cls: str
    name: str
    ok: bool
    reason: str
    critical: bool = False
    weight: float = 1.0
    excerpt: str = ""


class Report:
    def __init__(self) -> None:
        self.checks: list[Check] = []
        self.metrics: dict[str, Any] = {}

    def add(
        self,
        cls: str,
        name: str,
        ok: bool,
        reason: str,
        *,
        critical: bool = False,
        weight: float = 1.0,
        excerpt: str = "",
    ) -> None:
        self.checks.append(
            Check(cls, name, bool(ok), reason, critical, weight, excerpt[:400] if not ok else "")
        )

    def metric(self, name: str, value: Any) -> None:
        self.metrics[name] = value

    def class_score(self, cls: str) -> tuple[float, int, int]:
        rows = [c for c in self.checks if c.cls == cls]
        if not rows:
            return (1.0, 0, 0)
        total = sum(c.weight for c in rows)
        passed = sum(c.weight for c in rows if c.ok)
        return (passed / total, sum(1 for c in rows if c.ok), len(rows))

    def overall(self) -> float:
        num = den = 0.0
        for cls in CLASS_ORDER:
            rows = [c for c in self.checks if c.cls == cls]
            if not rows:
                continue
            score, _, _ = self.class_score(cls)
            weight = CLASS_WEIGHTS[cls]
            num += score * weight
            den += weight
        return num / den if den else 0.0

    def critical_failures(self, strict: bool = False) -> list[Check]:
        """Critical failures that gate the build. Tracked ones are excluded unless `strict`."""
        return [
            c
            for c in self.checks
            if c.critical and not c.ok and (strict or c.name not in KNOWN_FAILURES)
        ]

    def unexpected_failures(self, strict: bool = False) -> list[Check]:
        return [c for c in self.checks if not c.ok and (strict or c.name not in KNOWN_FAILURES)]

    def resolved_known_failures(self) -> list[str]:
        return sorted(c.name for c in self.checks if c.ok and c.name in KNOWN_FAILURES)


# --------------------------------------------------------------------------------- checks


def check_findability(report: Report, s: Server, c: Corpus) -> None:
    cls = "findability"

    cases = [
        ("single-occurrence spoken term", TERM_HALYARD, "halyard", "me"),
        ("term in a window title only", TERM_THERMOPYLAE, "thermopylae", "screen"),
        ("term buried mid-OCR", TERM_BASILISK, "basilisk", "screen"),
        ("repeated spoken term, lowercased query", "zephyrine", "zephyrine", "me"),
    ]
    for label, query, needle, kind in cases:
        r = s.call("recall", {"query": query})
        hits = parse_hits(r.text)
        found = [h for h in hits if needle in h.raw.lower()]
        report.add(
            cls,
            f"recall finds {label}",
            bool(found),
            f'"{query}" → {len(hits)} hit(s), {len(found)} containing "{needle}"',
            excerpt=r.text,
        )
        if found:
            report.add(
                cls,
                f"{label} comes back as the right kind",
                any(h.kind == kind for h in found),
                f"expected a *{kind}* hit, got {[h.kind for h in found]}",
                excerpt=r.text,
            )

    r = s.call("recall", {"query": "vendor contract Priyanka"})
    hits = parse_hits(r.text)
    report.add(
        cls,
        "multi-word query returns the one document holding all three words",
        bool(hits) and "priyanka" in hits[0].raw.lower(),
        f"top hit: {hits[0].raw[:90] if hits else '(none)'}",
        excerpt=r.text,
    )

    r = s.call("recall", {"query": "migrations"})
    report.add(
        cls,
        "porter stemming finds an inflected form",
        any("halyard" in h.raw.lower() for h in parse_hits(r.text)),
        '"migrations" should reach the seeded "migration"',
        excerpt=r.text,
    )

    # A term matched only through the app name column.
    r = s.call("recall", {"query": "Obsidian"})
    report.add(
        cls,
        "recall matches on the app name",
        any(h.app == "Obsidian" for h in parse_hits(r.text)),
        f"{len(parse_hits(r.text))} hit(s) for an app-name query",
        excerpt=r.text,
    )

    # Punctuated identifiers. The query sanitizer strips FTS operator characters and joins what is
    # left ("SCA-219" → the single term `sca219`), while the unicode61 index split the very same
    # string into `sca` and `219`. The two readings never meet, so the exact ticket the user was
    # looking at is unfindable by its own name — and the empty answer is phrased as a searched-and-
    # found-nothing negative, which is the licence to say it never happened.
    r = s.call("recall", {"query": "SCA-219"})
    report.add(
        cls,
        "a punctuated identifier finds the window that shows it",
        any("sca-219" in h.raw.lower() for h in parse_hits(r.text)),
        'searching "SCA-219" returns nothing while "219" returns the frame — query-side and '
        "index-side tokenisation disagree",
        excerpt=r.text,
    )
    r = s.call("recall", {"query": "219"})
    report.add(
        cls,
        "the split reading of that identifier still finds it",
        any("sca-219" in h.raw.lower() for h in parse_hits(r.text)),
        "even the bare number fails, so the frame is unreachable by any reading",
        excerpt=r.text,
    )

    # A possessive is how a person actually types a name into a question. The apostrophe is not an
    # FTS operator character, so it survives into the phrase `"priyanka's"`, which unicode61 splits
    # into two adjacent tokens — and no document says "priyanka s".
    r = s.call("recall", {"query": "Priyanka's"})
    report.add(
        cls,
        "a possessive form still finds the name",
        any("priyanka" in h.raw.lower() for h in parse_hits(r.text)),
        "\"Priyanka's\" becomes the FTS phrase \"priyanka s\", which matches no document",
        excerpt=r.text,
    )
    r = s.call("recall", {"query": "Halyard?"})
    report.add(
        cls,
        "trailing punctuation does not break a query",
        any("halyard" in h.raw.lower() for h in parse_hits(r.text)),
        "a question mark on the end of a word lost the match",
        excerpt=r.text,
    )

    # `recent` covers a window that ends well before now, so it must be empty — the interesting
    # property is that it says so as a local-only tool rather than implying an empty account.
    r = s.call("recent", {"minutes": 5})
    report.add(
        cls,
        "recent over an empty window returns no fabricated hits",
        not parse_hits(r.text),
        f"{len(parse_hits(r.text))} hit(s) in a window with nothing seeded",
        excerpt=r.text,
    )
    r = s.call("recent", {"minutes": 9 * 60})
    report.add(
        cls,
        "recent over a covered window returns the corpus",
        len(parse_hits(r.text)) >= 6,
        f"{len(parse_hits(r.text))} hit(s) across 9 hours of seeded capture",
        excerpt=r.text,
    )

    r = s.call("screen", {"limit": 60})
    screen_hits = parse_hits(r.text)
    apps = {h.app for h in screen_hits if h.app}
    report.add(
        cls,
        "screen reaches every seeded app",
        {"Cursor", "Arc", "Obsidian", "Safari", "Warp"} <= apps,
        f"apps returned: {sorted(a for a in apps if a)}",
        excerpt=r.text,
    )


def check_no_confabulation(report: Report, servers: dict[str, Server], c: Corpus) -> None:
    cls = "no_confabulation"
    s = servers["main"]

    for label, query in [
        ("a term never captured", TERM_UNSEEN),
        ("a near neighbour of a captured term", TERM_NEAR_MISS),
    ]:
        r = s.call("recall", {"query": query})
        hits = parse_hits(r.text)
        report.add(
            cls,
            f"recall returns nothing for {label}",
            not hits,
            f'"{query}" → {len(hits)} hit(s); nearest-neighbour output would be a fabrication',
            critical=True,
            excerpt=r.text,
        )
        report.add(
            cls,
            f"the empty answer for {label} says the search ran",
            has_any(r.text, ["no results", "were found in", "no match"]),
            "an empty answer must state that a search happened",
            excerpt=r.text,
        )
        report.add(
            cls,
            f"the empty answer for {label} names the half that did not run",
            has_any(r.text, ["**not** searched", "no omi mcp api key is configured"]),
            "with no Omi credential the account half was not searched and must say so",
            critical=True,
            excerpt=r.text,
        )

    # Every hit that does come back must literally contain a query word. This is the general form of
    # "do not present a nearest neighbour as a match".
    offenders = []
    for query in [TERM_HALYARD, "zephyrine", "vendor contract Priyanka", "parity pack", "probeword"]:
        r = s.call("recall", {"query": query})
        for h in parse_hits(r.text):
            if not contains_any_term(h.raw, query):
                offenders.append((query, h.raw[:80]))
    report.add(
        cls,
        "every returned hit contains at least one query word",
        not offenders,
        f"{len(offenders)} hit(s) matched nothing in their query: {offenders[:2]}",
        critical=True,
    )

    # Absence claimed outside the coverage window is the failure the whole design exists to prevent.
    r = s.call(
        "recall", {"query": TERM_UNSEEN, "since": iso(c.a0 - 2 * 365 * 86400), "until": iso(c.a0)}
    )
    report.add(
        cls,
        "an empty answer outside the coverage window states the coverage window",
        "covering **" in r.text or "coverage" in r.text.lower(),
        "a reader must be told what was actually recorded before reading absence as evidence",
        critical=True,
        excerpt=r.text,
    )
    report.add(
        cls,
        "an empty answer hedges rather than asserting the thing never happened",
        has_any(
            r.text,
            [
                "before telling the user it did not happen",
                "rules anything out",
                "not captured",
                "before concluding",
            ],
        ),
        "no hedge found in an out-of-coverage empty answer",
        excerpt=r.text,
    )

    # No database at all: a search that never ran is not a negative result.
    nodb = servers["nodb"]
    r = nodb.call("recall", {"query": TERM_HALYARD})
    report.add(
        cls,
        "with no database, recall says the local half was not searched",
        has_any(r.text, ["was not searched", "not searched"]),
        "must not read as a negative result",
        critical=True,
        excerpt=r.text,
    )
    report.add(
        cls,
        "with no database, recall never claims it looked and found nothing",
        "found no match" not in r.text.lower(),
        'output claims "found no match" for a search that could not run',
        critical=True,
        excerpt=r.text,
    )

    # A database that opens but cannot answer — the third state, and the one a `try?` erases.
    broken = servers["broken"]
    r = broken.call("recall", {"query": TERM_HALYARD})
    report.add(
        cls,
        "with an unreadable database, recall reports a reader fault",
        has_any(r.text, ["was not searched", "could not be read"]),
        "an unreadable database must not render as an empty history",
        critical=True,
        excerpt=r.text,
    )
    r = broken.call("status", {})
    report.add(
        cls,
        "status distinguishes 'opened but unreadable' from 'nothing captured'",
        has_any(r.text, ["could not be read", "fault in this reader"]),
        "status must not report an empty history for a database it failed to query",
        critical=True,
        excerpt=r.text,
    )
    report.add(
        cls,
        "status does not assert an empty history from a reader fault",
        "recorded nothing locally" not in r.text.lower(),
        "reader fault rendered as 'recorded nothing'",
        excerpt=r.text,
    )

    # An empty database with a denied permission: missing, not absent.
    empty = servers["empty"]
    r = empty.call("recall", {"query": TERM_HALYARD})
    report.add(
        cls,
        "an empty database is reported as 'nothing recorded', not as 'did not happen'",
        has_any(r.text, ["recorded nothing", "rules anything out"]),
        "empty capture must not read as evidence of absence",
        excerpt=r.text,
    )
    r = empty.call("screen", {})
    report.add(
        cls,
        "a denied capture permission is named in the empty answer",
        has_any(r.text, ["not granted", "never captured at all"]),
        "screen recording is denied in this fixture and the answer must say so",
        critical=True,
        excerpt=r.text,
    )


def check_ranking(report: Report, s: Server, c: Corpus) -> None:
    """Relevance decides *which* hits survive; the page is then printed newest-first.

    That split is deliberate and both halves matter. `recall`'s description promises a dated,
    chronological list, so display order is a contract — but selection is where the original bug
    lived: the one genuine match for a query was pushed past `limit` by newer incidental ones, and
    an empty-looking answer inside the coverage window is exactly what a reader is licensed to call
    proof that something never happened. So the probe is a tight `limit`: what survives it is what
    the ranker actually preferred.
    """
    cls = "ranking"

    # The historical regression: a window titled "SCA-219: Parity Pack v0" was buried under three
    # browser bookmark bars whose only tie to the query was the word "pack".
    scenarios = [
        ("Omi parity pack SCA-219", "sca-219", "Arc", 6),
        ("SCA-219 parity pack", "sca-219", "Arc", 6),
        # The harder shape: four decoys share two of three query words and clear the relevance
        # floor, and the genuine match is the oldest frame in the corpus. Only relevance, never
        # recency, can keep it.
        (f"{TERM_KESTREL} deployment checklist", TERM_KESTREL.lower(), "Chrome", 4),
    ]
    for query, needle, decoy_app, decoy_count in scenarios:
        top = parse_hits(s.call("recall", {"query": query, "limit": 1}).text)
        report.add(
            cls,
            f'the genuine match is the single hit kept at limit=1 for "{query}"',
            len(top) == 1 and needle in top[0].raw.lower(),
            f"limit=1 kept: {top[0].raw[:90] if top else '(nothing)'}",
            critical=True,
            excerpt="\n".join(h.raw for h in top),
        )
        three = parse_hits(s.call("recall", {"query": query, "limit": 3}).text)
        report.add(
            cls,
            f'the genuine match survives limit=3 for "{query}"',
            any(needle in h.raw.lower() for h in three),
            f"{len(three)} hit(s) at limit=3, none of them the genuine match",
            critical=True,
            excerpt="\n".join(h.raw for h in three),
        )
        full = parse_hits(s.call("recall", {"query": query}).text)
        decoys = [h for h in full if h.app == decoy_app]
        report.metric(f"decoys_surviving[{query}]", f"{len(decoys)} of {decoy_count}")
        report.add(
            cls,
            f'the genuine match is present in the full answer for "{query}"',
            any(needle in h.raw.lower() for h in full),
            f"{len(full)} hit(s), genuine match absent",
            critical=True,
            excerpt="\n".join(h.raw for h in full),
        )

    # Incidental single-word matches must be trimmed rather than padding the answer to `limit`: a
    # page of near-misses reads as "the database is full of this".
    full = parse_hits(s.call("recall", {"query": "Omi parity pack SCA-219"}).text)
    bookmark_bars = [h for h in full if h.app == "Arc"]
    report.add(
        cls,
        "one-word incidental matches are floored out",
        len(bookmark_bars) <= 2,
        f"{len(bookmark_bars)} of 6 bookmark-bar frames survived the relevance floor",
        excerpt="\n".join(h.raw[:90] for h in bookmark_bars),
    )
    # …but a genuine partial match is a lead, not noise, and must still be reachable.
    partials = [h for h in parse_hits(
        s.call("recall", {"query": f"{TERM_KESTREL} deployment checklist"}).text
    ) if h.app == "Chrome"]
    report.add(
        cls,
        "two-of-three-word matches are kept as leads",
        bool(partials),
        "every partial match was floored away, so a real lead is unreachable",
    )

    # Speech and screen are scored on one blended scale; whichever table holds every query word wins.
    top = parse_hits(s.call("recall", {"query": "vendor contract Priyanka", "limit": 1}).text)
    report.add(
        cls,
        "a speech line can win the cap against screen text",
        len(top) == 1 and top[0].kind == "me",
        f"limit=1 kept a *{top[0].kind}* hit" if top else "nothing came back",
        excerpt="\n".join(h.raw for h in top),
    )

    # The display contract `recall` states in its own description. If selection order ever leaked
    # into the page, the day headings would stop meaning anything. Scored on the seeded order of the
    # probe nonces rather than on printed clock times, which wrap at midnight.
    r = s.call("recall", {"query": "probeword"})
    seen = [n for n in re.findall(r"nqx[a-z]+", r.text.lower()) if n in ALL_PROBE_NONCES]
    expected = [NONCE[k] for k in ("g2", "g1", "b2", "b1", "a2", "a1")]
    report.add(
        cls,
        "the rendered page is newest-first, as the tool description promises",
        seen == expected,
        f"rendered order {seen} != newest-first {expected}",
        excerpt=r.text,
    )


def check_dedup(report: Report, s: Server, c: Corpus) -> None:
    cls = "dedup"
    lo, hi = c.a0 + 2400, c.a0 + 2700
    raw_frames = len(c.frames_at(lo, hi))

    r = s.call("screen", {"app": "Warp", "since": iso(lo), "until": iso(hi), "limit": 60})
    hits = [h for h in parse_hits(r.text) if h.kind == "screen"]
    report.metric("dedup_raw_frames", raw_frames)
    report.metric("dedup_moments", len(hits))
    report.metric("dedup_collapse_ratio", round(raw_frames / len(hits), 2) if hits else None)

    report.add(
        cls,
        "near-identical consecutive frames collapse",
        len(hits) <= 3,
        f"{raw_frames} raw frames → {len(hits)} rendered observation(s)",
        excerpt=r.text,
    )
    collapsed = [h for h in hits if h.frames >= 10]
    report.add(
        cls,
        "the collapsed run reports how many frames it stands for",
        bool(collapsed),
        f"no observation carried a '[N frames · …]' span; frame counts were {[h.frames for h in hits]}",
        excerpt=r.text,
    )
    distinct = [h for h in hits if TERM_WARP_NOVEL in h.raw.lower()]
    report.add(
        cls,
        "the genuinely different frame did NOT collapse into the run",
        bool(distinct),
        f'the frame containing "{TERM_WARP_NOVEL}" was swallowed by the near-identical run',
        critical=True,
        excerpt=r.text,
    )
    if distinct and collapsed:
        report.add(
            cls,
            "the different frame is a separate observation from the run",
            distinct[0].raw != collapsed[0].raw,
            "the distinct frame and the collapsed run rendered as one line",
            excerpt=r.text,
        )

    # Collapsing must not eat a limit either: unfiltered `screen` should span the whole corpus
    # rather than thirteen minutes of one editor.
    r = s.call("screen", {"limit": 60})
    hits = [h for h in parse_hits(r.text) if h.kind == "screen"]
    apps = {h.app for h in hits}
    report.add(
        cls,
        "an unfiltered screen answer spans many windows, not one",
        len(apps) >= 5,
        f"{len(hits)} observation(s) across {len(apps)} app(s)",
        excerpt=r.text,
    )
    report.add(
        cls,
        "distinct windows of the same app are not collapsed together",
        len([h for h in hits if h.app == "Arc"]) >= 5,
        "six differently-titled Arc windows must stay six observations",
        excerpt=r.text,
    )

    # Identical text, same window, eleven minutes apart: the gap alone makes them two events, and
    # collapsing them would report a person as present for a stretch they were away.
    r = s.call("screen", {"app": "Terminal", "limit": 60})
    hits = [h for h in parse_hits(r.text) if h.kind == "screen"]
    report.add(
        cls,
        "identical frames either side of the moment gap stay separate",
        len(hits) == 2,
        f"{len(hits)} observation(s) for two identical frames 11 minutes apart; expected 2",
        excerpt=r.text,
    )


def check_uncertainty(report: Report, s: Server, c: Corpus) -> None:
    cls = "uncertainty"

    r = s.call("transcript", {"session_id": 1})
    hits = parse_hits(r.text)

    def find(needle: str) -> Hit | None:
        for h in hits:
            if needle in h.raw.lower():
                return h
        return None

    low = find("invoice")
    nil = find("park the pricing")
    high = find("halyard")
    highest = find("priyanka")

    report.add(
        cls,
        "a low-confidence line is marked",
        bool(low) and low.uncertain,
        "the 0.41 line must carry the uncertainty marker" if low else "line missing from transcript",
        critical=True,
        excerpt=r.text,
    )
    report.add(
        cls,
        "a nil-confidence line is NOT marked",
        bool(nil) and not nil.uncertain,
        "an unknown score must never render as doubt" if nil else "line missing from transcript",
        critical=True,
        excerpt=r.text,
    )
    for label, hit in [("0.92", high), ("0.99", highest)]:
        report.add(
            cls,
            f"a high-confidence line ({label}) is NOT marked",
            bool(hit) and not hit.uncertain,
            "high confidence must not be marked" if hit else "line missing from transcript",
            excerpt=r.text,
        )
    report.add(
        cls,
        "the marker's meaning is stated once above the results",
        r.text.count("confidence floor of") == 1,
        f"legend appeared {r.text.count('confidence floor of')} time(s); expected exactly 1",
        excerpt=r.text,
    )

    r2 = s.call("transcript", {"session_id": 2})
    report.add(
        cls,
        "a transcript with no doubtful line carries no marker and no legend",
        UNCERTAIN_MARKER not in r2.text and "confidence floor of" not in r2.text,
        "a legend over a page with nothing marked teaches a reader to expect doubt everywhere",
        excerpt=r2.text,
    )

    r3 = s.call("recall", {"query": "invoice"})
    marked = [h for h in parse_hits(r3.text) if h.uncertain]
    report.add(
        cls,
        "the mark survives the recall path, not just transcript",
        bool(marked),
        "a low-confidence line reached recall unmarked",
        excerpt=r3.text,
    )

    r4 = s.call("screen", {"limit": 60})
    report.add(
        cls,
        "screen text is never marked with speech doubt",
        not any(h.uncertain for h in parse_hits(r4.text)),
        "OCR accuracy is a different question and must not wear a 'background audio' mark",
        critical=True,
        excerpt=r4.text,
    )

    # The boundary. Marking is `< floor`, and a score that is not a probability on this scale must
    # say nothing at all rather than mark the whole archive.
    r5 = s.call("transcript", {"session_id": 3})
    boundary = [
        ("exactlyatfloor", False, "0.65 sits on the floor, and the test is strictly below it"),
        ("justunderfloor", True, "0.649 is below the floor"),
        ("zeroscore", True, "0.0 is a real score and a very low one"),
        ("perfectscore", False, "1.0 is certainty"),
        ("negativelogprob", False, "-3.2 is not a probability on this scale, so it says nothing"),
        ("aboveone", False, "5.0 is not a probability on this scale, so it says nothing"),
    ]
    for needle, expect_marked, why in boundary:
        hit = next((h for h in parse_hits(r5.text) if needle in h.raw.lower()), None)
        report.add(
            cls,
            f"confidence boundary: {needle} is {'marked' if expect_marked else 'unmarked'}",
            bool(hit) and hit.uncertain == expect_marked,
            why if hit else "line missing from the transcript",
            excerpt=r5.text,
        )


def check_coherence(report: Report, s: Server, c: Corpus) -> None:
    """Two answers about the same facts must not contradict each other.

    A model reads several of these tools in one turn. If `status` says one thing about the corpus
    and `screen` implies another, whichever it believes it is believing something false — and it has
    no way to find out which.
    """
    cls = "coherence"

    r = s.call("status", {})
    counts = re.search(
        r"holds ([\d,]+) transcript lines? across ([\d,]+) conversations? and ([\d,]+) screen",
        r.text,
    )

    def num(text: str) -> int:
        return int(text.replace(",", ""))

    report.add(
        cls,
        "status counts exactly what was seeded",
        bool(counts)
        and (num(counts.group(1)), num(counts.group(2)), num(counts.group(3)))
        == (len(c.segments), len(c.sessions), len(c.frames)),
        (
            f"status says {counts.groups()}, seeded "
            f"{(len(c.segments), len(c.sessions), len(c.frames))}"
            if counts
            else "no count sentence found in status"
        ),
        critical=True,
        excerpt=r.text,
    )

    oldest = min([s_["at"] for s_ in c.segments] + [f["at"] for f in c.frames])
    newest = max([s_["at"] for s_ in c.segments] + [f["at"] for f in c.frames])
    report.add(
        cls,
        "the reported coverage window is the window that was captured",
        describe(oldest) in r.text and describe(newest) in r.text,
        f"expected coverage {describe(oldest)} → {describe(newest)}",
        critical=True,
        excerpt=r.text,
    )

    # `conversations` summarises what `transcript` then shows in full; the two must agree.
    conv = s.call("conversations", {})
    lines = re.search(r"### Conversation #1\n[^\n]*?· (\d+) lines", conv.text)
    transcript = s.call("transcript", {"session_id": 1})
    counted = len(parse_hits(transcript.text))
    report.add(
        cls,
        "the line count in conversations matches the transcript it points at",
        bool(lines) and int(lines.group(1)) == counted,
        f"conversations says {lines.group(1) if lines else '?'} lines, transcript renders {counted}",
        critical=True,
        excerpt=conv.text,
    )

    # Determinism. An answer that drifts between two identical calls cannot be reasoned about, and
    # cannot be regression-tested either.
    first = s.call("recall", {"query": "zephyrine"}).text
    second = s.call("recall", {"query": "zephyrine"}).text
    report.add(
        cls,
        "the same question twice gives the same answer",
        first == second,
        "recall is not deterministic over a static corpus",
    )

    # A truncated list must say it was truncated, or a reader treats the cap as the total. `screen`
    # has the sentence for it ("the N newest of at least M"), but `Queries.screen` already caps to
    # `limit` before `Tools` compares the two counts — so the disclosure can only ever fire when the
    # Omi half contributed rows, and never on a local-only answer.
    r = s.call("screen", {"limit": 3})
    hits = [h for h in parse_hits(r.text) if h.kind == "screen"]
    report.add(
        cls,
        "a capped list discloses that it was capped",
        len(hits) == 3 and "of at least" in r.text,
        f"{len(hits)} of 19 observations returned with no note that more matched",
        excerpt=r.text,
    )

    # Collapsed moments must account for real frames, never more than exist.
    lo, hi = c.a0, c.a0 + 3600
    r = s.call("screen", {"since": iso(lo), "until": iso(hi), "limit": 200})
    claimed = sum(h.frames for h in parse_hits(r.text) if h.kind == "screen")
    actual = len(c.frames_at(lo, hi))
    report.add(
        cls,
        "the frame counts a collapsed answer claims are real frames",
        0 < claimed <= actual,
        f"answer accounts for {claimed} frames; {actual} exist in that window",
        critical=True,
        excerpt=r.text,
    )

    # `activity` measures a span it was given; blocks cannot exceed it.
    span_lo, span_hi = c.b0 + 3200, c.b0 + 4200
    r = s.call("activity", {"since": iso(span_lo), "until": iso(span_hi)})
    blocks = re.findall(r"\((\d+) (sec|min)\)", r.text)
    total = sum(int(v) * (1 if unit == "sec" else 60) for v, unit in blocks)
    report.add(
        cls,
        "activity blocks never total more time than the range they cover",
        0 < total <= (span_hi - span_lo),
        f"blocks total {total}s over a {int(span_hi - span_lo)}s range",
        excerpt=r.text,
    )

    # `recent` clamps rather than inventing a window it did not have.
    r = s.call("recent", {"minutes": 10**9})
    report.add(
        cls,
        "recent clamps an absurd window and prints the clamped one",
        "1,440 minutes" in r.text,
        "an out-of-range minutes value must be clamped and the clamped value printed",
        excerpt=r.text.split("\n")[0],
    )


def check_filter_integrity(report: Report, s: Server, c: Corpus) -> None:
    """Every filter the output claims must be the filter that ran.

    Scored on exact nonce sets rather than on prose: each probe row carries a unique token, so what
    came back is comparable to what should have.
    """
    cls = "filter_integrity"
    b = c.b0

    r = s.call("recall", {"query": "probeword"})
    baseline = nonces_in(r.text)
    report.add(
        cls,
        "unfiltered recall reaches every probe row",
        baseline == ALL_PROBE_NONCES,
        f"missing {sorted(ALL_PROBE_NONCES - baseline)}",
        excerpt=r.text,
    )

    windows = [
        ("since+until", b + 1100, b + 1900, {NONCE["b1"], NONCE["b2"]}),
        ("since only", b + 2000, None, {NONCE["g1"], NONCE["g2"]}),
        ("until only", None, b + 400, {NONCE["a1"], NONCE["a2"]}),
        ("a one-row window", b + 1400, b + 1600, {NONCE["b2"]}),
    ]
    for label, since, until, expected in windows:
        args = {}
        if since is not None:
            args["since"] = iso(since)
        if until is not None:
            args["until"] = iso(until)
        for tool in ("recall", "screen"):
            call_args = dict(args)
            if tool == "recall":
                call_args["query"] = "probeword"
            r = s.call(tool, call_args)
            got = nonces_in(r.text)
            report.add(
                cls,
                f"{tool} applies {label}",
                got == expected,
                f"expected {sorted(expected)}, got {sorted(got)}",
                critical=True,
                excerpt=r.text,
            )
            # The header is a claim about what was filtered; both boundaries it prints must be the
            # boundaries that were asked for, to the minute.
            wanted = [describe(x) for x in (since, until) if x is not None]
            missing = [w for w in wanted if w not in r.text]
            report.add(
                cls,
                f"{tool} prints the {label} boundary it applied",
                not missing,
                f"header does not name {missing}",
                critical=True,
                excerpt=r.text.split("\n")[0],
            )

    # `app`, alone and combined with a range. A printed app filter that was not applied is the same
    # class of lie as an understated coverage window.
    r = s.call("screen", {"app": "ProbeGamma"})
    hits = [h for h in parse_hits(r.text) if h.kind == "screen"]
    apps = {h.app for h in hits}
    report.add(
        cls,
        "screen applies the app filter",
        apps <= {"ProbeGamma"} and nonces_in(r.text) == {NONCE["g1"], NONCE["g2"]},
        f"apps returned: {sorted(a for a in apps if a)}; nonces {sorted(nonces_in(r.text))}",
        critical=True,
        excerpt=r.text,
    )
    report.add(
        cls,
        "screen prints the app it filtered by",
        "in ProbeGamma" in r.text,
        "the header must name the applied app filter",
        excerpt=r.text.split("\n")[0],
    )

    r = s.call("screen", {"app": "ProbeBeta", "since": iso(b + 1400), "until": iso(b + 1600)})
    got = nonces_in(r.text)
    apps = {h.app for h in parse_hits(r.text) if h.kind == "screen"}
    report.add(
        cls,
        "screen applies app and range together",
        got == {NONCE["b2"]} and apps <= {"ProbeBeta"},
        f"nonces {sorted(got)}, apps {sorted(a for a in apps if a)}",
        critical=True,
        excerpt=r.text,
    )

    # A substring app filter is documented behaviour ("Chrome" means "Google Chrome") — it must
    # still not reach a different app.
    r = s.call("screen", {"app": "Probe"})
    apps = {h.app for h in parse_hits(r.text) if h.kind == "screen"}
    report.add(
        cls,
        "a substring app filter stays inside matching apps",
        bool(apps) and all(a and a.startswith("Probe") for a in apps),
        f"apps returned: {sorted(a for a in apps if a)}",
        critical=True,
        excerpt=r.text,
    )

    # A filter present but unreadable must fail the call, never be dropped. `dateArg` throws for an
    # unparseable *string*, but a boolean or an array falls through its type checks and returns nil,
    # which the caller reads as "no filter asked for" — so the search runs over the whole corpus and
    # the header prints no range at all. The caller believes it bounded the question and cannot tell
    # that it did not.
    for label, value in [("a boolean", True), ("an array", [1, 2]), ("an object", {"x": 1})]:
        r = s.call("recall", {"query": "probeword", "since": value})
        got = nonces_in(r.text)
        report.add(
            cls,
            f"a since of {label} is rejected rather than silently dropped",
            r.is_error or got != ALL_PROBE_NONCES,
            f"the filter was ignored and all {len(got)} rows came back unbounded",
            critical=True,
            excerpt=r.text.split("\n")[0],
        )

    # conversations
    r = s.call("conversations", {"since": iso(c.a0 + 600)})
    ids = set(re.findall(r"id `(\d+)`", r.text))
    report.add(
        cls,
        "conversations applies since",
        ids == {"2", "3"},
        f"expected sessions 2 and 3, got {sorted(ids)}",
        critical=True,
        excerpt=r.text,
    )
    r = s.call("conversations", {"until": iso(c.a0 + 600)})
    ids = set(re.findall(r"id `(\d+)`", r.text))
    report.add(
        cls,
        "conversations applies until",
        ids == {"1"},
        f"expected only session 1, got {sorted(ids)}",
        critical=True,
        excerpt=r.text,
    )

    # activity
    r = s.call("activity", {"since": iso(b + 3200), "until": iso(b + 3600)})
    report.add(
        cls,
        "activity applies its range",
        "ProbeDelta" in r.text and "ProbeEpsilon" not in r.text,
        "the neighbouring block leaked into a bounded activity answer",
        critical=True,
        excerpt=r.text,
    )
    report.add(
        cls,
        "activity prints the range it summarised",
        describe(b + 3200) in r.text and describe(b + 3600) in r.text,
        "the header must name both boundaries",
        excerpt=r.text.split("\n")[0],
    )
    r = s.call("activity", {"since": iso(b + 3600), "until": iso(b + 3200)})
    report.add(
        cls,
        "a reversed range is corrected and the correction is disclosed",
        "other way round" in r.text.lower() or "ProbeDelta" in r.text,
        "an inverted range must not silently return nothing",
        excerpt=r.text,
    )

    # An empty range must come back empty rather than falling back to everything — a filter that
    # quietly stops applying when it excludes everything is the worst version of this failure.
    r = s.call("screen", {"since": iso(b + 5000), "until": iso(b + 5100)})
    report.add(
        cls,
        "an empty range returns nothing rather than falling back",
        not nonces_in(r.text) and not [h for h in parse_hits(r.text) if h.kind == "screen"],
        "rows leaked into a window with nothing in it",
        critical=True,
        excerpt=r.text,
    )


def check_bad_input(report: Report, s: Server, c: Corpus) -> None:
    cls = "bad_input"

    # Unparseable dates must fail the call, never run without the filter.
    for value in ["banana", "2026-13-45", "last quarter", "", "  ", "3 fortnights ago", "🐙"]:
        r = s.call("recall", {"query": "probeword", "since": value})
        if value.strip() == "":
            # An empty string is "no filter asked for"; it may pass through, but must not be
            # reported as an applied filter.
            report.add(
                cls,
                f"empty since ({value!r}) does not print a filter it did not apply",
                "since" not in r.text.split("\n")[0].lower(),
                "header claims a range for an empty `since`",
                excerpt=r.text.split("\n")[0],
            )
            continue
        report.add(
            cls,
            f"unparseable since {value!r} is rejected explicitly",
            r.is_error and "could not understand" in r.text.lower(),
            f"isError={r.is_error}; text={r.text[:120]!r}",
            critical=True,
            excerpt=r.text,
        )
        report.add(
            cls,
            f"rejection of {value!r} names the offending value",
            value.strip() in r.text,
            "the error must quote what it could not read",
            excerpt=r.text,
        )

    r = s.call("activity", {})
    report.add(
        cls,
        "a required argument missing is an explicit error",
        r.is_error and "since" in r.text.lower(),
        f"isError={r.is_error}; text={r.text[:120]!r}",
        excerpt=r.text,
    )
    r = s.call("recall", {})
    report.add(
        cls,
        "recall without a query is an explicit error",
        r.is_error and "query" in r.text.lower(),
        f"isError={r.is_error}; text={r.text[:120]!r}",
        excerpt=r.text,
    )

    # Hostile FTS input must be neutralised, not crash and not error.
    hostile = ['"', "*", "AND", "AND OR NOT", "NEAR(a b)", '"unclosed', "foo* AND \"bar", "🐙🐙🐙",
               "()", "^", "-", "a" * 4000]
    for query in hostile:
        r = s.call("recall", {"query": query})
        report.add(
            cls,
            f"hostile FTS input {query[:14]!r} does not crash or error",
            not r.is_error and r.rpc_error is None,
            f"isError={r.is_error}, rpcError={r.rpc_error}",
            critical=True,
            excerpt=r.text,
        )

    # Out-of-range limits are clamped, never fatal.
    for limit, expect_max in [(0, 1), (-5, 1), (1, 1), (10**9, 500), (2, 2)]:
        r = s.call("recall", {"query": "probeword", "limit": limit})
        hits = parse_hits(r.text)
        report.add(
            cls,
            f"limit={limit} is clamped, not fatal",
            not r.is_error and len(hits) <= max(expect_max, 1),
            f"isError={r.is_error}, {len(hits)} hit(s) for limit={limit}",
            excerpt=r.text,
        )
    r = s.call("recall", {"query": "probeword", "limit": "not a number"})
    report.add(
        cls,
        "a non-numeric limit falls back to the default rather than failing",
        not r.is_error,
        f"isError={r.is_error}; text={r.text[:120]!r}",
        excerpt=r.text,
    )
    r = s.call("recent", {"minutes": -10})
    report.add(
        cls,
        "a negative minutes value is clamped",
        not r.is_error,
        f"isError={r.is_error}",
        excerpt=r.text,
    )

    # Wrong types where a type is expected: loud is the only acceptable outcome.
    r = s.call("recall", {"query": 12345})
    report.add(
        cls,
        "a non-string query is refused loudly",
        r.is_error,
        f"isError={r.is_error}; text={r.text[:120]!r}",
        excerpt=r.text,
    )
    r = s.request("tools/call", {"name": "recall", "arguments": ["not", "an", "object"]})
    result = r.get("result", {})
    report.add(
        cls,
        "array-shaped arguments are refused, not misread",
        bool(result.get("isError")) or r.get("error") is not None,
        f"got {json.dumps(r)[:160]}",
        critical=True,
    )
    r = s.request("tools/call", {"name": "recall"})
    result = r.get("result", {})
    report.add(
        cls,
        "tools/call with no arguments at all is refused",
        bool(result.get("isError")) or r.get("error") is not None,
        f"got {json.dumps(r)[:160]}",
    )

    # Identifiers.
    r = s.call("transcript", {"session_id": {"nested": 1}})
    report.add(
        cls,
        "a structurally wrong session_id is rejected with the expected shapes named",
        r.is_error and "uuid" in r.text.lower(),
        f"isError={r.is_error}; text={r.text[:140]!r}",
        excerpt=r.text,
    )
    r = s.call("transcript", {})
    report.add(
        cls,
        "transcript without session_id is an explicit error",
        r.is_error and "session_id" in r.text,
        f"isError={r.is_error}; text={r.text[:120]!r}",
        excerpt=r.text,
    )

    # Unknown tool.
    r = s.call("teleport", {})
    report.add(
        cls,
        "an unknown tool is rejected and the real ones are listed",
        r.is_error and "recall" in r.text and "teleport" in r.text,
        f"isError={r.is_error}; text={r.text[:140]!r}",
        excerpt=r.text,
    )

    # The process must still be answering after all of that.
    r = s.call("status", {})
    report.add(
        cls,
        "the server still answers after every hostile input",
        not r.is_error and "Context for Claude" in r.text,
        "the server stopped answering after the bad-input battery",
        critical=True,
        excerpt=r.text,
    )


def check_protocol(report: Report, s: Server, c: Corpus) -> None:
    cls = "protocol"

    init = s.request(
        "initialize",
        {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "e", "version": "0"}},
    )
    result = init.get("result", {})
    report.add(
        cls,
        "initialize returns a protocol version and server identity",
        bool(result.get("protocolVersion")) and bool(result.get("serverInfo", {}).get("name")),
        f"result keys: {sorted(result)}",
    )
    report.add(
        cls,
        "initialize carries non-empty server instructions",
        len(result.get("instructions") or "") > 200,
        f"instructions length {len(result.get('instructions') or '')}",
    )

    listed = s.request("tools/list").get("result", {}).get("tools", [])
    names = [t.get("name") for t in listed]
    report.add(
        cls,
        "all seven tools are advertised",
        sorted(names)
        == sorted(["recall", "recent", "conversations", "transcript", "screen", "activity", "status"]),
        f"advertised: {sorted(n for n in names if n)}",
    )
    bad_schema = [
        t.get("name")
        for t in listed
        if not isinstance(t.get("inputSchema"), dict)
        or t["inputSchema"].get("type") != "object"
        or not isinstance(t["inputSchema"].get("properties"), dict)
    ]
    report.add(
        cls,
        "every tool has a well-formed object input schema",
        not bad_schema,
        f"malformed schemas: {bad_schema}",
    )
    short = [t.get("name") for t in listed if len(t.get("description") or "") < 120]
    report.add(
        cls,
        "every tool description is substantive",
        not short,
        f"descriptions under 120 chars: {short}",
    )

    # A notification takes no reply; the ping that follows it proves the stream stayed in step.
    s.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
    pong = s.request("ping")
    report.add(
        cls,
        "a notification produces no response line",
        pong.get("result") == {} and pong.get("error") is None,
        f"the frame after the notification was {json.dumps(pong)[:120]}",
        critical=True,
    )

    unknown = s.request("does/not/exist")
    report.add(
        cls,
        "an unknown method is a JSON-RPC method-not-found",
        (unknown.get("error") or {}).get("code") == -32601,
        f"got {json.dumps(unknown)[:140]}",
    )

    s.send_raw(b"{not json at all\n")
    parse_error = s.read()
    report.add(
        cls,
        "a malformed frame is a parse error, not a crash",
        (parse_error.get("error") or {}).get("code") == -32700,
        f"got {json.dumps(parse_error)[:140]}",
        critical=True,
    )
    s.send_raw(b"\xff\xfe not utf8\n")
    non_utf8 = s.read()
    report.add(
        cls,
        "a non-UTF-8 frame is a parse error, not a crash",
        (non_utf8.get("error") or {}).get("code") == -32700,
        f"got {json.dumps(non_utf8)[:140]}",
    )

    nameless = s.request("tools/call", {"arguments": {}})
    report.add(
        cls,
        "tools/call without a name is invalid params",
        (nameless.get("error") or {}).get("code") == -32602,
        f"got {json.dumps(nameless)[:140]}",
    )

    r = s.call("status", {})
    content = r.response.get("result", {}).get("content")
    report.add(
        cls,
        "tool results use the MCP text content shape",
        isinstance(content, list)
        and bool(content)
        and content[0].get("type") == "text"
        and isinstance(content[0].get("text"), str),
        f"content: {json.dumps(content)[:120]}",
    )


def check_traceability(report: Report, s: Server, c: Corpus) -> None:
    cls = "traceability"

    r = s.call("conversations", {})
    ids = re.findall(r"id `([^`]+)`", r.text)
    report.add(
        cls,
        "conversations prints a copy-paste id for every entry",
        len(ids) >= 2,
        f"ids printed: {ids}",
        excerpt=r.text,
    )

    if ids:
        t = s.call("transcript", {"session_id": int(ids[0]) if ids[0].isdigit() else ids[0]})
        report.add(
            cls,
            "an id printed by conversations resolves in transcript",
            bool(parse_hits(t.text)),
            f"transcript for id {ids[0]!r} returned no lines",
            critical=True,
            excerpt=t.text,
        )

    t = s.call("transcript", {"session_id": 2})
    report.add(
        cls,
        "transcript returns the requested conversation, not a neighbouring one",
        "zephyrine" in t.text.lower() and "halyard" not in t.text.lower(),
        "session 2's transcript contains session 1's lines (or is missing its own)",
        critical=True,
        excerpt=t.text,
    )

    t = s.call("transcript", {"session_id": 9999})
    report.add(
        cls,
        "an unknown local id is refused rather than answered with something else",
        not parse_hits(t.text) and "9999" in t.text,
        "an unknown id produced transcript lines",
        critical=True,
        excerpt=t.text,
    )

    t = s.call("transcript", {"session_id": "5db3de8c-3c1c-5fee-bad1-2907d2a5a473"})
    report.add(
        cls,
        "an Omi id with no account configured reads as 'unreachable', not 'does not exist'",
        has_any(t.text, ["could not be read", "could not be reached", "not configured"])
        and "holds no conversation" not in t.text.lower(),
        "an unreachable account must never be reported as a missing conversation",
        critical=True,
        excerpt=t.text,
    )

    r = s.call("status", {})
    report.add(
        cls,
        "status names the database it actually read",
        "Database: `" in r.text,
        "status must say which file it answered from",
        excerpt=r.text,
    )
    report.add(
        cls,
        "status reports the coverage window that licenses a negative result",
        "Local coverage:" in r.text,
        "no coverage window in status",
        excerpt=r.text,
    )
    report.add(
        cls,
        "status reports per-permission capture state",
        "**microphone**" in r.text and "**screen**" in r.text,
        "status must report which capture permissions are granted",
        excerpt=r.text,
    )


# --------------------------------------------------------------------------------- driver


def ensure_binary(binary: Path, force_build: bool, quiet: bool) -> None:
    if binary.exists() and not force_build:
        return
    for attempt in (1, 2):
        if not quiet:
            print(f"building context-for-claude-mcp (attempt {attempt})…", file=sys.stderr)
        proc = subprocess.run(
            ["swift", "build", "-c", "release", "--product", "context-for-claude-mcp"],
            cwd=str(PKG_ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and binary.exists():
            return
        if attempt == 2:
            sys.stderr.write(proc.stdout[-4000:] + "\n" + proc.stderr[-4000:] + "\n")
            raise SystemExit(
                "harness error: could not build context-for-claude-mcp. If another agent is "
                "editing the package concurrently, retry when the tree is quiet."
            )
        time.sleep(3)


def make_fixture(root: Path, name: str, corpus: Corpus | None, kind: str) -> Path:
    home = root / name
    support = home / "Library" / "Application Support" / "ContextForClaude"
    support.mkdir(parents=True, exist_ok=True)
    db = support / "context.db"
    if kind == "seeded":
        seed_database(db, corpus)
        write_heartbeat(home, True, GRANTED)
    elif kind == "empty":
        seed_database(db, None)
        write_heartbeat(home, False, SCREEN_DENIED)
    elif kind == "broken":
        # A real SQLite file with none of the tables: it opens, then every query fails. That third
        # state is exactly what a `try?` used to fold into "nothing was ever captured".
        scratch = sqlite3.connect(db)
        scratch.execute("CREATE TABLE decoy(x)")
        scratch.commit()
        scratch.close()
        write_heartbeat(home, False, GRANTED)
    elif kind == "nodb":
        pass  # no database, no heartbeat: the honest first-run state
    return home


def preflight(report: Report, s: Server, root: Path) -> None:
    """Prove the isolation before scoring anything that depends on it."""
    r = s.call("status", {})
    path_match = re.search(r"Database: `([^`]+)`", r.text)
    db_path = path_match.group(1) if path_match else ""
    inside = bool(db_path) and (
        os.path.realpath(db_path).startswith(os.path.realpath(str(root)))
    )
    if not inside:
        raise SystemExit(
            "harness error: the MCP binary did not open the temp database.\n"
            f"  it reported: {db_path or '(no path printed)'}\n"
            f"  expected under: {root}\n"
            "CFFIXED_USER_HOME redirection is what keeps this eval off the real "
            "~/Library/Application Support/ContextForClaude. Refusing to score against real data."
        )
    report.metric("temp_database", db_path)

    if "Not configured" not in r.text:
        raise SystemExit(
            "harness error: an Omi credential resolved inside the eval's temp home. This run would "
            "hit the network and a real account. Refusing to continue."
        )
    report.metric("omi_backend", "not configured (offline, as required)")


def run_eval(binary: Path, root: Path, only: str | None) -> Report:
    report = Report()
    corpus = build_corpus(time.time())

    homes = {
        "main": make_fixture(root, "main", corpus, "seeded"),
        "empty": make_fixture(root, "empty", None, "empty"),
        "broken": make_fixture(root, "broken", None, "broken"),
        "nodb": make_fixture(root, "nodb", None, "nodb"),
    }
    servers = {name: Server(binary, home) for name, home in homes.items()}
    try:
        for s in servers.values():
            s.initialize()
        preflight(report, servers["main"], root)

        suites: list[tuple[str, Callable[[], None]]] = [
            ("findability", lambda: check_findability(report, servers["main"], corpus)),
            ("no_confabulation", lambda: check_no_confabulation(report, servers, corpus)),
            ("ranking", lambda: check_ranking(report, servers["main"], corpus)),
            ("dedup", lambda: check_dedup(report, servers["main"], corpus)),
            ("uncertainty", lambda: check_uncertainty(report, servers["main"], corpus)),
            ("filter_integrity", lambda: check_filter_integrity(report, servers["main"], corpus)),
            ("bad_input", lambda: check_bad_input(report, servers["main"], corpus)),
            ("coherence", lambda: check_coherence(report, servers["main"], corpus)),
            ("protocol", lambda: check_protocol(report, servers["main"], corpus)),
            ("traceability", lambda: check_traceability(report, servers["main"], corpus)),
        ]
        for name, fn in suites:
            if only and name != only:
                continue
            try:
                fn()
            except ProtocolViolation as exc:
                report.add(name, f"{name} suite completed", False, f"transport failure: {exc}",
                           critical=True)

        # Aggregate protocol property: nothing but JSON-RPC ever reached stdout.
        junk = []
        for name, s in servers.items():
            for line in s.raw_stdout:
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    junk.append(f"{name}: {line[:80]}")
        if not only or only == "protocol":
            report.add(
                "protocol",
                "stdout carries JSON-RPC and nothing else",
                not junk,
                f"{len(junk)} non-JSON line(s) on stdout: {junk[:2]}",
                critical=True,
            )
        report.metric("stderr_notes", sum(len(s.stderr) for s in servers.values()))
    finally:
        for s in servers.values():
            s.close()
    return report


# --------------------------------------------------------------------------------- output

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def paint(text: str, colour: str, enabled: bool) -> str:
    return f"{colour}{text}{RESET}" if enabled else text


def print_summary(
    report: Report, floor: float, baseline: dict | None, colour: bool, strict: bool
) -> None:
    print()
    print(paint("Context for Claude — answer quality eval", BOLD, colour))
    print()
    for cls in CLASS_ORDER:
        rows = [c for c in report.checks if c.cls == cls]
        if not rows:
            continue
        score, passed, total = report.class_score(cls)
        head = f"{cls:<18} {score * 100:5.1f}%  ({passed}/{total})  weight {CLASS_WEIGHTS[cls]}"
        print(paint(head, GREEN if score == 1 else RED, colour))
        for check in rows:
            known = check.name in KNOWN_FAILURES and not strict
            mark = "pass" if check.ok else ("fail" if known else "FAIL")
            tag = ""
            if not check.ok:
                tag = " [known]" if known else (" [critical]" if check.critical else "")
            line = f"    {mark}  {check.name}{tag}"
            print(paint(line, GREEN if check.ok else (DIM if known else RED), colour))
            if not check.ok:
                print(paint(f"          ↳ {check.reason}", DIM, colour))
                if known:
                    print(paint(f"          ↳ tracked: {KNOWN_FAILURES[check.name]}", DIM, colour))
        print()

    overall = report.overall()
    failures = [c for c in report.checks if not c.ok]
    criticals = report.critical_failures(strict)

    if report.metrics:
        print(paint("metrics", BOLD, colour))
        for key, value in report.metrics.items():
            print(f"    {key}: {value}")
        print()

    regressions: list = []
    if baseline:
        before = {(c["class"], c["name"]): c["ok"] for c in baseline.get("checks", [])}
        now = {(c.cls, c.name): c.ok for c in report.checks}
        regressed = sorted(k for k, ok in now.items() if not ok and before.get(k) is True)
        fixed = sorted(k for k, ok in now.items() if ok and before.get(k) is False)
        delta = overall - baseline.get("overall", overall)
        arrow = "↑" if delta > 0.0005 else ("↓" if delta < -0.0005 else "→")
        print(
            paint(
                f"vs previous run: {baseline.get('overall', 0) * 100:.1f}% {arrow} "
                f"{overall * 100:.1f}%  ({delta * 100:+.1f} points)",
                BOLD,
                colour,
            )
        )
        regressions = regressed
        for cls, name in regressed:
            print(paint(f"    REGRESSED  {cls}: {name}", RED, colour))
        for cls, name in fixed:
            print(paint(f"    fixed      {cls}: {name}", GREEN, colour))
        print()

    _ = regressions
    resolved = report.resolved_known_failures()
    if resolved:
        print(paint("known failures that now pass — delete them from KNOWN_FAILURES:", BOLD, colour))
        for name in resolved:
            print(paint(f"    {name}", GREEN, colour))
        print()

    print(paint(f"overall  {overall * 100:.1f}%   floor {floor * 100:.1f}%", BOLD, colour))
    tracked = len([c for c in failures if c.name in KNOWN_FAILURES]) if not strict else 0
    print(
        f"         {len(report.checks) - len(failures)}/{len(report.checks)} checks passed"
        + (f"  ({tracked} tracked failure(s) not gating)" if tracked else "")
    )
    if criticals:
        print(paint(f"         {len(criticals)} new critical failure(s)", RED, colour))
    print()

    return regressions

def main() -> int:
    ap = argparse.ArgumentParser(description="Answer-quality eval for the Context for Claude MCP server.")
    ap.add_argument("--binary", type=Path, default=DEFAULT_BINARY)
    ap.add_argument("--build", action="store_true", help="rebuild the MCP product first")
    ap.add_argument("--floor", type=float, default=OVERALL_FLOOR)
    ap.add_argument("--json", type=Path, default=RESULTS_PATH)
    ap.add_argument("--only", help="run one class only")
    ap.add_argument("--keep", action="store_true", help="keep the temp fixture directory")
    ap.add_argument("--no-baseline", action="store_true", help="do not diff against the last run")
    ap.add_argument("--no-color", action="store_true")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="ignore KNOWN_FAILURES; every failing critical check gates the build",
    )
    args = ap.parse_args()

    if args.only and args.only not in CLASS_WEIGHTS:
        raise SystemExit(f"unknown class {args.only!r}; pick from {', '.join(CLASS_ORDER)}")

    colour = not args.no_color and sys.stdout.isatty()
    ensure_binary(args.binary, args.build, quiet=False)

    baseline = None
    if not args.no_baseline and args.json.exists():
        try:
            baseline = json.loads(args.json.read_text())
        except (json.JSONDecodeError, OSError):
            baseline = None

    root = Path(tempfile.mkdtemp(prefix="cfc-eval-"))
    try:
        report = run_eval(args.binary, root, args.only)
    finally:
        if args.keep:
            print(f"fixtures kept at {root}", file=sys.stderr)
        else:
            shutil.rmtree(root, ignore_errors=True)

    overall = report.overall()
    gating = report.critical_failures(args.strict)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "binary": str(args.binary),
        "overall": round(overall, 4),
        "floor": args.floor,
        "strict": args.strict,
        "passed": overall >= args.floor and not gating,
        "gating_failures": [c.name for c in gating],
        "known_failures": sorted(
            c.name for c in report.checks if not c.ok and c.name in KNOWN_FAILURES
        ),
        "resolved_known_failures": report.resolved_known_failures(),
        "classes": {
            cls: {
                "score": round(report.class_score(cls)[0], 4),
                "passed": report.class_score(cls)[1],
                "total": report.class_score(cls)[2],
                "weight": CLASS_WEIGHTS[cls],
            }
            for cls in CLASS_ORDER
            if any(c.cls == cls for c in report.checks)
        },
        "metrics": report.metrics,
        "checks": [
            {
                "class": c.cls,
                "name": c.name,
                "ok": c.ok,
                "critical": c.critical,
                "known": c.name in KNOWN_FAILURES,
                "weight": c.weight,
                "reason": c.reason,
                "excerpt": c.excerpt,
            }
            for c in report.checks
        ],
    }
    # A partial run must not overwrite the baseline the next full run diffs against.
    wrote = args.only is None or args.json != RESULTS_PATH
    if wrote:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    regressions = print_summary(report, args.floor, baseline, colour, args.strict)
    print(f"wrote {args.json}" if wrote else "(partial run — results file left untouched)")

    if gating:
        print(
            "FAIL: %d critical check(s) failed that are not tracked in KNOWN_FAILURES: %s"
            % (len(gating), ", ".join(c.name for c in gating)),
            file=sys.stderr,
        )
        return 1
    if overall < args.floor:
        print(f"FAIL: {overall * 100:.1f}% is below the {args.floor * 100:.1f}% floor.", file=sys.stderr)
        return 1
    # A check that passed on the previous run and fails now is a regression, and it fails the run
    # whether or not it is "critical" and whether or not the overall score is still above the floor.
    # Verified by reintroducing a real defect: the harness named the broken check, scored 99.0%, and
    # still exited 0 — a gate that reports a regression and then blesses the build is not a gate.
    if regressions:
        print(
            "FAIL: %d check(s) regressed since the last run: %s"
            % (len(regressions), ", ".join(f"{c}: {n}" for c, n in regressions)),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
