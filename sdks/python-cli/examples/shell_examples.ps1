#Requires -Version 5.1
<#
.SYNOPSIS
    omi-cli — runnable Windows PowerShell example snippets (read-only).

.DESCRIPTION
    PowerShell counterpart to shell_examples.sh. Each region is self-contained;
    pick what you need. Examples are READ-ONLY: nothing here creates, updates,
    or deletes data. Auth is handled separately (see the Auth region and
    examples/README.md) — no credentials live in this file.

.NOTES
    Requires the omi CLI on PATH (pip install omi-cli). JSON parsing uses
    ConvertFrom-Json, so jq is not needed. Every omi call checks $LASTEXITCODE
    before touching its output: on a nonzero exit the script stops with a
    useful error instead of parsing garbage.
#>

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------------------
# Helpers (used by the examples below)
# ---------------------------------------------------------------------------

function Invoke-OmiJson {
    <#
    .SYNOPSIS
        Runs an omi command, asserts success, and returns parsed JSON (or $null
        for empty output). All read-only examples go through this helper so a
        CLI failure stops the script instead of feeding broken JSON to
        ConvertFrom-Json.
    #>
    param(
        [Parameter(Mandatory = $true)][string[]]$OmiArgs
    )

    $output = & omi @OmiArgs 2>&1
    if ($LASTEXITCODE -ne 0) {
        $detail = ($output | Out-String).Trim()
        throw "omi $($OmiArgs -join ' ') failed with exit code $LASTEXITCODE. Output: $detail"
    }
    $text = ($output | Out-String).Trim()
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    try {
        return $text | ConvertFrom-Json
    } catch {
        throw "omi $($OmiArgs -join ' ') printed output that is not valid JSON: $($_.Exception.Message)"
    }
}

# ---------------------------------------------------------------------------
# Auth (setup — nothing below runs without it)
# ---------------------------------------------------------------------------

# Interactive login (recommended — input is hidden, never lands in history):
#   omi auth login
#
# Headless / CI:
#   $env:OMI_API_KEY = 'omi_dev_...'   # never commit real keys
#   omi auth status
#
# Auth is documented separately on purpose: this script contains no credentials
# and performs no login or mutation merely by being run.

# ---------------------------------------------------------------------------
# Memories (read-only)
# ---------------------------------------------------------------------------

# The 10 most recent memories, as JSON objects:
# (--json is a root-level option: it goes BEFORE the verb.)
$memories = Invoke-OmiJson @('--json', 'memory', 'list', '--limit', '10')
if ($memories) {
    $memories | Select-Object id, category, content | Format-Table -AutoSize
}

# Just the first memory's content:
if ($memories -and @($memories).Count -gt 0) {
    $first = @($memories)[0]
    "First memory: $($first.content)"
}

# ---------------------------------------------------------------------------
# Conversations (read-only)
# ---------------------------------------------------------------------------

# Count conversations since a given date (native JSON, no jq):
$conversations = Invoke-OmiJson @(
    '--json', 'conversation', 'list',
    '--start-date', '2026-04-01T00:00:00Z',
    '--limit', '50'
)
"Conversation count: $(@($conversations).Count)"

# Titles of the 5 most recent conversations:
# (structured may be absent for some conversations — guard before reading title.)
$conversations |
    Select-Object -First 5 |
    ForEach-Object { if ($_.structured) { $_.structured.title } }

# ---------------------------------------------------------------------------
# Action items (read-only)
# ---------------------------------------------------------------------------

# All open action items, newest first:
$openItems = Invoke-OmiJson @('--json', 'action-item', 'list', '--open')
$openItems |
    Sort-Object -Property created_at -Descending |
    Select-Object -First 5 id, description, due_at |
    Format-Table -AutoSize

# ---------------------------------------------------------------------------
# Goals (read-only)
# ---------------------------------------------------------------------------

# Active goals with progress:
$goals = Invoke-OmiJson @('--json', 'goal', 'list')
$goals | Select-Object id, title, current_value, target_value, unit |
    Format-Table -AutoSize

# Progress history for one goal (last 7 days):
#   Replace <goal-id> with an id from the listing above.
# $history = Invoke-OmiJson @('goal', 'history', '<goal-id>', '--days', '7')
# $history | Select-Object date, value | Format-Table -AutoSize

# ---------------------------------------------------------------------------
# Error handling (what a failure looks like)
# ---------------------------------------------------------------------------

# Invoke-OmiJson throws on a nonzero exit or on non-JSON stdout, so a bad flag
# or an auth problem stops the script with the CLI's own message attached:
try {
    Invoke-OmiJson @('--json', 'memory', 'list', '--limit', '0') | Out-Null
} catch {
    Write-Host "Caught expected-style failure: $($_.Exception.Message)"
}
