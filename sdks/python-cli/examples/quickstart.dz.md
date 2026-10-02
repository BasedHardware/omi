# omi-cli དང་འགོ་བཙུགས་ནི།

ལམ་སྟོན་འདི་ omi-cli གི་དོན་ལུ་ རྫོང་ཁ་ནང་ ཐོག་མའི་གོམ་པ་ཚུ་ འགྲེལ་བཤད་འབདཝ་ཨིན། བཀོད་རྒྱ་དང་ ལས་རིམ་གྱི་འཕྲིན་དོན་ཚུ་ ཨིང་ལིཤ་ནང་ལུས་ཡོད། དཔེ་ཚུ་གིས་ ཁྱོད་ཀྱི་ དྲན་ཚུལ (memories), ཁ་བཤད (conversations), ལས་འགུལ (action items) དང་ དམིགས་ཡུལ (goals) ཚུ་ མི་བསྒྱུར།

## གཏན་འཁེལ་འབད་ནི།

དགོས་མཁོ་ཡོད: Python 3.10 ཡང་ན་ དེ་ལས་གསར་བ, དང་ Omi རྩིས་ཁྲ (account).

`pipx` ཡོད་པ་ཅིན:

```sh
pipx install omi-cli
omi --help
```

ཡང་ན་ Python virtual environment ནང་:

```sh
python -m pip install omi-cli
omi --help
```

`omi` མ་ཐོབ་པ་ཅིན: virtual environment ལས་འགུལ་ཡོད་པ་དང་ `pipx` ཡིག་སྣོད་ `$PATH` ནང་ཡོད་པ་ ཞིབ་བཤེར་འབད།

## ནང་འཛུལ་འབད་ནི། (Login)

Asistęnt འགོ་བཙུགས:

```sh
omi auth login
```

Browser ཡང་ན་ Omi developer API key གདམ། Key གབ་ཡོད; terminal history ནང་ མ་བཀོད།

Browser ལུ་ ཐད་ཀར་འགྲོ་ནི།

```sh
omi auth login --browser
```

Terminal གནས་ས་ computer དང་ གཅིག་པའི་ནང་ ནང་འཛུལ་འབད། Authentication གི་ལན་ local address ལུ་འགྲོ། Screen གི་ལམ་སྟོན་ལུ་ རྗེས་སུ་འབྲང་།

དེ་གི་ཤུལ་ལས་ configuration དང་ API ཞིབ་བཤེར་འབད:

```sh
omi auth status
omi auth whoami
```

`status` གིས་ local གནས་སྟངས་དང་ secrets གབ་ནི་སྟོན་འབདཝ་ཨིན, འོན་ཀྱང་ server ལུ་ བདེན་དཔྱད་མི་འབད། `whoami` གིས་ authenticated request འབདཝ་ཨིན; ལེགས་ཤོམ་ཅིན, credentials ཚུ་ ལས་འགུལ་ཡོདཔ་ མིང་མ་སྟོན་པར་ བདེན་དཔྱད་འབདཝ་ཨིན།

Configuration ཚུ་ `~/.omi/config.toml` ནང་ བཞག་ཡོད། ཡིག་སྣོད་འདི་ གཞན་ལུ་ མ་བགོ་བཤའ་རྐྱབ། ནང་ན་ private credentials ཡོད་ཚུགས།

## གནས་ཚུལ་བལྟ་ནི།

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

སྟོང་པའི་ཐོ་ཡིག་ཅིག་གིས་ འཚོལ་ཞིབ་དང་མཐུན་པ་མེད་པ་སྟོན་འབདཝ་ཨིན། Help ནང་ filter ཚུ་:

```sh
omi memory list --help
omi action-item list --help
```

## JSON དང་ཤོག་ལེབ་ཚུ།

`--json` **འགོ་ཐོག་** command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

འགོ་ཐོག་ command གིས་ 25 memories དང་ གཉིས་པ་གིས་ ཤུལ་མམ་ 25. ཤོག་ལེབ་གཅིག་ backup ཆ་ཚང་ མིན། JSON གིས་ identifier ཆ་ཚང་སྟོན་འབད, table གིས་ screen ལུ་ བསྡུས་ཏེ་སྟོན་འབད་ཚུགས།

ཤོག་ལེབ་ ཡིག་སྣོད་ནང་ ཉར་:

```sh
omi --json memory list --limit 25 --offset 0 > dren-tshul-1.json
```

ཡིག་སྣོད་ གསར་བཟོ་ ཡང་ན་ བསྐྱར་འབྲི་འབདཝ་ཨིན། དེ་གི་ཧེ་མ་ command མཇུག་མཐར་ བདེན་དཔྱད་འབད། Errors ཚུ་ stderr ནང་འགྲོ; སྟོང་པ་ཡིག་སྣོད་གིས་ data མེདཔ་མི་སྟོན། Personal information ཡོད་ཚུགས — private བཞག།

## ཕྱིར་ཐོན་འབད་ནི། (Logout)

```sh
omi auth logout
```

Local credentials ཚུ་ བསུབ་འབདཝ་ཨིན། Server གི་ key བསུབ་ནི་ལུ་ developer key management ལག་ལེན་འཐབ།

བཀོད་རྒྱ་དང་ options ཚུ་གི་དོན་ལུ་ [ཨིང་ལིཤ་ལམ་སྟོན](../README.md) དང་ `omi --help` བལྟ།
