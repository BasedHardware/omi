# omi-cli Pikaopas

## Asennus

```bash
pip install omi-cli
```

## Kirjautuminen

```bash
omi auth login
```

Selain aukeaa tililläsi kirjautumista varten.

## Peruskomennot

### Keskustelujen listaaminen

```bash
omi conversation list
```

### Tietyn keskustelun tarkastelu

```bash
omi conversation get <keskustelu_id>
```

### Keskustelujen haku

```bash
# omi conversation list (search filters)
omi conversation list "hakulauseke"
```

## Lisäasetukset

### Suodatus rajan mukaan

```bash
omi conversation list --limit 10
```

### Sisällytä transkriptiot

```bash
omi conversation list --include-transcript
```

### Vie JSON-muodossa

```bash
omi --json conversation list
```

### Sivutus

```bash
omi conversation list --limit 50 --offset 100
```

## Uloskirjautuminen

```bash
omi auth logout
```

## Ohje

```bash
omi --help
omi conversation --help
```

## Resurssit

- [Dokumentaatio](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
