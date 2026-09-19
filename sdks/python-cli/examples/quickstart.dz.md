# omi-cli གི་ཐོག་མའི་གོམ་པ།

ལམ་སྟོན་འདི་གིས་ omi-cli གི་ཐོག་མའི་བཀོད་རྒྱ (commands) རྫོང་ཁ་ནང་འགྲེལ་བཤད་འབདཝ་ཨིན། བཀོད་རྒྱ་གི་མིང་དང་ལས་རིམ་གྱི་འཕྲིན་དོན་ཚུ་ཨིང་ལིཤ་ནང་ལུས་ཡོད། ནཱ་ལུ་བཀོད་ཡོད་པའི་འཚོལ་ཞིབ་དཔེ་ཚུ་གིས་ ཁྱོད་ཀྱི་དྲན་ཚུལ (memories), གནས་ཚུལ་བསྡུས་པ (conversations), ལས་འགུལ (action items), དང་དམིགས་ཡུལ (goals) ཚུ་མི་བསྒྱུར།

## གཏན་འཁེལ།

དགོས་མཁོ: Python 3.10 ཡང་ན་དེ་ལས་གསར་བ, དང་ Omi རྩིས་ཁྲ (account).

`pipx` ཡོད་པ་ཅིན:

```sh
pipx install omi-cli
omi --help
```

Python virtual environment ནང་ལུ་ཡང་གཏན་འཁེལ་འབད་ཚུགས:

```sh
python -m pip install omi-cli
omi --help
```

`omi` མ་ཐོབ་པ་ཅིན, virtual environment ལས་འགུལ་ཡོད་པ་དང་ `pipx` ཡིག་སྣོད་ `$PATH` ནང་ཡོད་པ་གཏན་འབེབས་འབད།

## ཐོ་བཀོད་མཐུད་པ།

Asistęnt འགོ་བཙུགས:

```sh
omi auth login
```

Browser ཡང་ན་ Omi developer API key གདམ། Key གབ་ཡོད; terminal history ནང་མ་འབྲི།

Browser ལུ་ཐད་ཀར་འགྲོ:

```sh
omi auth login --browser
```

Terminal དང་ computer གཅིག་པ་ནང་འཛུལ། Authentication ལན local address ལུ་འགྲོ། Screen གི་ལམ་སྟོན་ལུ་རྗེས་སུ་འབྲང་།

དེ་ལས་ཤུལ་ལས་ configuration དང་ API:

```sh
omi auth status
omi auth whoami
```

`status` local གནས་སྟངས་དང་ secret གབ, འོན་ཀྱང་ server ལུ་བདེན་དཔྱད་མི་འབད། `whoami` authenticated request; ལེགས་ཤོམ་ཅིན, credentials ལས་འགུལ་ཡོད, མིང་མ་སྟོན་པར།

Configuration `~/.omi/config.toml` ནང་ཉར་ཚགས་འབདཝ་ཨིན། ཡིག་སྣོད་འདི་མ་བགོ་བཤའ་རྐྱབ། private credentials ཡོད་ཚུགས།

## གནས་ཚུལ་བལྟ།

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

སྟོང་པའི་ཐོ་ཡིག་གིས་འཚོལ་ཞིབ་དང་མཐུན་པ་མེད་པ་སྟོན། Help filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON དང་ཤོག་ལེབ།

`--json` **འགོ་ཐོག** command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

འགོ་ཐོག command 25 memories; གཉིས་པ 25. ཤོག་ལེབ་གཅིག་ཆ་ཚང་མིན། JSON ཨང་གྲངས; table screen.

ཤོག་ལེབ file:

```sh
omi --json memory list --limit 25 --offset 0 > memory-page-1.json
```

File གསར་བཟོ་ཡང་ན་བསྐྱར་འབྲི། Command མཇུག Errors stderr; སྟོང་པ file data མིན། Personal information: private.

## ཕྱིར་ཐོན།

```sh
omi auth logout
```

Local credentials བསུབ། Server key developer key management.

Commands དང་ options: [English guide](../README.md) དང་ `omi --help`.
