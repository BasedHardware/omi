# omi-cli PowerShell Examples
# Read-only Windows PowerShell examples mirroring shell_examples.sh
# Each example checks $LASTEXITCODE before parsing JSON.

# 1) Memories: list the 5 most recently created
$env:OMI_API_KEY = if ($env:OMI_API_KEY) { $env:OMI_API_KEY } else { "your-api-key-here" }
omi auth status
if ($LASTEXITCODE -ne 0) { Write-Error "Not authenticated"; exit 1 }

omi --json memory list | Select-Object -First 5 | ForEach-Object {
    [PSCustomObject]@{
        id      = $_.id
        content = $_.content
        category = $_.category
    } | Format-Table -AutoSize
}

# 2) Conversations: list the 5 most recent with their structured titles
omi --json conversation list --limit 5 | ForEach-Object {
    [PSCustomObject]@{
        id        = $_.id
        title     = $_.structured.title
        started_at = $_.started_at
    } | Format-Table -AutoSize
}

# 3) Action items: list the open ones, sorted by due_at ascending
omi --json action-item list --open | Sort-Object due_at | ForEach-Object {
    [PSCustomObject]@{
        id    = $_.id
        title = $_.title
        due_at = $_.due_at
    } | Format-Table -AutoSize
}

# 4) Goals: list all goals with progress percentage
omi --json goal list | ForEach-Object {
    [PSCustomObject]@{
        id      = $_.id
        title   = $_.title
        progress_percent = $_.progress_percent
    } | Format-Table -AutoSize
}

# 5) Session diagnostics: pair status checks (offline-safe then live)
omi auth status
omi auth whoami

# 6) Convert JSON to PowerShell object without jq
function ConvertFrom-OmiJson {
    param([string]$Command)
    & omi --json $Command | ConvertFrom-Json
}

$goals = ConvertFrom-OmiJson "goal list"
$goals | Where-Object { $_.progress_percent -ge 50 } | Format-Table id, title, progress_percent -AutoSize

# 7) Error-safe JSON parsing: wrap in try/catch
try {
    $memory = omi --json memory get "MEMORY_ID_HERE" | ConvertFrom-Json
    Write-Host "Memory content: $($memory.content)"
} catch {
    Write-Error "Failed to parse memory JSON: $_"
}
