# omi-cli жылдам іске қосу нұсқаулығы

## Орнату

```bash
pip install omi-cli
```

## Жүйеге кіру

```bash
omi auth login
```

Тіркелгіңізбен кіру үшін шолғыш ашылады.

## Негізгі командалар

### Әңгімелесулер тізімі

```bash
omi conversation list
```

### Нақты әңгімелесуді көру

```bash
omi conversation get <әңгімелесу_id>
```

### Әңгімелесулерді іздеу

```bash
# omi conversation list (search filters)
omi conversation list "іздеу сұрауы"
```

## Кеңейтілген опциялар

### Шектеу бойынша сүзу

```bash
omi conversation list --limit 10
```

### Жазбаларды қосу

```bash
omi conversation list --include-transcript
```

### JSON пішімінде экспорттау

```bash
omi --json conversation list
```

### Беттерге бөлу

```bash
omi conversation list --limit 50 --offset 100
```

## Жүйеден шығу

```bash
omi auth logout
```

## Көмек

```bash
omi --help
omi conversation --help
```

## Ресурстар

- [Құжаттама](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
