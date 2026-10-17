# Quick start wit omi-cli

Dis guide dey explain di basic commands for Nigerian Pidgin. Command names and
program messages still dey for English. Di example commands under no go change
your memories, conversations, action items, or goals.

## Install di program

Wetin you need: Python 3.10 or newer and one Omi account.

If `pipx` don dey installed:

```sh
pipx install omi-cli
omi --help
```

Or install am inside activated Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

If terminal no fit find `omi`, check say di virtual environment don active or
say di folder wey `pipx` dey put executables dey inside `PATH`.

## Connect your account

Run di interactive guide:

```sh
omi auth login
```

Pick browser login or paste one Omi developer API key. Di interactive input
dey hide di key; no type am inside commands wey go enter terminal history.

To use browser straight:

```sh
omi auth login --browser
```

Login for di same computer wey get di terminal because di authentication dey
use local callback address. Follow wetin show for screen.

After login, check di configuration and API access:

```sh
omi auth status
omi auth whoami
```

`status` dey show di local state and dey mask secrets, but e no dey check if
dem still dey valid for server. `whoami` dey send authenticated request; if e
work, your credentials dey work without showing your name.

Configuration dey save inside `~/.omi/config.toml` by default. No share dis
file — e fit get credentials inside.

## Read your data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Empty list fit mean say nothing match di filter. See each command's options
for help:

```sh
omi memory list --help
omi action-item list --help
```

## Get JSON and page through am

Put di global `--json` option **before** di command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Di first command dey ask for di first 25 memories; di second dey ask for di
next 25. One page no be full backup. JSON output dey keep full IDs, while
table fit shorten IDs for display.

To save one page into file:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

Dis redirect dey create or overwrite local file. Make sure di command finish
successfully before you use di content. Errors dey write to stderr; empty
file no dey prove say data no dey. Di export file fit get personal
information — keep am private.

## Use profiles

State dey save inside `~/.omi/config.toml` (you fit change am wit
`$OMI_CONFIG`). Each profile get im own authentication method and API address.
Switch profile wit `--profile`:

```sh
omi config profile use work
omi auth login
omi --profile personal memory list
```

Common configuration commands:

```sh
omi config show
omi config path
omi config profile list
```

## Exit codes

Dis exit codes dey stable and useful for scripts or agents:

| Code | Meaning | Example situation |
| ---: | --- | --- |
| 0 | success | Command finish |
| 1 | usage error | Wrong flag, missing argument, or validation fail |
| 2 | authentication error | No credentials, token don expire, or permission no reach |
| 3 | server error | Server 5xx or connection fail |
| 4 | rate limited | Server return HTTP 429 |
| 5 | not found | Server return HTTP 404 |

## Log out

```sh
omi auth logout
```

E dey remove credentials wey dey saved locally. To revoke di key for server,
use di developer key management for your account.

For more commands and options, see di [main English README](../README.md) and
run `omi --help`.
