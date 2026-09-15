# Destpêka Bilez a omi-cli

## Sazkirinê

```bash
pip install omi-cli
```

## Têketin

```bash
omi auth login
```

Gerok dê vebibe ku hûn bi hesabê xwe re têkevin.

## Fermanên Bingehîn

### Lîsteya axaftinan

```bash
omi conversation list
```

### Axaftineke taybet bibînin

```bash
omi conversation get <nasnameya_axaftinê>
```

### Lêgerîna axaftinan

```bash
omi conversation search "pirsa lêgerînê"
```

## Vebijarkên Pêşketî

### Fîlterkirina li gorî sînor

```bash
omi conversation list --limit 10
```

### Tev li transkrîptan

```bash
omi conversation list --include-transcript
```

### Hinardekirina bi formata JSON

```bash
omi conversation list --json
```

### Rûpelkirin

```bash
omi conversation list --limit 50 --offset 100
```

## Derketin

```bash
omi auth logout
```

## Alîkarî

```bash
omi --help
omi conversation --help
```

## Çavkanî

- [Belgelêkirin](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
