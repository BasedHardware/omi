# omi-cli ᐱᒋᐊᕈᑎᒃᓴᐃᑦ ᒪᓕᒐᒃᓴᖅ

ᑖᓐᓇ ᒪᓕᒐᒃᓴᖅ ᐅᓂᒃᑳᖅᑐᖅ ᓯᕗᓪᓕᕐᓂᒃ ᐱᓕᕆᔾᔪᑎᓂᒃ ᐃᓄᒃᑎᑐᑦ (Inuktitut). ᐱᓕᕆᔾᔪᑏᑦ ᐊᑎᖏᑦ ᐊᒻᒪ ᑐᓴᐅᒪᔾᔪᑏᑦ ᖃᓪᓗᓈᑐᑦ ᐃᓕᖓᓂᐊᖅᑐᑦ. ᑖᒃᑯᐊ ᐊᑐᖅᑕᐅᔪᑦ ᓱᕋᐃᔾᔮᖏᑦᑐᑦ ᐃᖅᑲᐅᒪᔭᕐᓂᒃ (memories), ᐅᖃᖃᑎᒌᒍᑎᓂᒃ (conversations), ᐱᓕᕆᐊᒃᓴᓂᒃ (action items), ᐅᕝᕙᓘᓐᓃᑦ ᑐᕌᒐᕐᓂᒃ (goals).

## ᐱᓕᕆᔾᔪᑎᒥᒃ ᐋᖅᑭᒃᓱᐃᓂᖅ

ᐊᑐᕆᐊᓖᑦ: Python 3.10 ᐅᕝᕙᓘᓐᓃᑦ ᓄᑖᖑᓂᖅᓴᖅ ᐊᒻᒪ Omi ᐊカウント.

`pipx` ᐊᑐᐃᓐᓇᐅᒍᓂ:

```sh
pipx install omi-cli
omi --help
```

ᐅᕝᕙᓘᓐᓃᑦ ᐋᖅᑭᒃᓱᕈᓐᓇᖅᑕᐃᑦ Python virtual environment-ᒥ:

```sh
python -m pip install omi-cli
omi --help
```

## ᐊカウントᒥᒃ ᐊᑕᑎᑦᑎᓂᖅ

ᐱᒋᐊᕐᓗᒍ ᐊᐱᖅᓱᖅᑐᖅ:

```sh
omi auth login
```

ᓂᕈᐊᕐᓗᑎᑦ ᖃᕋᓴᐅᔭᒃᑯᑦ ᐅᕝᕙᓘᓐᓃᑦ Omi developer API key-ᒥᒃ.

ᖃᕋᓴᐅᔭᒃᑯᑦ ᑐᕌᖓᓂᖅ:

```sh
omi auth login --browser
```

ᖃᐅᔨᓴᕐᓗᒍ API-ᒧᑦ ᐊᑐᐃᓐᓇᐅᓂᖓ:

```sh
omi auth status
omi auth whoami
```

`status` ᑕᑯᒃᓴᐅᑎᑦᑎᔪᖅ ᐋᖅᑭᒃᓯᒪᓂᖓᓂᒃ, `whoami` ᑐᓴᖅᑎᑦᑎᔪᖅ ᐊᑐᕈᓐᓇᕐᓂᖓᓂᒃ.

## ᑐᓴᐅᒪᔾᔪᑎᓂᒃ ᕿᒥᕐᕈᓂᖅ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ᐃᑲᔪᖅᑕᐅᔪᒪᒍᕕᑦ:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ᐊᒻᒪ ᒪᒃᐱᒐᓂᒃ ᕿᒥᕐᕈᓂᖅ (Pagination)

`--json` ᓯᕗᓪᓕᐅᑎᓗᒍ:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ᑎᑎᕋᕐᓗᒍ ᒪᒃᐱᒐᖅ:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

## ᐊᓂᓂᖅ ᐊカウントᒥᑦ

```sh
omi auth logout
```

ᑖᓐᓇ ᐱᓕᕆᔾᔪᑎ ᐲᖅᓯᕗᖅ ᐃᓕᓯᒪᔪᓂᒃ ᓇᓗᓇᐃᒃᑯᑕᕐᓂᒃ.

ᑐᑭᓯᒋᐊᒃᑲᓐᓂᕈᒪᒍᕕᑦ [ᖃᓪᓗᓈᑐᑦ ᒪᓕᒐᒃᓴᖅ](../README.md) ᐊᒻᒪ `omi --help`.
