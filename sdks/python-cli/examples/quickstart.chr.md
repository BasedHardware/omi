# omi-cli ᎠᎴᏅᏗ ᎠᎵᏍᏕᎵᏍᎩ

ᎯᎠ ᎠᎵᏍᏕᎵᏍᎩ ᎧᏁᎢᏍᏗ ᎢᎬᏱᏱ ᏄᏍᏛ ᎬᏙᏗ ᏣᎳᎩ ᎦᏬᏂᎯᏍᏗ. ᎧᏁᏨᎯ ᏚᏙᎥ ᎠᎴ ᎤᏂᎩᏍᏗ ᎧᏃᎮᎸᎯ ᎩᎵᏏ ᏱᎬᏩᏍᏗᏉ. ᎯᎠ ᏕᎦᎧᏛᎢ ᎠᏎᎯᏍᏗ ᎥᏝ ᏱᏗᎦᏁᏟᏴᏍᏗ ᏣᏤᎵ ᎤᏅᏛ (memories), ᎧᏃᎮᎸᎯ (conversations), ᏧᎸᏫᏍᏓᏁᏗ (action items), ᎠᎴ ᏗᎦᎵᏱᎵᏒ (goals).

## ᎧᏁᏨᎯ ᏗᎦᎧᎯᏱ

ᎠᏚᎸᏗ: Python 3.10 ᎠᎴ ᎢᏤᎢ ᎤᏓᏂᏝᏅᎯ ᎠᎴ Omi account.

ᎢᏳᏃ `pipx` ᏣᏤᎵᎦ:

```sh
pipx install omi-cli
omi --help
```

ᎠᎴ ᏰᎵᏉ ᎭᏫᏂ Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

ᎢᏳᏃ terminal ᎬᏩᏍᏛ `omi` ᏄᏛᏁᎸᎾ, ᎦᏛᏂ virtual environment ᎠᎴ `pipx` ᏕᎪᏪᎸ $PATH.

## ᏣᏤᎵ ᎤᏂᎩᏍᏗ ᏕᎪᏪᎵ ᏗConnect

ᎠᎴᏅᏗ ᏓᎵᏍᏛᎯ ᎠᎵᏍᏕᎵᏍᎩ:

```sh
omi auth login
```

ᎯᏯᏑᎵ browser ᎠᎴ paste Omi developer API key. ᎤᏕᎵᏒ ᎯᎸᏫᏍᏓᏏ ᏕᎪᏪᎸᎢ.

Browser ᏫᏂᎦᎵᏍᏗᏍᎬ:

```sh
omi auth login --browser
```

ᎬᏔᏂ ᏄᏍᏛ ᎯᎸᏫᏍᏓᏏ. ᎣᏂ ᎠᎦᏎᏍᏙᏗ API ᎤᎵᏁᏨ:

```sh
omi auth status
omi auth whoami
```

`status` ᏕᎪᏪᎸ ᎦᏚᎢ ᎤᏓᏁᎶᏗ, ᎠᏎᏃ `whoami` ᏗᎬᏩᎶᏒᎯ ᎧᏃᎮᎸᎯ ᎢᏳᏍᏗ.

ᏕᎪᏪᎸᎢ ᎨᏐ `~/.omi/config.toml`. ᏞᏍᏗ ᏱᏥᎧᏁᏟᏴᏍᏔᏁᏍᏗ.

## ᏣᏤᎵ ᎠᏎᎯᏍᏗ ᏗᎪᏩᏘᏍᎩ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ᎢᏳᏃ ᎤᏏᏩ ᏱᎩ, ᏂᎯ ᎥᏝ ᎪᎱᏍᏗ ᏱᏣᎭ. ᎬᏔᏂ ᎠᎵᏍᏕᎵᏍᎩ:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ᎠᎴ ᎤᏯᎸᏒ Ꮧ Pagination

ᎢᎬᏱᏱ `--json` ᎯᎧᏅᎦ:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ᎢᎬᏱᏱ 25 ᎤᏅᏛ ᎯᎩᏍᎩ, ᏔᎵᏁ 25 ᎤᏅᏛ ᎯᎩᏍᎩ.

ᏕᎪᏪᎵ ᎦᏟᏐᏗ:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

## ᎤᏂᎩᏍᏗ ᎠᏑᎵᎪᎬ

```sh
omi auth logout
```

ᎯᎠ ᎧᏁᏨᎯ ᎢᎬᏩᏓᎵᏍᏗ ᏣᏤᎵ credentials.

ᏂᎦᏛ ᎤᏟ ᎢᎦᎢ ᎧᏃᎮᏗ, ᏫᎪᏩᏔ [ᎩᎵᏏ README](../README.md) ᎠᎴ `omi --help`.
