# omi-cli ɲɛfɔlikan teliya la

Nin ɲɛfɔlikan in bɛ cikan fɔlɔw kɔrɔbɔ Bamanankan na `omi-cli` kama. Cikan tɔgɔw ni porogaramu laselikanso bɛ to Tubabukan na. Kɔrɔbɔli misali minnu bɛ kɛ yan, olu tɛ i ka hakilijagɛlɛyabaaw (memories), barow (conversations), baarow minnu ka kan ka kɛ (action items), walima i ka kuntilenna (goals) foyi yɛlɛma.

## Porogaramu kɛcogo (Installation)

Wajibi fɛnw: Python 3.10 walima kurayalenba ani Omi jatebɔlan (account).

Ni `pipx` bɛ i bolo kaban:

```sh
pipx install omi-cli
omi --help
```

I bɛ se fana k'a bila Python sɔrɔyɔrɔ baarakɛla dɔ kɔnɔ (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ni `omi` cikan ma sɔrɔ i ka kɔmpiyutɛri tɛriminali kɔnɔ, a lajɛ ni virtual environment bɛ baara la walima ni `pipx` yɔrɔ bɛ i ka `$PATH` kɔnɔ.

## I ka jatebɔlan bila ɲɔgɔn na (Authentication)

Dɛmɛbaga kumanyɔgɔnyalenba daminɛ:

```sh
omi auth login
```

A sugandi ka don marakɛla (browser) fɛ walima k'i ka Omi developer API key bila a kɔnɔ. Nin donli in bɛ konko kɔrɔbɔ; i kana a sɛbɛn cikanw na minnu bɛ to tɛriminali tariku kɔnɔ.

Ka taga marakɛla la tiɲɛ na:

```sh
omi auth login --browser
```

Don kɔmpiyutɛri kelen kan i bɛ tɛriminali labaara min kan: dannaya jaabi bɛ kɛ dugu kɔnɔ adɛrɛsi de fɛ. Ladilikan minnu bɛ kɛ fasa kan, o labato.

O kɔfɛ, sariyaw ani API lajɛ:

```sh
omi auth status
omi auth whoami
```

`status` bɛ yɔrɔ kɔnɔ cogoya jira ani k'a gundo lakana, nka a tɛ a lajɛ ni porogaramu gansan bɛ baara la siribaga (server) kan. `whoami` bɛ dɛmɛ deli kɛ; n'a kɛra hɛɛrɛ ye, a bɛ a jira k'a seko bɛ kɛ k'a sɔrɔ i tɔgɔ ma bɔ kɛnɛ kan.

Labɛnw bɛ don kabako kɔnɔ yɔrɔ min, o ye `~/.omi/config.toml` ye. I kana nin dosiye in tilatila: gundow bɛ se ka kɛ a kɔnɔ.

## I ka kunnafoniw kɔrɔbɔli (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ni foyi tɛ lisi kɔnɔ, o bɛ se ka kɔrɔ foyi ma sɔrɔ ɲinini la. Dɛmɛ bila k'a sugandiliw ye cikan kelen-kelen bɛɛ la:

```sh
omi memory list --help
omi action-item list --help
```

## JSON sɔrɔli ani ɲɛ tilatila (Pagination)

Duniya bɛɛ sugandili `--json` bila cikan jɛkulu **ɲɛfɛ**:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Cikan fɔlɔ bɛ hakilijakow 25 fɔlɔ deli; filanan bɛ 25 nataw deli. Ɲɛ kelen tɛ bɛɛ labɛnbaliya ye (backup). JSON kɔrɔbɔli bɛ tɔgɔ bɛɛ mara, hali ni fasa tabali bɛ se k'a dɔgɔya k'a jira kosɛbɛ.

Ka ɲɛ dɔ mara dosiye kɔnɔ:

```sh
omi --json memory list --limit 25 --offset 0 > hakilijakow-nye-1.json
```

Nin sira in bɛ dosiye dɔ dabɔ walima k'a yɛlɛma i ka kɔmpiyutɛri kan. A lajɛ ko cikan banna ka ɲi sani i ka a kɔnɔnafɛn labaara. Filiw bɛ sɛbɛn fili bɔyɔrɔ la (stderr); dosiye lankolon tɛ kɔrɔ foyi tɛ yen ye. Dosiye bɔlen in bɛ se ka kɛ i yɛrɛ ka kunnafoni ye: a lakana kosɛbɛ.

## Ka bɔ jatebɔlan kɔnɔ (Logout)

```sh
omi auth logout
```

Nin cikan in bɛ seko sɛbɛnw bɔ minnu mara i ka kɔmpiyutɛri kan. Walasa ka seko konko bɔ siribaga kan, i ka developer key kow lajɛ i ka jatebɔlan kɔnɔ.

Cikan wɛrɛw ani fɛn caman nataw kama, [Tubabukan ɲɛfɔliba](../README.md) ani `omi --help` lajɛ.
