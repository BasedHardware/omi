# Begin met omi-cli

Hierdie gids verduidelik die eerste opdragte in Afrikaans. Die name van die opdragte en die stelselboodskappe bly in Engels. Die navraagvoorbeelde hier wysig nie jou herinneringe, gesprekke, aksie-items of doelwitte nie.

## Installeer die program

Vereistes: Python 3.10 of nuwer en 'n Omi-rekening.

As jy `pipx` geinstalleer het:

```sh
pipx install omi-cli
omi --help
```

Alternatiewelik kan jy dit binne 'n geaktiveerde Python virtuele omgewing installeer:

```sh
python -m pip install omi-cli
omi --help
```

As die terminaal nie `omi` vind nie, maak seker dat die virtuele omgewing aktief is of dat die gids waar `pipx` sy uitvoerbare leers plaas in jou `PATH` is.

## Koppel jou rekening

Om met jou e-posadres en wagwoord aan te meld:

```sh
omi auth login --api-key <jou-sleutel>
```

Jy kan ook die omgewingsveranderlike `OMI_API_KEY` direk stel:

```sh
export OMI_API_KEY="jou-toegangskode"
omi auth status
```

## Raadpleeg jou data

Bekyk jou herinneringe (memories):

```sh
omi memory list
```

Raadpleeg jou gesprekke (conversations):

```sh
omi conversation list
```

Raadpleeg jou aksie-items (action items):

```sh
omi action-item list
```

## Verkry JSON en blaai deur bladsye

`omi-cli` ondersteun JSON-uitvoer vir outomatiese verwerking:

```sh
omi --json memory list
omi memory list --limit 10 --offset 0
```

## Teken uit

Om jou plaaslike sessie veilig te beeindig:

```sh
omi auth logout
```
