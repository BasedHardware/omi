# មគ្គុទ្ទេសក៍ចាប់ផ្តើមរហ័ស omi-cli

## ការដំឡើង

```bash
pip install omi-cli
```

## ការចូល

```bash
omi auth login
```

កម្មវិធីរុករកនឹងបើកដើម្បីអ្នកចូលដោយប្រើគណនីរបស់អ្នក។

## ពាក្យបញ្ជាមូលដ្ឋាន

### បញ្ជីសន្ទនា

```bash
omi conversation list
```

### មើលសន្ទនាជាក់លាក់

```bash
omi conversation get <លេខសម្គាល់_សន្ទនា>
```

### ស្វែងរកសន្ទនា

```bash
# omi conversation list (search filters)
omi conversation list "សំណួរស្វែងរក"
```

## ជម្រើសកម្រិតខ្ពស់

### ត្រងតាមដែនកំណត់

```bash
omi conversation list --limit 10
```

### រួមបញ្ចូលប្រតិចារិក

```bash
omi conversation list --include-transcript
```

### នាំចេញជាទម្រង់ JSON

```bash
omi --json conversation list
```

### ការបែងចែកទំព័រ

```bash
omi conversation list --limit 50 --offset 100
```

## ការចេញ

```bash
omi auth logout
```

## ជំនួយ

```bash
omi --help
omi conversation --help
```

## ធនធាន

- [ឯកសារ](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.omi.me)
