# Ardorde Jaawnde ngam omi-cli

Ndee ɗoo ardorde ina faamnina yamiroore arandeere nder ɗemngal Fulfulde (Pulaar / Fula). Inɗe yamiroore e mesaasuuji porogaraam ɗii ina keddoo e ɗemngal Engele. Yeruuji ƴeewndo kollitaaɗi ɗoo ɗii waylataa siftorɗe maa (memories), jeewte maa (conversations), kuule baɗeteeɗe (action items), walla faandaare maa (goals).

## Loowgol porogaraam (Installation)

Baɗte ɗaɓɓiraaɗe: Python 3.10 walla ko ɓuri kesum e konte Omi.

So aɗa jogii `pipx` loowaande:

```sh
pipx install omi-cli
omi --help
```

Ina waawi kadi looweede nder nokku gonɗo e golloraade mo Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

So tawii yamiroore `omi` yiytaaka e nder terminal, ƴeewto so tawii nokku gollorɗo oo ina golloroo walla dosiyeer `pipx` oo ina woodi e `$PATH` maa.

## Seŋde konte maa (Authentication)

Fuɗɗo balloowo gonɗo e jeewte:

```sh
omi auth login
```

Suɓo naatgol rewrude e wanngorde (browser) walla cuɓe ɗo cakkataa Omi developer API key. Naatgol ngol ina suuɗa coktirgal ngal; hoto winndu ngal e yamiroore heddotoonde e daartol terminal maa.

Ngam yahde to wanngorde e hoore mum:

```sh
omi auth login --browser
```

Naatu e ordinateer gooto ɗo terminal ngal dogata: jaabawol gollal ngal ina huutortoo adiresi nokkuujo. Rew doosɗe ɗe kollita-ɗaa e ekran.

Caggal ɗuum, ƴeewto saaktugol ngol e keɓgol laawol API ngol:

```sh
omi auth status
omi auth whoami
```

`status` ina holla ngonka nokkuujo ka suuɗa sirlu nguu, kono ƴeewtataako so tawii ina golloroo e serwer oo. `whoami` ina nelda ɗaɓɓannde gollal ngal; so naatii no haanirta, ina tabitina wonde seedanteeje ɗee ina ngolloroo tawa ɗum ɗaɓɓaani hollaande innde maa.

Konto oo ina mooftaa e dow laawol gootol e `~/.omi/config.toml`. Hoto renndin ndee fiilde: ina waawi jogaade seedanteeje sirlu.

## Ƴeewtaade keɓe maa (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Doggol ngol alaa ko woni e mum firti tan ko alaa ko heɓaa e ƴeewndo ngoo. Huutoro ballal ngam heɓde cuɓe e nder kala yamiroore:

```sh
omi memory list --help
omi action-item list --help
```

## Keɓgol JSON e Feccere Kelle (Pagination)

Waɗ cuɓol ngol `--json` **hade** fedde yamiroore ndee:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Yamiroore adannde ndee ɗaɓɓata ko siftorɗe 25 gadane ɗee; ɗiɗmere ndee, 25 jokkuɗe ɗee. Hello ngooto wonaa kopol timmuɗo. Keɓe JSON ɗee ina njogoo maandeeji timmuɗi ɗii, hay so tawii taable ekran ɗee ina mbaawi ustude ɗum ngam hollirde.

Ngam mooftude hello e nder fiilde:

```sh
omi --json memory list --limit 25 --offset 0 > siftorde-hello-1.json
```

Ngol ɗoo laawol ina sosa walla wayla fiilde nde e nder nokku hee. Ƴeewto so yamiroore ndee timmii no haanirta hade huutoraade ko woni e mum. Juumre kala ina winndee e feccere juumre (stderr); fiilde nde alaa ko woni e mum fawaaki e alaa keɓe. Fiilde yaltinaande ndee ina waawi jogaade kabaruuji keertiiɗi: reenu ɗum.

## Seŋtude e konte (Logout)

```sh
omi auth logout
```

Ndee yamiroore ina itta seedanteeje mooftaaɗe e nder nokku hee. Ngam momtude coktirgal e serwer oo, huutoro njuɓɓudi developer key e nder konte maa.

Ngam yamiroore woɗnde e cuɓe ɓeydaaɗe, ƴeew [ardorde Engele heewnde faayiida](../README.md) e `omi --help`.
