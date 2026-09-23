# Imeqriyen imezwura n omi-cli

Amur-a yettmeslay ɣef tnezmiwin imezwura n omi-cli s Taqbaylit. Ismawen n tnezmiwin d iznan n wahil ad qqimen s Taglizit. Imedyaten-a ur ttbeddilen ara ismiren (memories) inek, idiwenniyen (conversations), tmahilin n uxeddim (action items), neɣ iswan (goals) inek.

## Asbeddi

Txesyeḍ: Python 3.10 neɣ asuɣar amaynut, d umiḍan n Omi.

Ma yella pipx yettusbedded:

```sh
pipx install omi-cli
omi --help
```

Neɣ deg unavaḍ virtual n Python i terreḍ urmid:

```sh
python -m pip install omi-cli
omi --help
```

Tamawt: tazmilt `omi` ahat ur telli ara deg PATH s tuzzya — ḥder belli unavaḍ virtual yestermed neɣ akaram n pipx yella deg `$PATH`.

## Tuqqna

Qqen qbel:

```sh
omi auth login
```

Tzemreḍ ad teqqneḍ s browser neɣ s tsarit API n uneflay n Omi. Sarit-a ad tt-tesxedmeḍ s umsali — ur tettsekkar ara deg umazray n terminal.

I tuqqna s browser ɣef tmacint-a:

```sh
omi auth login --browser
```

I tmacinin i yesɛan kan terminal: tasiregt ad tḍeḍ deg tansa tanaḍt. Ḍfeṛ ayen i d-yettmawan deg ugdil.

Senqed tawila d tsarit API tamiranit:

```sh
omi auth status
omi auth whoami
```

`status` yeskanay talɣut tanarazt, yeffer tiqura, ur yesseqsaḍ ara aqeddac. `whoami` yazen asuter yettusarnan; ma yedda, aya yebna belli iseknan-inek xeddmen akken iwata.

Tawila tettwaḥerz deg `~/.omi/config.toml`. Ur tt-beddil ara afaylu-a s ifassen-ik — tiqura n tsarit llant deg-s.

## Tabdart n ismiren d idiwenniyen

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ma yella tabdart tilemt, aya yebna kan belli ulac acem yellan akka tura. I wwal n imsizdeg n yal tazmilt:

```sh
omi memory list --help
omi action-item list --help
```

## JSON d tisuffɣar

Taxtiṛt tamatut `--json` ilaq ad tili QABEL n agraw n tnezmiwin:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Tazmilt tamezwarut ddu-yas 25 n ismiren imezwura; tis snat ddu-yas 25 i d-tekka deffir. Tuffɣa JSON tesɛa imyetwanen ičuranen, ma yella tarrayt n tfelwit ten-tegsen.

I usekles deg afaylu:

```sh
omi --json memory list --limit 25 --offset 0 > ismiren-asebter-1.json
```

Awiḍan-a yesnulfu afaylu amiran amaynut neɣ yesfeḍ i yellan. Senqed tameẓṛa n tazmilt qbel. Tuccḍiwin tteffɣent deg stderr; afaylu ilem ur yebni ara belli ulac isefka. Isuffɣar zemren ad sɛun talɣut tudmawant — ḥerz-ten.

## Tuffɣa

```sh
omi auth logout
```

Tazmilt-a tekkis iseknan imezɣanen. Tisura yettwaxelṣen ɣaf aqeddac llant ddaw usefrek n tisura n uneflay.

Ugar: [tidlit s Taglizit](../README.md) d `omi --help`.
