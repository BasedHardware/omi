# Rychlý průvodce omi-cli

## Instalace

```bash
pip install omi-cli
```

## Přihlášení

```bash
omi auth login
```

Otevře se prohlížeč pro přihlášení pomocí vašeho účtu.

## Základní příkazy

### Zobrazení konverzací

```bash
omi conversation list
```

### Zobrazení konkrétní konverzace

```bash
omi conversation get <id_konverzace>
```

### Vyhledávání v konverzacích

```bash
omi conversation search "vyhledávací dotaz"
```

## Pokročilé možnosti

### Filtrování podle limitu

```bash
omi conversation list --limit 10
```

### Zahrnutí přepisů

```bash
omi conversation list --include-transcript
```

### Export do formátu JSON

```bash
omi conversation list --json
```

### Stránkování

```bash
omi conversation list --limit 50 --offset 100
```

## Odhlášení

```bash
omi auth logout
```

## Nápověda

```bash
omi --help
omi conversation --help
```

## Zdroje

- [Dokumentace](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
