# Pasu primeiru ho omi-cli

Guia ida ne'e esplika pasu primeiru (commands) husi omi-cli iha Tetun. Naran commands no mensajen programa nian sei hela iha Ingles. Ezemplu buka ne'ebé hatudu iha ne'e la troka ita-nia memória (memories), konversasaun (conversations), serbisu (action items) ka objetivu (goals).

## Instalasaun

Presiza: Python 3.10 ka foun liu, no konta Omi ida.

Se iha `pipx`:

```sh
pipx install omi-cli
omi --help
```

Mós bele instala iha ambiente virtual Python ne'ebé ativu:

```sh
python -m pip install omi-cli
omi --help
```

Se terminal la hetan `omi`, asegura katak ambiente virtual ativu ka pasta `pipx` iha `$PATH`.

## Liga ita-nia konta

Hahú asistente interativu:

```sh
omi auth login
```

Hili tama liu husi browser ka tau API key Omi developer. Input interativu subar key; evita hakerek key iha commands ne'ebé sei rai iha históriu terminal.

Atu bá diretamente ba browser:

```sh
omi auth login --browser
```

Tama iha komputador hanesan ho terminal: resposta autentikasaun bá ba enderesu lokal. Tuir instrusaun iha ekrán.

Depois, verifika konfigurasaun no asesu API:

```sh
omi auth status
omi auth whoami
```

`status` hatudu kondisaun lokal no subar segredu, maibé la verifika validade iha servidór. `whoami` halo pedidu autentikadu; se susesu, klaru katak kredensiál sira funsiona, la hatudu ita-nia naran.

Konfigurasaun rai hanesan default iha `~/.omi/config.toml`. La fahe file ida ne'e: bele iha kredensiál privadu.

## Haree ita-nia dadus

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Lista mamuk normalmente signifika de'it la iha buat ne'ebé koresponde ho buka. Uza ajuda atu hetan filtru ba komanda ida-idak:

```sh
omi memory list --help
omi action-item list --help
```

## JSON no pájina

Tau opsaun globál `--json` **antes** grupu komanda:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Komanda primeiru husu memória 25 primeiru; ida segundu husu 25 tuir mai. Pájina ida la'ós kópia kompletu. JSON rai númeru tomak, maibé tabela iha ekrán bele badak sira.

Atu rai pájina ida iha file:

```sh
omi --json memory list --limit 25 --offset 0 > memória-pájina-1.json
```

Redirect ida ne'e kria ka hakerek foun file lokal. Asegura katak komanda remata antes uza konteúdu. Erru hakerek ba output erru (stderr); file mamuk la'ós prova katak la iha dadus. File esportadu bele iha informasaun pesoál: rai privadu.

## Sai

```sh
omi auth logout
```

Komanda ida ne'e hamoos kredensiál ne'ebé rai lokal. Atu invalida key iha servidór, uza jestaun key developer iha ita-nia konta rasik.

Atu komanda no opsaun seluk, haree [guia prinsipál iha Ingles](../README.md) no `omi --help`.
