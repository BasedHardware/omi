# Prědne kšace z omi-cli

Toś ten pśewodnik wujasnja prědne pśikaze z omi-cli w dolnoserbšćinje. Mena pśikazow a zdźělenja programa wóstanu w engelšćinje. Pśikłady w tom pśewodniku njeměnjaju waše dopomnjeśa (memories), rozgrony (conversations), akciske dypki (action items) ani cile (goals).

## Instalacija

Zawiski: Python 3.10 abo nowšy a konto Omi.

Jolic `pipx` jo zainstalowany:

```sh
pipx install omi-cli
omi --help
```

Alternatiwnje móžośo jen w aktiwnem wirtuelnem wobswěśe Pythona instalowaś:

```sh
python -m pip install omi-cli
omi --help
```

Jolic terminal `omi` njenamaka, kontrolujśo, lěc jo wirtuelne wobswěśe aktiwne abo lěc jo katalog pipx w `$PATH`.

## Zezwězajśo swójo konto

Startujśo interaktiwny asistent pśizjewjenja:

```sh
omi auth login
```

Wubjeŕśo pśizjewjenje pśez wobglědowak abo pśez zasajźenje API-kluca wuwiwarja Omi. Interaktiwne pśizjewjenje schowa waš kluc; njewóstajśo jen w historiji terminala.

Aby so direktnje pśez wobglědowak pśizjewiś:

```sh
omi auth login --browser
```

Pśizjewśo so na samem kompjuterje, na kótaremž terminal běžy: wótegrono awtorizacije wužywa lokalnu adresu. Slědujśo instrukcijam na ekranje.

Pótom kontrolujśo konfiguraciju a API-kluc:

```sh
omi auth status
omi auth whoami
```

`status` pokazujo lokalny status a schowawa sekrety, ale njepśeglědujo płaśiwosć na serwerje. `whoami` cyni napšašowanje z awtorizaciju; jolic se to radźi, wobkšuśijo, až waše pśistupne daty funkcioněruju, a njepokazujo wašo mě.

Konfiguracija se zwětšego w `~/.omi/config.toml` składujo. Njepódajśo toś ten dataj datalej: móžo se w nim loginowe sekrety namakaś.

## Wobglědowanje datow

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prozny lisćik móžo jadnorje wóznamjeniś, až daty napšašowanjeju wótpowědujuce njejsu. Aby spóznał dostupne filtry kuždego pśikaza, zawoglědajśo do pomocy:

```sh
omi memory list --help
omi action-item list --help
```

## JSON-wudaśe a stronicowanje

Stajśo globalnu opciju `--json` **pśed** kupku pśikazow:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prědny pśikaz se wó prědnych 25 dopomnjeśow pšaša; drugi wó pśiduce 25. Jaden bok njejo dopołne zachowanje. JSON-wudaśe se wšykne identifikatory wobchowujo, a tabele na ekranje mógu je za wobglědowanje skrotkiś.

Aby jaden bok do dataje zachował:

```sh
omi --json memory list --limit 25 --offset 0 > dopomnjeśa-bok-1.json
```

Toś to pśesměrowanje lokalnu dataju twóri abo pśepisujo. Pśed wužywanim wopśimjeśa kontrolujśo, lěc jo se pśikaz wuspěšnje skóńcył. Zmólki se do stderr pšisu; prozna dataja njeda garantiju, až datow njejo. Eksportowane dataje mógu wósobne daty wopśimowaś: źaržćo je w tajnosći.

## Wótzjewjenje

```sh
omi auth logout
```

Toś ten pśikaz wulašujo lokalnje składone pśistupne daty. Aby kluc na serwerje wótwółał, wužyjśo zastojanje klucow wuwiwarja w swójom konśe.

Za dalšne pśikaze a rozšyrjone opcije zawoglědajśo do [engelskego głownego pśewodnika](../README.md) a `omi --help`.
