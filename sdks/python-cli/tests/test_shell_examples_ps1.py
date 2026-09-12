"""The PowerShell example script must stay parseable, read-only, and honest
about CLI failures. These tests stub the ``omi`` command (no network, no live
account) and assert the script's helper behavior plus a few structural
guarantees that the examples keep working."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
PS1 = EXAMPLES_DIR / "shell_examples.ps1"

# Only tests that actually launch PowerShell need the skip; the structural
# text checks below run on every platform so regressions are caught on
# non-Windows CI too.
requires_powershell = pytest.mark.skipif(
    shutil.which("powershell") is None and shutil.which("pwsh") is None,
    reason="no Windows PowerShell available on this platform",
)


def _powershell() -> str:
    return shutil.which("pwsh") or shutil.which("powershell")


def _run(ps_code: str, *, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-Command", ps_code],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _ps1_path_for_ps() -> str:
    """Windows PowerShell needs a Windows path; forward slashes are accepted."""
    return str(PS1).replace("\\", "/")


def test_script_exists() -> None:
    assert PS1.is_file()


@requires_powershell
def test_script_parses_cleanly() -> None:
    result = _run(
        "$err = $null; $tokens = $null; "
        f"$null = [System.Management.Automation.Language.Parser]::ParseFile("
        f"'{_ps1_path_for_ps()}', [ref]$tokens, [ref]$err); "
        "if ($err) { $err | ForEach-Object { Write-Host ('PARSE-ERR line ' + "
        "$_.Extent.StartLineNumber + ': ' + $_.Message) }; exit 1 } else { Write-Host 'PARSE OK' }"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PARSE OK" in result.stdout


def test_script_is_read_only() -> None:
    """No mutating verb may appear in an executed (non-comment) line.

    Examples invoke the CLI through ``Invoke-OmiJson @('--json', 'verb', ...)``
    argument arrays, so the guard matches mutating verbs inside the quoted
    tokens of every invocation (the failure mode the old ``\\bomi\\b.*verb``
    regex missed), as well as any direct ``omi ...`` call.
    """
    # Strip block comments (<# ... #>) line-range-wise, then line comments.
    lines = PS1.read_text(encoding="utf-8").splitlines()
    in_block = False
    code_lines = []
    for line in lines:
        stripped = line.strip()
        if "<#" in stripped:
            in_block = True
        if "#>" in stripped:
            in_block = False
            continue
        if in_block or stripped.startswith("#"):
            continue
        code_lines.append(stripped)
    mutating = re.compile(
        r"\b(create|update|delete|progress|complete|from-segments|logout)\b",
        re.IGNORECASE,
    )
    quoted_verb = re.compile(
        r"'[^']*\b(create|update|delete|progress|complete|from-segments|logout)\b",
        re.IGNORECASE,
    )
    for stripped in code_lines:
        assert not quoted_verb.search(stripped), f"mutating command in script: {stripped!r}"
        if re.search(r"\bomi\b", stripped, re.IGNORECASE) and "Invoke-OmiJson" not in stripped:
            assert not mutating.search(stripped), f"mutating direct omi call: {stripped!r}"


def test_script_has_no_embedded_credentials() -> None:
    text = PS1.read_text(encoding="utf-8")
    assert "omi_dev_" not in text.replace("omi_dev_...", ""), "realistic key prefix found"
    assert not re.search(r"OMI_API_KEY\s*=\s*'[^']{20,}", text), "hardcoded API key found"


def test_every_omi_call_checks_exit_code() -> None:
    """Direct omi invocations are allowed only inside the guarded helper."""
    text = PS1.read_text(encoding="utf-8")
    helper_start = text.index("function Invoke-OmiJson")
    helper_end = text.index("# ---", helper_start + 10)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or "& omi" not in stripped:
            continue
        pos = text.index(line)
        assert helper_start <= pos <= helper_end, f"unguarded omi call: {stripped!r}"


@requires_powershell
def test_helper_throws_on_nonzero_exit_and_malformed_json() -> None:
    """Stub omi: nonzero exit must throw; malformed JSON must throw; valid JSON
    must parse; empty output must yield $null."""
    script = PS1.read_text(encoding="utf-8")
    start = script.index("function Invoke-OmiJson")
    end = script.index("# ---", start + 10)
    helper = script[start:end]
    ps = f"""
{helper}
function omi {{ Write-Output 'boom'; $global:LASTEXITCODE = 2 }}
try {{ Invoke-OmiJson @('memory','list','--wat'); Write-Host 'A: NO-THROW' }}
catch {{ Write-Host 'A: THREW' }}
function omi {{ Write-Output '{{not json'; $global:LASTEXITCODE = 0 }}
try {{ Invoke-OmiJson @('memory','list','--json'); Write-Host 'B: NO-THROW' }}
catch {{ Write-Host 'B: THREW' }}
function omi {{ Write-Output '[{{"id":"m1"}}]'; $global:LASTEXITCODE = 0 }}
$r = Invoke-OmiJson @('memory','list','--json')
Write-Host ('C: ' + $r[0].id)
function omi {{ $global:LASTEXITCODE = 0 }}
$r2 = Invoke-OmiJson @('goal','list','--json')
if ($null -eq $r2) {{ Write-Host 'D: NULL' }} else {{ Write-Host 'D: NOT-NULL' }}
"""
    result = _run(ps)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "A: THREW" in result.stdout, result.stdout
    assert "B: THREW" in result.stdout, result.stdout
    assert "C: m1" in result.stdout, result.stdout
    assert "D: NULL" in result.stdout, result.stdout


def test_readme_links_the_script() -> None:
    readme = (EXAMPLES_DIR / "README.md").read_text(encoding="utf-8")
    assert "shell_examples.ps1" in readme


@pytest.mark.skipif(shutil.which("omi") is None, reason="omi CLI not installed on this machine")
def test_real_cli_json_position() -> None:
    """Regression net for the --json position: the root-level flag must go
    BEFORE the verb. Verified against the real binary (unauthenticated, no
    network): the wrong position fails option parsing with a usage error,
    while the right position parses and emits the JSON auth error object."""
    omi = shutil.which("omi")
    wrong = subprocess.run(
        [omi, "memory", "list", "--json", "--limit", "1"],
        capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
    )
    right = subprocess.run(
        [omi, "--json", "memory", "list", "--limit", "1"],
        capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
    )
    assert "No such option '--json'" not in (right.stdout + right.stderr), (
        "--json must be accepted before the verb"
    )
    wrong_rejected = "No such option '--json'" in (wrong.stdout + wrong.stderr)
    right_parsed = (right.stdout + right.stderr).lstrip().startswith("{")
    assert wrong_rejected or right_parsed, (
        f"unexpected CLI behavior: wrong={wrong.stdout!r}/{wrong.stderr!r} "
        f"right={right.stdout!r}/{right.stderr!r}"
    )

