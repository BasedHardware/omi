# Greitas pradžios vadovas omi-cli

## Diegimas

```bash
pip install omi-cli
```

## Prisijungimas

```bash
omi auth login
```

Atsidarys naršyklė, kad galėtumėte prisijungti naudodami savo paskyrą.

## Pagrindinės komandos

### Pokalbių sąrašas

```bash
omi conversation list
```

### Konkretaus pokalbio peržiūra

```bash
omi conversation get <pokalbio_id>
```

### Pokalbių paieška

```bash
omi conversation search "paieškos užklausa"
```

## Išplėstinės parinktys

### Filtravimas pagal limitą

```bash
omi conversation list --limit 10
```

### Stenogramų įtraukimas

```bash
omi conversation list --include-transcript
```

### Eksportas JSON formatu

```bash
omi conversation list --json
```

### Puslapiavimas

```bash
omi conversation list --limit 50 --offset 100
```

## Atsijungimas

```bash
omi auth logout
```

## Pagalba

```bash
omi --help
omi conversation --help
```

## Ištekliai

- [Dokumentacija](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
