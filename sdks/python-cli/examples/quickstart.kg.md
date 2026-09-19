# Bandisa na omi-cli

Mukanda yai ketendula bansiku ya ntete na Kikongo. Bazina ya bansiku ti bansangu ya
programe bikala na Kingelesi. Bambandu yai lenda soba ve ba souvenir, masolo,
bisalu to balukanu na nge.

## Kutula Programe

Bima ya mfunu: Python 3.10 to ya mpa ti konte ya Omi.

Kana nge kele na `pipx`:

```sh
pipx install omi-cli
omi --help
```

Nge lenda tula mpe na kati ya kisika ya kisalu ya Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Kana terminal kemona `omi` ve, tala kana `pipx` kele na kati ya `$PATH` na nge.

## Kangisa Konte na Nge

Yantika lusadisu:

```sh
omi auth login
```

Pona kukota na browser to tula API key ya Omi.
Kukota na mutindu yai kesweka key; kusonika ve na nsiku yina lenda bikala na lisolo ya terminal.

Sambu na kukwenda mbala mosi na browser:

```sh
omi auth login --browser
```

Kota na ordinatere ya kiteso mosi yina terminal kesala. Landa bansangu na ekran.

Na nima, tala mambu ya kutula ti kukota na API:

```sh
omi auth status
omi auth whoami
```

`status` kemonisa kiteso ya ordinatere mpe kesweka kinsweki. `whoami` kendimisa nde key kesala mbote.

Bima yonso kele na `~/.omi/config.toml`. Kabula ve dosie yai sambu kele na bansweki.

## Tala Bansangu na Nge

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mukanda ya pamba ketendula nde kima kele ve. Sadila lusadisu:

```sh
omi memory list --help
omi action-item list --help
```

## Baka JSON ti Balukasa (Pagination)

Tula `--json` **na ntwala** ya nsiku:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Nsiku ya ntete kelomba ba souvenir 25 ya ntete; ya zole kelomba 25 ya kelanda. JSON kebikisa ba ID yonso.

Sambu na kubumba lukasa na dosie:

```sh
omi --json memory list --limit 25 --offset 0 > souvenir-lukasa-1.json
```

Dosie yai lenda vanda na bansangu ya muntu yandi mosi: bumba na kinsweki.

## Kubasika (Logout)

```sh
omi auth logout
```

Nsiku yai kekatula key na ordinatere na nge. Sambu na kukatula key na server, kota na kisika ya developer key na konte na nge.

Sambu na bansiku ya nkaka, tala [mukanda ya Kingelesi](../README.md) ti `omi --help`.
