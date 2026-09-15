# Brzi vodič za omi-cli

## Instalacija

```bash
pip install omi-cli
```

## Prijava

```bash
omi auth login
```

Otvorit će se preglednik za prijavu putem vašeg računa.

## Osnovne naredbe

### Prikaz razgovora

```bash
omi conversation list
```

### Prikaz određenog razgovora

```bash
omi conversation get <id_razgovora>
```

### Pretraživanje razgovora

```bash
omi conversation search "upit za pretraživanje"
```

## Napredne mogućnosti

### Filtriranje prema ograničenju

```bash
omi conversation list --limit 10
```

### Uključivanje transkripata

```bash
omi conversation list --include-transcript
```

### Izvoz u JSON format

```bash
omi conversation list --json
```

### Straničenje

```bash
omi conversation list --limit 50 --offset 100
```

## Odjava

```bash
omi auth logout
```

## Pomoć

```bash
omi --help
omi conversation --help
```

## Resursi

- [Dokumentacija](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
