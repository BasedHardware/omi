# Guia d'inici ràpid d'omi-cli

## Instal·lació

```bash
pip install omi-cli
```

## Inici de sessió

```bash
omi auth login
```

S'obrirà el navegador per iniciar sessió amb el vostre compte.

## Ordres bàsiques

### Llistar converses

```bash
omi conversation list
```

### Veure una conversa concreta

```bash
omi conversation get <id_conversa>
```

### Cercar converses

```bash
omi conversation search "consulta de cerca"
```

## Opcions avançades

### Filtrar per límit

```bash
omi conversation list --limit 10
```

### Incloure transcripcions

```bash
omi conversation list --include-transcript
```

### Exportar en format JSON

```bash
omi conversation list --json
```

### Paginació

```bash
omi conversation list --limit 50 --offset 100
```

## Tancament de sessió

```bash
omi auth logout
```

## Ajuda

```bash
omi --help
omi conversation --help
```

## Recursos

- [Documentació](https://docs.omi.me)
- [GitHub](https://github.com/BasedHardware/omi)
- [Discord](https://discord.gg/omi)
