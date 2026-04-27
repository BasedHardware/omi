# omi-cli

> Talk to Omi from your terminal. Designed for humans **and** agents.

`omi-cli` is the command-line interface to the [Omi](https://omi.me) developer
API. It exposes scoped, agent-friendly verbs for the four primary nouns Omi
maintains about you:

* **memories** — facts and learnings the system knows about you
* **conversations** — captured & processed audio/text exchanges
* **action items** — tasks and follow-ups
* **goals** — tracked progress metrics

It's intentionally small, scriptable, and JSON-first — everything you need to
plug Omi into shell pipelines, CI jobs, agent harnesses, or just your own
personal automation.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Docs:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Source:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

## Install

```bash
pipx install omi-cli            # recommended — isolated install
# or
pip install omi-cli
```

After install, the binary on your `$PATH` is named `omi`:

```bash
omi --version
omi --help
```

> The PyPI distribution name is `omi-cli` (the bare `omi` slot belongs to an
> unrelated package). The console command is `omi` regardless.

## Quickstart

```bash
# 1. Log in. With no flags, omi-cli asks how you want to authenticate:
omi auth login
# → 1) Browser — sign in with Google or Apple (recommended for humans)
# → 2) API key — paste a developer key from app.omi.me (recommended for agents/CI)

# 2. Start using it:
omi memory list
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Pass `--json` to any command (as a global flag, before the verb) to get
machine-readable output, ready for `jq`, agent harnesses, or whatever else:

```bash
omi --json memory list | jq '.[] | {id, content}'
```

## Auth

Two auth methods, both fully wired:

| Method                       | Best for                                 | How to use                                |
| ---------------------------- | ---------------------------------------- | ----------------------------------------- |
| Dev API key (`omi_dev_*`)    | Agents, CI, headless, scoped permissions | `omi auth login --api-key ...` or env var |
| Firebase OAuth (Google/Apple) | Humans on a laptop                       | `omi auth login --browser`                |

The browser flow opens your default browser for OAuth, captures the code on a
localhost callback, and stores a Firebase ID token + refresh token. The ID
token is auto-refreshed before each request when it's near expiry — you
shouldn't need to think about it.

```bash
omi auth login                  # interactive picker (browser or key)
omi auth login --browser        # force OAuth (default provider: google)
omi auth login --browser --provider apple
omi auth login --api-key K      # force API-key path
omi auth login < key.txt        # piped key, useful in CI
omi auth status                 # show profile + masked credential + expiry
omi auth whoami                 # round-trip to verify the credential works
omi auth refresh                # force a Firebase refresh (no-op for API keys)
omi auth logout                 # wipe the credential
```

You can also set `OMI_API_KEY` in the environment to bypass on-disk config
entirely — handy in containers and CI:

```bash
export OMI_API_KEY=omi_dev_...
omi memory list
```

## Profiles

State lives at `~/.omi/config.toml` (overridable via `$OMI_CONFIG`). The file
holds one or more named profiles, each with its own auth method and API base.
Switch between them with `--profile`:

```bash
omi config profile use work
omi auth login                  # logs in the active profile (work)
omi --profile personal memory list
```

Common config:

```bash
omi config show
omi config path
omi config set api_base https://api.staging.omi.me
omi config profile list
omi config profile delete old-account --yes
```

## Command surface

The full tree (run `omi --help` for the live version):

```text
omi
├── auth
│   ├── login [--browser] [--api-key KEY]
│   ├── logout
│   ├── status
│   ├── whoami
│   └── refresh
├── config
│   ├── show
│   ├── path
│   ├── set <key> <value>
│   └── profile
│       ├── list
│       ├── use <name>
│       └── delete <name>
├── memory
│   ├── list [--limit N] [--offset N] [--categories ...]
│   ├── get <id>
│   ├── create <content> [--category ...] [--visibility ...] [--tag ...]
│   ├── update <id> [--content ...] [--category ...] [--visibility ...] [--tag ...]
│   └── delete <id> [-y]
├── conversation
│   ├── list [--limit N] [--start-date ...] [--end-date ...] [--include-transcript]
│   ├── get <id> [--include-transcript]
│   ├── create [--text ...] [--text-source ...] [...]
│   ├── from-segments <file.json> [--source ...]
│   ├── update <id> [--title ...] [--discarded/--no-discarded]
│   └── delete <id> [-y]
├── action-item
│   ├── list [--completed/--open] [--conversation-id ...] [...]
│   ├── get <id>
│   ├── create <description> [--due-at ...]
│   ├── update <id> [--description ...] [--completed/--open] [--due-at ...]
│   ├── complete <id>
│   └── delete <id> [-y]
└── goal
    ├── list [--limit N] [--include-inactive]
    ├── get <id>
    ├── create <title> --target N [--type ...] [--current N] [--unit ...]
    ├── update <id> [...]
    ├── progress <id> <value>
    ├── history <id> [--days N]
    └── delete <id> [-y]
```

## Global flags

```text
--json                 Emit JSON to stdout (machine-readable, agent-friendly).
--profile, -p NAME     Use a specific profile.
--api-base URL         Override the API base URL.
--verbose, -v          Log HTTP traffic to stderr.
--no-color             Disable colored output (also honors $NO_COLOR).
--version              Print the version.
--help                 Show contextual help.
```

## Exit codes (stable contract)

```text
0  success
1  usage error (bad flags, missing args, validation)
2  auth error (no creds, expired token, insufficient scope)
3  server error (5xx, connection failure)
4  rate limited (429) — retry recommended
5  not found (404)
```

## For agents

The CLI is built so an LLM can use it without a wrapper:

* `--json` returns valid JSON to stdout. Nothing else writes to stdout in JSON
  mode (errors go to stderr as `{"error": "...", "detail": "..."}`).
* Stable exit codes (above) let an agent disambiguate retryable vs terminal
  errors.
* Rate-limit errors include a `Retry-After` window in the message and surface
  the policy name (`dev:conversations`, etc.) so an agent can back off
  intelligently.
* `OMI_API_KEY` and `OMI_API_BASE` env vars work without any prior `auth login`.

See [`examples/agent_quickstart.md`](examples/agent_quickstart.md) for a worked
example.

## Rate limits

The dev API enforces per-policy hourly limits:

| Policy                | Limit       |
| --------------------- | ----------- |
| `dev:conversations`   | 25/hour     |
| `dev:memories`        | 120/hour    |
| `dev:memories_batch`  | 15/hour     |

The CLI retries `429` automatically with exponential backoff and honors the
server's `Retry-After` hint where present. After all retries are exhausted you
get exit code `4` plus a message telling you how long to wait.

## Development

```bash
# Editable install with dev extras
pip install -e .[dev]

# Run the test suite
pytest -q

# Lint
black --check --line-length 120 --skip-string-normalization sdks/python-cli/
mypy omi_cli

# Build a wheel + sdist (no upload, no tag)
bash release.sh --build-only
```

## License

MIT — see [`LICENSE`](LICENSE).
