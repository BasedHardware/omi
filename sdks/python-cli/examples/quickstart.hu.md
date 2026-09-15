# Gyors kezdés az omi-cli-vel

## Telepítés

```bash
pip install omi-cli
```

## Bejelentkezés

```bash
omi auth login
```

A böngésző megnyílik, hogy bejelentkezzen a fiókjával.

## Alapvető parancsok

### Beszélgetések listázása

```bash
omi conversation list
```

### Egy adott beszélgetés megtekintése

```bash
omi conversation get <beszélgetés_azonosító>
```

### Keresés a beszélgetésekben

```bash
# omi conversation list (search filters)
omi conversation list "keresési kifejezés"
```

## Haladó beállítások

### Szűrés korlát alapján

```bash
omi conversation list --limit 10
```

### Átiratok hozzáadása

```bash
omi conversation list --include-transcript
```

### Exportálás JSON formátumban

```bash
omi --json conversation list
```

### Lapozás

```bash
omi conversation list --limit 50 --offset 100
```

## Kijelentkezés

```bash
omi auth logout
```

## Segítség

```bash
omi --help
omi conversation --help
```

## Források

- [Dokumentáció](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
