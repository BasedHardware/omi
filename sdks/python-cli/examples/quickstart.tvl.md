# Nga laasaga muamua ki omi-cli

Te fakamatala nei e fakamatala nga laasaga muamua (commands) o omi-cli i te gagana Tuvalu. Ko nga ingoa o command mo nga fekau a te polokalame e nofo i te gagana Peletania. Nga fakatai o te saili e fakaaoga i konei e se suia au manatu (memories), au talanoaga (conversations), au galuega (action items) mo au sini (goals).

## Fakatuu

Mea e manakomia: Python 3.10 pe sili atu, mo se akauniti Omi.

Kafai e isi sau `pipx`:

```sh
pipx install omi-cli
omi --help
```

E mafai foki o fakatuu i loto i se Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Kafai e se maua e te terminal a `omi`, fakamautu me e galue te virtual environment pe e isi te `pipx` folder i `$PATH`.

## Fesokotaki ki tou akauniti

Fakaamata te fesoasoani:

```sh
omi auth login
```

Filifili o ulu atu i te browser pe fakapiki se Omi developer API key. Te ulu atu e nana te key; sē tusi te key i se command e nofo i te terminal history. Ulu atu saʻo i te browser:

```sh
omi auth login --browser
```

Ulu atu i te kompiuta e tasi mo te terminal: te authentication e alu ki te local address. Mulimuli ki nga fakatonuga i te lau.

I muri, sivi te configuration mo te API:

```sh
omi auth status
omi auth whoami
```

`status` e fakaasi te tulaga o te loto ifo mo nana te secret, kae e se sivi te server. `whoami` e fai se authenticated request; kafai e manuia, e manino me e galue credentials. Te configuration e nofo i `~/.omi/config.toml`. Sē tufa: private credentials.

## Keukeu tou data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Te lisi gaogao e fakaasi me seai se mea e maua. Fakaoga te help ki nga filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON mo nga peeji

Tuu te `--json` **i mua** o te command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Te command muamua e fai atu mo 25; te lua mo te 25 e sosoo. Te peeji e tasi e se kopi katoa. JSON e tausi numela katoa; nga laulau i te lau e mafai o fakapuupuu.

Ki se faila:

```sh
omi --json memory list --limit 25 --offset 0 > memories-peeji-1.json
```

Te command e uma. Errors i stderr; faila gaogao e se data. Private.

## Fakauma

```sh
omi auth logout
```

Local credentials. Developer key.

[Peletania](../README.md) mo `omi --help`.
