# Awọn igbesẹ akọkọ pẹlu omi-cli

Itọsọna yii ṣe alaye awọn aṣẹ akọkọ ni ede Yoruba. Awọn orukọ aṣẹ ati awọn ifiranṣẹ eto wa ni ede Gẹẹsi. Awọn apẹẹrẹ ibeere ti o han nibi ko yi awọn iranti, awọn ibaraẹnisọrọ, awọn iṣẹ ṣiṣe, tabi awọn ibi-afẹde rẹ pada.

## Fi eto naa sori ẹrọ (Installation)

Awọn ibeere: Python 3.10 tabi ẹya ti o ga julọ ati akọọlẹ Omi kan.

Ti o ba ni `pipx` ti a fi sii:

```sh
pipx install omi-cli
omi --help
```

Gẹgẹbi yiyan, o le fi sii laarin agbegbe foju Python ti o ṣiṣẹ:

```sh
python -m pip install omi-cli
omi --help
```

Ti ebute naa ko ba ri `omi`, ṣayẹwo pe agbegbe foju wa ni iṣẹ tabi pe folda nibiti `pipx` fi awọn faili sii wa ninu `PATH` rẹ.

## So akọọlẹ rẹ pọ (Authentication)

Bẹrẹ oluranlọwọ ibaraenisọrọ:

```sh
omi auth login
```

Yan lati wọle nipasẹ aṣawakiri tabi lẹẹmọ bọtini API idagbasoke Omi kan. Titẹ sii ibaraenisọrọ yoo tọju bọtini rẹ; o yago fun kikọ rẹ sinu aṣẹ ti yoo wa ninu itan ebute rẹ.

Lati lọ taara si aṣawakiri:

```sh
omi auth login --browser
```

Wọle lori kọnputa kanna gẹgẹbi ebute rẹ: idahun ijẹrisi nlo adirẹsi agbegbe kan. Tẹle awọn itọnisọna ti o han loju iboju.

Lẹhinna, ṣayẹwo iṣeto ati iraye si API:

```sh
omi auth status
omi auth whoami
```

`status` fihan ipo agbegbe ati tọju asiri, ṣugbọn ko ṣayẹwo iwulo rẹ lori olupin. `whoami` ṣe ibeere ti o ni ijẹrisi; ti o ba ṣaṣeyọri, o jẹrisi pe awọn iwe-ẹri n ṣiṣẹ laisi afihan orukọ rẹ dandan.

Iṣeto naa wa ni fipamọ sinu `~/.omi/config.toml` nipasẹ aiyipada. Maṣe pin faili yii: o le ni awọn iwe-ẹri rẹ ninu.

## Wo data rẹ (Inspect data)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Atokọ ti o ṣofo le tumọ si pe ko si awọn ohun ti o baamu ibeere naa. Lo iranlọwọ lati ṣawari awọn asẹ fun aṣẹ kọọkan:

```sh
omi memory list --help
omi action-item list --help
```

## Gba JSON ki o lọ kiri nipasẹ awọn oju-iwe (JSON output & pagination)

Gbe aṣayan gbogbogbo `--json` si **ṣaaju** ẹgbẹ aṣẹ:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Aṣẹ akọkọ beere fun awọn iranti 25 akọkọ; ekeji beere fun 25 ti o tẹle. Nitorinaa, oju-iwe kan kii ṣe afẹyinti pipe. Ijade JSON ṣe itọju awọn idanimọ pipe, lakoko ti awọn tabili le kuru wọn lati ṣafihan wọn.

Lati fi oju-iwe pamọ sinu faili kan:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

Itọsọna yii ṣẹda tabi rọpo faili agbegbe. Ṣayẹwo pe aṣẹ naa pari ni aṣeyọri ṣaaju lilo akoonu rẹ. Awọn aṣiṣe ni a kọ sinu iṣelọpọ aṣiṣe; faili ti o ṣofo ko ṣe iṣeduro pe ko si data. Faili ti a firanṣẹ le ni alaye ti ara ẹni ninu: jẹ ki o jẹ ikọkọ.

## Jade (Logout)

```sh
omi auth logout
```

Aṣẹ yii yọkuro awọn iwe-ẹri ti o fipamọ ni agbegbe. Lati fagilee bọtini kan lori olupin, lo iṣakoso bọtini olupilẹṣẹ ninu akọọlẹ rẹ.

Fun awọn aṣẹ to ku ati awọn aṣayan ilọsiwaju, wo [itọsọna akọkọ ni ede Gẹẹsi](../README.md) ati `omi --help`.
