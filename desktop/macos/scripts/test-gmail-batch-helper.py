#!/usr/bin/env python3
"""Hermetic failure-path tests for the embedded Gmail batch helper.

The Gmail Atom batch fetch runs as a Python script embedded as a Swift string
literal in Desktop/Sources/GmailReaderService.swift (with shared cookie-decrypt
support from BrowserGoogleSession.swift). Swift unit tests cover the parser and
budget math, but not the generated script's own failure classification.

This harness reconstructs the exact script the app runs — reproducing Swift's
multiline-literal indentation stripping and the one string interpolation — then
drives it as a subprocess with synthetic payloads. No network, no real cookies:
it asserts only on the JSON result contract (error_class, deadline handling,
empty/no-browser cases). Run before changing the embedded helper.

Usage: python3 scripts/test-gmail-batch-helper.py
Exit code 0 = all pass, 1 = a failure, 2 = sources not found.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = os.path.normpath(os.path.join(HERE, "..", "Desktop", "Sources"))
SUPPORT_SWIFT = os.path.join(SOURCES, "BrowserGoogleSession.swift")
GMAIL_SWIFT = os.path.join(SOURCES, "GmailReaderService.swift")
SUPPORT_INTERPOLATION = r"\(BrowserGoogleSession.chromiumCookiePythonSupport)"


def extract_multiline_literal(path, assignment_marker):
    """Return the Swift multiline string literal that follows an assignment.

    Swift strips indentation up to the column of the closing delimiter, so we
    detect that column from the closing-delimiter line and strip it per line.
    """
    lines = open(path).read().splitlines()
    start = None
    for i, line in enumerate(lines):
        if assignment_marker in line and line.rstrip().endswith('"""'):
            start = i + 1
            break
    if start is None:
        raise SystemExit(f"marker not found in {path}: {assignment_marker}")

    end = None
    for j in range(start, len(lines)):
        if lines[j].strip() == '"""':
            end = j
            break
    if end is None:
        raise SystemExit(f"closing delimiter not found in {path} after {assignment_marker}")

    strip = len(lines[end]) - len(lines[end].lstrip())
    body = []
    for line in lines[start:end]:
        body.append(line[strip:] if line[:strip].strip() == "" else line.lstrip())
    return "\n".join(body)


def build_script():
    if not (os.path.exists(SUPPORT_SWIFT) and os.path.exists(GMAIL_SWIFT)):
        print("Gmail helper sources not found; skipping", file=sys.stderr)
        sys.exit(2)
    support = extract_multiline_literal(SUPPORT_SWIFT, "static let chromiumCookiePythonSupport = ")
    gmail = extract_multiline_literal(GMAIL_SWIFT, "let pythonScript = ")
    if SUPPORT_INTERPOLATION not in gmail:
        raise SystemExit("support interpolation placeholder missing from gmail script")
    return gmail.replace(SUPPORT_INTERPOLATION, support, 1)


SCRIPT = build_script()
_fd, SCRIPT_PATH = tempfile.mkstemp(suffix=".py", prefix="omi_gmail_helper_")
with os.fdopen(_fd, "w") as _f:
    _f.write(SCRIPT + "\n")

# Fail loudly if the reconstructed script is not even valid Python.
subprocess.run([sys.executable, "-m", "py_compile", SCRIPT_PATH], check=True)


def run_script(payload):
    proc = subprocess.run(
        [sys.executable, SCRIPT_PATH],
        input=json.dumps(payload).encode(),
        capture_output=True,
        timeout=60,
    )
    return read_result(proc)


def read_result(proc):
    out_path = proc.stdout.decode().strip()
    assert out_path and os.path.exists(
        out_path
    ), f"no output file; stdout={proc.stdout!r} stderr={proc.stderr.decode()[:500]!r}"
    with open(out_path) as f:
        result = json.load(f)
    os.remove(out_path)
    return result


# Test-only override, activated by OMI_GMAIL_TEST_FAKE, that replaces just the
# two network leaf functions so the real orchestration (probe → warm session →
# parallel workers → fail-fast os._exit) runs offline. The production script has
# no such env check, so this never affects shipped behavior. Injected before the
# orchestration block, after the real defs, so late-bound calls hit the fakes.
FAKE_FETCH_INJECTION = (
    "if os.environ.get('OMI_GMAIL_TEST_FAKE'):\n"
    "    _FAKE_ATOM = b'<?xml version=\"1.0\"?><feed xmlns=\"http://purl.org/atom/ns#\">"
    "<entry><title>t</title><summary>s</summary>"
    "<author><name>A</name><email>a@b.com</email></author>"
    "<issued>2026-01-01T00:00:00Z</issued></entry></feed>'\n"
    "    def fetch_home_page(jar):\n"
    "        return 200, b'<html>fake</html>'\n"
    "    def fetch_atom_feed(jar, request):\n"
    "        rid = request.get('id')\n"
    "        if rid == 'label:atom/fail':\n"
    "            return 500, b'boom'\n"
    "        if rid == 'label:atom/slow':\n"
    "            time.sleep(10)\n"
    "        return 200, _FAKE_ATOM\n"
)


def run_script_faked(payload, timeout=20):
    anchor = "if not requests:"
    assert SCRIPT.count(anchor) == 1, "fake-injection anchor is not unique"
    faked = SCRIPT.replace(anchor, FAKE_FETCH_INJECTION + anchor, 1)
    fd, path = tempfile.mkstemp(suffix=".py", prefix="omi_gmail_helper_fake_")
    with os.fdopen(fd, "w") as f:
        f.write(faked + "\n")
    try:
        proc = subprocess.run(
            [sys.executable, path],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=timeout,
            env=dict(os.environ, OMI_GMAIL_TEST_FAKE="1"),
        )
        return read_result(proc)
    finally:
        os.remove(path)


# Temp cookie-DB dirs created during the run; removed in the final cleanup.
_COOKIE_DB_DIRS = []


def make_cookie_db(rows, with_journal=False):
    d = tempfile.mkdtemp(prefix="omi_gmail_cookiedb_")
    _COOKIE_DB_DIRS.append(d)
    path = os.path.join(d, "Cookies")
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE meta (key TEXT, value TEXT)")
    conn.execute("INSERT INTO meta VALUES ('version', '13')")
    conn.execute(
        "CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB,"
        " path TEXT, is_secure INTEGER, expires_utc INTEGER)"
    )
    for host, name, value in rows:
        conn.execute("INSERT INTO cookies VALUES (?, ?, ?, '/', 1, 0)", (host, name, value.encode()))
    conn.commit()
    conn.close()
    if with_journal:
        # A hot-journal sidecar the copy step must pick up alongside the DB.
        open(path + "-journal", "wb").close()
    return path


REQS = [{"id": "query", "max_results": 5, "query": "newer_than:365d", "feed_path": "", "use_bootstrap": False}] + [
    {
        "id": f"label:atom/{n}",
        "max_results": 5,
        "query": "newer_than:365d",
        "feed_path": f"atom/{n}",
        "use_bootstrap": False,
    }
    for n in ("inbox", "sent")
]

failures = 0


def check(name, cond, detail=""):
    global failures
    if not cond:
        failures += 1
    print(f"{'PASS' if cond else 'FAIL'}: {name} {detail}")


def main():
    # 1. Missing cookie DB → copy fails → decrypt attempt → decrypt_failed.
    r = run_script(
        {
            "browsers": [{"name": "Fake", "db_path": "/nonexistent/Cookies", "password": "x"}],
            "requests": REQS,
            "max_workers": 4,
            "deadline_seconds": 30,
        }
    )
    check(
        "missing DB → decrypt_failed",
        r.get("ok") is False and r.get("error_class") == "decrypt_failed",
        f"got {r.get('error_class')}",
    )

    # 2. DB with a hot-journal sidecar but no Google auth cookies → not_signed_in.
    #    Also exercises the sidecar-aware copy path (#1 fix).
    db = make_cookie_db([(".google.com", "NID", "plain")], with_journal=True)
    r = run_script(
        {
            "browsers": [{"name": "Fake", "db_path": db, "password": "x"}],
            "requests": REQS,
            "max_workers": 4,
            "deadline_seconds": 30,
        }
    )
    check(
        "no auth cookies (with journal sidecar) → not_signed_in",
        r.get("ok") is False and r.get("error_class") == "not_signed_in",
        f"got {r.get('error_class')}",
    )

    # 3. Auth cookies present but deadline already exhausted → probe stops
    #    before any network fetch (deadline fix, #3).
    db = make_cookie_db([(".google.com", "SID", "s"), (".google.com", "HSID", "h")])
    r = run_script(
        {
            "browsers": [{"name": "Fake", "db_path": db, "password": "x"}],
            "requests": REQS,
            "max_workers": 4,
            "deadline_seconds": 0,
        }
    )
    reasons = [a.get("reason") for a in r.get("attempts", [])]
    check(
        "exhausted deadline stops probe pre-network",
        r.get("ok") is False and "deadline exceeded" in reasons,
        f"reasons={reasons}",
    )

    # 4. Empty request list → ok with empty responses, no top-level emails.
    r = run_script({"browsers": [], "requests": [], "max_workers": 4, "deadline_seconds": 30})
    check(
        "empty requests → ok, empty responses",
        r.get("ok") is True and r.get("responses") == [] and "emails" not in r,
        f"got {r}",
    )

    # 5. No browsers at all → no_browser.
    r = run_script({"browsers": [], "requests": REQS, "max_workers": 4, "deadline_seconds": 30})
    check(
        "no browsers → no_browser",
        r.get("ok") is False and r.get("error_class") == "no_browser",
        f"got {r.get('error_class')}",
    )

    # 6. Fail-fast (#2 fix): probe succeeds, one worker fails immediately while
    #    another hangs for 10s. The helper must write a classified failure and
    #    exit promptly via os._exit — not join the in-flight hang.
    db = make_cookie_db([(".google.com", "SID", "s"), (".google.com", "HSID", "h")])
    reqs = [
        {"id": "query", "max_results": 5, "query": "q", "feed_path": "", "use_bootstrap": False},
        {"id": "label:atom/fail", "max_results": 5, "query": "q", "feed_path": "atom/fail", "use_bootstrap": False},
        {"id": "label:atom/slow", "max_results": 5, "query": "q", "feed_path": "atom/slow", "use_bootstrap": False},
    ]
    start = time.monotonic()
    r = run_script_faked(
        {
            "browsers": [{"name": "Fake", "db_path": db, "password": "x"}],
            "requests": reqs,
            "max_workers": 4,
            "deadline_seconds": 30,
        }
    )
    elapsed = time.monotonic() - start
    check(
        "worker fail-fast writes a classified failure",
        r.get("ok") is False and r.get("error_class") in ("network", "session_expired", "unknown"),
        f"got {r.get('error_class')}",
    )
    check("worker fail-fast exits without joining the 10s hang", elapsed < 5.0, f"elapsed={elapsed:.2f}s")

    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


try:
    code = main()
finally:
    try:
        os.remove(SCRIPT_PATH)
    except OSError:
        pass
    for _dir in _COOKIE_DB_DIRS:
        shutil.rmtree(_dir, ignore_errors=True)
sys.exit(code)
