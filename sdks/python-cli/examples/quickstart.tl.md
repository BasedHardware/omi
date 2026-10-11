# Mga Unang Hakbang gamit ang omi-cli

Ipinapaliwanag ng gabay na ito ang mga unang utos (commands) sa Tagalog. Ang
mga pangalan ng utos at mga mensahe ng programa ay nananatiling nasa Ingles.
Ang mga halimbawa ng query na ipinapakita dito ay hindi nagbabago sa iyong mga
alaala (memories), pag-uusap (conversations), gawain (action items), o mga
layunin (goals).

## Pag-install ng programa

Mga Kinakailangan: Python 3.10 o mas bagong bersyon at isang Omi account.

Kung mayroon kang `pipx` na naka-install:

```sh
pipx install omi-cli
omi --help
```

Bilang alternatibo, maaari mo itong i-install sa loob ng isang aktibong Python
virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Kung hindi mahanap ng terminal ang `omi`, tiyaking aktibo ang virtual environment
o ang direktoryo kung saan nag-i-install ang `pipx` ay nasa iyong `PATH`.

## Pagkonekta sa iyong account

Simulan ang interactive assistant:

```sh
omi auth login
```

Pumili sa pag-log in sa pamamagitan ng browser o ang opsyon na i-paste ang isang
Omi developer API key. Itinatago ng interactive input ang key; iwasang isulat
ito sa isang utos na mananatili sa kasaysayan ng terminal.

Upang direktang pumunta sa browser:

```sh
omi auth login --browser
```

Mag-log in sa parehong kompyuter kung saan tumatakbo ang terminal: gumagamit ang
tugon ng authentication ng isang lokal na address. Sundin ang mga tagubilin sa
screen.

Pagkatapos nito, i-verify ang configuration at access sa API:

```sh
omi auth status
omi auth whoami
```

Ipinapakita ng `status` ang lokal na kalagayan at itinatago ang lihim, ngunit
hindi nito sinusuri ang validity sa server. Ang `whoami` ay gumagawa ng isang
authenticated na kahilingan; kung matagumpay, kinukumpirma nito na gumagana ang
mga kredensyal, nang hindi kinakailangang ipakita ang iyong pangalan.

Naka-save ang configuration bilang default sa `~/.omi/config.toml`. Huwag
ibahagi ang file na ito: maaari itong maglaman ng iyong mga kumpidensyal na
kredensyal.

## Pagsusuri sa iyong data

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ang isang walang lamang listahan ay maaaring mangahulugan lamang na walang mga
item na tumutugma sa query. Gamitin ang tulong upang matuklasan ang mga filter
ng bawat utos:

```sh
omi memory list --help
omi action-item list --help
```

## Pagkuha ng JSON at pag-navigate sa mga pahina

Ilagay ang pandaigdigang opsyon na `--json` **bago** ang grupo ng utos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Hinihiling ng unang utos ang unang 25 alaala; ang pangalawa, ang susunod na 25.
Ang isang pahina ay hindi isang kumpletong backup. Pinapanatili ng output ng JSON
ang buong mga identifier, habang maaaring paikliin ng mga talahanayan sa screen
ang mga ito para sa pagpapakita.

Upang mag-save ng isang pahina sa isang file:

```sh
omi --json memory list --limit 25 --offset 0 > mga-alaala-pahina-1.json
```

Ang pag-redirect na ito ay lumilikha o pumapalit sa lokal na file. Tiyaking
matagumpay na natapos ang utos bago gamitin ang nilalaman nito. Ang mga error ay
isinusulat sa error output (stderr); ang isang walang laman na file ay hindi
naggagarantiya na walang data. Ang na-export na file ay maaaring maglaman ng
personal na impormasyon: panatilihin itong pribado.

## Pag-log out sa account (Logout)

```sh
omi auth logout
```

Tinatanggal ng utos na ito ang mga kredensyal na naka-save nang lokal. Upang
magpawalang-bisa ng key sa server, gamitin ang pamamahala ng developer key sa
iyong account.

Para sa iba pang mga utos at advanced options, tingnan ang
[pangunahing gabay sa Ingles](../README.md) at `omi --help`.
