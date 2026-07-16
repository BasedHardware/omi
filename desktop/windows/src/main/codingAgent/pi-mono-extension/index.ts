// Omi Provider Extension for pi-mono (Windows port of
// desktop/macos/pi-mono-extension/index.ts).
//
// Responsibilities:
//   1. Register "omi" as an LLM provider using the OpenAI-compatible
//      completions API. All inference routes through the Omi backend for
//      server-side cost tracking, model selection, and billing.
//   2. Install a "tool_call" handler that denies a small set of clearly
//      dangerous operations before pi runs its built-in tools, so tool
//      execution is seamless for normal work but cannot brick the user's
//      machine on a single hallucinated command.
//   3. Install a "tool_result" handler that appends every tool invocation to a
//      per-user audit log (~/.omi/pi-mono-audit.log).
//   4. Register Omi product/control tools that relay to the host over
//      OMI_BRIDGE_PIPE (a Windows named pipe on win32).
//
// WINDOWS DENYLIST REWRITE (security-critical): pi's built-in `bash` tool runs
// on win32 through Git Bash (`bash.exe -c "<command>"`, verified in
// @earendil-works/pi-coding-agent dist/utils/shell.js) — NOT cmd.exe/PowerShell.
// So command SYNTAX is bash, but dangerous TARGETS are Windows paths, and the
// model can invoke powershell/cmd from bash. macOS's POSIX path/shell regexes
// (`/System`, `/etc`, `launchctl`, `sudo`) match nothing here (path.resolve →
// `C:\...`) = silent allow-everything. This file ships a Windows-specific rule
// set (drive roots, C:\Windows, Program Files, %USERPROFILE% credential files;
// Remove-Item/-Recurse/del/rmdir, format/diskpart, iwr|iex pipe-to-shell,
// takeown/icacls of system paths, shutdown/restart, plus cross-platform
// destructive git). pi's write/edit tools take a `path` param; classifyFileWrite
// resolves it to a Windows absolute path first.
//
// WINDOWS RELAY HANDSHAKE (one addition vs macOS): on connect the client sends
// `{type:'hello',token}` (token from OMI_BRIDGE_TOKEN) and awaits
// `{type:'hello_ok'}` before writing any tool_use frame, matching the Windows
// host relay server (toolRelayBridge). The host is authoritative — it resolves
// identity from the registered token binding, never from wire-claimed ids.
//
// The classifier functions are exported so they can be unit-tested. Pi's
// extension loader calls the default export with an ExtensionAPI instance.

import {
  defineTool,
  type ExtensionAPI,
  type ToolCallEvent,
  type ToolCallEventResult,
  type ToolResultEvent
} from '@earendil-works/pi-coding-agent'
import { Type } from '@earendil-works/pi-ai'
import { appendFile, mkdir, readFile, writeFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { createConnection, type Socket } from 'node:net'
import { dirname, join, resolve } from 'node:path'
import { isSafeSkillName, loadSkillInstructions } from './node-tools'
import {
  buildToolAvailabilitySnapshot,
  toolsForAdapter,
  type OmiToolInputSchema,
  type OmiToolManifestEntry
} from '../../agentKernel/omiToolManifest'

// ---------------------------------------------------------------------------
// Denylist patterns (WINDOWS)
// ---------------------------------------------------------------------------
//
// THREAT-MODEL CEILING (read before extending these rules): this denylist is a
// best-effort guard against ACCIDENTAL / HALLUCINATED destructive commands — it
// is NOT a hard security boundary against an adversarial model. It classifies
// the command/path TEXT statically, before bash runs; bash expands variables and
// splits quotes at exec time, AFTER the classifier has seen the text. So forms
// that only resolve to a dangerous target at runtime CANNOT be closed by any
// regex here, e.g. arbitrary variable indirection (`d=/c/Windows; rm -rf "$d"`)
// or internal-quote splitting (`rm -rf C:/Win""dows/System32`). We deliberately
// do NOT chase these — the real boundary is process sandboxing / least privilege
// (pi runs non-elevated with no write access outside the workspace). What we DO
// close: the common literal spellings a model reaches for in a single command
// (drive roots, C:\Windows / Program Files, credential files, the idiomatic
// $env:/%VAR%/$WINDIR env-var names, 8.3 short names, device-namespace paths).

/** A single deny rule. `pattern` MUST match something clearly dangerous;
 *  `reason` is shown to the LLM so it can pick a safer alternative. */
export interface DenyRule {
  pattern: RegExp
  reason: string
}

/** Lookahead for "end of this shell argument" (bash — Git Bash on win32). */
const TARGET_END = `(?=\\s|$|[;&|'"])`

/** Optional leading shell-quote absorber before a DANGEROUS_TARGET. Handles
 *  bare, `"`, `'`, ANSI-C (`$'...'`) and locale (`$"..."`) quoting so
 *  `rm "C:\\Windows"`, `rm 'C:\\Windows'`, `rm $'C:\\Windows'` all match. */
const TARGET_QUOTE = `(?:\\$['"]|['"])?`

/** Windows system directory names (case-insensitive matching applied by the
 *  rules that embed this). */
const WIN_SYS_DIR = `(?:Windows|Program Files(?: \\(x86\\))?|ProgramData)`

/** A shell argument that names a Windows drive root, a system-owned tree, or
 *  the whole user home. Used by rm / Remove-Item / del / takeown / icacls
 *  rules. Written to match Git-Bash-visible forms: MSYS (`/c/Windows`, bare
 *  `/`), native (`C:\\Windows`, `C:/Windows`, `C:\\`), and home (`~`, `$HOME`,
 *  `$USERPROFILE`). Deliberately does NOT match project subpaths like
 *  `C:\\Users\\me\\proj\\build` or `/c/Users/me/build`. */
const DANGEROUS_TARGET =
  `(?:` +
  // MSYS root "/" and "/*"
  `\\/${TARGET_END}` +
  `|\\/\\*` +
  // bare MSYS drive root "/c" (but NOT "/c/Users/..." — TARGET_END stops it)
  `|\\/[a-zA-Z]${TARGET_END}` +
  // MSYS system path "/c/Windows", "/c/Program Files/..."
  `|\\/[a-zA-Z]\\/${WIN_SYS_DIR}(?:\\/[^\\s;&|'"]*)?${TARGET_END}` +
  // native drive root "C:", "C:\\", "C:/"
  `|[a-zA-Z]:[\\\\/]?${TARGET_END}` +
  // native system path "C:\\Windows", "C:/Program Files/..."
  `|[a-zA-Z]:[\\\\/]${WIN_SYS_DIR}(?:[\\\\/][^\\s;&|'"]*)?${TARGET_END}` +
  // DOS 8.3 short names under a drive root — resolve() does NOT expand these,
  // so `C:\\PROGRA~1` reaches Program Files unblocked. PROGRA~n covers Program
  // Files / Program Files (x86) / ProgramData; WINDOW~n is defensive (Windows
  // itself is <=8 chars and has no short form). Native + git-bash mount forms.
  `|[a-zA-Z]:[\\\\/](?:PROGRA~\\d|WINDOW~\\d)(?:[\\\\/][^\\s;&|'"]*)?${TARGET_END}` +
  `|\\/[a-zA-Z]\\/(?:PROGRA~\\d|WINDOW~\\d)(?:\\/[^\\s;&|'"]*)?${TARGET_END}` +
  // parent-traversal root escape "../.." or "..\\.." (restored from macOS —
  // classifyBash cannot resolve `..`, so this literal guard is the only defense
  // against `rm -rf ../../../../`).
  `|\\.\\.[\\\\/]\\.\\.` +
  // cmd env-var system dirs (any subpath) and the whole home (bare only)
  `|%(?:windir|systemroot|programfiles(?:\\(x86\\))?|programdata)%` +
  `|%userprofile%[\\\\/]?${TARGET_END}` +
  // PowerShell env-var system dirs (any subpath) and the whole home (bare only).
  // Single-quoted in bash so bash does not expand them; PowerShell expands them
  // at run time — the idiomatic way PowerShell names these paths.
  `|\\$env:(?:windir|systemroot|programfiles(?:\\(x86\\))?|programdata|allusersprofile)\\b` +
  `|\\$env:(?:userprofile|homepath|homedrive)[\\\\/]?${TARGET_END}` +
  // bash-inherited Windows env vars — Git Bash exposes $WINDIR, $SYSTEMROOT
  // (both = C:\\Windows) and $SystemDrive (= C:). `rm -rf "$WINDIR"` and
  // `rm -rf "$SYSTEMROOT/System32"` are idiomatic and were reachable. System
  // dirs match on any subpath (\\b); $SystemDrive is the drive root, blocked on
  // any reference too so `"$SystemDrive/Windows"` is also caught. Brace forms
  // included. NOTE: bash expands these BEFORE the classifier sees the text only
  // when written literally — see the best-effort ceiling note at the head.
  `|\\$(?:WINDIR|SYSTEMROOT|SystemDrive)\\b` +
  `|\\$\\{(?:WINDIR|SYSTEMROOT|SystemDrive)\\}` +
  // home: "~", "~/", "~\\"
  `|~[\\\\/]?${TARGET_END}` +
  // "$HOME", "${HOME}", "$USERPROFILE", "${USERPROFILE}"
  `|\\$HOME[\\\\/]?${TARGET_END}` +
  `|\\$\\{HOME\\}[\\\\/]?${TARGET_END}` +
  `|\\$USERPROFILE[\\\\/]?${TARGET_END}` +
  `|\\$\\{USERPROFILE\\}[\\\\/]?${TARGET_END}` +
  `)`

/** Windows system path as a redirect target (`> C:\\Windows\\...`). */
const WIN_SYS_REDIRECT_TARGET =
  `(?:` + `\\/[a-zA-Z]\\/${WIN_SYS_DIR}` + `|[a-zA-Z]:[\\\\/]${WIN_SYS_DIR}` + `)`

/** Bash command denylist (Git Bash on win32). Allow-by-default: only block on
 *  an explicit match. */
export const BASH_DENY_RULES: DenyRule[] = [
  {
    // Privilege escalation: runas / gsudo / sudo / doas / pkexec at the start
    // of the line, after a newline, or after a shell operator / subshell head.
    pattern: /(?:^|[\n;&|`(]|\$\()\s*(?:runas|gsudo|sudo|doas|pkexec)\b/i,
    reason:
      'Privilege escalation (runas/gsudo/sudo) is blocked by the Omi pi-mono ' +
      'denylist. Perform the operation as your current user or ask the user to ' +
      'run the command manually with elevation.'
  },
  {
    // PowerShell elevation: Start-Process ... -Verb RunAs.
    pattern: /-Verb\s+['"]?runas\b/i,
    reason:
      'Launching an elevated process (-Verb RunAs) is blocked. Run the ' +
      'operation without elevation or ask the user to elevate manually.'
  },
  {
    // `rm` targeting a drive root, system tree, or the whole home — ANY flag
    // combination. A single-file `rm C:\Windows\System32\x` is as destructive
    // as `rm -rf C:\Windows`, so the rule blocks on target, not flags.
    pattern: new RegExp(`\\brm\\b[^\\n]*?\\s${TARGET_QUOTE}${DANGEROUS_TARGET}`, 'i'),
    reason:
      'Deleting a drive root, C:\\Windows / Program Files, or the whole user ' +
      'home with `rm` is blocked. Delete a specific subdirectory under the ' +
      'working tree instead.'
  },
  {
    // PowerShell / cmd delete-or-move of a dangerous target: Remove-Item, rd,
    // rmdir, del, erase, plus Move-Item / move / mv (moving a system tree away
    // bricks it just like deleting it) — targeting a system path or the whole
    // home. Catches `Remove-Item -Recurse -Force C:\Windows`. The bare `ri`
    // alias is deliberately omitted: `\bri\b` collides with common flags like
    // grep's `-ri`, and Remove-Item is the realistic form.
    pattern: new RegExp(
      `\\b(?:Remove-Item|rmdir|rd|del|erase|Move-Item|move|mv)\\b[^\\n]*?${TARGET_QUOTE}${DANGEROUS_TARGET}`,
      'i'
    ),
    reason:
      'Deleting or moving a drive root, C:\\Windows / Program Files, or the ' +
      'whole user home (Remove-Item/del/rmdir/Move-Item/mv) is blocked. Operate ' +
      'on a specific subdirectory under the working tree instead.'
  },
  {
    // Destructive delete with command/process substitution — the target is not
    // statically verifiable, so block outright for rm/Remove-Item/del/rmdir.
    pattern: /\b(?:rm|Remove-Item|del|rmdir|rd)\b[^\n]*?(?:\$\(|`|<\()/i,
    reason:
      'Command or process substitution ($(...), `...`, <(...)) with a delete ' +
      'command is blocked — the classifier cannot statically verify the target ' +
      'is safe. Resolve the substitution yourself and pass a literal path.'
  },
  {
    // Low-level disk destruction: format C:, diskpart, Format-Volume,
    // Clear-Disk, Initialize-Disk, dd to a physical drive.
    pattern:
      /\bformat\s+(?:\/[A-Za-z:]+\s+)*[A-Za-z]:|\bdiskpart\b|\b(?:Format-Volume|Clear-Disk|Initialize-Disk)\b|\bdd\s+[^\n]*\bof=(?:\\\\\.\\|\/dev\/)/i,
    reason:
      'Low-level disk destruction (format, diskpart, Format-Volume, Clear-Disk, ' +
      'dd to a physical drive) is blocked.'
  },
  {
    // System recovery / registry destruction (ransomware-style bricking):
    // vssadmin delete shadows, wbadmin delete, bcdedit /set|/delete, and
    // `reg delete` / Remove-Item of a HKLM/HKU system hive.
    pattern:
      /\bvssadmin\s+delete\s+shadows\b|\bwbadmin\s+delete\b|\bbcdedit\b[^\n]*\/(?:set|delete)|\breg\s+delete\s+[^\n]*\bHK(?:LM|EY_LOCAL_MACHINE|U|EY_USERS)\b|\bRemove-Item\b[^\n]*\bHK(?:LM|CU|U):/i,
    reason:
      'Destroying system recovery state or system registry hives (vssadmin ' +
      'delete shadows, bcdedit, wbadmin delete, reg delete HKLM) is blocked.'
  },
  {
    // Shell redirect into a Windows system path: `> C:\Windows\...`,
    // `>> /c/Windows/...`.
    pattern: new RegExp(`>>?\\s*${TARGET_QUOTE}${WIN_SYS_REDIRECT_TARGET}`, 'i'),
    reason:
      'Redirecting shell output into a Windows system path (C:\\Windows, ' +
      'Program Files) is blocked. Use the write tool with a path under the ' +
      'project or the user home instead.'
  },
  {
    // Redirect target uses command/process substitution — unverifiable.
    pattern: />>?\s*['"]?(?:\$\(|`|<\()/,
    reason:
      'Redirect target uses command or process substitution — the classifier ' +
      'cannot statically verify the destination is safe. Use a literal path ' +
      'under the project or the user home.'
  },
  {
    // Shell redirect into SSH keys or cloud credential files (bash-only attacks
    // the write/edit denylist does not see, e.g. `echo ... > ~/.ssh/id_rsa`).
    pattern:
      />>?\s*(?:[^\s|;&<>()`]*[\\/])?(?:\.ssh[\\/](?:authorized_keys|id_[^\s/\\;&|'"`]+)|\.aws[\\/]credentials|gcloud[\\/]application_default_credentials\.json|\.kube[\\/]config)\b/i,
    reason:
      'Redirecting shell output into SSH keys (authorized_keys, id_*) or cloud ' +
      'credential files (.aws\\credentials, gcloud ADC, .kube\\config) is blocked.'
  },
  {
    // Shutdown / restart the host.
    pattern: /\b(?:shutdown|reboot|halt|poweroff|Restart-Computer|Stop-Computer)\b/i,
    reason:
      'Shutting down or restarting the host is blocked. Ask the user to restart ' +
      'manually if that is really what they want.'
  },
  {
    // Destructive git — force push (any positional args before the flag) or a
    // hard reset to a remote ref. Cross-platform; identical to macOS.
    pattern:
      /\bgit\s+push\b[^\n]*?\s(?:-f\b|--force\b|--force-with-lease\b)|\bgit\s+reset\s+--hard\s+(?:origin\/|upstream\/|remotes\/)/,
    reason:
      'Destructive git operation (force-push, hard reset to remote) is blocked. ' +
      'Create a new commit on a feature branch instead.'
  },
  {
    // Download piped straight into a shell/interpreter: `curl ... | bash`,
    // `iwr ... | iex`, `curl ... | powershell`. Still allows writing the
    // script to a file for review first.
    pattern:
      /\b(?:curl|wget|iwr|irm|Invoke-WebRequest|Invoke-RestMethod)\b[^\n|]*\|\s*(?:[^\s|;&<>]*[\\/])?(?:bash|sh|zsh|dash|iex|Invoke-Expression|powershell|pwsh|cmd)\b/i,
    reason:
      'Piping a downloaded script straight into a shell/interpreter is blocked. ' +
      'Download the script to a file, review it, then run it.'
  },
  {
    // Invoke-Expression consuming a web download without an explicit pipe:
    // `iex (iwr ...)`, `iex (New-Object Net.WebClient).DownloadString(...)`.
    pattern:
      /\b(?:iex|Invoke-Expression)\b\s*\(?\s*(?:iwr|irm|Invoke-WebRequest|Invoke-RestMethod|New-Object\s+Net\.WebClient)/i,
    reason:
      'Executing a downloaded string via Invoke-Expression is blocked. Download ' +
      'the script to a file, review it, then run it.'
  },
  {
    // Base64-encoded PowerShell command: `powershell -enc <b64>`,
    // `pwsh -EncodedCommand ...`. The payload is opaque to any content-based
    // classifier, so an encoded command is inherently unverifiable — block it
    // outright (same philosophy as blocking command substitution).
    pattern: /\b(?:powershell|powershell\.exe|pwsh)\b[^\n]*?\s-(?:e|en|enc|encodedcommand|ec)\b/i,
    reason:
      'Running a base64-encoded PowerShell command (-EncodedCommand) is blocked — ' +
      'its payload cannot be inspected. Pass the command as readable text instead.'
  },
  {
    // takeown / icacls of a drive root or system tree.
    pattern: new RegExp(`\\b(?:takeown|icacls)\\b[^\\n]*?${TARGET_QUOTE}${DANGEROUS_TARGET}`, 'i'),
    reason:
      'Taking ownership or changing ACLs of a drive root or Windows system path ' +
      '(takeown/icacls) is blocked. Apply permissions to specific files under ' +
      'the project tree.'
  }
]

/** Write/edit path denylist (WINDOWS). Absolute paths under drive roots or
 *  OS-owned trees and well-known credential files are blocked. Matched against
 *  the resolved, backslash-normalized absolute path, case-insensitively. */
export const WRITE_PATH_DENY_RULES: DenyRule[] = [
  {
    // A file written directly at a drive root (`C:\bootmgr`-style).
    pattern: /^[A-Za-z]:\\[^\\]*$/i,
    reason:
      'Writing directly at a drive root (C:\\) is blocked. Use a path under the project or user home.'
  },
  {
    pattern: /^[A-Za-z]:\\Windows\\/i,
    reason: 'Writing under C:\\Windows is blocked (system tree, incl. System32).'
  },
  {
    pattern: /^[A-Za-z]:\\Program Files(?: \(x86\))?\\/i,
    reason: 'Writing under Program Files is blocked (installed system binaries).'
  },
  {
    // DOS 8.3 short name for a system dir under a drive root (PROGRA~1 = Program
    // Files, PROGRA~2 = Program Files (x86)/ProgramData). resolve() does not
    // expand these, so without this rule `C:\PROGRA~1\evil.dll` plants a DLL in
    // Program Files. WINDOW~n is defensive.
    pattern: /^[A-Za-z]:\\(?:PROGRA~\d|WINDOW~\d)(?:\\|$)/i,
    reason:
      'Writing under a DOS 8.3 short name of a system dir (PROGRA~1 = Program ' +
      'Files) is blocked.'
  },
  {
    pattern: /[\\/]\.ssh[\\/](?:authorized_keys|id_[^\\/]+)$/i,
    reason:
      'Writing SSH private keys or authorized_keys is blocked. Ask the user to ' +
      'manage their SSH credentials manually.'
  },
  {
    pattern:
      /[\\/]\.aws[\\/]credentials$|[\\/]gcloud[\\/]application_default_credentials\.json$|[\\/]\.kube[\\/]config$/i,
    reason: 'Writing cloud credential files (AWS, gcloud, kubeconfig) is blocked.'
  }
]

// ---------------------------------------------------------------------------
// Classifier functions (pure, exported for unit tests)
// ---------------------------------------------------------------------------

export interface DenyDecision {
  blocked: true
  reason: string
}

/** Collapse bash line continuations so a split command classifies the same as
 *  its single-line form. Line continuations have no semantic meaning in bash,
 *  so this cannot produce a false positive. */
function normalizeBashCommand(command: string): string {
  return command.replace(/\\\n/g, ' ')
}

/** Classify a bash command (Git Bash on win32). Returns null when allowed. */
export function classifyBash(command: string): DenyDecision | null {
  if (typeof command !== 'string' || command.length === 0) return null
  const normalized = normalizeBashCommand(command)
  for (const rule of BASH_DENY_RULES) {
    if (rule.pattern.test(normalized)) {
      return { blocked: true, reason: rule.reason }
    }
  }
  return null
}

/** Classify a write/edit target path. Returns null when allowed. Resolves to a
 *  Windows absolute path (backslash-normalized) before matching so that
 *  `..\..\..\Windows\System32\x` is caught the same as `C:\Windows\System32\x`. */
export function classifyFileWrite(filePath: string): DenyDecision | null {
  if (typeof filePath !== 'string' || filePath.length === 0) return null
  // Resolve to absolute to prevent ..\..\..\Windows traversal bypass, then
  // normalize any forward slashes to backslashes so the rules match regardless
  // of the separator the model used (`C:/Windows` vs `C:\Windows`).
  const normalized = resolve(filePath).replace(/\//g, '\\')
  // Strip a Windows extended-length / device-namespace prefix — both the
  // `\\?\` extended-length form AND the sibling Win32 device form `\\.\`
  // (`\\?\C:\...`, `\\.\C:\...`, `\\?\UNC\server\share`). Both are honored by
  // pi's fs-based write/edit tool and both keep the drive letter behind the
  // prefix, so without stripping them `\\.\C:\Windows\System32\x` slips past the
  // drive-letter-anchored rules and lands the bytes at the plain path.
  const resolved = normalized.replace(/^\\\\[.?]\\(UNC\\)?/i, (_m, unc) => (unc ? '\\\\' : ''))
  for (const rule of WRITE_PATH_DENY_RULES) {
    if (rule.pattern.test(resolved)) {
      return { blocked: true, reason: rule.reason }
    }
  }
  return null
}

/** Tools whose calls this denylist actually enforces (dispatched in
 *  inspectToolCall). A classifier THROW for one of these must fail CLOSED —
 *  never silently permit a dangerous command — so the tool_call handler blocks
 *  these on error. Any other tool (read/grep/ls/…) is pass-through anyway. */
export const ENFORCED_TOOL_NAMES: ReadonlySet<string> = new Set([
  'bash',
  'write',
  'edit',
  'edit-diff'
])

/** Classify a whole tool_call event by dispatching on toolName.
 *  When OMI_YOLO_MODE=1, all tool calls are allowed (no denylist).
 *  Yolo mode is gated by the adapter — only forwarded from dev builds. */
export function inspectToolCall(event: ToolCallEvent): DenyDecision | null {
  if (process.env.OMI_YOLO_MODE === '1') {
    process.stderr.write(`[omi-provider] YOLO bypass: ${event.toolName}\n`)
    return null
  }
  switch (event.toolName) {
    case 'bash': {
      const command = (event.input as { command?: unknown })?.command
      return typeof command === 'string' ? classifyBash(command) : null
    }
    case 'write':
    case 'edit':
    case 'edit-diff': {
      const path = (event.input as { path?: unknown })?.path
      return typeof path === 'string' ? classifyFileWrite(path) : null
    }
    default:
      // read, grep, find, ls, and custom tools pass through unchanged.
      return null
  }
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export interface AuditEntry {
  ts: string
  phase: 'before' | 'after'
  tool: string
  decision: 'allow' | 'deny' | 'ok' | 'error'
  reason?: string
  summary: string
}

/** One-line redacted summary of a tool-call input for the audit log. */
export function summarizeInput(event: ToolCallEvent): string {
  const { toolName, input } = event
  try {
    switch (toolName) {
      case 'bash': {
        const cmd = (input as { command?: string })?.command ?? ''
        return truncate(cmd, 200)
      }
      case 'write':
      case 'edit':
      case 'edit-diff':
        return (input as { path?: string })?.path ?? ''
      case 'read':
        return (input as { path?: string })?.path ?? ''
      case 'grep':
        return truncate(
          `${(input as { pattern?: string })?.pattern ?? ''} @ ${
            (input as { path?: string })?.path ?? '.'
          }`,
          200
        )
      case 'find':
        return truncate(
          `${(input as { pattern?: string })?.pattern ?? ''} @ ${
            (input as { path?: string })?.path ?? '.'
          }`,
          200
        )
      case 'ls':
        return (input as { path?: string })?.path ?? ''
      default:
        return truncate(JSON.stringify(input ?? {}), 200)
    }
  } catch {
    return `<unserializable ${toolName} input>`
  }
}

function truncate(s: string, max: number): string {
  if (s.length <= max) return s
  return s.slice(0, max - 1) + '…'
}

/** Resolve the audit log path. Overridable via OMI_PI_AUDIT_LOG for tests. */
function auditLogPath(): string {
  return (
    process.env.OMI_PI_AUDIT_LOG || join(process.env.HOME || homedir(), '.omi', 'pi-mono-audit.log')
  )
}

let auditWarned = false

/** Test-only: reset the `auditWarned` one-shot so tests can assert the stderr
 *  warning fires exactly once per process. */
export function __resetAuditWarnedForTest(): void {
  auditWarned = false
}

/** Append a single JSONL line to the audit log. Never throws; on failure, logs
 *  to stderr once per process so we don't flood on disk-full. */
export async function appendAudit(entry: AuditEntry): Promise<void> {
  const path = auditLogPath()
  const line = JSON.stringify(entry) + '\n'
  try {
    await mkdir(dirname(path), { recursive: true })
    await appendFile(path, line, 'utf-8')
  } catch (err) {
    if (!auditWarned) {
      auditWarned = true
      const msg = err instanceof Error ? err.message : String(err)
      process.stderr.write(
        `[omi-provider] audit log unavailable (${msg}); continuing without audit\n`
      )
    }
  }
}

// ---------------------------------------------------------------------------
// Omi tools — forwarded to the host over OMI_BRIDGE_PIPE (a Windows named pipe)
// ---------------------------------------------------------------------------

let omiPipeConnection: Socket | null = null
let omiPipeBuffer = ''
let omiCallIdCounter = 0
const omiPendingCalls = new Map<string, { connection: Socket; resolve: (result: string) => void }>()
/** `${pipePath}\0${token}` the live socket is authenticated to, or null. Lets a
 *  per-turn target change (pool-eviction token remint) trigger a socket
 *  reconnect — never a subprocess restart. */
let omiConnectedKey: string | null = null
/** An in-flight connect, so concurrent tool calls share one handshake. */
let omiConnecting: { key: string; promise: Promise<void> } | null = null

/** Handshake timeout — if the host does not answer hello with hello_ok within
 *  this window, the connect promise rejects (tools then go unregistered). */
export const OMI_BRIDGE_HANDSHAKE_TIMEOUT_MS = 10_000

/**
 * Connect to the host relay pipe and perform the Windows hello/hello_ok
 * handshake before resolving. The client sends `{type:'hello',token}` (token
 * from OMI_BRIDGE_TOKEN) on connect and the returned promise resolves only
 * after the host replies `{type:'hello_ok'}`. This is the ONE addition vs the
 * macOS client — the macOS pipe was un-authed. The host is authoritative: it
 * validates the token→binding and never trusts wire-claimed identity.
 */
function connectOmiPipe(pipePath: string, token: string): Promise<void> {
  return new Promise((resolvePromise, reject) => {
    let handshakeDone = false
    const connection = createConnection(pipePath, () => {
      process.stderr.write(`[omi-tools] Connected to bridge pipe\n`)
      connection.write(JSON.stringify({ type: 'hello', token }) + '\n')
    })
    omiPipeConnection = connection

    const handshakeTimer = setTimeout(() => {
      if (!handshakeDone) {
        handshakeDone = true
        reject(new Error('Omi bridge handshake timed out'))
        connection.destroy()
      }
    }, OMI_BRIDGE_HANDSHAKE_TIMEOUT_MS)

    connection.on('data', (data: Buffer) => {
      omiPipeBuffer += data.toString()
      let idx
      while ((idx = omiPipeBuffer.indexOf('\n')) >= 0) {
        const line = omiPipeBuffer.slice(0, idx)
        omiPipeBuffer = omiPipeBuffer.slice(idx + 1)
        if (line.trim()) {
          try {
            const msg = JSON.parse(line)
            if (!handshakeDone && msg.type === 'hello_ok') {
              handshakeDone = true
              clearTimeout(handshakeTimer)
              resolvePromise()
              continue
            }
            if (msg.type === 'tool_result' && msg.callId) {
              const pending = omiPendingCalls.get(msg.callId)
              if (pending) {
                pending.resolve(msg.result)
                omiPendingCalls.delete(msg.callId)
              }
            }
          } catch {
            /* ignore malformed messages */
          }
        }
      }
    })
    connection.on('error', (err) => {
      process.stderr.write(`[omi-tools] Pipe error: ${err.message}\n`)
      if (!handshakeDone) {
        handshakeDone = true
        clearTimeout(handshakeTimer)
        reject(err)
      }
    })
    // Handle pipe close — resolve all pending tool calls with an error so they
    // don't hang forever if the bridge disconnects mid-call. A close before the
    // handshake completes rejects the connect promise (e.g. host rejected the
    // token).
    connection.on('close', () => {
      process.stderr.write('[omi-tools] Pipe disconnected\n')
      if (!handshakeDone) {
        handshakeDone = true
        clearTimeout(handshakeTimer)
        reject(new Error('Omi bridge closed before handshake'))
      }
      if (omiPipeConnection === connection) {
        omiPipeConnection = null
        omiConnectedKey = null
        for (const [callId, pending] of omiPendingCalls) {
          if (pending.connection === connection) {
            pending.resolve('Error: Omi bridge disconnected')
            omiPendingCalls.delete(callId)
          }
        }
      }
    })
  })
}

/**
 * Resolve this turn's host bridge target (pipe + token) and ensure a live,
 * authenticated socket to it. Idempotent: reuses the current socket when it is
 * already authenticated to the same pipe+token; when the token changes (a
 * pool-eviction remint) it drops the stale socket and reconnects — a socket
 * reconnect, NEVER a subprocess restart. Concurrent callers share one handshake.
 */
async function ensureOmiConnection(pipePath: string, token: string): Promise<void> {
  const key = `${pipePath}\0${token}`
  if (omiConnectedKey === key && omiPipeConnection) return
  if (omiConnecting && omiConnecting.key === key) return omiConnecting.promise
  // A different key (first connect, or a token/path change): drop any stale socket
  // and its in-flight connect before reconnecting.
  if (omiPipeConnection) {
    const stale = omiPipeConnection
    omiPipeConnection = null
    omiConnectedKey = null
    stale.destroy()
  }
  omiConnecting = null
  const promise = connectOmiPipe(pipePath, token)
    .then(() => {
      omiConnectedKey = key
    })
    .finally(() => {
      if (omiConnecting?.key === key) omiConnecting = null
    })
  omiConnecting = { key, promise }
  return promise
}

/**
 * The host tool-relay target for THIS turn: `{ pipePath, token }`. Read fresh from
 * the per-turn context file (OMI_CONTEXT_FILE) written by the host adapter — so it
 * tracks resume + pool-eviction remint with no subprocess restart. Falls back to
 * spawn env (OMI_BRIDGE_PIPE/OMI_BRIDGE_TOKEN) only if BOTH are present, for
 * compatibility with an env-injection host. Returns null when no target is
 * available (tools then degrade gracefully per call).
 */
async function omiBridgeTarget(): Promise<{ pipePath: string; token: string } | null> {
  const path = process.env.OMI_CONTEXT_FILE
  if (path) {
    try {
      const parsed = JSON.parse(await readFile(path, 'utf8')) as Record<string, unknown>
      const pipePath = typeof parsed.bridgePipe === 'string' ? parsed.bridgePipe : ''
      const token = typeof parsed.bridgeToken === 'string' ? parsed.bridgeToken : ''
      if (pipePath && token) return { pipePath, token }
    } catch {
      // Unreadable/partial context file → no target from this source.
    }
  }
  const envPipe = process.env.OMI_BRIDGE_PIPE
  const envToken = process.env.OMI_BRIDGE_TOKEN
  if (envPipe && envToken) return { pipePath: envPipe, token: envToken }
  return null
}

async function callSwiftTool(
  name: string,
  input: Record<string, unknown>,
  signal?: AbortSignal,
  timeoutMs = OMI_TOOL_TIMEOUT_MS
): Promise<string> {
  if (signal?.aborted) return Promise.resolve('Error: tool call aborted')
  const callId = `omi-ext-${++omiCallIdCounter}-${Date.now()}`
  const correlation = await omiRelayCorrelation()
  if (correlation.disableSwiftBackedTools === true) {
    return Promise.resolve(
      'Error: Swift-backed Omi tools are disabled for this control-created run'
    )
  }
  if (signal?.aborted) return Promise.resolve('Error: tool call aborted')

  // Lazy connect: resolve this turn's host bridge target and (re)connect on demand.
  // When no target is present but a socket is already live (e.g. an env-injection
  // host, or a pre-connected test), reuse it. When neither exists, degrade.
  const target = await omiBridgeTarget()
  if (signal?.aborted) return Promise.resolve('Error: tool call aborted')
  if (target) {
    try {
      await ensureOmiConnection(target.pipePath, target.token)
    } catch (err) {
      return `Error: could not connect to Omi bridge: ${
        err instanceof Error ? err.message : String(err)
      }`
    }
    if (signal?.aborted) return Promise.resolve('Error: tool call aborted')
  }

  const connection: Socket | null = omiPipeConnection
  if (!connection) return Promise.resolve('Error: not connected to Omi bridge')
  return new Promise<string>((resolvePromise) => {
    const timer = setTimeout(() => {
      omiPendingCalls.delete(callId)
      resolvePromise(`Error: tool '${name}' timed out after ${timeoutMs / 1000}s`)
    }, timeoutMs)
    const cleanup = (): void => {
      clearTimeout(timer)
      omiPendingCalls.delete(callId)
      resolvePromise('Error: tool call aborted')
    }
    signal?.addEventListener('abort', cleanup, { once: true })
    omiPendingCalls.set(callId, {
      connection,
      resolve: (result: string) => {
        clearTimeout(timer)
        signal?.removeEventListener('abort', cleanup)
        resolvePromise(result)
      }
    })
    connection.write(
      JSON.stringify({
        type: 'tool_use',
        callId,
        name,
        input,
        ...correlation
      }) + '\n'
    )
  })
}

async function omiRelayCorrelation(): Promise<Record<string, string | number | boolean>> {
  const correlation: Record<string, string | number | boolean> = {}
  if (process.env.OMI_ADAPTER_ID) correlation.adapterId = process.env.OMI_ADAPTER_ID
  if (process.env.OMI_REQUEST_ID) correlation.requestId = process.env.OMI_REQUEST_ID
  if (process.env.OMI_CLIENT_ID) correlation.clientId = process.env.OMI_CLIENT_ID
  if (process.env.OMI_SESSION_ID) correlation.sessionId = process.env.OMI_SESSION_ID
  if (process.env.OMI_RUN_ID) correlation.runId = process.env.OMI_RUN_ID
  if (process.env.OMI_ATTEMPT_ID) correlation.attemptId = process.env.OMI_ATTEMPT_ID
  if (process.env.OMI_ADAPTER_SESSION_ID)
    correlation.adapterSessionId = process.env.OMI_ADAPTER_SESSION_ID
  correlation.protocolVersion = 2
  Object.assign(correlation, await omiContextFileCorrelation())
  return correlation
}

async function omiContextFileCorrelation(): Promise<Record<string, string | number | boolean>> {
  const path = process.env.OMI_CONTEXT_FILE
  if (!path) return {}
  try {
    const parsed = JSON.parse(await readFile(path, 'utf8')) as Record<string, unknown>
    const correlation: Record<string, string | number | boolean> = {}
    for (const key of [
      'adapterId',
      'requestId',
      'clientId',
      'sessionId',
      'runId',
      'attemptId',
      'adapterSessionId'
    ]) {
      const value = parsed[key]
      if (typeof value === 'string' && value.length > 0) correlation[key] = value
    }
    correlation.protocolVersion = 2
    if (parsed.disableSwiftBackedTools === true) correlation.disableSwiftBackedTools = true
    return correlation
  } catch {
    return {}
  }
}

export const OMI_TOOL_TIMEOUT_MS = 30_000
export const OMI_LONG_CONTROL_TOOL_TIMEOUT_MS = 10 * 60_000

export { isSafeSkillName }

// ---------------------------------------------------------------------------
// Omi tool definitions — pi-mono defineTool() with TypeBox schemas
// ---------------------------------------------------------------------------

/** Factory: create a defineTool()-compliant Omi tool that forwards to the host. */
function omiTool<T extends Parameters<typeof Type.Object>[0]>(spec: {
  name: string
  label: string
  description: string
  promptSnippet: string
  promptGuidelines?: string[]
  properties: T
  required: (keyof T)[]
  timeoutMs?: number
}): ReturnType<typeof defineTool> {
  const parameters = Type.Object(spec.properties, { additionalProperties: false })
  const tool = defineTool({
    name: spec.name,
    label: spec.label,
    description: spec.description,
    promptSnippet: spec.promptSnippet,
    promptGuidelines: spec.promptGuidelines,
    parameters,
    async execute(_toolCallId, params, signal) {
      const result = await callSwiftTool(
        spec.name,
        params as Record<string, unknown>,
        signal,
        spec.timeoutMs
      )
      return { content: [{ type: 'text' as const, text: result }], details: undefined }
    }
  })
  Object.defineProperty(tool, '__omiTimeoutMsForTest', {
    value: spec.timeoutMs ?? OMI_TOOL_TIMEOUT_MS,
    enumerable: false
  })
  return tool
}

function typeBoxSchemaForJsonSchema(schema: Record<string, unknown>): unknown {
  const options: Record<string, unknown> = {}
  if (typeof schema.description === 'string') options.description = schema.description
  if (Array.isArray(schema.enum)) options.enum = schema.enum
  switch (schema.type) {
    case 'string':
      return Type.String(options)
    case 'number':
    case 'integer':
      return Type.Number(options)
    case 'boolean':
      return Type.Boolean(options)
    case 'array': {
      const itemSchema =
        schema.items && typeof schema.items === 'object'
          ? typeBoxSchemaForJsonSchema(schema.items as Record<string, unknown>)
          : Type.Unknown()
      return Type.Array(itemSchema as never, options)
    }
    case 'object': {
      const properties =
        typeof schema.properties === 'object' && schema.properties
          ? typeBoxPropertiesForInputSchema({
              type: 'object',
              properties: schema.properties as Record<string, unknown>,
              required: Array.isArray(schema.required) ? (schema.required as string[]) : [],
              additionalProperties: schema.additionalProperties === true
            })
          : {}
      return Type.Object(properties, {
        ...options,
        additionalProperties: schema.additionalProperties === true
      })
    }
    default:
      return Type.Unknown(options)
  }
}

function typeBoxPropertiesForInputSchema(
  tool: OmiToolInputSchema
): Parameters<typeof Type.Object>[0] {
  const required = new Set(tool.required ?? [])
  return Object.fromEntries(
    Object.entries(tool.properties).map(([name, property]) => {
      const schema = typeBoxSchemaForJsonSchema(property as Record<string, unknown>)
      return [name, required.has(name) ? schema : Type.Optional(schema as never)]
    })
  ) as Parameters<typeof Type.Object>[0]
}

function omiManifestTool(tool: OmiToolManifestEntry): ReturnType<typeof defineTool> {
  return omiTool({
    name: tool.name,
    label: tool.label,
    description: tool.description,
    promptSnippet: tool.promptSnippet,
    promptGuidelines: tool.promptGuidelines,
    properties: typeBoxPropertiesForInputSchema(tool.inputSchema),
    required: (tool.inputSchema.required ?? []) as never[],
    timeoutMs: tool.timeoutClass === 'long' ? OMI_LONG_CONTROL_TOOL_TIMEOUT_MS : OMI_TOOL_TIMEOUT_MS
  })
}

function loadSkillTool(): ReturnType<typeof defineTool> {
  return defineTool({
    name: 'load_skill',
    label: 'Load Skill',
    description: 'Load the full instructions for a named skill listed in available_skills.',
    promptSnippet: 'load_skill - Load the full SKILL.md instructions for an available skill',
    parameters: Type.Object(
      {
        name: Type.String({ description: 'Skill name exactly as listed in available_skills' })
      },
      { additionalProperties: false }
    ),
    async execute(_toolCallId, params) {
      const name = String((params as { name?: unknown }).name ?? '').trim()
      if (!isSafeSkillName(name)) {
        return {
          content: [
            {
              type: 'text' as const,
              text: 'Invalid skill name. Use the exact skill name listed in available_skills.'
            }
          ],
          details: undefined
        }
      }
      return {
        content: [{ type: 'text' as const, text: await loadSkillInstructions(name) }],
        details: undefined
      }
    }
  })
}

const executionRole = process.env.OMI_EXECUTION_ROLE === 'leaf' ? 'leaf' : 'coordinator'
const projectionContext = { executionRole } as const

/** The product ("swiftTool") tools this process may advertise, from the spawn env
 *  OMI_SERVICEABLE_PRODUCT_TOOLS (a comma list the host derives from the executor
 *  registry). Absent/empty ⇒ fail-closed to NO product tools (control + load_skill
 *  only). Read fresh so it tracks the spawn env and tests can set it per-case. */
function serviceableProductTools(): ReadonlySet<string> {
  const raw = process.env.OMI_SERVICEABLE_PRODUCT_TOOLS
  if (!raw) return new Set()
  return new Set(
    raw
      .split(',')
      .map((name) => name.trim())
      .filter(Boolean)
  )
}

export function omiToolsForExecutionRole(
  role: 'coordinator' | 'leaf'
): ReturnType<typeof defineTool>[] {
  const serviceable = serviceableProductTools()
  return toolsForAdapter('pi-mono', { executionRole: role })
    .filter((tool) =>
      // swiftTool = a product tool relayed to the host: advertise ONLY the ones
      // the host can actually service, so the model never burns turns on tools
      // that only degrade. nodeTool (load_skill, in-process) and runtimeControl
      // (control tools) always pass through.
      tool.executor.kind === 'swiftTool' ? serviceable.has(tool.name) : true
    )
    .map((tool) => (tool.executor.kind === 'nodeTool' ? loadSkillTool() : omiManifestTool(tool)))
}

export const OMI_TOOLS = omiToolsForExecutionRole(executionRole)

async function registerOmiTools(pi: ExtensionAPI): Promise<void> {
  // Advertisement is INDEPENDENT of the host bridge: register the role- and
  // serviceable-filtered tools unconditionally so the model always sees the
  // serviceable toolset. The socket connection is LAZY — established on the first
  // tool call from that turn's context-file target (bridgePipe/bridgeToken) and
  // reconnected on a token remint. A tool call with no host target for the turn
  // degrades gracefully (see callSwiftTool), rather than the tools going dark.
  for (const tool of OMI_TOOLS) {
    pi.registerTool(tool)
  }
  // Report the set actually registered (serviceable-filtered), not the raw
  // manifest projection, so the snapshot/stderr reflect what the model can see.
  const registeredNames = OMI_TOOLS.map((tool) => tool.name)
  const snapshot = {
    ...buildToolAvailabilitySnapshot('pi-mono', projectionContext),
    advertisedToolCount: registeredNames.length,
    advertisedToolNames: registeredNames
  }
  if (process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH) {
    try {
      await writeFile(
        process.env.OMI_TOOL_AVAILABILITY_SNAPSHOT_PATH,
        `${JSON.stringify(snapshot, null, 2)}\n`
      )
    } catch (err) {
      process.stderr.write(
        `[omi-tools] Failed to write tool availability snapshot: ${
          err instanceof Error ? err.message : err
        }\n`
      )
    }
  }
  process.stderr.write(
    `[omi-tools] adapter=pi-mono advertisedToolCount=${snapshot.advertisedToolCount} advertisedTools=${snapshot.advertisedToolNames.join(',')}\n`
  )
}

export async function __registerOmiToolsForTest(pi: ExtensionAPI): Promise<void> {
  await registerOmiTools(pi)
}

// ---------------------------------------------------------------------------
// Extension entry point
// ---------------------------------------------------------------------------

export default function omiProvider(pi: ExtensionAPI): void {
  const baseUrl = process.env.OMI_API_BASE_URL || 'https://api.omi.me/v2'
  const apiKey = process.env.OMI_API_KEY || ''

  // BYOK: the app sets OMI_BYOK_* env vars (all four, or none) when the user is
  // on the free plan with their own provider keys. Attach them as X-BYOK-*
  // headers on every request so the backend applies the request-level
  // all-four-keys paywall exemption and routes inference through the user's own
  // key. We only attach the complete set — the backend's has_all_byok_keys()
  // requires all four to be present. (Env-var names match src/shared/byok.ts.)
  const byokMap: Array<[string, string]> = [
    ['OMI_BYOK_OPENAI', 'X-BYOK-OpenAI'],
    ['OMI_BYOK_ANTHROPIC', 'X-BYOK-Anthropic'],
    ['OMI_BYOK_GEMINI', 'X-BYOK-Gemini'],
    ['OMI_BYOK_DEEPGRAM', 'X-BYOK-Deepgram']
  ]
  const byokHeaders: Record<string, string> = {}
  for (const [envName, headerName] of byokMap) {
    const value = process.env[envName]
    if (value && value.length > 0) byokHeaders[headerName] = value
  }
  const byokActive = Object.keys(byokHeaders).length === byokMap.length
  if (byokActive) {
    process.stderr.write(
      `[omi-provider] BYOK active — attaching ${byokMap.length} X-BYOK headers\n`
    )
  }

  pi.registerProvider('omi', {
    api: 'openai-completions',
    baseUrl,
    apiKey,
    ...(byokActive ? { headers: byokHeaders } : {}),
    models: [
      {
        id: 'omi-sonnet',
        name: 'Omi Sonnet',
        reasoning: true,
        input: ['text', 'image'],
        contextWindow: 200_000,
        maxTokens: 16_384,
        // Cost set to 0 client-side — tracked server-side by the backend.
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
      },
      {
        id: 'omi-opus',
        name: 'Omi Opus',
        reasoning: true,
        input: ['text', 'image'],
        contextWindow: 200_000,
        maxTokens: 16_384,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 }
      }
    ]
  })

  pi.on('tool_call', async (event): Promise<ToolCallEventResult | void> => {
    let decision: DenyDecision | null = null
    try {
      decision = inspectToolCall(event)
    } catch (err) {
      // FAIL CLOSED for the tools the denylist enforces: an internal classifier
      // error must never silently permit a bash/write/edit call (that would
      // contradict the whole point of a load-bearing guard). Non-enforced tools
      // (read/grep/ls/…) are pass-through regardless, so a throw there is safe to
      // allow. Always audit-log the error either way.
      const msg = err instanceof Error ? err.message : String(err)
      void appendAudit({
        ts: new Date().toISOString(),
        phase: 'before',
        tool: event.toolName,
        decision: 'error',
        reason: `classifier threw: ${msg}`,
        summary: summarizeInput(event)
      })
      if (ENFORCED_TOOL_NAMES.has(event.toolName)) {
        return { block: true, reason: 'denylist classifier error — blocked for safety' }
      }
      return undefined
    }

    void appendAudit({
      ts: new Date().toISOString(),
      phase: 'before',
      tool: event.toolName,
      decision: decision ? 'deny' : 'allow',
      reason: decision?.reason,
      summary: summarizeInput(event)
    })

    if (decision) {
      return { block: true, reason: decision.reason }
    }
    return undefined
  })

  pi.on('tool_result', async (event: ToolResultEvent): Promise<void> => {
    void appendAudit({
      ts: new Date().toISOString(),
      phase: 'after',
      tool: event.toolName,
      decision: event.isError ? 'error' : 'ok',
      summary: summarizeInput({
        type: 'tool_call',
        toolName: event.toolName,
        toolCallId: event.toolCallId,
        input: event.input
      } as ToolCallEvent)
    })
  })

  // Register Omi-specific tools (execute_sql, semantic_search, etc.). These
  // forward to the host over the OMI_BRIDGE_PIPE named pipe.
  void registerOmiTools(pi)
}

// ---------------------------------------------------------------------------
// Test-only exports — relay internals for unit tests
// ---------------------------------------------------------------------------

/** Test-only: connect the pipe relay to a pipe path (performs the handshake).
 *  The token defaults to OMI_BRIDGE_TOKEN for back-compat with existing call
 *  sites that set it in env; pass an explicit token to exercise a remint. */
export const __connectOmiPipeForTest = (pipePath: string, token?: string): Promise<void> =>
  connectOmiPipe(pipePath, token ?? process.env.OMI_BRIDGE_TOKEN ?? '')

/** Test-only: the lazy connect-or-reuse path callSwiftTool uses in production. */
export const __ensureOmiConnectionForTest = ensureOmiConnection

/** Test-only: call a host tool through the pipe relay. */
export const __callSwiftToolForTest = callSwiftTool
export const __omiRelayCorrelationForTest = omiRelayCorrelation

/** Test-only: access to pending calls map for assertions. */
export const __omiPendingCallsForTest = omiPendingCalls

/** Test-only: reset pipe state between tests. */
export function __resetOmiPipeForTest(): void {
  if (omiPipeConnection) {
    omiPipeConnection.destroy()
    omiPipeConnection = null
  }
  omiPipeBuffer = ''
  omiCallIdCounter = 0
  omiPendingCalls.clear()
  omiConnectedKey = null
  omiConnecting = null
}
