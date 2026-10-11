# Awọn Igbesẹ Akọkọ pẹlu omi-cli

Itọsọna yii ṣe alaye awọn aṣẹ akọkọ ni Èdè Yorùbá. Awọn orukọ aṣẹ ati awọn ifiranṣẹ
eto wa ni ede Gẹẹsi. Awọn apẹẹrẹ ibeere ti o han nibi ko yi awọn iranti rẹ,
awọn ibaraẹnisọrọ, awọn iṣẹ-ṣiṣe, tabi awọn ibi-afẹde rẹ pada.

## Fifi eto sii

Awọn ibeere: Python 3.10 tabi ẹya tuntun ati akọọlẹ Omi kan.

Ti o ba ni `pipx` ti a fi sii:

```sh
pipx install omi-cli
omi --help
```

Ni ọna miiran, o le fi sii laarin agbegbe foju Python ti a mu ṣiṣẹ (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Ti ebute (terminal) ko ba ri `omi`, ṣayẹwo pe agbegbe foju n ṣiṣẹ tabi pe folda
ti `pipx` n fi awọn faili sii wa ninu `PATH` rẹ.

## Sisopọ akọọlẹ rẹ

Bẹrẹ oluranlọwọ ibaraenisepo:

```sh
omi auth login
```

Yan lati wọle nipasẹ aṣawakiri (browser) tabi aṣayan lati lẹ kọkọrọ API Olùgbéejáde Omi.
Iṣagbewọle ibaraenisepo n fi kọkọrọ naa pamọ; yago fun kikọ rẹ sinu aṣẹ ti yoo wa ninu itan ebute.

Lati lọ taara si aṣawakiri:

```sh
omi auth login --browser
```

Wọle lori kọnputa kanna nibiti ebute n ṣiṣẹ: idahun ijẹrisi n lo adirẹsi agbegbe kan.
Tẹle awọn ilana lori iboju.

Lẹhin iyẹn, rii daju iṣeto ati iraye si API:

```sh
omi auth status
omi auth whoami
```

`status` fihan ipo agbegbe ati pe o fi asiri pamọ, ṣugbọn ko ṣayẹwo idaniloju lori olupin.
`whoami` ṣe ibeere ti a fọwọsi; ti o ba ṣaṣeyọri, o jẹrisi pe awọn iwe-ẹri n ṣiṣẹ laisi afihan orukọ rẹ dandan.

Iṣeto naa wa ni fipamọ nipasẹ aiyipada ninu `~/.omi/config.toml`. Maṣe pin faili yii:
o le ni awọn iwe-ẹri asiri rẹ ninu.

## Wiwo data rẹ

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Atokọ ti o ṣofo le tumọ si pe ko si awọn nkan ti o ba ibeere mu. Lo iranlọwọ lati ṣawari awọn asẹ aṣẹ kọọkan:

```sh
omi memory list --help
omi action-item list --help
```

## Gbigba JSON ati lilọ kiri nipasẹ awọn oju-iwe

Fi aṣayan agbaye `--json` si **iwaju** ẹgbẹ aṣẹ:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Aṣẹ akọkọ n beere fun awọn iranti 25 akọkọ; ekeji, 25 ti o tẹle. Nitorinaa oju-iwe kan
kii ṣe afẹyinti pipe (backup). Iṣelọpọ JSON ṣe itọju awọn idanimọ ni kikun, lakoko ti awọn tabili le kuru wọn fun ifihan.

Lati fi oju-iwe pamọ sinu faili kan:

```sh
omi --json memory list --limit 25 --offset 0 > iranti-oju-iwe-1.json
```

Àtúnjúwe yii ṣẹda tabi rọpo faili agbegbe. Rii daju pe aṣẹ pari ni aṣeyọri ṣaaju lilo akoonu rẹ.
Awọn aṣiṣe ni a kọ si iṣelọpọ aṣiṣe (stderr); faili ti o ṣofo ko ṣe iṣeduro pe ko si data. Faili ti a firanṣẹ le ni alaye ti ara ẹni: jẹ ki o wa ni ikọkọ.

## Jade kuro ni akọọlẹ (Logout)

```sh
omi auth logout
```

Aṣẹ yii npa awọn iwe-ẹri ti o fipamọ ni agbegbe rẹ rẹ. Lati fagilee kọkọrọ kan lori olupin,
lo iṣakoso awọn bọtini olùgbéejáde ninu akọọlẹ rẹ.

Fun awọn aṣẹ to ku ati awọn aṣayan ilọsiwaju, wo [itọsọna akọkọ ni ede Gẹẹsi](../README.md) ati `omi --help`.
