# Kamata ngāue mo e omi-cli

ʻOku fakahaaʻi ʻe he tohi fakahinohino ko ʻení ʻa e ngaahi ʻuluaki fekau ʻi he Lea Fakatonga. Ko e ngaahi hingoa ʻo e fekau mo e ngaahi popoaki ʻo e polokalama ʻoku kei nofo pē ʻi he lea Fakapālangi. Ko e ngaahi fakatātā lau ko ʻeni ʻoku ʻoatu heni he ʻikai ke ne liliu hoʻo ngaahi manatu, fealēleaʻaki, lisi ngāue pe ngaahi taumuʻa.

## Fokotuʻu ʻa e polokalama

Ngaahi Meʻa ʻOku Fiemaʻu: Python 3.10 pe ko ha liliu foʻou ange pea mo ha ʻakauni Omi.

> Fakatokangaʻi Ange: Ko e hingoa ʻo e kofukofu ʻi he PyPI ko e **`omi-cli`**, ka ko e fekau ʻoku lele hili hono fokotuʻu ko e **`omi`**. ʻOku ʻi ai ha kofukofu kehe ʻoku ʻikai fekauʻaki ʻoku ui ko e `omi` ʻi he PyPI — ʻoua ʻe fokotuʻu ʻa e kofukofu ko iá.

Kapau kuo fokotuʻu ʻa e `pipx`:

```sh
pipx install omi-cli
omi --help
```

Pe ko hono toe fai ʻi ha ʻātakai fakaʻilekitulōnika Python ʻoku lele:

```sh
python -m pip install omi-cli
omi --help
```

Kapau ʻoku ʻikai maʻu ʻe he fakaʻilonga ʻa e `omi`, fakapapauʻi ʻoku ngāue ʻa e ʻātakai pe ʻoku ʻi hoʻo `PATH` ʻa e fakamatala fakahinohino `pipx`.

## Fakafehokotaki hoʻo ʻakauni

Kamata ʻa e tokoni fetuʻutaki:

```sh
omi auth login
```

Fili ke hū ʻi he meʻa fakakomipiuta ki he ʻinitaneti, pe fili ʻa e fili ke fakapipiki ʻa e kī API ki hono langa ʻo e Omi. Ko e fakahu kī ʻoku fufū ʻa e kī; ʻoua ʻe tohi ʻa e kī ʻi he ngaahi fekau ʻe lava ke nofo ʻi he hisitōlia ʻo e mīsini.

Ki he hū fakahangatonu ʻi he uepisaiti:

```sh
omi auth login --browser
```

Fakakakato ʻa e hū ʻi he komipiuta tatau pē ʻoku lele ai ʻa e meʻangāue, he ko e fakamoʻoni ʻoku foki mai ki he tuʻasila fakalotofonua. Muimui ki he ngaahi fakahinohino ʻoku hā ʻi he lauʻi sioʻata.

Hili ia, vakaiʻi ʻa e fokotuʻutuʻu mo e hu ki he API:

```sh
omi auth status
omi auth whoami
```

ʻOku fakahaaʻi ʻe he `status` ʻa e tuʻunga fakalotofonua pea fufū ʻa e ngaahi meʻa fakapulipuli, ka ʻoku ʻikai ke ne fakamoʻoniʻi mo e tēpile tefito. ʻOku ʻave ʻe he `whoami` ha kole kuo fakalao; ko e ola lelei ʻoku ʻuhinga ia ʻoku ngāue totonu hoʻo ngaahi fakamoʻoni.

ʻOku tauhi ʻa e fokotuʻutuʻu ʻi he `~/.omi/config.toml`. ʻOua ʻe vahevahe ʻa e faile ko ʻeni he ʻoku ʻi ai hoʻo ngaahi fakamatala fakapulipuli.

## Vakai ki hoʻo ngaahi fakamatala

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ko ha lisi maha pē ʻoku ʻuhinga pē nai he ʻikai ha meʻa ʻe feʻunga mo e meʻa naʻe kole. Ke mahino ʻa e meʻa sivi ʻo ha fekau, vakai ki he tokoni:

```sh
omi memory list --help
omi action-item list --help
```

## Maʻu ʻa e JSON mo e ngaahi peesi

Fokotuʻu ʻa e fili fakalukufua `--json` **ki muʻa** ʻi he kulupu fekau:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ko e ʻuluaki fekau ʻoku kole ki he ngaahi lēkooti ʻe 25 ʻuluaki; ko hono ua ʻoku kole ki he 25 hoko. Ko ia ai, ko ha peesi ʻe taha ʻoku ʻikai ko ha tatau kakato ia. ʻOku tauhi ʻe he ola ʻo e JSON ʻa e ngaahi fakaʻilonga kakato, ka ʻe lava ke fakanoʻunoʻu ia ʻe he ngaahi tēpile.

Ke fakahaofi ha peesi ki ha faile:

```sh
omi --json memory list --limit 25 --offset 0 > manatu-peesi-1.json
```

ʻOku fakatupu pe fetongi ʻe he fekau ko ʻeni ha faile fakalotofonua. Ki muʻa pea ngāue ʻaki ʻa e konga tohi, fakapapauʻi naʻe lavameʻa ʻa e fekau. ʻOku tohi ʻa e fehālaaki ʻi he stderr; ko ha faile maha ʻoku ʻikai ko ha fakamoʻoni ia ʻoku ʻikai ha fakamatala. Fakapapauʻi ʻoku malu ʻa e faile naʻe hiki he ʻe lava ke ʻi ai ha ngaahi fakamatala fakatautaha.

## Hu ki Tuʻa (Log out)

```sh
omi auth logout
```

ʻOku toʻo ʻe he fekau ko ʻeni ʻa e ngaahi fakamoʻoni naʻe tauhi fakalotofonua. Ke taʻofi pe fakafoki ha kī ʻi he meʻa tefito, ngāueʻaki ʻa e puleʻi ʻo e kī langa ʻi hoʻo ʻakauni.

Ki ha ngaahi fekau kehe mo ha ngaahi fili lahi ange, kātaki ʻo mamata ki he tohi fakahinohino Fakapālangi:
[../README.md](../README.md) mo e `omi --help`.
