# Ngaahi sitepu fuofua mo e omi-cli

ʻO e fakahinohino ni ʻoku fakamatalaʻi ai ʻa e ngaahi tuʻutuʻuni fuofua (commands) ʻo e omi-cli ʻi he lea faka-Tonga. ʻOku nofo pē ʻa e hingoa ʻo e ngaahi tuʻutuʻuni mo e ngaahi pōpoaki ʻo e polokalama ʻi he lea faka-Pilitānia. ʻOku ʻikai liliu ʻe he ngaahi fakatātā fekumi ʻoku fakahā ʻi heni hoʻo manatu (memories), hoʻo ngaahi talanoa (conversations), hoʻo ngaahi ngāue (action items) pe hoʻo ngaahi taumuʻa (goals).

## Fokotuʻu

ʻOku fie maʻu: Python 3.10 pe lahi ange, mo ha ʻakauni Omi.

Kapau ʻoku ʻi ai hoʻo `pipx`:

```sh
pipx install omi-cli
omi --help
```

ʻE lava foki ke ke fokotuʻu ia ʻi ha ʻātakai Python fakatafito ʻoku ngāue:

```sh
python -m pip install omi-cli
omi --help
```

Kapau ʻoku ʻikai maʻu ʻe he terminal ʻa e `omi`, fakapapauʻi ʻoku ngāue ʻa e ʻātakai fakatafito pe ʻoku ʻi he `$PATH` ʻa e fāila ʻo e `pipx`.

## Fakafekauʻi hoʻo ʻakauni

Kamataʻi ʻa e tokoni fetuʻutaki:

```sh
omi auth login
```

Fili ke hū atu ʻi he browser pe ke fakapipiki ha kī API ʻa e Omi developer. ʻOku fufū ʻe he fakakaukau fetuʻutaki ʻa e kī; fakaʻehiʻehi mei hono tohi ʻi ha tuʻutuʻuni ʻe tauhi ʻi he hisitōlia ʻo e terminal.

Ke ʻalu hangatonu ki he browser:

```sh
omi auth login --browser
```

Hū atu ʻi he komipiuta tatau mo e terminal: ʻoku ʻalu ʻa e tali fakamoʻoni ki he tuʻasila fakalotofonua. Muimui ki he ngaahi fakahinohino ʻi he sikilini.

Hili iá, vakaiʻi ʻa e fokotuʻutuʻu mo e ʻeke API:

```sh
omi auth status
omi auth whoami
```

ʻOku fakahā ʻe he `status` ʻa e tuʻunga fakalotofonua ʻo fufū ʻa e meʻa lilo, ka ʻoku ʻikai te ne vakaiʻi ʻa e ʻaonga ʻi he sēvā. ʻOku fai ʻe he `whoami` ha kole fakamoʻoni; kapau ʻoku ola, ʻoku mahino ʻoku ngāue ʻa e ngaahi fakamaama, ʻikai fakahā ho hingoa.

ʻOku tauhi ʻa e fokotuʻutuʻu ʻi he tuʻunga tatau ʻi he `~/.omi/config.toml`. ʻOua ʻe vahevahe ʻa e fāila ni: ʻe lava ke ʻi ai ha fakamaama fakalilolilo.

## Vakai ki hoʻo lekooti

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

ʻOku faʻa ʻuhinga pē ʻa e lisi ʻoku ʻatā ʻoku ʻikai ha meʻa ʻoku feʻungamālie mo e fekumi. Ngāueʻaki ʻa e tokoni ke kumi ʻa e ngaahi filita ʻo e tuʻutuʻuni kotoa:

```sh
omi memory list --help
omi action-item list --help
```

## JSON mo e ngaahi peesi

Tuku ʻa e filifili fakalūkufua `--json` **ʻi muʻa** ʻi he kulupu tuʻutuʻuni:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

ʻOku kole ʻe he tuʻutuʻuni fuofua ʻa e manatu ʻe 25 fuofua; ʻoku kole ʻe he ua ʻa e 25 hoko. ʻOku ʻikai ko ha tatau kakato ʻa e peesi ʻe taha. ʻOku tauhi ʻe he JSON ʻa e ngaahi fika kakato, ka ʻe lava ke fakanounou ʻe he ngaahi tēpile ʻi he sikilini.

Ke tauhi ha peesi ʻi ha fāila:

```sh
omi --json memory list --limit 25 --offset 0 > manatu-peesi-1.json
```

ʻOku fakatupu pe toe tohi ʻe he fakafolau ni ha fāila fakalotofonua. Fakapapauʻi kuo ʻosi ʻa e tuʻutuʻuni kimuʻa pea ke ngāueʻaki ʻa e meʻa ʻoku ʻi loto. ʻOku tohi ʻa e ngaahi hala ki he tukuakiʻi hala (stderr); ʻoku ʻikai ko ha fakamoʻoni ʻa e fāila ʻatā ʻoku ʻikai ha lekooti. ʻE lava ke ʻi ai ha fakamatala fakataautaha ʻi ha fāila ʻoku ʻave ki tuʻa: tauhi fakalilolilo.

## Hū atu

```sh
omi auth logout
```

ʻOku tamateʻi ʻe he tuʻutuʻuni ni ʻa e ngaahi fakamaama ʻoku tauhi fakalotofonua. Ke fakaʻikai ha kī ʻi he sēvā, ngāueʻaki ʻa e pule ʻo e ngaahi kī developer ʻi hoʻo ʻakauni.

Ki ha ngaahi tuʻutuʻuni mo ha ngaahi filifili kehe, vakai ki he [fakahinohino lahi ʻi he lea faka-Pilitānia](../README.md) mo e `omi --help`.
