# Nā lau muamua ma omi-cli

Tuhi nei e fakamālamalama nā lau muamua (commands) o omi-cli i te gagana Tokelau. Ko nā igoa o command ma nā fekau o te polokalame e nofo i te gagana Peletānia. Ko nā fakatai o te kikila e fakaoga i konei e hē fakahela a ō manatunatuga (memories), ō talanoaga (conversations), ō gāluega (action items) ma ō sini (goals).

## Fakatu

Ko nā mea e manakomia: Python 3.10 pe mua atu, ma he akaun Omi.

Mai te mea e isi tō `pipx`:

```sh
pipx install omi-cli
omi --help
```

E mafai foki o fakatu i loto i he Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Kafai e hē maua e te terminal a `omi`, fakamautu me e gāluega te virtual environment pe e isi te `pipx` fōtā i `$PATH`.

## Fesōtai ki tō akaun

Kamata te fesoasoani:

```sh
omi auth login
```

Filifili o hū atu i te browser pe fakapiki he Omi developer API key. E nāna te hū atu i te key, kae hē tuhi te key i he command e nofo i te terminal history. Hū atu hako i te browser:

```sh
omi auth login --browser
```

Hū atu i te komipiuta e taha ma te terminal: e haere te authentication ki te local address. Mumuli ki nā fakatonu i te lau.

I muri, sivi te configuration ma te API:

```sh
omi auth status
omi auth whoami
```

E fakaasi e `status` te tūlaga o te loto ifo ma e nāna te secret, kae e hē sivi i te server. E fai e `whoami` he authenticated request; kafai e manuia, e manino me e gāluega nā credentials. E nofo te configuration i `~/.omi/config.toml`. Hē tufa te fōtā nei: e mafai o isi ai he private credentials.

## Kikila tō data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ko te lisi gaogao e fakamālamalama noa me hēai he mea e maua. Fakaoga te fesoasoani ki nā filter o ia command:

```sh
omi memory list --help
omi action-item list --help
```

## JSON ma nā laupepa

Tuu te `--json` **i mua** o te command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

E ole te command muamua ki nā 25 muamua; e ole te lua ki nā 25 e sosoo mai. Ko te laupepa e taha e hē he kopi katoa. E tausi e JSON nā numela katoa, kae e mafai e nā laulau i te lau o fakapuupuu.

Ki he fōtā:

```sh
omi --json memory list --limit 25 --offset 0 > memories-laupepa-1.json
```

E uma te command. E alu nā errors ki te stderr; ko te fōtā gaogao e hē he fakamāoniga me hēai he data. E mafai o isi he private information i te fōtā: tausi i te private.

## Fakaoti

```sh
omi auth logout
```

E tāmate e te command nei nā credentials i te local. Ki te fakagāoā he key i te server, fakaoga te developer key management i tō akaun.

[Peletānia](../README.md) ma `omi --help`.
