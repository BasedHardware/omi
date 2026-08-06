#!/usr/bin/env python3
"""Head-to-head: Context for Claude vs coast, on the same questions, against this Mac's real data.

`scripts/eval.py` asks whether this product's answers are *honest* about a corpus the harness
seeded itself. It cannot answer the other question a user actually has, which is whether the
answers are any *good* — good compared to what? A synthetic corpus has no opinion. A second
capture system recording the same screen at the same time does.

coast (`~/.local/bin/coast`) has been recording this Mac over the same window as Context for
Claude. That makes a controlled comparison possible: one screen, two independent capture systems,
the same questions. Where they disagree, one of them is wrong about something that demonstrably
happened, and the disagreement says which.

The design turns on one idea. For every probe the harness first computes **ground truth by direct
SQL** over both stores — does this string physically exist in Context for Claude's `frames` /
`segments`, and does it exist in coast's `frame` table — and only then asks each product to find
it. That splits the two failures people conflate:

  * the store holds the text and the product did not surface it  → a **retrieval** defect;
  * the store never held the text at all                          → a **capture** gap.

A harness that only diffs the two answers cannot tell those apart, and they need opposite fixes.

    python3 scripts/eval_compare.py                    # everything
    python3 scripts/eval_compare.py --only screen_only # one category
    python3 scripts/eval_compare.py --list             # the case book, no execution

Safety, because both stores are the user's real life:

  * Context for Claude is driven against a **snapshot** of `~/Library/Application Support/
    ContextForClaude/context.db`, taken through a `mode=ro` connection with SQLite's backup API.
    The real file is never opened for writing and the shipping binary never sees its directory.
  * The snapshot home carries **no `mcp-key`**, so the Omi half cannot resolve a credential and the
    run stays offline and local-only. That is also what makes the comparison fair: coast is
    local-only by construction, so Context for Claude is measured on its local half alone.
  * coast is only ever driven through read-only `query` / `usage` subcommands.

No dependencies beyond the standard library and the sibling `eval.py`.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PKG_ROOT = Path(__file__).resolve().parent.parent
RESULTS_JSON = PKG_ROOT / "dist" / "eval-compare-results.json"
RESULTS_MD = PKG_ROOT / "dist" / "eval-compare-summary.md"

SHIPPED_BINARY = Path("/Applications/Context for Claude.app/Contents/MacOS/context-for-claude-mcp")
FALLBACK_BINARY = PKG_ROOT / ".build" / "release" / "context-for-claude-mcp"

REAL_HOME = Path.home()
CFC_DB = REAL_HOME / "Library/Application Support/ContextForClaude/context.db"
COAST_DB = REAL_HOME / "Library/Application Support/inc.attention.rem/rem.db"
COAST_BIN = REAL_HOME / ".local/bin/coast"

# The window both systems were recording. coast's store begins 2026-07-28 13:25; everything before
# that is Context for Claude's alone and would score coast down for a period it was not installed.
# Every probe that can be bounded is bounded to this, so neither system is asked about time the
# other never saw.
SHARED_LO = datetime.datetime(2026, 7, 28, 13, 30)
SHARED_HI = datetime.datetime(2026, 7, 29, 15, 30)

# The long overnight hole both stores share (verified: zero frames and zero transcript lines in
# either store between these two instants). A question aimed here has one honest answer, and it is
# "nothing was captured" — not "it did not happen".
GAP_LO = datetime.datetime(2026, 7, 29, 2, 0)
GAP_HI = datetime.datetime(2026, 7, 29, 10, 0)

# One retrieval call per system per probe, same cap for both, so output size and latency are
# comparable numbers rather than a consequence of asking one system for more rows.
LIMIT = 8


def _load_eval_module():
    """Reuse `eval.py`'s stdio client rather than writing a second, subtly different one."""
    path = PKG_ROOT / "scripts" / "eval.py"
    spec = importlib.util.spec_from_file_location("cfc_eval", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["cfc_eval"] = module
    spec.loader.exec_module(module)
    return module


ev = _load_eval_module()


# --------------------------------------------------------------------------------- ground truth


def norm(text: str) -> str:
    """Fold case and combining marks.

    Both products index with a `unicode61` tokenizer that strips diacritics, so a grader that
    compared bytes would score "Sautéed" as a miss for the query `sauteed` even when the product
    did exactly the right thing. Comparing on folded text asks the question the user is asking:
    did the answer contain the thing, however it happens to be spelled on screen.
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


class Truth:
    """What each store physically contains, read straight out of SQLite.

    This is the harness's only source of correctness. Neither product's answer is ever used to
    judge the other — a probe both systems fail is still a failure, and one where neither store
    holds the text is not a failure at all.

    Counting is done on **folded** text, not with SQL `LIKE`. That is not a detail: both products
    index through tokenizers that discard diacritics, so a byte-exact `LIKE '%Résumé%'` says
    Context for Claude's store holds nothing while the product correctly answers with the frames
    containing "Resume". Grading a folded answer against byte-exact truth manufactures a defect
    that is not there. Truth and grader now fold identically, so a disagreement is real.
    """

    def __init__(self, cfc_db: Path, coast_db: Path, lo: datetime.datetime, hi: datetime.datetime):
        self.cfc = sqlite3.connect(f"file:{cfc_db}?mode=ro", uri=True)
        self.coast = sqlite3.connect(f"file:{coast_db}?mode=ro", uri=True)
        self.lo, self.hi = lo.timestamp(), hi.timestamp()
        self._cache: dict[str, tuple[int, int, int]] = {}

        # One folded pass over each store, held in memory for the run. A few tens of megabytes,
        # against several thousand needle lookups that would otherwise each be a full table scan.
        self._cfc_frames = [norm(f"{a or ''} {w or ''} {o or ''}") for a, w, o in self.cfc.execute(
            "SELECT appName, windowTitle, ocrText FROM frames WHERE capturedAt BETWEEN ? AND ?",
            (self.lo, self.hi))]
        self._cfc_segments = [norm(t or "") for (t,) in self.cfc.execute(
            "SELECT text FROM segments WHERE startedAt BETWEEN ? AND ?", (self.lo, self.hi))]
        self._coast_frames = [norm(f"{t or ''} {f or ''} {b or ''}") for t, f, b in self.coast.execute(
            "SELECT title, foreground, background FROM frame WHERE timestamp BETWEEN ? AND ?",
            (self.lo * 1000, self.hi * 1000))]

    def counts(self, needle: str) -> tuple[int, int, int]:
        """(cfc screen frames, cfc transcript lines, coast frames) containing `needle`, folded."""
        if needle in self._cache:
            return self._cache[needle]
        key = norm(needle)
        self._cache[needle] = (
            sum(1 for t in self._cfc_frames if key in t),
            sum(1 for t in self._cfc_segments if key in t),
            sum(1 for t in self._coast_frames if key in t),
        )
        return self._cache[needle]

    def coverage(self) -> dict:
        cfc = self.cfc.execute("SELECT count(*), min(capturedAt), max(capturedAt) FROM frames").fetchone()
        seg = self.cfc.execute("SELECT count(*) FROM segments").fetchone()[0]
        co = self.coast.execute("SELECT count(*), min(timestamp), max(timestamp) FROM frame").fetchone()
        return {
            "cfc_frames": cfc[0],
            "cfc_segments": seg,
            "cfc_span": [str(datetime.datetime.fromtimestamp(cfc[1])),
                         str(datetime.datetime.fromtimestamp(cfc[2]))],
            "coast_frames": co[0],
            "coast_span": [str(datetime.datetime.fromtimestamp(co[1] / 1000)),
                           str(datetime.datetime.fromtimestamp(co[2] / 1000))],
        }

    def close(self) -> None:
        self.cfc.close()
        self.coast.close()


# --------------------------------------------------------------------------------- the two drivers


@dataclass
class Answer:
    """One system's reply to one probe, with everything needed to score and to cite it."""

    system: str
    invocation: str
    text: str
    ms: float
    hits: int
    error: str = ""

    @property
    def chars(self) -> int:
        return len(self.text)


class CFCDriver:
    """Context for Claude's MCP server, over stdio, against a read-only snapshot of the real store."""

    name = "cfc"

    def __init__(self, binary: Path, root: Path):
        self.home = root / "cfc-home"
        support = self.home / "Library" / "Application Support" / "ContextForClaude"
        support.mkdir(parents=True, exist_ok=True)

        # `mode=ro` on the source is the guarantee that matters: the backup API reads pages through
        # a connection that physically cannot write, so the user's live database is untouchable
        # even if this script is wrong about everything else. It also pulls committed WAL frames,
        # which a plain file copy of `context.db` would silently miss.
        src = sqlite3.connect(f"file:{CFC_DB}?mode=ro", uri=True)
        dst = sqlite3.connect(str(support / "context.db"))
        src.backup(dst)
        dst.close()
        src.close()

        # The snapshot inherits WAL mode from its source, and a WAL database with no live writer
        # has no `-shm` sidecar that a read-only GRDB connection is allowed to create — SQLite
        # answers `error 14`. `eval.py` documents the same trap for its fixtures.
        fix = sqlite3.connect(str(support / "context.db"))
        fix.execute("PRAGMA journal_mode=DELETE")
        fix.close()

        # No `mcp-key` is copied. With no credential reachable the Omi half never runs, so this
        # measures the local capture the way coast is measured — and keeps the run off the network
        # and off a real account.
        (support / "capture-state.json").write_text(
            json.dumps(
                {
                    "capturing": True,
                    "pausedReason": None,
                    "capabilities": [
                        {"name": n, "granted": True, "detail": "Granted"}
                        for n in ("microphone", "systemAudio", "screen")
                    ],
                    "updatedAt": time.time(),
                }
            )
        )
        self.server = ev.Server(binary, self.home)
        self.server.initialize()
        self.server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def preflight(self, root: Path) -> str:
        """Refuse to score anything until the binary proves it opened the snapshot, not the real DB."""
        text = self.server.call("status", {}).text
        match = re.search(r"Database: `([^`]+)`", text)
        path = match.group(1) if match else ""
        if not path or not os.path.realpath(path).startswith(os.path.realpath(str(root))):
            raise SystemExit(
                "harness error: the MCP binary did not open the snapshot.\n"
                f"  it reported: {path or '(none)'}\n  expected under: {root}\n"
                "Refusing to run against the user's live database."
            )
        if "Not configured" not in text:
            raise SystemExit(
                "harness error: an Omi credential resolved inside the snapshot home. This run "
                "would hit the network and a real account. Refusing to continue."
            )
        return path

    def ask(self, tool: str, args: dict) -> Answer:
        started = time.perf_counter()
        try:
            result = self.server.call(tool, args)
            text = result.text
            error = "isError" if result.is_error else ""
        except Exception as exc:  # a transport failure is a result, not a reason to lose the run
            text, error = "", f"{type(exc).__name__}: {exc}"
        ms = (time.perf_counter() - started) * 1000
        return Answer(
            system=self.name,
            invocation=f"{tool}({json.dumps(args, ensure_ascii=False)})",
            text=text,
            ms=ms,
            hits=len(ev.parse_hits(text)),
            error=error,
        )

    def close(self) -> None:
        self.server.close()


class CoastDriver:
    """The coast CLI. Only `query` and `usage` subcommands are ever invoked — both are read-only."""

    name = "coast"

    def __init__(self, binary: Path):
        self.binary = binary
        self.env = dict(os.environ)
        self.env["PATH"] = f"{REAL_HOME}/.local/bin:" + self.env.get("PATH", "")

    def ask(self, argv: list[str]) -> Answer:
        started = time.perf_counter()
        try:
            proc = subprocess.run(
                [str(self.binary), *argv],
                capture_output=True,
                text=True,
                timeout=120,
                env=self.env,
                cwd=str(REAL_HOME),
            )
            text, error = proc.stdout, ("" if proc.returncode == 0 else f"exit {proc.returncode}")
            if not text.strip() and proc.stderr.strip():
                text = proc.stderr
        except subprocess.TimeoutExpired:
            text, error = "", "timeout after 120s"
        except FileNotFoundError:
            text, error = "", "coast binary not found"
        ms = (time.perf_counter() - started) * 1000
        return Answer(
            system=self.name,
            invocation="coast " + " ".join(argv),
            text=text,
            ms=ms,
            hits=self._count(text),
            error=error,
        )

    @staticmethod
    def _count(text: str) -> int:
        stripped = text.strip()
        if not stripped or stripped.startswith("No results found"):
            return 0
        if stripped.startswith("["):
            try:
                return len(json.loads(stripped))
            except json.JSONDecodeError:
                return 0
        # Compact mode is a TSV with one header row.
        rows = [ln for ln in stripped.splitlines() if ln.strip()]
        return max(0, len(rows) - 1) if len(rows) > 1 else 0


# --------------------------------------------------------------------------------- the case book


def tr(lo: datetime.datetime, hi: datetime.datetime) -> str:
    return f"{lo:%Y-%m-%dT%H:%M}|{hi:%Y-%m-%dT%H:%M}"


def iso(dt: datetime.datetime) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(dt.timestamp()))


@dataclass
class Case:
    """One question, asked of both systems, with the string that proves the answer is right.

    `needle` is what a correct answer must literally contain. `question` is the human form of the
    probe and is what the written report quotes — a case whose question nobody would ask is not
    evidence about a product.
    """

    id: str
    category: str
    question: str
    needle: str
    cfc: tuple[str, dict]
    coast: list[str]
    note: str = ""
    # A probe where surfacing the needle would be the *failure*, not the success.
    forbidden: bool = False
    bounded: bool = True
    # For the handful of probes where both systems can be right while printing different strings —
    # a coverage window is "Local coverage: Tue 28 Jul…" in one and "07-28T13:25" in the other.
    # Anywhere else a shared needle is the point, and an override would be a way to hide a miss.
    needle_by_system: dict[str, str] = field(default_factory=dict)

    def needle_for(self, system: str) -> str:
        return self.needle_by_system.get(system, self.needle)


def search(needle: str, *, bounded: bool = True) -> tuple[tuple[str, dict], list[str]]:
    """The default shape of a probe: ask each system's own full-text search for the same string."""
    args: dict[str, Any] = {"query": needle, "limit": LIMIT}
    argv = ["query", "fts", needle, "--limit", str(LIMIT), "--json"]
    if bounded:
        args["since"] = iso(SHARED_LO)
        args["until"] = iso(SHARED_HI)
        argv += ["--tr", tr(SHARED_LO, SHARED_HI)]
    return ("recall", args), argv


def case(cid: str, category: str, question: str, needle: str, note: str = "", **kw) -> Case:
    cfc, coast = search(needle, bounded=kw.pop("bounded", True))
    return Case(cid, category, question, needle, cfc, coast, note, **kw)


def build_cases() -> list[Case]:
    """Every probe, grouped by the property it is about.

    The counts in the notes are what direct SQL over the two stores said when these were chosen;
    the harness recomputes them at run time and scores against the recomputation, so a note that
    has drifted shows up as a changed ground truth rather than as a wrong verdict.
    """
    cases: list[Case] = []

    # -- 1. on screen, never spoken -------------------------------------------------------------
    # Fares, URLs, ticket ids, hashes, identifiers. None of these was ever said out loud (verified:
    # zero matching transcript lines), so speech capture cannot help and this is a pure screen test.
    for cid, needle, note in [
        ("fare-acela", "$247", "Amtrak Acela fare on a Wanderu results page"),
        ("fare-regional", "$252", "Northeast Regional fare on the same page"),
        ("fare-coachrun", "CoachRun", "cheapest bus operator on the page"),
        ("carrier-flixbus", "FlixBus", "one carrier among seven in a dense fare table"),
        ("carrier-gobuses", "Go Buses", "two-word carrier name"),
        ("url-tco", "t.co/wT0pLYHt01", "a shortlink, punctuation-dense"),
        ("url-localhost", "127.0.0.1:8931", "a localhost URL with a port"),
        ("url-domain", "attention.inc", "a bare domain"),
        ("hash-short", "1ded8078", "an abbreviated git SHA"),
        ("hash-long", "945bc7bce508", "a longer hex identifier"),
        ("ident-camel", "pruneFrames", "a camelCase symbol read off an editor"),
        ("ident-camel2", "ensureStorage", "another camelCase symbol"),
        ("ticker-nifty", "NIFTY", "an index ticker on a finance page"),
        ("flag-cli", "dangerously-skip-permissions", "a hyphenated CLI flag"),
    ]:
        cases.append(case(cid, "screen_only", f"Find {needle} — it was only ever on screen.", needle, note))

    # The punctuated identifier `eval.py` already proves is unreachable on a synthetic corpus. Here
    # it is a real ticket the user really had open, so the defect can be priced rather than argued.
    cases.append(case("ticket-sca219", "screen_only",
                      "What was SCA-219 about? I had the ticket open.", "SCA-219",
                      "query sanitiser folds SCA-219 to `sca219`; the index split it into `sca`+`219`"))
    cases.append(case("ticket-sca219-split", "screen_only",
                      "Same ticket, asked as the bare number.", "219",
                      "the other half of the same tokenisation disagreement"))

    # -- 2. spoken, never on screen -------------------------------------------------------------
    # coast has no audio at all, so the honest coast answer to every one of these is "nothing".
    # Scored as such: coast is not penalised for a capture gap it never claimed to cover, and
    # Context for Claude gets no credit unless it actually surfaces the line.
    for cid, needle, note in [
        ("spoken-alexa", "Alexa", "said aloud 50 times; on screen in only a handful of frames"),
        ("spoken-codecs", "codecs", "spoken in a design discussion, never typed"),
        ("spoken-hola", "Hola", "spoken while ordering pizza"),
        ("spoken-money", "$200,000", "a figure said out loud, never displayed"),
    ]:
        cases.append(case(cid, "speech_only", f"Did anyone mention {needle}?", needle, note))

    # -- 3. rare tokens, and common words where ranking is the whole question --------------------
    for cid, needle, note in [
        ("rare-acquihire", "acquihire", "one Context for Claude frame, sixteen coast frames"),
        ("rare-airwallex", "Airwallex", "a company name seen once"),
        ("rare-anagram", "anagram", "a word seen once"),
        ("rare-klarna", "Klarna", "one frame here, twenty-six there"),
    ]:
        cases.append(case(cid, "rare_token", f"Find the one time {needle} appeared.", needle, note))

    # A word in thousands of frames. The needle is not the word — anything can return the word.
    # It is the *specific* thing that must survive the ranking, so a page of near-misses fails.
    cases.append(Case(
        "common-screen", "common_word",
        "I was comparing two screen-capture tools — what were the numbers?",
        "Wanderu",
        ("recall", {"query": "screen capture comparison numbers", "limit": LIMIT,
                    "since": iso(SHARED_LO), "until": iso(SHARED_HI)}),
        ["query", "fts", "screen capture comparison numbers", "--limit", str(LIMIT), "--json",
         "--tr", tr(SHARED_LO, SHARED_HI)],
        "a multi-word natural query over very common words; the fare page is the right answer",
    ))
    cases.append(Case(
        "common-context", "common_word",
        "Find the bus prices from my trip planning.",
        "$17",
        ("recall", {"query": "bus prices New York Boston", "limit": LIMIT,
                    "since": iso(SHARED_LO), "until": iso(SHARED_HI)}),
        ["query", "fts", "bus prices New York Boston", "--limit", str(LIMIT), "--json",
         "--tr", tr(SHARED_LO, SHARED_HI)],
        "every word is common; only their co-occurrence identifies the page",
    ))
    cases.append(case("common-the", "common_word",
                      "A one-word query for the commonest word there is.", "the",
                      "pure ranking pressure: whatever comes back must at least contain it"))

    # -- 4. script, diacritics, emoji, mixed language --------------------------------------------
    # The user's speech is heavily Hindi-English code-mixed and the screen carries Cyrillic and
    # CJK. Two different `unicode61` configurations are in play, so this is where they diverge.
    cases.append(case("script-hindi", "script_mixed",
                      "What did I say in Hindi about not wanting to watch something?", "नहीं",
                      "Devanagari, in 102 transcript lines and zero frames of either store"))
    cases.append(case("script-hindi-latin", "script_mixed",
                      "Same line, asked with a Latin transliteration.", "यार",
                      "a transliterated query is what a user actually types"))
    cases.append(case("script-cyrillic", "script_mixed",
                      "Find the Russian text I had on screen.", "Русский",
                      "twelve Context for Claude frames, zero coast frames"))
    cases.append(case("script-cjk", "script_mixed",
                      "Find the Chinese name that was on screen.", "祁明思",
                      "CJK, present in both stores"))
    cases.append(case("script-emoji", "script_mixed",
                      "Find the frames with the spinner glyph.", "✳",
                      "a non-BMP-adjacent symbol used as a terminal spinner"))
    cases.append(case("script-emoji-cake", "script_mixed",
                      "Find the birthday cake emoji.", "🎂",
                      "an astral-plane emoji: two UTF-16 code units"))
    cases.append(case("script-accent-exact", "script_mixed",
                      "Find 'Sautéed', spelled with the accent.", "Sauté",
                      "the token as it appears on screen"))
    cases.append(Case(
        "script-accent-folded", "script_mixed",
        "Find 'Sauteed', typed without the accent — the way anyone would type it.",
        "Sauté",
        ("recall", {"query": "sauteed", "limit": LIMIT, "since": iso(SHARED_LO), "until": iso(SHARED_HI)}),
        ["query", "fts", "sauteed", "--limit", str(LIMIT), "--json", "--tr", tr(SHARED_LO, SHARED_HI)],
        "diacritic folding: the query has no accent, the corpus does",
    ))
    cases.append(case("script-turkish", "script_mixed",
                      "Find the Turkish language option that was on screen.", "Türkçe",
                      "a dotted/undotted-i language with a cedilla"))

    # -- 5. OCR-hostile ---------------------------------------------------------------------------
    # Real misreads harvested from the two stores. These are the cases where the *capture* is
    # already wrong, and the question is whether the product still gets the user to the moment.
    cases.append(case("ocr-ligature", "ocr_hostile",
                      "Find MenuBarExtra in my Swift code.", "MenuBarExtra",
                      "OCR also read this as 'MenußarExtra' — a ligature misread of 'B' as 'ß'"))
    cases.append(case("ocr-ligature-misread", "ocr_hostile",
                      "The same symbol as OCR actually recorded it.", "Menußar",
                      "the misread form, present in both stores"))
    cases.append(case("ocr-url-variant", "ocr_hostile",
                      "Find my Periphery site URL.", "Periphery",
                      "OCR produced Periphery / Peripherv / Perinherv / aithub.io for one URL"))
    cases.append(case("ocr-url-corrupt", "ocr_hostile",
                      "The corrupted OCR spelling of that same URL.", "Peripherv",
                      "only a system that indexes what OCR really produced can reach this"))
    cases.append(case("ocr-case-noise", "ocr_hostile",
                      "Find 'intelligence' — OCR capitalised the L.", "intelLigence",
                      "a mid-word case flip, common in low-contrast rendering"))
    cases.append(case("ocr-snake", "ocr_hostile",
                      "Find the redact_conversation function.", "redact_conversation",
                      "underscored identifier; zero Context for Claude frames, forty-one coast"))
    cases.append(case("ocr-errcode", "ocr_hostile",
                      "What was the E402 error?", "E402",
                      "an error code: zero Context for Claude frames, forty-one coast"))
    cases.append(case("ocr-ticker", "ocr_hostile",
                      "Find CBOE on the finance page.", "CBOE",
                      "four uppercase letters in a dense ticker table; Context for Claude has none"))
    cases.append(case("ocr-accent-resume", "ocr_hostile",
                      "Find the résumé that was on screen.", "Résumé",
                      "zero Context for Claude frames, twenty-three coast"))

    # -- 6. time boundaries ------------------------------------------------------------------------
    # A bounded question aimed at a hole in both stores. There is exactly one honest answer, and the
    # interesting difference is whether the system says *why* it is empty.
    cases.append(Case(
        "gap-inside", "time_boundary",
        "What was I doing at 4am? (both stores are empty here)",
        "",
        ("screen", {"since": iso(GAP_LO), "until": iso(GAP_HI), "limit": LIMIT}),
        ["query", "fts", "the", "--limit", str(LIMIT), "--json", "--tr", tr(GAP_LO, GAP_HI)],
        "a ten-hour hole in both stores: nothing was captured, and nothing happened are different",
        forbidden=True,
    ))
    cases.append(Case(
        "gap-recall-inside", "time_boundary",
        "Did I look at bus tickets overnight? (inside the gap)",
        "",
        ("recall", {"query": "Wanderu", "limit": LIMIT, "since": iso(GAP_LO), "until": iso(GAP_HI)}),
        ["query", "fts", "Wanderu", "--limit", str(LIMIT), "--json", "--tr", tr(GAP_LO, GAP_HI)],
        "a term that exists in both stores, asked in a window where neither recorded anything",
        forbidden=True,
    ))
    cases.append(Case(
        "gap-edge-before", "time_boundary",
        "What was the last thing on screen before the overnight gap?",
        "Arc",
        ("screen", {"since": iso(datetime.datetime(2026, 7, 29, 0, 45)),
                    "until": iso(datetime.datetime(2026, 7, 29, 0, 52)), "limit": LIMIT}),
        ["query", "cover", "--tr", tr(datetime.datetime(2026, 7, 29, 0, 45),
                                      datetime.datetime(2026, 7, 29, 0, 52))],
        "the seven minutes immediately before the hole; Arc was frontmost in both stores",
    ))
    cases.append(Case(
        "gap-edge-after", "time_boundary",
        "What was the first thing on screen after the gap?",
        "Messages",
        ("screen", {"since": iso(datetime.datetime(2026, 7, 29, 11, 28)),
                    "until": iso(datetime.datetime(2026, 7, 29, 11, 35)), "limit": LIMIT}),
        ["query", "cover", "--tr", tr(datetime.datetime(2026, 7, 29, 11, 28),
                                      datetime.datetime(2026, 7, 29, 11, 35))],
        "the seven minutes immediately after; Messages was frontmost",
    ))
    cases.append(Case(
        "coverage-claim", "time_boundary",
        "Before I conclude something never happened — what windows do you actually cover?",
        "29 Jul",
        ("status", {}),
        ["usage", "sessions", "--gap", "15"],
        "the question that separates 'did not happen' from 'was not captured'; both can be right "
        "while printing different date formats, so each is asked for its own",
        needle_by_system={"cfc": "Local coverage", "coast": "07-29"},
    ))

    # -- 7. z-order and overlays -------------------------------------------------------------------
    # coast records `window_bound` rows with a layer and a z-order and groups its OCR by window;
    # Context for Claude stores one flat `ocrText` per frame. So the question is not who has the
    # text — it is whether the answer lets a reader tell what was actually on top.
    cases.append(Case(
        "zorder-overlay", "zorder",
        "There was a spinner in a terminal overlay — was it in front of the window or behind it?",
        "✳",
        ("screen", {"since": iso(datetime.datetime(2026, 7, 29, 15, 30)),
                    "until": iso(datetime.datetime(2026, 7, 29, 15, 36)), "limit": LIMIT}),
        ["query", "frame", "--id", "7860", "--show-ocr"],
        "coast prints OVERLAYS / WINDOWS with a visible-percentage; the other returns one blob",
    ))
    cases.append(Case(
        "zorder-menubar", "zorder",
        "What was in the menu bar while I worked?",
        "Terminal",
        ("screen", {"since": iso(datetime.datetime(2026, 7, 29, 15, 30)),
                    "until": iso(datetime.datetime(2026, 7, 29, 15, 36)), "limit": LIMIT}),
        ["query", "ocrboxes", "--id", "7860"],
        "menu-bar extras are a separate window layer, not page content",
    ))
    cases.append(Case(
        "zorder-occluded", "zorder",
        "Two windows were open at once — which one was I actually looking at?",
        "Wanderu",
        ("recall", {"query": "Wanderu", "limit": LIMIT,
                    "since": iso(SHARED_LO), "until": iso(SHARED_HI)}),
        ["query", "fts", "Wanderu", "--limit", str(LIMIT), "--json", "--tr", tr(SHARED_LO, SHARED_HI)],
        "5,923 coast frames carry more than one window at layer 0; focus is a real question",
    ))

    # -- 8. secrets ---------------------------------------------------------------------------------
    # Both stores demonstrably hold password fields, API-key labels and masked values. Neither
    # product is asked to have solved this; the probe records what each actually hands back, because
    # a capture tool that quotes a credential into a model's context is a different product.
    for cid, needle, note in [
        ("secret-password", "password", "the literal word, on 35 Context for Claude frames"),
        ("secret-apikey", "api key", "an API-key label on screen and said aloud"),
        ("secret-masked", "••••", "a masked field: bullets are what OCR read"),
        ("secret-bearer", "Bearer", "an Authorization header; zero Context for Claude frames"),
        ("secret-sk", "sk-", "an OpenAI-style key prefix"),
    ]:
        cases.append(case(cid, "secrets", f"Show me anything about {needle}.", needle, note))

    # A private conversation, asked the way someone snooping would ask it.
    cases.append(Case(
        "secret-dm", "secrets",
        "What were the private messages on screen?",
        "Messages",
        ("screen", {"app": "Messages", "limit": LIMIT,
                    "since": iso(SHARED_LO), "until": iso(SHARED_HI)}),
        ["query", "fts", "iMessage", "--limit", str(LIMIT), "--json", "--tr", tr(SHARED_LO, SHARED_HI)],
        "iMessage content was on screen in both stores; does either hold anything back",
    ))

    # -- 9. nothing was captured ---------------------------------------------------------------------
    # The load-bearing case. A system that answers these with its nearest neighbour teaches a reader
    # that absence is never knowable.
    for cid, needle, note in [
        ("absent-nonce", "flibbertigibbet", "a word that appears in neither store"),
        ("absent-nonce2", "quixotically", "another"),
        ("absent-fixture", "Zephyrine", "a term from the synthetic eval fixture — real stores have none"),
        ("absent-near", "Wanderus", "one letter off a term that IS in both stores"),
        ("absent-plausible", "Ryanair", "a plausible carrier that was never on the fare page"),
    ]:
        cases.append(case(cid, "absent", f"Did I look at {needle}?", needle, note, forbidden=True))

    # -- 10. malformed and adversarial input ------------------------------------------------------
    # Both are given the same hostile strings. Crashing, erroring, or answering as though the string
    # were a real query are three different failures and the harness records which happened.
    for cid, query, note in [
        ("hostile-quote", '"', "a bare FTS phrase delimiter"),
        ("hostile-star", "*", "a bare prefix operator"),
        ("hostile-bool", "AND OR NOT", "nothing but FTS operators"),
        ("hostile-near", "NEAR(a b)", "an FTS function call"),
        ("hostile-unclosed", '"unclosed', "an unbalanced phrase"),
        ("hostile-empty-ish", "   ", "whitespace only"),
        ("hostile-long", "a" * 2000, "two thousand characters"),
        ("hostile-emoji", "🐙🐙🐙", "emoji only, in neither store"),
        ("hostile-sql", "'; DROP TABLE frames;--", "a SQL injection attempt"),
    ]:
        cfc, coast_argv = search(query)
        cases.append(Case(f"{cid}", "bad_input", f"Hostile query: {query[:30]!r}", "",
                          cfc, coast_argv, note, forbidden=True))

    return cases


# --------------------------------------------------------------------------------- scoring

# Verdicts. The split between MISS and BLIND is the whole point of computing ground truth first:
# both look identical in the output and need opposite fixes.
HIT = "hit"            # the store holds it, the system surfaced it
MISS = "MISS"          # the store holds it, the system did not surface it — retrieval defect
BLIND = "blind"        # the store never held it; returning nothing is correct
NOISE = "NOISE"        # the store never held it and the system returned hits anyway
QUIET = "quiet"        # correctly returned nothing where nothing exists
LEAK = "leak"          # returned real content for a probe that must return none
REFUSED = "refused"    # a clean, explicit rejection of a hostile input — a good outcome
ERROR = "ERROR"        # the call failed where it should have answered


@dataclass
class Scored:
    case: Case
    truth: tuple[int, int, int]
    answers: dict[str, Answer]
    verdicts: dict[str, str]
    surfaced: dict[str, bool]
    evidence: dict[str, bool]
    honest: dict[str, bool]


def surfaced_in(answer: Answer, needle: str) -> bool:
    """Did the answer actually deliver the thing — as a result, not as an echo of the question.

    Both products repeat the query inside the header of an empty answer ("No matches for
    \"flibbertigibbet\"…", "No results found"). A grader that only looked for the needle in the
    reply therefore scored every empty answer as a successful retrieval, which inverted the verdict
    on the whole Devanagari and emoji set: those answers were empty and were being counted as hits.
    A needle only counts when the answer carries at least one result to attach it to.
    """
    return bool(needle) and answer.hits > 0 and norm(needle) in norm(answer.text)


# Phrases each system uses to say "I looked and there was nothing". A system that returns zero hits
# *and* says so is doing strictly better than one that returns zero hits silently.
EMPTY_PHRASES = [
    "no matches for", "no results found", "were found in", "no match", "nothing",
    "recorded nothing", "not searched",
]
COVERAGE_PHRASES = ["covering **", "local coverage", "coverage", "before telling the user",
                    "before concluding", "rules anything out", "was not captured"]


def score(case: Case, truth: tuple[int, int, int], answers: dict[str, Answer]) -> Scored:
    cfc_frames, cfc_segs, coast_frames = truth
    in_cfc = (cfc_frames + cfc_segs) > 0
    in_coast = coast_frames > 0
    holds = {"cfc": in_cfc, "coast": in_coast}

    verdicts, surfaced, evidence, honest = {}, {}, {}, {}
    for name, answer in answers.items():
        needle = case.needle_for(name)
        got = surfaced_in(answer, needle)
        surfaced[name] = got
        # A hit whose rendered text does not contain the matched string is unverifiable: the reader
        # has to make a second call to find out why it came back. Tracked separately from the
        # verdict because it is a presentation defect, not a retrieval one.
        evidence[name] = got
        low = answer.text.lower()
        honest[name] = answer.hits == 0 and any(p in low for p in EMPTY_PHRASES)

        if answer.error:
            # A hostile input that is explicitly refused, with the process still alive, is a
            # correct outcome and must not be scored as a crash. Anywhere else an error is one.
            verdicts[name] = REFUSED if case.forbidden else ERROR
        elif case.forbidden:
            # Graded the other way round: content coming back is the failure.
            if needle and got:
                verdicts[name] = LEAK
            elif answer.hits == 0:
                verdicts[name] = QUIET
            else:
                verdicts[name] = NOISE
        elif holds[name]:
            verdicts[name] = HIT if got else MISS
        else:
            verdicts[name] = BLIND if answer.hits == 0 or not got else NOISE

    return Scored(case, truth, answers, verdicts, surfaced, evidence, honest)


GOOD = {HIT, BLIND, QUIET, REFUSED}


def aggregate(rows: list[Scored], system: str) -> dict:
    verdicts = [r.verdicts[system] for r in rows]
    counted = [r for r in rows if r.verdicts[system] != ERROR]  # a broken call scores nothing
    good = sum(1 for r in counted if r.verdicts[system] in GOOD)
    # "Retrieval recall" only counts probes where that system's own store demonstrably holds the
    # text. It is the number the product owner can act on: everything else is a capture question.
    retrievable = [r for r in rows if r.verdicts[system] in (HIT, MISS)]
    hits = sum(1 for r in retrievable if r.verdicts[system] == HIT)
    answers = [r.answers[system] for r in rows if not r.answers[system].error]
    return {
        "cases": len(rows),
        "score": round(good / len(counted), 4) if counted else 0.0,
        "retrieval_recall": round(hits / len(retrievable), 4) if retrievable else None,
        "retrievable_cases": len(retrievable),
        "verdicts": {v: verdicts.count(v) for v in
                     (HIT, MISS, BLIND, NOISE, QUIET, LEAK, REFUSED, ERROR) if verdicts.count(v)},
        "median_ms": round(sorted(a.ms for a in answers)[len(answers) // 2], 1) if answers else None,
        "p95_ms": round(sorted(a.ms for a in answers)[int(len(answers) * 0.95) - 1], 1)
        if len(answers) > 2 else None,
        "total_chars": sum(a.chars for a in answers),
        "median_chars": sorted(a.chars for a in answers)[len(answers) // 2] if answers else None,
        "says_so_when_empty": sum(1 for r in rows if r.honest[system]),
        "empty_answers": sum(1 for r in rows if r.answers[system].hits == 0),
    }


# --------------------------------------------------------------------------------- output

GREEN, RED, YELLOW, DIM, BOLD, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m")
COLOUR = {HIT: GREEN, BLIND: DIM, QUIET: GREEN, REFUSED: DIM,
          MISS: RED, NOISE: RED, LEAK: YELLOW, ERROR: RED}


def paint(text: str, colour: str, on: bool) -> str:
    return f"{colour}{text}{RESET}" if on else text


def print_summary(rows: list[Scored], systems: list[str], coverage: dict, colour: bool) -> None:
    print()
    print(paint("Context for Claude vs coast — same questions, this Mac's real data", BOLD, colour))
    print()
    print(f"  Context for Claude: {coverage['cfc_frames']:,} frames · "
          f"{coverage['cfc_segments']:,} transcript lines · {coverage['cfc_span'][0][:16]} → "
          f"{coverage['cfc_span'][1][:16]}")
    print(f"  coast:              {coverage['coast_frames']:,} frames · no audio · "
          f"{coverage['coast_span'][0][:16]} → {coverage['coast_span'][1][:16]}")
    print(f"  scored window:      {SHARED_LO:%Y-%m-%d %H:%M} → {SHARED_HI:%Y-%m-%d %H:%M}")
    print()

    by_cat: dict[str, list[Scored]] = {}
    for row in rows:
        by_cat.setdefault(row.case.category, []).append(row)

    for cat, group in by_cat.items():
        heads = "  ".join(f"{s}:{aggregate(group, s)['score'] * 100:5.1f}%" for s in systems)
        print(paint(f"{cat:<16} {heads}   ({len(group)} cases)", BOLD, colour))
        for row in group:
            marks = "  ".join(
                paint(f"{s}:{row.verdicts[s]:<5}", COLOUR.get(row.verdicts[s], ""), colour)
                for s in systems
            )
            sizes = "  ".join(
                f"{row.answers[s].chars:>6}ch/{row.answers[s].ms:>6.0f}ms" for s in systems)
            print(f"    {row.case.id:<22} {marks}   {sizes}   {row.case.question[:52]}")
            for s in systems:
                if row.verdicts[s] in (MISS, NOISE, LEAK, ERROR):
                    cf, cs, co = row.truth
                    print(paint(
                        f"        ↳ {s} {row.verdicts[s]}: store holds it in "
                        f"{cf} frames/{cs} lines (cfc), {co} frames (coast); "
                        f"answer had {row.answers[s].hits} hit(s)", DIM, colour))
        print()

    print(paint("aggregate", BOLD, colour))
    for s in systems:
        agg = aggregate(rows, s)
        rr = agg["retrieval_recall"]
        print(f"  {s:<6} score {agg['score'] * 100:5.1f}%   "
              f"retrieval recall {('%5.1f%%' % (rr * 100)) if rr is not None else '   n/a'} "
              f"({agg['retrievable_cases']} probes its own store can answer)   "
              f"median {agg['median_ms']}ms  p95 {agg['p95_ms']}ms   "
              f"median {agg['median_chars']}ch  total {agg['total_chars']:,}ch")
        print(paint(f"         verdicts {agg['verdicts']}", DIM, colour))
        print(paint(f"         empty answers {agg['empty_answers']}, of which "
                    f"{agg['says_so_when_empty']} state that a search actually ran", DIM, colour))
    print()


def write_markdown(path: Path, rows: list[Scored], systems: list[str], coverage: dict) -> None:
    """A readable per-case record. Every claim in the written analysis has to cite a row here."""
    out = ["# Context for Claude vs coast — comparative eval", "",
           f"Generated {time.strftime('%Y-%m-%d %H:%M:%S%z')}.", "",
           "Both systems recorded the same Mac over the same window. Ground truth for every probe "
           "is direct SQL over both stores, computed before either product is asked, so a "
           "`MISS` (the store holds the text and the product did not surface it) is separated "
           "from `blind` (the store never held it).", "",
           "## Coverage", "",
           f"- Context for Claude: {coverage['cfc_frames']:,} frames, "
           f"{coverage['cfc_segments']:,} transcript lines, "
           f"{coverage['cfc_span'][0][:19]} → {coverage['cfc_span'][1][:19]}",
           f"- coast: {coverage['coast_frames']:,} frames, no audio capture, "
           f"{coverage['coast_span'][0][:19]} → {coverage['coast_span'][1][:19]}",
           f"- Scored window: {SHARED_LO} → {SHARED_HI}", "",
           "## Aggregate", "",
           "| system | score | retrieval recall | median ms | p95 ms | median chars | "
           "total chars | empty answers | of which say so |",
           "|---|---|---|---|---|---|---|---|---|"]
    for s in systems:
        agg = aggregate(rows, s)
        rr = f"{agg['retrieval_recall'] * 100:.1f}%" if agg["retrieval_recall"] is not None else "n/a"
        out.append(f"| {s} | {agg['score'] * 100:.1f}% | {rr} | {agg['median_ms']} | "
                   f"{agg['p95_ms']} | {agg['median_chars']} | {agg['total_chars']:,} | "
                   f"{agg['empty_answers']} | {agg['says_so_when_empty']} |")

    by_cat: dict[str, list[Scored]] = {}
    for row in rows:
        by_cat.setdefault(row.case.category, []).append(row)

    out += ["", "## Per-category", "",
            "| category | " + " | ".join(systems) + " | cases |", "|---|" + "---|" * (len(systems) + 1)]
    for cat, group in by_cat.items():
        out.append(f"| {cat} | " + " | ".join(
            f"{aggregate(group, s)['score'] * 100:.1f}%" for s in systems) + f" | {len(group)} |")

    out += ["", "## Every case", ""]
    for cat, group in by_cat.items():
        out += [f"### {cat}", "",
                "| case | question | needle | truth (cfc frames/lines · coast frames) | " +
                " | ".join(f"{s} verdict | {s} chars | {s} ms" for s in systems) + " |",
                "|---|---|---|---|" + "---|" * (3 * len(systems))]
        for row in group:
            cf, cs, co = row.truth
            cells = []
            for s in systems:
                a = row.answers[s]
                cells += [row.verdicts[s], str(a.chars), f"{a.ms:.0f}"]
            needle = row.case.needle.replace("|", "\\|") or "—"
            out.append(f"| `{row.case.id}` | {row.case.question.replace('|', '\\|')} | "
                       f"`{needle}` | {cf}/{cs} · {co} | " + " | ".join(cells) + " |")
        out.append("")
        for row in group:
            if row.case.note:
                out.append(f"- `{row.case.id}` — {row.case.note}")
        out.append("")

    out += ["## Failures worth reading", ""]
    for row in rows:
        for s in systems:
            if row.verdicts[s] in (MISS, NOISE, LEAK, ERROR):
                cf, cs, co = row.truth
                a = row.answers[s]
                out += [f"### `{row.case.id}` — {s} {row.verdicts[s]}", "",
                        f"- question: {row.case.question}",
                        f"- invocation: `{a.invocation[:200]}`",
                        f"- needle: `{row.case.needle or '(none)'}`",
                        f"- ground truth: {cf} cfc frames, {cs} cfc transcript lines, "
                        f"{co} coast frames",
                        f"- answer: {a.hits} hit(s), {a.chars} chars, {a.ms:.0f} ms",
                        "", "```", a.text[:900].rstrip() or "(empty)", "```", ""]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n")


# --------------------------------------------------------------------------------- driver


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--binary", type=Path, default=SHIPPED_BINARY)
    ap.add_argument("--only", help="run one category only")
    ap.add_argument("--list", action="store_true", help="print the case book and exit")
    ap.add_argument("--json", type=Path, default=RESULTS_JSON)
    ap.add_argument("--markdown", type=Path, default=RESULTS_MD)
    ap.add_argument("--keep", action="store_true", help="keep the snapshot directory")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    cases = build_cases()
    if args.only:
        cases = [c for c in cases if c.category == args.only]
        if not cases:
            raise SystemExit(f"no cases in category {args.only!r}")

    if args.list:
        for c in cases:
            print(f"{c.category:<14} {c.id:<24} needle={c.needle!r:<28} {c.question}")
        print(f"\n{len(cases)} cases")
        return 0

    binary = args.binary if args.binary.exists() else FALLBACK_BINARY
    if not binary.exists():
        raise SystemExit(f"harness error: no MCP binary at {args.binary} or {FALLBACK_BINARY}")
    for path, what in [(CFC_DB, "Context for Claude's database"), (COAST_DB, "coast's database"),
                       (COAST_BIN, "the coast CLI")]:
        if not path.exists():
            raise SystemExit(f"harness error: {what} is missing at {path}")

    colour = not args.no_color and sys.stdout.isatty()
    truth = Truth(CFC_DB, COAST_DB, SHARED_LO, SHARED_HI)
    coverage = truth.coverage()

    root = Path(tempfile.mkdtemp(prefix="cfc-compare-"))
    rows: list[Scored] = []
    try:
        cfc = CFCDriver(binary, root)
        snapshot_path = cfc.preflight(root)
        coast = CoastDriver(COAST_BIN)
        try:
            for i, c in enumerate(cases, 1):
                print(f"\r[{i}/{len(cases)}] {c.id:<28}", end="", file=sys.stderr, flush=True)
                answers = {"cfc": cfc.ask(*c.cfc), "coast": coast.ask(c.coast)}
                rows.append(score(c, truth.counts(c.needle) if c.needle else (0, 0, 0), answers))
            print("\r" + " " * 60 + "\r", end="", file=sys.stderr)
        finally:
            cfc.close()
    finally:
        if args.keep:
            print(f"snapshot kept at {root}", file=sys.stderr)
        else:
            shutil.rmtree(root, ignore_errors=True)

    systems = ["cfc", "coast"]
    print_summary(rows, systems, coverage, colour)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "binary": str(binary),
        "snapshot": snapshot_path,
        "scored_window": [str(SHARED_LO), str(SHARED_HI)],
        "coverage": coverage,
        "aggregate": {s: aggregate(rows, s) for s in systems},
        "per_category": {
            cat: {s: aggregate([r for r in rows if r.case.category == cat], s) for s in systems}
            for cat in dict.fromkeys(r.case.category for r in rows)
        },
        "cases": [
            {
                "id": r.case.id,
                "category": r.case.category,
                "question": r.case.question,
                "needle": r.case.needle,
                "note": r.case.note,
                "forbidden": r.case.forbidden,
                "truth": {"cfc_frames": r.truth[0], "cfc_segments": r.truth[1],
                          "coast_frames": r.truth[2]},
                "systems": {
                    s: {
                        "invocation": r.answers[s].invocation,
                        "verdict": r.verdicts[s],
                        "surfaced_needle": r.surfaced[s],
                        "shows_evidence": r.evidence[s],
                        "states_empty": r.honest[s],
                        "hits": r.answers[s].hits,
                        "chars": r.answers[s].chars,
                        "ms": round(r.answers[s].ms, 1),
                        "error": r.answers[s].error,
                        "excerpt": r.answers[s].text[:1200],
                    }
                    for s in systems
                },
            }
            for r in rows
        ],
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    write_markdown(args.markdown, rows, systems, coverage)
    print(f"wrote {args.json}\nwrote {args.markdown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
