# ᎢᎬᏱ ᏗᏂᎩᏍᏗ omi-cli

ᎯᎠ ᏗᎦᏔᎾᏫᏍᏗ omi-cli ᎢᎬᏱ ᏗᏟᎶᏍᏗ (commands) ᏣᎳᎩ ᎦᏬᏂᎯᏍᏗ. ᏗᏟᎶᏍᏗ ᏚᏙᏢᏒ ᎠᎴ ᏗᎾᏙᏢᏅ ᏗᎧᏃᎩᏍᏗ ᏓᎵᏆᎶᏍᏗ ᏂᎦᏓ ᎩᎵᏏ. ᎯᎠ ᏗᏟᎶᏍᏗ Ꮭ ᏱᏓᏁᏟᏗ: ᏗᎦᏁᏟᏗ (memories), ᏗᎵᏃᎮᏗ (conversations), ᏗᎸᏫᏍᏓᏁᏗ (action items), ᎠᎴ ᏗᏍᎦᏚᎩ (goals).

## ᏗᏙᎳᏅᏗ

ᎤᏚᎳᏗ: Python 3.10 ᎠᎴ Omi ᎠᏕᎳᏗᏍᏗ (account).

`pipx`:

```sh
pipx install omi-cli
omi --help
```

Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

`omi` ᏂᎨᏒᎾ, virtual environment ᏚᎸᏫᏍᏓᏁᏗ ᎠᎴ `pipx` ᏗᎪᏪᎶᏙᏗ `$PATH`.

## ᏗᏕᎬᏙᏗ ᎠᏕᎳᏗᏍᏗ

Asistęnt:

```sh
omi auth login
```

Browser ᎠᎴ Omi developer API key. Key ᎦᏄᎪᏍᏗ; ᏞᏍᏗ terminal history ᏱᏗᏟᎶᏍᏗ.

Browser:

```sh
omi auth login --browser
```

Terminal ᎠᎴ computer: authentication ᏗᎧᏁᎢᏍᏗ local address. Screen ᏗᏕᏲᎲᏍᏗ.

ᎣᏂ, configuration ᎠᎴ API:

```sh
omi auth status
omi auth whoami
```

`status` local ᎠᎴ secret ᎦᏄᎪᏍᏗ, ᎠᏎᏃ server ᏂᎨᏒᎾ. `whoami` authenticated request; ᏚᎸᏫᏍᏓᏁᏗ, credentials ᏚᎸᏫᏍᏓᏁᏗ, ᏙᏓᏒᏍᏗ ᏂᎨᏒᎾ.

Configuration `~/.omi/config.toml`. ᏞᏍᏗ ᏱᏗᏰᎵᏍᏗ: private credentials.

## ᏂᎦᏓ ᏗᎪᏪᎶᏙᏗ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ᎦᏄᎪᏍᏗ list ᏂᎨᏒᎾ. Help filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ᎠᎴ ᏗᎦᎪᏗ

`--json` **ᎢᎬᏱ** command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ᎢᎬᏱ command 25 memories; ᏔᎵᏁ 25. ᏌᏉ page ᏂᎦᏓ ᏂᎨᏒᎾ. JSON numbers; table screen.

Page file:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

File ᏗᏙᎳᏅᏗ ᎠᎴ ᏗᎪᏪᎶᏙᏗ. Command ᎠᏍᏆᏂᎪᏗᏍᎬ. Errors stderr; ᏂᎨᏒᎾ file data ᏂᎨᏒᎾ. Personal information: private.

## ᎠᏓᏅᏍᏗ

```sh
omi auth logout
```

Local credentials ᏗᎦᏘᏲᏍᏗ. Server key developer key management.

Commands ᎠᎴ options: [English guide](../README.md) ᎠᎴ `omi --help`.
