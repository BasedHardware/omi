# Tallaabooyinka ugu Horeeya ee omi-cli

Hagahan wuxuu sharxayaa amarrada ugu horreeya ee af Soomaali ah. Magacyada
amarrada iyo farriimaha barnaamijku waxay ahaanayaan Ingiriis. Tusaalooyinka
weydiinta ee halkan ku yaal waxba kama beddelaan xusuustaada, wada hadalladaada,
hawlahaaga, ama yoolalkaaga.

## Rakibidda barnaamijka

Shuruudaha: Python 3.10 ama nooc ka dambeeya iyo akoon Omi ah.

Haddii aad leedahay `pipx` oo rakiban:

```sh
pipx install omi-cli
omi --help
```

Haddii kale, waxaad ku rakibi kartaa gudaha deegaan dalwaddii Python
oo shaqeynaya (activated virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Haddii terminal-ku waayo `omi`, hubi in deegaanka dalwaddii uu shaqeynayo
ama dariiqa `pipx` ku rakibo faylashan uu ku jiro `PATH`-kaaga.

## Isku xirka akoonkaaga

Bilow caawiyaha is-dhexgalka (interactive assistant):

```sh
omi auth login
```

Dooro inaad ka gasho biraawsarka (browser) ama doorashada inaad dhajiso
furaha API (developer API key) ee Omi. Gelitaanka is-dhexgalka wuxuu qariyaa
furaha; ka fogow inaad ku qorto amar ku hadhaya taariikhda terminal-ka.

Si toos ah biraawsarka ugu gudub:

```sh
omi auth login --browser
```

Ka gal isla kombiyuutarka uu terminal-ku ku yaal: jawaabta xaqiijintu
waxay isticmaashaa cinwaan maxalli ah. Raac tilmaamaha ka muuqda shaashadda.

Ka dib, xaqiiji qaabeynta iyo marin-u-helka API:

```sh
omi auth status
omi auth whoami
```

`status` wuxuu muujinayaa xaaladda maxalliga ah wuuna qariyaa sirta, laakiin
ma hubiyo ansaxnimada server-ka. `whoami` wuxuu diraa codsi la xaqiijiyay;
haddii uu guuleysto, wuxuu xaqiijinayaa inay shaqeynayaan aqoonsiyadaadu,
iyadoo aan loo baahnayn in magacaaga la muujiyo.

Qaabeynta waxaa si toos ah loogu keydiyaa `~/.omi/config.toml`. Ha la wadaagin
faylkan dadka kale: waxa ku jiri kara aqoonsigaaga sirta ah.

## La tashiga xogtaada

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Liis madhan waxay si fudud uga dhigan kartaa inaysan jirin wax u dhigma
weydiintaada. Isticmaal caawinta si aad u ogaato shaandhooyinka amar kasta:

```sh
omi memory list --help
omi action-item list --help
```

## Helitaanka JSON iyo bogagga dhex socodka

Dhig ikhtiyaarka guud ee `--json` **kahor** kooxda amarka:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Amarka koowaad wuxuu weydiisanayaa 25-ka xusuusood ee ugu horreeya; kan labaadna,
25-ka xiga. Hal bog sidaas darteed ma aha koobi buuxa oo kayd ah (full backup).
Soo-saarka JSON wuxuu ilaaliyaa aqoonsiyada buuxa, halka miisaska shaashaddu
ay gaabin karaan si loo muujiyo.

Si bog loogu keydiyo fayl:

```sh
omi --json memory list --limit 25 --offset 0 > xusuus-bog-1.json
```

Dib-u-hagaajintani waxay abuurtaa ama beddeshaa faylka maxalliga ah. Hubi in
amarku si guul leh u dhammaaday ka hor intaadan isticmaalin waxa ku jira.
Khaladaadka waxaa lagu qoraa meesha khaladaadka loogu talagalay (stderr);
fayl madhan ma dammaanad qaadayo inaysan xog jirin. Faylka la dhoofiyay waxaa
ku jiri kara macluumaad shakhsiyeed: ka dhig mid qarsoodi ah.

## Ka bixidda akoonka (Logout)

```sh
omi auth logout
```

Amarkani wuxuu tirtirayaa aqoonsiyada maxalliga ah ee la keydiyay. Si aad
u joojiso furaha API ee server-ka, isticmaal maamulka furayaasha horumariyaha
ee akoonkaaga.

Wixii amarro dheeraad ah iyo ikhtiyaarro horumarsan, eeg
[hagaha ugu weyn ee Ingiriiska](../README.md) iyo `omi --help`.
