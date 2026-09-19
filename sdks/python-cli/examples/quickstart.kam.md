# Ũtongoi wa Mĩtũkĩ wa omi-cli

Ũtongoi ũũ ũũeleka mĩao ya mbee na kĩthyomo kya Kĩkamba (Kamba) kwondũ wa `omi-cli`. Masyĩtwa ma mĩao na ũvoo wa mbokilamu ikaendeea kwĩthĩwa syĩ sya Kĩthũngũ. Ngelekanyʼo sya kũsianĩsya ila syonanĩtwʼe vaa iikavĩndũa makũmbũkilyo maku (memories), ũneeni waku (conversations), mawĩa ma kwĩkwa (action items), kana mawoni maku (goals).

## Kwĩkĩa mbokilamu (Installation)

Ila syĩendekaa: Python 3.10 kana ĩla nzaũ mweeno na akauntĩ ya Omi.

Ethĩwa wĩ na `pipx`:

```sh
pipx install omi-cli
omi --help
```

No ũyĩkĩe nthĩnĩ wa kĩsio kĩla kĩtetheesya kya Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ethĩwa mwao wa `omi` ndwĩoneka theminonĩ, sisya nesa ethĩwa virtual environment nĩyĩkũthũkũma kana ethĩwa nzĩa ya `pipx` yĩ nthĩnĩ wa `$PATH` yaku.

## Kũkwatanyʼa akauntĩ yaku (Authentication)

Ambĩĩsya mũtetheesi ũla ũneenaa naku:

```sh
omi auth login
```

Nyuvĩte kũlika kũtũmĩa browser kana kwĩkĩa Omi developer API key yaku. Nzĩa ĩno nĩvithaa kĩvungũo kĩu; ndũkaandĩke kĩvungũo mĩaonĩ ĩla ĩtonya kũtiwa nthĩnĩ wa themino.

Kũthi browser nthĩnĩ ĩmwe kwa ĩmwe:

```sh
omi auth login --browser
```

Lika kompiutanĩ o ĩla themino yĩĩthũkũmĩa vo: ũsũngĩo wa kũĩkĩĩthya ũtũmĩaa kĩsio kya vaa vau. Atĩĩa mĩao ĩla yĩ kĩkoinĩ.

Ĩtina wa ũu, sisya ũseũvyo na ũtonyi wa kũlika API:

```sh
omi auth status
omi auth whoami
```

`status` yonanasya ũndũ vailye vaa vau na ĩkavitha maũndũ ma kĩmbithĩ, ĩndĩ ndĩsisyaa ethĩwa nĩkũthũkũma kũla sevanĩ (server). `whoami` ĩtũmaa ĩkũlyo yĩkĩĩthĩtwʼe; yaenda nesa, yĩĩkĩĩthasya kana maũndũ nĩmekũthũkũma vate kũtũmĩa ĩsyĩtwa yaku.

Mĩvango kaingĩ yĩwʼawa nthĩnĩ wa `~/.omi/config.toml`. Ndũkanathanganyʼe faeli ĩno na andũ angĩ: no yĩthĩwe yĩ na maũndũ ma kĩmbithĩ.

## Kũsisya maũndũ maku (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mũthĩnzo ũte kĩndũ ũtonya kwonanyʼa o kana vai kĩndũ kĩkomanĩte na kũmantha kwaku. Tũmĩa ũtethyo kwona mĩvango ya mwao o mwao:

```sh
omi memory list --help
omi action-item list --help
```

## Kũkwata JSON na Kũvĩndũa Mambũtĩ (Pagination)

Ĩkĩa ũnyuvĩo wa nthĩ yonthe wa `--json` **mbee** wa nguluvu ya mĩao:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Mwao wa mbee ũkũlasya makũmbũkilyo 25 ma mbee; wa kelĩ ũkũlya 25 ala matĩĩe. Ĩvũtĩ yĩmwe ti kũsũvĩa kwonthe (backup). Maũndũ ala mauma JSON meethĩawa na masyĩtwa monthe vyũ, o na ethĩwa tevo ya kĩkoi no ĩvanzye nĩ kenda kwoneke nesa.

Kũsũvĩa ĩvũtĩ nthĩnĩ wa faeli:

```sh
omi --json memory list --limit 25 --offset 0 > makumbukilyo-ivuti-1.json
```

Nzĩa ĩno nĩseũvasya kana kũvĩndũa faeli ya vaa vau. Sisya mwao nĩwathĩna nesa ũteanambĩĩa kũtũmĩa kĩla kĩ nthĩnĩ. Mavĩtyo maandĩkawa vandũ va mavĩtyo (stderr); faeli ĩte kĩndũ ndĩonanyʼa kana vai maũndũ. Faeli ĩla yaumwʼa no yĩthĩwe yĩ na maũndũ maku ma kĩmbithĩ: yĩsũvĩe nesa vyũ.

## Kuma akauntĩnĩ (Logout)

```sh
omi auth logout
```

Mwao ũũ nĩwusaa kĩla kĩsũvĩĩtwʼe vaa vau. Kũveta kĩvungũo kũla sevanĩ, tũmĩa ũũngamĩi wa developer key akauntĩnĩ yaku.

Kwondũ wa mĩao ĩngĩ na ũnyuvĩo wa kwongela, sisya [ũtongoi mũnene wa Kĩthũngũ](../README.md) na `omi --help`.
