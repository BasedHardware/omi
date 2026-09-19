# ᓯᕗᓪᓕᐹ omi-cli

ᐅᓇ ᐃᓕᓐᓂᐊᕐᓂᖅ omi-cli ᓯᕗᓪᓕᖅᐹ ᑲᔾᔮᓇᐅᔭᖅ (commands) ᖃᓪᓗᓈᑎᑐᑦ ᐅᖃᐅᓯᕐᒥ. ᑲᔾᔮᓇᐅᔭᖅ ᐊᑎᖏᑦ ᐊᒻᒪ ᐱᕙᓪᓕᐊᔪᖅ ᑐᓴᒐᒃᓴᖏᑦ ᖃᓪᓗᓈᑎᑐᑦ. ᐅᑯᐊ ᖃᐅᔨᓴᕐᓂᖅ ᐊᒥᓱᐊᖅᑐᑦ ᓇᓗᓇᐃᔭᖅᑕᐅᔪᑦ ᓄᑖᖑᔪᑦ: ᐃᓅᓯᕐᒥ ᐃᓱᒪᒃᑯᑦ (memories), ᐅᖃᓕᒫᒐᕐᒥ (conversations), ᐱᓕᕆᔾᔪᑎᑦ (action items), ᐊᒻᒪ ᑐᕌᒐᖅ (goals).

## ᓴᓇᐅᑎᓕᐅᕐᓂᖅ

ᐱᔭᐅᔭᕆᐊᖃᖅᑐᑦ: Python 3.10 ᐅᕝᕙᓘᓐᓃᑦ ᓄᑖᖅᑎᓄᑦ, ᐊᒻᒪ Omi ᑎᑎᕋᖅᓯᒪᔪᖅ (account).

`pipx` ᖃᓄᐃᑦᑑᓂᖓ:

```sh
pipx install omi-cli
omi --help
```

Python virtual environment-ᒥ ᓴᓇᐅᑎᓕᐅᕐᓂᖅ ᐊᒥᓱᐊᖅᑐᑦ:

```sh
python -m pip install omi-cli
omi --help
```

`omi` ᓇᓂᔭᐅᙱᑉᐸᑦ, virtual environment ᐱᕙᓪᓕᐊᔪᖅ ᐅᕝᕙᓘᓐᓃᑦ `pipx` ᐊᑎᖅ `$PATH`-ᒥ.

## ᑎᑎᕋᖅᓯᒪᔪᖅ ᑲᑐᔾᔨᖃᑎᒌᖕᓂᖅ

Asistanti ᐱᒋᐊᕐᓗᒍ:

```sh
omi auth login
```

Browser-ᒥ ᐅᕝᕙᓘᓐᓃᑦ Omi developer API key-ᒥ ᐃᓯᕆᐊᕐᓗᒍ. ᐃᓯᕆᐊᕐᓂᖅ key ᐸᐃᑉᐹᖅ; terminal history-ᒥ ᑎᑎᕋᖅᓯᒪᔪᖅ.

Browser-ᒧᑦ ᐊᑐᕆᐊᕐᓗᒍ:

```sh
omi auth login --browser
```

Terminal ᐊᒻᒪ computer ᑲᑐᔾᔨᖃᑎᒌᑦᑐᖅ: authentication ᑭᐅᔪᖅ local address-ᒧᑦ. Screen-ᒥ ᒪᓕᒐᖅ.

ᑭᐅᔪᖅ, configuration ᐊᒻᒪ API:

```sh
omi auth status
omi auth whoami
```

`status` local-ᒥ ᓇᓗᓇᐃᔭᖅᑐᖅ ᐊᒻᒪ secret ᐸᐃᑉᐹᖅ, ᑭᓯᐊᓂ server-ᒥ ᓇᓗᓇᐃᔭᖅᑐᖅ. `whoami` authenticated request; ᐊᑑᑎᔪᖅ, credentials ᐱᕙᓪᓕᐊᔪᑦ, ᐊᑎᖅ ᓇᓗᓇᐃᔭᖅᑐᖅ.

Configuration `~/.omi/config.toml`-ᒥ. ᐊᑐᐃᓐᓇᖅᑎᑦᑎᓇᓱᒃᓇᖅ: private credentials.

## ᒪᓕᒐᖅ ᖃᐅᔨᓴᕐᓂᖅ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

List ᐊᑐᐃᓐᓇᖅ: ᓇᓂᔭᐅᙱᑦᑐᖅ. Help filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ᐊᒻᒪ ᒪᐅᖓ

`--json` **ᓯᕗᓪᓕᖅ** command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ᓯᕗᓪᓕᖅ command 25 memories; ᑎᓴᒪ 25. ᐊᑕᐅᓯᖅ ᒪᐅᖓ ᐊᑕᐅᓯᖅ ᑲᑎᒪᔾᔪᑎᖅ. JSON numbers ᑲᑎᒪᔾᔪᑎᖅ; table screen-ᒥ.

ᒪᐅᖓ file-ᒧᑦ:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

File ᓴᖅᑭᑎᑦᑎᓂᖅ ᐅᕝᕙᓘᓐᓃᑦ allanngortitsineq. Command ᐱᔭᐅᔭᕆᐊᖃᖅᑐᖅ. Errors stderr; file ᐊᑐᐃᓐᓇᖅ data. Personal information: private.

## ᐊᓂᒍᐃᓂᖅ

```sh
omi auth logout
```

Local credentials ᐲᖅᑕᐅᔪᑦ. Server key developer key management.

Commands ᐊᒻᒪ options: [English guide](../README.md) ᐊᒻᒪ `omi --help`.
