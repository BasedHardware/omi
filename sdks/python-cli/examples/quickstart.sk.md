# Rýchly sprievodca omi-cli

## Inštalácia

```bash
pip install omi-cli
```

## Prihlásenie

```bash
omi auth login
```

Otvorí sa prehliadač na prihlásenie pomocou vášho účtu.

## Základné príkazy

### Zobrazenie konverzácií

```bash
omi conversation list
```

### Zobrazenie konkrétnej konverzácie

```bash
omi conversation get <id_konverzácie>
```

### Vyhľadávanie v konverzáciách

```bash
omi conversation search "vyhľadávací dopyt"
```

## Pokročilé možnosti

### Filtrovanie podľa limitu

```bash
omi conversation list --limit 10
```

### Zahrnutie prepisov

```bash
omi conversation list --include-transcript
```

### Export do formátu JSON

```bash
omi conversation list --json
```

### Stránkovanie

```bash
omi conversation list --limit 50 --offset 100
```

## Odhlásenie

```bash
omi auth logout
```

## Pomoc

```bash
omi --help
omi conversation --help
```

## Zdroje

- [Dokumentácia](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
