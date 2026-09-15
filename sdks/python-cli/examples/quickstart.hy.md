# omi-cli Արագ մեկնարկի ուղեցույց

## Տեղադրում

```bash
pip install omi-cli
```

## Մուտք գործել

```bash
omi auth login
```

Ձեր հաշվով մուտք գործելու համար բրաուզերը կբացվի:

## Հիմնական հրամաններ

### Զրույցների ցանկ

```bash
omi conversation list
```

### Դիտել որոշակի զրույց

```bash
omi conversation get <զրույցի_id>
```

### Փնտրել զրույցներում

```bash
# omi conversation list (search filters)
omi conversation list "որոնման հարցում"
```

## Ընդլայնված ընտրանքներ

### Զտել ըստ սահմանաչափի

```bash
omi conversation list --limit 10
```

### Ներառել սղագրությունները

```bash
omi conversation list --include-transcript
```

### Արտահանել JSON ձևաչափով

```bash
omi --json conversation list
```

### Էջավորում

```bash
omi conversation list --limit 50 --offset 100
```

## Ելք

```bash
omi auth logout
```

## Օգնություն

```bash
omi --help
omi conversation --help
```

## Ռեսուրսներ

- [Փաստաթղթեր](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
