# Prěnje kroki z omi-cli

Tuta přiručka wujasnja prěnje přikazy (commands) omi-cli w hornjoserbšćinje. Mjena přikazow a zdźělenki programa wostanu w jendźelšćinje. Přikłady pytanja, kotrež so tu pokazuja, njezměnjau waše spomni (memories), waše rozmołwy (conversations), waše nadawki (action items) ani waše cile (goals).

## Instalacija

Trěbne: Python 3.10 abo nowši, a konto Omi.

Jeli maš `pipx`:

```sh
pipx install omi-cli
omi --help
```

Móžeš jón tež do aktiwneho Pythonoweho wirtualneho wokrjesa instalować:

```sh
python -m pip install omi-cli
omi --help
```

Jeli terminal `omi` njenamaka, zawěsć, zo wirtualny wokrjes dźěła abo zo je rjadowak `pipx` w `$PATH`.

## Zwjazaj swój konto

Započni interaktiwneho pomocnika:

```sh
omi auth login
```

Wubjer přizjewjenje přez wobhladowak abo zasadźenje kluca API wuwiwarja Omi. Interaktiwne zapodaće kluc schowa; wobeń kluc do přikaza pisać, kotryž so w stawiznach terminala wobchowa.

Zo by direktnje k wobhladowakej šoł:

```sh
omi auth login --browser
```

Přizjew so na samsnym kompjuterje kaž terminal: wotmołwa awtentifikacije dźe k lokalnej adresy. Slěduj pokiwy na wobrazowce.

Potom přepruwuj konfiguraciju a API-přistup:

```sh
omi auth status
omi auth whoami
```

`status` pokazuje lokalny status a schowa tajne, ale njepřepruwuje płaćiwosć na serwerje. `whoami` sćele awtentifikowany naprašowanje; jeli so poradźi, je jasne, zo přistupne daty dźěłaja, bjez to, zo by so twoje mjeno pokazało.

Konfiguracija so po standardźe w `~/.omi/config.toml` wobchowa. Njedźěl tutu dataju: móže privátne přistupne daty wobsahować.

## Přehladaj swoje daty

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Prózdna lisćina zwjetša jenož woznamjenja, zo ničo pytanju njewotpowěduje. Wužij pomoc, zo by filtry kóždeho přikaza namakał:

```sh
omi memory list --help
omi action-item list --help
```

## JSON a strony

Staj globalnu opciju `--json` **před** přikaznej skupinu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Prěni přikaz sej 25 prěnich spomni wupraji; druhi přichodne 25. Jedna strona dospołna kopija njeje. JSON-wudaće cyłe ličby wobchowa, mjeztym tabelki na wobrazowce móža je skrótšić.

Zo by stronu do dataje składował:

```sh
omi --json memory list --limit 25 --offset 0 > spomni-strona-1.json
```

Tute dalesposrědkowanje lokalnu dataju wutwori abo přepisuje. Zawěsć, zo přikaz je hotowy, prjedy hač wobsah wužiwaš. Zmylki so do zmylkoweho wudaća (stderr) pisa; prózdna dataja doklad za to njeje, zo daty njejsu. Eksportowana dataja móže wosobne informacije wobsahować: wobchowaj ju privatnje.

## Wotzjewjenje

```sh
omi auth logout
```

Tutón přikaz wušmórnje lokalnje składowane přistupne daty. Zo by kluc na serwerje znjemóžnił, wužij rjadowanje wuwiwarskich klucow w swojim kontom.

Za dalše přikazy a opcije hlej [hlownu přiručku w jendźelšćinje](../README.md) a `omi --help`.
