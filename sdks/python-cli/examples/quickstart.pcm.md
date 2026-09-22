# How to take start use omi-cli

Dis guide dey explain di first omi-cli commands for Nigerian Pidgin. Di command names and program messages go still dey for English. Di example queries wey dey here no go change your memories, conversations, action items, or goals.

## Installation

Wetin you need: Python 3.10 or newer one, and one Omi account.

If you don install pipx:

```sh
pipx install omi-cli
omi --help
```

Or put am inside Python virtual environment wey you don activate:

```sh
python -m pip install omi-cli
omi --help
```

Note: `omi` command fit no dey your PATH straight away — make sure say di virtual environment dey active or di pipx folder dey inside `$PATH`.

## Login

Login first before you fit use am:

```sh
omi auth login
```

You fit login wit browser or wit Omi developer API key. You go paste di key — e no go enter terminal history.

To login wit browser for dis computer:

```sh
omi auth login --browser
```

For machines wey get only terminal: di authorization go happun for local address. Just follow wetin di screen dey tell you.

Check di configuration and API key wey dey now:

```sh
omi auth status
omi auth whoami
```

`status` go show local info and e go hide secrets, e no go ask di server anything. `whoami` go send authenticated request; if e work, e mean say your credentials dey work well.

Dem dey keep configuration inside `~/.omi/config.toml`. No touch dis file wit hand — key secrets dey inside am.

## List memories and conversations

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

If di list empty, e just mean say notin dey there yet. To see di filters wey each command get:

```sh
omi memory list --help
omi action-item list --help
```

## JSON and exports

Di global `--json` option must come BEFORE di command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Di first command go carry di first 25 memories; di second one go carry di next 25. JSON output get di full identifiers, but di table view dey cut dem short.

To save am inside file:

```sh
omi --json memory list --limit 25 --offset 0 > memories-pej-1.json
```

Dis redirect go create new local file or overwrite di old one. Check di command output first. Errors dey go stderr; empty file no mean say data no dey. Export files fit carry personal info — guard dem well.

## Logout

```sh
omi auth logout
```

Dis command go delete di local credentials. Di keys wey dem create for server side dey under developer key management.

For more commands and options: [English docs](../README.md) and `omi --help`.
