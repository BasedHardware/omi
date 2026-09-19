# Tutuhon Ha'u-nia omi-cli

Matenek-na'in ne'e esplika komandu sira primeiru iha lian Tetun. Naran komandu nian
ho mensajen husi programa kontinua nafatin iha lian Inglés. Ezemplu husu sira ne'e
la troka ita-boot nia memória, konversasaun, knaar, ka objetivu sira.

## Instala programa

Presiza: Python 3.10 ka foun liu no konta Omi ida.

Se ita-boot instala ona `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mós bele instala iha ambiente virtuál (virtual environment) Python nian ne'ebé ativu:

```sh
python -m pip install omi-cli
omi --help
```

Se terminál la hetan `omi`, haree se ambiente virtuál ativu ka pasta `pipx` nian iha variável `PATH`.

## Ligasaun ba ita-boot nia konta

Lansa asisténsia interativu:

```sh
omi auth login
```

Hili atu tama liuhusi navegadór (browser) ka kela xave API dezenvolvedór Omi.
Tama ho modu interativu sei subar xave; labele hakerek iha komandu ne'ebé bele hela iha istória terminál nian.

Atu bá direta ba navegadór:

```sh
omi auth login --browser
```

Tama iha komputadór hanesan ne'ebé terminál funsiona bá. Tuir instrusaun iha ekrã.

Depois, verifika konfigurasaun no asesu ba API:

```sh
omi auth status
omi auth whoami
```

`status` hatudu estadu lokál no subar segredu. `whoami` haruka pedidu ida ne'ebé konfirma xave funsiona duni.

Konfigurasaun rai baibain iha `~/.omi/config.toml`. Keta fahe arkivu ne'e.

## Esplora ita-boot nia dadus

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lista mamuk bele dehan katak la iha dadus ne'ebé hanesan ho pedidu. Uza ajuda atu haree filtru:

```sh
omi memory list --help
omi action-item list --help
```

## Download JSON no pájina sira

Tau opsaun globál `--json` **molok** grupu komandu:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Komandu primeiru husu memória 25 primeiru; segundu husu 25 tuirmai. JSON rai ID kompletu sira.

Atu rai pájina ida iha arkivu:

```sh
omi --json memory list --limit 25 --offset 0 > memoria-pajina-1.json
```

Arkivu ne'e bele iha informasaun privadu: rai ho segredu.

## Sai (Logout)

```sh
omi auth logout
```

Komandu ne'e hamoos dadus tama nian husi lokál.

Ba komandu seluk, haree [matadalan prinsipál iha lian Inglés](../README.md) no `omi --help`.
