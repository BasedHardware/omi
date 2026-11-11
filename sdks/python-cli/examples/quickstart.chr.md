# ᎢᎬᏱ ᏗᏕᏲᏗ omi-cli

ᎯᎠ ᏗᏕᏲᏗ omi-cli ᎢᎬᏱ ᏗᏟᎶᏍᏗ (commands) ᏣᎳᎩ ᎦᏬᏂᎯᏍᏗ. ᏗᏟᎶᏍᏗ ᏚᏙᏢᏒ ᎠᎴ program ᎧᏃᎮᏛ ᏂᎦᏓ ᎩᎵᏏ. Ꮭ ᏱᏓᏁᏟᏗ: ᏗᎦᏁᏟᏗ (memories), ᏗᎵᏃᎮᏗ (conversations), ᏗᎸᏫᏍᏓᏁᏗ (action items), ᎠᎴ ᏗᏍᎦᏚᎩ (goals).

## ᏗᏙᎳᏅᏗ

ᎤᏚᎳᏗ ᏂᎯ: Python 3.10 ᎠᎴ Omi ᎠᏕᎳᏗᏍᏗ (account).

`pipx` ᎾᎿ:

```sh
pipx install omi-cli
omi --help
```

ᎠᎴ Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

`omi` ᏂᎨᏒᎾ ᏱᎩ: virtual environment ᎠᎴ `pipx` ᏗᎪᏪᎶᏙᏗ `$PATH` ᏣᏩᏛᏗ.

## ᏗᏕᎬᏙᏗ (Login)

Asistęnt:

```sh
omi auth login
```

Browser ᎠᎴ Omi developer API key ᎯᏯᏍᏗ. Key ᎠᏍᏚᏗ; terminal history ᏞᏍᏗ ᏱᏗᎪᏪᎳ.

Browser:

```sh
omi auth login --browser
```

Terminal ᎠᎴ computer ᎤᏠᏱ: authentication ᎾᏍᎩ local address. Screen ᎾᎿ ᏗᏕᏲᎲᏍᏗ.

ᎣᏂ: configuration ᎠᎴ API:

```sh
omi auth status
omi auth whoami
```

`status` local ᎠᎴ secret ᎠᏍᏚᏗ, ᎠᏎᏃ server ᏂᎨᏒᎾ. `whoami` authenticated request; ᏚᎸᏫᏍᏓᏁᏗ, credentials ᏚᎸᏫᏍᏓᏁᏗ, ᏙᏓᏒᏍᏗ ᏂᎨᏒᎾ.

Configuration `~/.omi/config.toml`. ᏞᏍᏗ ᏱᏗᏰᎵᏍᏗ: private credentials.

## ᏗᎪᏩᏛᏗ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

List ᏂᎨᏒᎾ — Ꮭ ᎪᎱᏍᏗ ᏱᏗᏩᏛᏗ. Help:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ᎠᎴ ᏗᎪᏪᎵ

Global `--json` **ᎢᎬᏱ** command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ᎢᎬᏱ command 25 memories; ᏔᎵᏁ 25. ᏌᏉ page ᏂᎦᏓ backup ᏂᎨᏒᎾ. JSON ᏂᎦᏓ identifiers; table screen.

Page file:

```sh
omi --json memory list --limit 25 --offset 0 > diganehlidi-1.json
```

File ᏗᏙᎳᏅᏗ ᎠᎴ ᏚᏁᏟᏗ. Command ᎠᏍᏆᏂᎪᏗᏍᎬ ᎪᏩᏛᏗ. Errors stderr ᎾᎿ; ᏂᎨᏒᎾ file data ᏂᎨᏒᎾ. Personal information: private.

## ᎠᏓᏅᏍᏗ (Logout)

```sh
omi auth logout
```

Local credentials ᏗᎦᏘᏲᏍᏗ. Server key: developer key management.

Commands ᎠᎴ options: [ᎩᎵᏏ ᏗᏕᏲᏗ](../README.md) ᎠᎴ `omi --help`.
