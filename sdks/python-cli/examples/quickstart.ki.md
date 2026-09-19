# Ũtongoria wa Narua wa omi-cli

Ũtongoria ũyũ ũrataarĩria mawatho ma kĩambĩrĩria na rũthiomi rwa Gĩkũyũ (Kikuyu) harĩ `omi-cli`. Marĩĩtwa ma mawatho na ndũmĩrĩri cia mbũgĩrĩrio nĩ igũtũũra irĩ cia Gĩthũngũ. Ngerekano cia ũtuuria iria cionanĩtio haha itikanagarũra iririkano ciaku (memories), mĩario (conversations), mawĩra ma gwĩkwo (action items), kana mĩorooto yaku (goals).

## Kũhunjia mbũgĩrĩrio (Installation)

Mabataro: Python 3.10 kana ĩrĩa njerũ makĩria hamwe na akaunti ya Omi.

Angĩkorwo nĩ ũkoragwo na `pipx`:

```sh
pipx install omi-cli
omi --help
```

No ũhunjie o na kũrĩ rũtũũngo rũrĩa rũraruta wĩra rwa Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Angĩkorwo watho wa `omi` ndũroneka thĩinĩ wa theminaro, thuthuria ũmenye kana virtual environment nĩ ĩraruta wĩra kana njĩra ya `pipx` ĩrĩ thĩinĩ wa `$PATH` yaku.

## Kũnyitania akaunti yaku (Authentication)

Ambĩrĩria mũteithia wa kwarĩria:

```sh
omi auth login
```

Thuura kũtoonya na njĩra ya kĩharĩro kĩa ũcũthĩrĩria (browser) kana kũhũthĩra Omi developer API key yaku. Njĩra ĩno nĩ ĩhithaga kĩhingũro kĩu; ndũkaandĩke kĩhingũro thĩinĩ wa mawatho marĩa mangĩtũũra rũrenda-inĩ rwa theminaro.

Gũthiĩ kĩharĩro-inĩ kĩa ũcũthĩrĩria ĩmwe kwa ĩmwe:

```sh
omi auth login --browser
```

Toonya thĩinĩ wa kompiuta ĩyo ĩmwe theminaro ĩrarutĩra wĩra: macokio ma ũhoro mahũthagĩra andĩrethĩ ya kũu kũu. Rũmĩrĩra motaro marĩa maroneka kĩharĩro-inĩ.

Thutha ũcio, thuthuria mĩbango na ũhoti wa kũhũthĩra API:

```sh
omi auth status
omi auth whoami
```

`status` nĩ ĩronania ũrĩa kũrĩ kũu kũu na ĩkahitha maũndũ ma hitho, no ndĩthuthuragia kana nĩĩraruta wĩra wega kũrĩ kĩhũũro kĩnene (server). `whoami` ĩtũmaga kĩũria kĩheetwo rũtha; ũngĩgĩa na ũhootani, ĩratĩĩtĩkithia atĩ marũa nĩ mararuta wĩra ĩtekũhũthĩra rĩĩtwa rĩaku.

Mĩbango kũndũ kũingĩ ĩigagwo thĩinĩ wa `~/.omi/config.toml`. Ndũkanagaye faĩri ĩno na andũ angĩ: no ĩkorwo ĩrĩ na maũndũ ma hitho.

## Gũthuthuria maũndũ maku (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mũrũngũrũrĩ ũtarĩ kĩndũ no ũkorwo ũkĩonania atĩ gũtirĩ kĩndũ kĩronanĩtio kĩringanĩte na ũtuuria. Hũthĩra ũteithio kũmenya mawatho mongerere:

```sh
omi memory list --help
omi action-item list --help
```

## Kũgĩa na JSON na Kũhũra Mahũtĩ (Pagination)

Ĩga gĩthuuriro kĩa thĩ yothe kĩa `--json` **mbere** ya gĩkundi kĩa mawatho:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Watho wa mbere ũkũũragia iririkano 25 cia mbere; wa kerĩ ũkũũria 25 iria irũmĩrĩire. Ihũtĩ rĩmwe ti kũiga kũrĩa gũtũũraga (backup). Maũndũ marĩa mauma thĩinĩ wa JSON nĩ maigaga marĩĩtwa mothe wega, o na gũtuĩka metha ya kĩharĩro no ĩnyihie nĩguo yonekane wega.

Kũiga ihũtĩ thĩinĩ wa faĩri:

```sh
omi --json memory list --limit 25 --offset 0 > iririkano-ihuti-1.json
```

Njĩra ĩno nĩ ĩthondekaga kana ĩgacenjia faĩri ya kũu kũu. Thuthuria ũmenye watho nĩ warĩkire wega mbere ya kũhũthĩra maũndũ marĩa marĩ thĩinĩ. Mahĩtia maandĩkagwo thĩinĩ wa mwanya wa mahĩtia (stderr); faĩri ĩtarĩ kĩndũ ndĩronania atĩ gũtirĩ maũndũ. Faĩri ĩrĩa yaumio no ĩkorwo ĩrĩ na maũndũ maku ma hitho: mĩige wega mũno.

## Kuuma akaunti-inĩ (Logout)

```sh
omi auth logout
```

Watho ũyũ nĩ weheragia marũa marĩa maigĩtwo kũu kũu. Nĩguo weherie kĩhingũro kĩhũũro-inĩ kĩnene, hũthĩra ũrũgamĩrĩri wa developer key thĩinĩ wa akaunti yaku.

Nĩguo ũkũũre mawatho mangĩ na motaro marĩa mongereirwo, rora [ũtongoria mũnene wa Gĩthũngũ](../README.md) na `omi --help`.
