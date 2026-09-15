# omi-cli სწრაფი დაწყების გზამკვლევი

## ინსტალაცია

```bash
pip install omi-cli
```

## შესვლა

```bash
omi auth login
```

ბრაუზერი გაიხსნება თქვენი ანგარიშით შესასვლელად.

## ძირითადი ბრძანებები

### საუბრების სია

```bash
omi conversation list
```

### კონკრეტული საუბრის ნახვა

```bash
omi conversation get <საუბრის_id>
```

### საუბრების ძიება

```bash
# omi conversation list (search filters)
omi conversation list "საძიებო მოთხოვნა"
```

## დამატებითი პარამეტრები

### გაფილტვრა ლიმიტის მიხედვით

```bash
omi conversation list --limit 10
```

### ტრანსკრიპტების ჩართვა

```bash
omi conversation list --include-transcript
```

### ექსპორტი JSON ფორმატში

```bash
omi --json conversation list
```

### გვერდებად დაყოფა

```bash
omi conversation list --limit 50 --offset 100
```

## გამოსვლა

```bash
omi auth logout
```

## დახმარება

```bash
omi --help
omi conversation --help
```

## რესურსები

- [დოკუმენტაცია](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
