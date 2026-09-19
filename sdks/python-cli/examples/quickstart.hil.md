# Mga Una nga Tikang gamit ang omi-cli

Ginasaysay sang sini nga giya ang mga una nga mando (commands) sa pulong nga Hiligaynon (Ilonggo). Ang mga ngalan sang mando kag mga mensahe sang programa nagapabilin sa Ingles. Ang mga halimbawa sang pagpamangkot (query) nga ginapakita diri wala nagabag-o sang imo mga handumanan (memories), paghambalanay (conversations), mga hilikuton (action items), ukon mga tinutuyo (goals).

## Pag-instalar sang programa

Mga Kinahanglanon: Python 3.10 ukon mas bag-o nga bersyon kag isa ka Omi account.

Kon may yara ka sang `pipx` nga na-instalar:

```sh
pipx install omi-cli
omi --help
```

Bilang alternatibo, sarang mo ini ma-instalar sa sulod sang isa ka aktibo nga Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Kon indi makit-an sang terminal ang `omi`, pat-ura nga aktibo ang virtual environment ukon ang direktoryo sa diin nagabutang ang `pipx` sang mga executable files yara sa imo `$PATH`.

## Pagkonektar sang imo account

Sugiri ang interactive assistant:

```sh
omi auth login
```

Magpili sa tunga sang pag-log in paagi sa browser ukon ang opsyon nga i-paste ang isa ka Omi developer API key. Ginatago sang interactive input ang key; likawi ang pagsulat sini sa isa ka mando nga mabilin sa maragtas (history) sang terminal.

Agud direkta nga magkadto sa browser:

```sh
omi auth login --browser
```

Mag-log in sa amo man nga kompyuter sa diin nagadalagan ang terminal: nagagamit ang sabat sang authentication sang isa ka lokal nga address. Sunda ang mga panuytoy sa screen.

Pagkatapos sini, usisaa ang configuration kag pag-access sa API:

```sh
omi auth status
omi auth whoami
```

Ginapakita sang `status` ang lokal nga kahimtangan kag ginatago ang sekreto, apang wala ini nagasusi sang validity sa server. Ang `whoami` nagahimo sang isa ka authenticated nga pagpangabay; kon madinalag-on, ginakompirmar sini nga nagapanghikot ang mga kredensyal, nga wala nagakinahanglan nga ipahayag ang imo ngalan.

Naka-save ang configuration bilang default sa `~/.omi/config.toml`. Indi pag-ipamahagi ini nga file: mahimo nga may unod ini sang imo kompidensyal nga mga kredensyal.

## Pagsusi sang imo data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ang isa ka blangko nga listahan mahimo nga nagakahulugan lamang nga wala sang mga butang nga nagasibu sa pamangkot. Gamita ang bulig agud matukiban ang mga filter sang tagsa ka mando:

```sh
omi memory list --help
omi action-item list --help
```

## Pagkuha sang JSON kag pag-navigate sa mga pahina (Pagination)

Ibutang ang pangkabilugan nga opsyon nga `--json` **sa wala pa** ang grupo sang mando:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ginatinguhaan sang una nga mando ang una nga 25 ka mga handumanan; ang ikaduha, ang masunod nga 25. Ang isa ka pahina indi isa ka bug-os nga backup. Ginatipigan sang output sang JSON ang bug-os nga mga identifier, samtang mahimo nga palip-uton sang mga lamesa sa screen ini para sa pagpakita.

Agud mag-save sang isa ka pahina padulong sa isa ka file:

```sh
omi --json memory list --limit 25 --offset 0 > mga-handumanan-pahina-1.json
```

Ini nga pag-redirect nagatuga ukon nagailis sang lokal nga file. Pat-ura nga madinalag-on nga natapos ang mando antes gamiton ang unod sini. Ang mga sala (errors) ginasulat sa error output (stderr); ang isa ka blangko nga file indi garantiya nga wala sang data. Ang na-export nga file mahimo nga may unod sang personal nga impormasyon: tipigi ini nga pribado.

## Pag-log out sa account (Logout)

```sh
omi auth logout
```

Ginakuha sini nga mando ang mga kredensyal nga ginatipigan sa lokal nga paagi. Agud magpawalay-bili sang isa ka key sa server, gamita ang pagdumala sang developer key sa imo account.

Para sa iban pa nga mga mando kag abante nga mga opsyon, tan-awa ang [pangunang giya sa Ingles](../README.md) kag `omi --help`.
