# Jinoe in omi-cli

Kalimur in elōn̄ kōttōpar (commands) in omi-cli i Kajin M̧ajeļ. Ekkā an naan in kōttōpar im naan in program eo, rej pād i Kajin Pālle. Jikin joonjo in ukōt (memories), in kōnono (conversations), in jerbal (action items) ak in kōm̧m̧an (goals), ejjab ukōt kōjerbal in.

## Aōt

M̧ōņōņō: Python 3.10 ak lōn̄, im juon Omi akkaun.

Eļan̄n̄e ewōr aṃ `pipx`:

```sh
pipx install omi-cli
omi --help
```

Kwōmaron̄ bar āinwōt aṃ kōņaan ijo an Python virtual aorōk:

```sh
python -m pip install omi-cli
omi --help
```

Eļan̄n̄e terminal eo ejjeḷọk an loe `omi`, kwōj aikuj lale bwe virtual environment eo ej jerbal ak `pipx` folda eo ej pād i `$PATH`.

## Kōjparoki aṃ akkaun

Kadedeļo̧k assistant eo:

```sh
omi auth login
```

Kwōj kōm̧m̧ane login i browser ak likūt juon Omi developer API key. Input eo ej kōjenouņe key eo; jab jeje key eo i command eo ej pād i terminal history.

Ñan ilān tōre i browser:

```sh
omi auth login --browser
```

Login i computer eo juon wōt i terminal: authentication eo ej ilān ñan local address. Āinwōt uwaak eo i screen eo.

Ālikin, kakkure configuration eo im API access:

```sh
omi auth status
omi auth whoami
```

`status` ej kwalok local state im kōjenouņe secret eo, āinwōt jab kakkure validity i server eo. `whoami` ej kōm̧m̧ane authenticated request; eļan̄n̄e ej tōprak, ejelok bwe credentials rej jerbal, ilo kajjitōk in etan.

Configuration eo ej pād i `~/.omi/config.toml`. Jab kōjparok file in ñan ro jet: emaron̄ wōr private credentials.

## Lale aṃ data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Juon list eo ejjeḷọk an men, ej joļo̧k wōt bwe ejjeḷọk men eo ejjab erom i search eo. Kōjerbal help eo ñan loe filter ko an command eo kajjojo:

```sh
omi memory list --help
omi action-item list --help
```

## JSON im pej

Likūt option eo `--json` **m̧oktata** i command group eo:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Command eo m̧oktata ej kajjitōk 25 memories m̧oktata; eo kein karuo ej kajjitōk 25 ko rej ilān ālikin. Juon pej ejjab full copy. JSON eo ej kōjparok numbers otemjej, keter eo i screen emaron̄ kakeren.

Ñan kōjparok juon pej i file:

```sh
omi --json memory list --limit 25 --offset 0 > memories-pej-1.json
```

Redirect in ej kōm̧m̧ane ak ej replace juon local file. Kakkure bwe command eo em̧ōj m̧oktata aṃ kōjerbal content eo. Errors rej jeje ñan error output (stderr); file eo ejjeḷọk an men, ejjab proof bwe ejjeḷọk data. File eo eṃōj export emaron̄ wōr personal information: kōjparok private.

## Ilān waj

```sh
omi auth logout
```

Command in ej jipañ an local credentials ko. Ñan invalidate juon key i server eo, kōjerbal developer key management i aṃ akkaun.

Ñan elōn̄ kōttōpar im options, lale [English guide eo aorōk](../README.md) im `omi --help`.
