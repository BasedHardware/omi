# Te tīmata me te omi-cli

Ka whakaatu tēnei aratohu i ētahi whakahau tuatahi i te reo Māori. Ka noho tonu ngā ingoa whakahau me ngā karere pūnaha ki te reo Pākehā. Kāore ngā tauira pānui i konei e huri i ō maharatanga, kōrerorero, rārangi mahi, whāinga rānei.

## Tāuta i te kaupapa

Ngā Hiahia: Python 3.10, tētahi putanga hōu ake rānei, me tētahi pūkete Omi.

> Kia mahara: Ko te ingoa mōkī i runga i te PyPI ko **`omi-cli`**, engari ko te whakahau e whakahaerehia ana i muri i te tāutanga ko **`omi`**. He mōkī kē anō kāore he pānga e kīia ana ko `omi` kei runga i te PyPI — kaua e tāuta i taua mōkī.

Mēnā kua tāutatia a `pipx`:

```sh
pipx install omi-cli
omi --help
```

Hei kōwhiringa anō, i roto i tētahi taiao mariko Python e mahi ana:

```sh
python -m pip install omi-cli
omi --help
```

Ki te kore te tauranga e kite i a `omi`, me whakarite kei te mahi te taiao mariko, kei roto rānei te whaiaronga `pipx` i tō `PATH`.

## Honoa tō pūkete

Tīmatahia te kaiawhina taunekeneke:

```sh
omi auth login
```

Kōwhiria kia takiuru mā te tirotiro ipurangi, kōwhiria rānei te kōwhiringa ki te whakapiri i te kī API kaiwhakawhanake Omi. Ka hunaia te kī e te tāurunga; kaua e tuhia te kī ki ngā whakahau ka noho tonu ki te hītori tauranga.

Mō te takiuru tōtika mā te pūtirotiro:

```sh
omi auth login --browser
```

Whakaotia te takiuru i runga i te rorohiko kotahi e rere ana te tauranga, nā te mea ka hoki mai te whakamotēheatanga ki tētahi wāhitau paetata. Whāia ngā tohutohu ka puta ki te mata.

Whai muri i tērā, tirohia te whirihoranga me te urunga API:

```sh
omi auth status
omi auth whoami
```

Ka whakaatu a `status` i te āhuatanga paetata me te huna i ngā mea ngaro, engari kāore e tirotiro ki te tūmau. Ka tukuna e `whoami` tētahi tono kua whakamanahia; ko te angitu he tohu kei te mahi tika ō tohu tohu.

Ka tiakina te whirihoranga ki `~/.omi/config.toml`. Kaua e tohatohahia tēnei kōnae nā te mea kei roto ō tohu tohu motuhake.

## Tirohia ō raraunga

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

He rārangi kau noa iho pea te tikanga kāore he tūemi e ōrite ana ki te uiui. Kia mōhio ai koe ki ngā whiriwhiringa o tētahi whakahau, tirohia te āwhina:

```sh
omi memory list --help
omi action-item list --help
```

## Tiki JSON me te whakatere whārangi

Whakatakotoria te kōwhiringa whānui `--json` **i mua** i te rōpū whakahau:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ka tono te whakahau tuatahi i ngā rekoata tuatahi e 25; ka tono te tuarua i te 25 e whai ake nei. Nō reira, ehara tētahi whārangi i te tārua katoa. Ka pupuri te putanga JSON i ngā tautuhi katoa, engari ka whakapoto pea ngā ripanga i aua mea.

Hei tiaki i tētahi whārangi ki tētahi kōnae:

```sh
omi --json memory list --limit 25 --offset 0 > mahara-wharangi-1.json
```

Mā tēnei arataki anō e hanga, e whakakapi rānei tētahi kōnae paetata. I mua i te whakamahi i ngā ihirangi, me whakarite i tutuki tika te whakahau. Ka tuhia ngā hapa ki stderr; ehara te kōnae kau i te tohu kāore he raraunga. Kia noho muna tēnei kōnae nā te mea he mōhiohio whaiaro pea kei roto.

## Takiwhaiaro (Log out)

```sh
omi auth logout
```

Ka tangohia e tēnei whakahau ngā tohu tohu kua tiakina ā-paetata. Hei whakakore i tētahi kī i te tūmau, whakamahia te whakahaere kī kaiwhakawhanake i tō pūkete.

Mō ētahi atu whakahau me ngā kōwhiringa matatau, tēnā tirohia te aratohu matua i te reo Pākehā:
[../README.md](../README.md) me `omi --help`.
