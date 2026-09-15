# omi-cli Sürətli Başlanğıc Bələdçisi

## Quraşdırma

```bash
pip install omi-cli
```

## Daxil olmaq

```bash
omi auth login
```

Hesabınızla daxil olmaq üçün brauzer açılacaq.

## Əsas Əmrlər

### Söhbətlərin siyahısı

```bash
omi conversation list
```

### Müəyyən bir söhbətə baxmaq

```bash
omi conversation get <söhbət_id>
```

### Söhbətlərdə axtarış

```bash
# omi conversation list (search filters)
omi conversation list "axtarış sorğusu"
```

## Təkmil Seçimlər

### Limitə görə filtrləmə

```bash
omi conversation list --limit 10
```

### Transkriptləri daxil etmək

```bash
omi conversation list --include-transcript
```

### JSON formatında ixrac

```bash
omi --json conversation list
```

### Səhifələmə

```bash
omi conversation list --limit 50 --offset 100
```

## Çıxış

```bash
omi auth logout
```

## Kömək

```bash
omi --help
omi conversation --help
```

## Resurslar

- [Sənədlər](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
