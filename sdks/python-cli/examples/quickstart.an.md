# Guía rapida d'inicio con omi-cli

Ista guía explica os primers pasos con omi-cli en aragonés (Aragonese). Os nombres d'os comandos y os mensaches d'o programa remanen en anglés. Os eixemplos aquí amostraus no modifican as tuyas memorias (memories), conversas (conversations), fainas pendients (action items) ni obchectivos (goals).

## Instalación d'o programa

Requisitos: Python 3.10 u superior y una cuenta d'Omi.

Si tiens `pipx` instalau:

```sh
pipx install omi-cli
omi --help
```

Tamién puetz instalar-lo en un entorno virtual (venv) de Python:

```sh
python -m pip install omi-cli
omi --help
```

## Conectar a tuya cuenta

Inicia l'asistent interactivo:

```sh
omi auth login
```

Triga encetar sesión dende o navegador u apegar a tuya clau API de desembolicador d'Omi.

Ta ubrir dreitament o navegador:

```sh
omi auth login --browser
```

Compreba a configuración y l'acceso a l'API:

```sh
omi auth status
omi auth whoami
```

`status` amuestra o tuyo estau local, y `whoami` confirma que as credencials sían validas en o servidor.

## Explorar os tuyos datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Amuestra os filtros disponibles con a opción d'aduya:

```sh
omi memory list --help
omi action-item list --help
```

## Obtener JSON y paginación

Posa a opción cheneral `--json` **denzima / debant** d'o comando:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Ta alzar una pachina de datos en un fichero:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-pachina-1.json
```

## Desconectar d'a cuenta

```sh
omi auth logout
```

Iste comando borra as credencials alzadas localment.

Ta más información, consulta a [guía prencipal en anglés](../README.md) y `omi --help`.
