# Te mau taahiraa matamua ma omi-cli

Teie aratai e faataa i te mau taahiraa matamua (commands) o omi-cli na roto i te reo Tahiti. E vai noa te mau iʻoa o te mau command e te mau poroi o te porohita i roto i te reo Peretane. Te mau hiʻoraa e faaitehia i ʻonei, ʻaore e taui i tō mau haamanaʻoraa (memories), tō mau paraparauraa (conversations), tō mau ʻohiparaa (action items) e tō mau faaʻiteraa (goals).

## Faʻatupuraʻa

Te mau mea e titauhia: Python 3.10 aore ra te rahi aʻe, e te hoê akaun Omi.

Mai te mea e vai tō `pipx`:

```sh
pipx install omi-cli
omi --help
```

E nehenehe atoa e faʻatupu i roto i te hoê Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Mai te mea ʻaore te terminal e ite i te `omi`, ʻa haapapū e te ohipa ra te virtual environment aore ra e vai te `pipx` putuputuraa i roto i te `$PATH`.

## Tāmau i tō akaun

Haamata i te tauturu:

```sh
omi auth login
```

Māʻiti i te tomo na roto i te browser aore ra i te faaô i te Omi developer API key. Te tomo e huna i te key; ʻaore e papaʻi i te key i roto i te command e vai i roto i te terminal history. Tomo atu i te browser:

```sh
omi auth login --browser
```

Tomo i roto i te hoê roro uira hoê â e te terminal: te authentication e haere i te local address. A pee i te mau faaue i niʻa i te hohoʻa.

I muri iho, hiʻopoi i te configuration e te API:

```sh
omi auth status
omi auth whoami
```

`status` e faaite i te huru o te vahi e e huna i te secret, tera rā ʻaore e hiʻopoi i te server. `whoami` e rave i te hoê authenticated request; mai te mea e manuia, e papū e te ohipa ra te credentials. Te configuration e vai i roto i `~/.omi/config.toml`. ʻAore e faaite: private credentials.

## Hiʻopoi i tō mau ʻōrama

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Te tabula ʻore e faaite noa e ʻaore e mea i roto. A faaohipa i te tauturu no te mau filter:

```sh
omi memory list --help
omi action-item list --help
```

## JSON e te mau ʻapi

A tuu i te `--json` **i mua** i te command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Te command matamua e ani i te 25; te piti e ani i te 25 e pee mai. Te hoê ʻapi ʻaore e kopi taatoa. JSON e tiai i te mau numera; te mau ʻapi i niʻa i te hohoʻa e nehenehe e poto.

I roto i te hoê puta:

```sh
omi --json memory list --limit 25 --offset 0 > memories-api-1.json
```

Te command e oti. Errors i roto i te stderr; puta ʻore e data. Private.

## Faaoti

```sh
omi auth logout
```

Local credentials. Developer key.

[Peretane](../README.md) e `omi --help`.
