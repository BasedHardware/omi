# Komencante per omi-cli

Tiu cxi gvidilo klarigas la unuajn komandojn en Esperanto. La nomoj de la komandoj kaj la mesagxoj de la programo restas en la angla.

## Instali la programon

Postuloj: Python 3.10 aux pli nova versio kaj konto de Omi.

```sh
pipx install omi-cli
omi --help
```

Alternative:

```sh
python -m pip install omi-cli
omi --help
```

## Konekti vian konton

```sh
omi auth login --api-key <via-ŝlosilo>
```

Aux per OMI_API_KEY:

```sh
export OMI_API_KEY="via-alirkodo"
omi auth status
```

## Konsulti viajn datumojn

```sh
omi memory list
omi conversation list
omi action-item list
```

## Akiri JSON kaj navigi tra la pagxoj

```sh
omi --json memory list
omi memory list --limit 10 --offset 0
```

## Elsaluti

```sh
omi auth logout
```
