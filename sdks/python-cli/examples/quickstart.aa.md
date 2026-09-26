# Qimbisa taamáy omi-cli

Tá gálto abbá yasgixeemih omi-cli taamáy (commands) Afar afat. Commands migaaqaay programma coox aqayakkiimeh ingiliis afat raaqa. Yo gexo tunkussoomih taamáy, mannu (memories), yaabaleela (conversations), taamá (action items) kee qimbi (goals) mabaxsa — usun inkih sinam faxxah yaniimih inna.

## Xeemiyya

Faxxah yaniimah: Python 3.10 wali nummah, kee Omi konte.

`pipx` lito koo:

```sh
pipx install omi-cli
omi --help
```

Python virtual environmenti le gexo xeemi:

```sh
python -m pip install omi-cli
omi --help
```

Terminal `omi` mogoota kaa, virtual environment yakkiime wali `pipx` folder `$PATH` lito kaa tuguu.

## Kontê xagnay

Asistente xagna:

```sh
omi auth login
```

Browseri kalla wali Omi developer API key xagtehik doorita. Key ugutukta, kinnih terminal historyi liimiyyah uktum. Browseri radak:

```sh
omi auth login --browser
```

Terminal kee komputaril radak: authentication gudduuh local address. Screenil geytoota kataya.

Wagitta, configuration kee API access xagnay:

```sh
omi auth status
omi auth whoami
```

`status` local casbiisaay secret ugutukta, kinnih serveril manxuysaana. `whoami` authenticated request abta; gufeh, credentials yakkiimah tuguu baxa. Configuration `~/.omi/config.toml` addah. Faxi yaafis: private credentials liimiyyah.

## Ku dagnay

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Baxa listi faxxuh. Help filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON kee farat

`--json` **kayo** command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Kayó command 25 memories; waggino 25. Page inkih copi. JSON numbers dacrisa; screenil table.

Page filet:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

Command gudduysa. Errors stderr; faxa file data. Personal information: private.

## Caxx

```sh
omi auth logout
```

Local credentials bayissa. Server key developer key management.

Commands kee options: [English guide](../README.md) kee `omi --help`.
