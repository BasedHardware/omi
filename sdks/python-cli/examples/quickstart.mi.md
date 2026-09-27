# Ngā hīkoi tuatahi me te omi-cli

Ka whakamārama tēnei aratohu i ngā whakahau tuatahi (commands) o te omi-cli i roto i te reo Māori. Ka noho tonu ngā ingoa whakahau me ngā karere o te papatono ki te reo Ingarihi. Kāore ngā tauira rapu e whakaaturia ana i konei e huri i ō mahara (memories), ō kōrero (conversations), ō take mahi (action items), ō whāinga rānei (goals).

## Te whakaurunga

Ngā mea e hiahiatia ana: Python 3.10, he hou ake rānei, me tētahi pūkete Omi.

Mēnā kei a koe te `pipx`:

```sh
pipx install omi-cli
omi --help
```

Ka taea hoki e koe te whakauru ki tētahi taiao Python mariko e hohe ana:

```sh
python -m pip install omi-cli
omi --help
```

Ki te kore te reanga (`terminal`) e kite i te `omi`, whakapūmautia kei te hohe te taiao mariko, kei roto rānei te kōpaki o te `pipx` i `$PATH`.

## Te hono i tō pūkete

Tīmatahia te kaiāwhina pāhekoheko:

```sh
omi auth login
```

Kōwhiria te takiuru mā te pūtirotiro, te whakapiri rānei i tētahi kī API o te kaiwhakawhanake Omi. Ka huna te tāurunga pāhekoheko i te kī; āraia te tuhituhi i te kī ki tētahi whakahau ka pupuri ki te hītori o te reanga.

Kia haere tika ki te pūtirotiro:

```sh
omi auth login --browser
```

Takiuru i te rorohiko kotahi me te reanga: ka haere te whakautu motuhēhēnga ki te wāhitau ā-rohe. Whāia ngā tohutohu i te mata.

Muri i tēnā, manatoko i te whirihoranga me te urunga API:

```sh
omi auth status
omi auth whoami
```

Ka whakaatu te `status` i te āhua ā-rohe, ka huna i te muna, engari kāore e manatoko i te whaitake i te tūmau. Ka mahi te `whoami` i tētahi tono motuhēhē: ki te angitu, ka mārama kei te mahi ngā taipitopito takiuru, me te kore e whakaatu i tō ingoa.

Ka tiakina te whirihoranga ā-taunoa ki `~/.omi/config.toml`. Kaua e tuari tēnei kōnae: tērā pea kei roto ngā taipitopito takiuru tūmataiti.

## Te tūhura i ō raraunga

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ko te tikanga o tētahi rārangi wātea, he kore noa iho pea tētahi mea e hāngai ana ki te rapu. Whakamahia te āwhina ki te kite i ngā tātari o ia whakahau:

```sh
omi memory list --help
omi action-item list --help
```

## JSON me te whārangi

Whakaurua te kōwhiringa ao `--json` **i mua** i te rōpū whakahau:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ka tono te whakahau tuatahi i ngā mahara 25 tuatahi; ka tono te tuarua i ngā 25 whai muri. Ehara te whārangi kotahi i te tāruatanga katoa. Ka tiaki te putanga JSON i ngā tau tōpū, engari ka taea e ngā rārangi i te mata te whakapoto.

Hei tiaki i tētahi whārangi ki tētahi kōnae:

```sh
omi --json memory list --limit 25 --offset 0 > mahara-wharangi-1.json
```

Ka hanga, ka tuhia rānei e tēnei arotāhanga he kōnae ā-rohe. Me mātua whakapūmau kua oti te whakahau i mua i te whakamahi i te ihirangi. Ka tuhia ngā hapa ki te putanga hapa (stderr); ehara te kōnae wātea i te tohu kāore he raraunga. Tērā pea kei roto i tētahi kōnae kaweake ngā mōhiohio whaiaro: puritia kia noho tūmataiti.

## Te puta atu

```sh
omi auth logout
```

Ka muku tēnei whakahau i ngā taipitopito takiuru kua tiakina ā-rohe. Hei whakakore i tētahi kī i te tūmau, whakamahia te whakahaere kī kaiwhakawhanake i tō ake pūkete.

Mō ētahi atu whakahau me ngā kōwhiringa, tirohia te [aratohu matua i te reo Ingarihi](../README.md) me te `omi --help`.
