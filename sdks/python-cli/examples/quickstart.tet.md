# Hahú uza omi-cli

Manoik ida-ne'e hatudu mandamentu dahuluk sira iha lian Tetun. Naran mandamentu nian no mensajen sistema nian sei kontinua iha lian Inglés. Ezemplu lektura ne'ebé fó iha ne'e sei la muda ita-boot nia memória, konversasaun, lista asaun ka meta sira.

## Instala programa

Rekizitu: Python 3.10 ka foun liu no konta Omi ida.

> Atensaun: Naran pakote nian iha PyPI mak **`omi-cli`**, enkuantu mandamentu ne'ebé halai depois de instalasaun mak **`omi`**. Iha pakote seluk ne'ebé la iha ligasaun ho naran `omi` iha PyPI — keta instala pakote ne'e.

Se `pipx` instala ona:

```sh
pipx install omi-cli
omi --help
```

Alternativa seluk, iha ambiente virtuál Python ne'ebé ativu:

```sh
python -m pip install omi-cli
omi --help
```

Se terminál la hetan `omi`, haree se ambiente virtuál ativu ka diretóriu `pipx` iha ita-boot nia `PATH`.

## Ligasaun ita-boot nia konta

Hahú asistente interativu:

```sh
omi auth login
```

Hili atu tama liu husi navegadór, ka hili opsaun atu hatama xave API dezenvolvedór Omi nian. Hatama interativu subar xave ne'e; keta hakerek xave iha mandamentu ne'ebé sei hela iha istória terminál nian.

Atu tama direta liu husi navegadór:

```sh
omi auth login --browser
```

Kompleta entrada iha komputadór hanesan ne'ebé terminál halai ba, tanba autentikasaun fila fali ba diresaun lokál. Tuir instrusaun iha ekrã.

Depois de ne'e, verifika konfigurasaun no asesu API:

```sh
omi auth status
omi auth whoami
```

`status` hatudu kondisaun lokál no subar segredu sira, maibé la verifika ho servidór. `whoami` haruka pedidu ida ne'ebé hetan autorizasaun; susesu katak ita-boot nia kredensiál sira funsiona ho loloos.

Konfigurasaun rai de'it iha `~/.omi/config.toml`. Keta fahe arkivu ida-ne'e tanba iha ita-boot nia kredensiál privadu sira.

## Haree ita-boot nia dadus

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lista mamuk bele signifika de'it katak la iha item ne'ebé hanesan ho pergunta ne'e. Atu hatene filtru husi mandamentu ida, haree ajuda:

```sh
omi memory list --help
omi action-item list --help
```

## Hetan JSON no troka pájina sira

Tau opsaun globál `--json` **molok** grupu mandamentu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Mandamentu dahuluk husu rejistu 25 primeiru; mandamentu daruak husu 25 tuirmai. Tanba ne'e pájina ida la'ós kópia seguransa kompletu. Rezultadu JSON rai identifikadór kompletu sira, maibé tabela sira bele habadak.

Atu rai pájina ida iha arkivu ida:

```sh
omi --json memory list --limit 25 --offset 0 > memoria-pajina-1.json
```

Rediresaun ida-ne'e kria ka troka arkivu lokál ida. Molok uza konteúdu, haree se mandamentu ne'e susesu duni. Erru sira hakerek iha stderr; arkivu mamuk la'ós prova katak la iha dadus. Arkivu ne'e bele iha informasaun pesoál: rai seguru.

## Sai (Log out)

```sh
omi auth logout
```

Mandamentu ida-ne'e hasai kredensiál sira ne'ebé rai iha lokál. Atu kansela xave iha servidór, uza jestaun xave dezenvolvedór iha ita-boot nia konta.

Ba mandamentu seluk no opsaun avansadu sira, favor haree gia prinsipiál iha lian Inglés:
[../README.md](../README.md) no `omi --help`.
