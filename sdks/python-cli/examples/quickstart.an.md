# Guía rapida d'omi-cli

Ista guía describe as primeras ordens en idioma aragonés (Aragonese). Os nombres d'as ordens y os mensaches d'o programa remanen en anglés. Os eixemplos d'exploración que s'amuestran aquí no modifican as tuyas memorias (memories), conversas (conversations), fayenas pendients (action items) ni obchectivos (goals).

## Instalación

Requisitos: Python 3.10 u una versión más recient y una cuenta d'Omi.

Si tiens `pipx` instalau:

```sh
pipx install omi-cli
omi --help
```

Tamién puetz instalar-lo adintro d'un entorno virtual de Python activo:

```sh
python -m pip install omi-cli
omi --help
```

Si a terminal no troba `omi`, aseguta-te de que o entorno virtual siga activo u que o directorio a on `pipx` instala os binaris se trobe en o tuyo `$PATH`.

## Conectar a tuya cuenta

Inicia l'asistent interactivo:

```sh
omi auth login
```

Tria entre iniciar sesión a traviés d'o navegador u apegar a clau API de desembolicador d'Omi. A dentrada interactiva amaga a clau; priva d'escribir-la directament en una orden que remanga gravada en l'historial d'a terminal.

Pa ir directament a o navegador:

```sh
omi auth login --browser
```

Inicia sesión en o mesmo ordinador a on s'executa a terminal: a respuesta d'autenticación fa servir una adreza local. Sigue as instruccions en pantalla.

Dimpués, confirma a configuración y l'acceso a l'API:

```sh
omi auth status
omi auth whoami
```

`status` amuestra o estau local y amaga o secreto, pero no en valida a vichéncia en o servidor. `whoami` fa una petición autenticada; si tien exito, confirma que as credencials funcionan, sin amenistar amostrar o tuyo nombre.

A configuración s'almagazena por defecto en `~/.omi/config.toml`. No compartas iste fichero: puede contener credencials confidencials.

## Exploración de datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista bueda puede significar simplament que encara no i hai elementos que coincidan con a busca. Fa servir l'aduya pa descubrir os filtros disponibles en cada orden:

```sh
omi memory list --help
omi action-item list --help
```

## Salida JSON y paxinación

Coloca a opción global `--json` **antes** d'o grupo d'ordens:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

A primera orden solicita as primeras 25 memorias; a segunda, as 25 siguients. Una paxina no ye una copia de seguranza completa. A salida JSON conserva os identificadors enteros, mientres que as tablas en pantalla pueden alcorzar-los pa a visualización.

Pa almagazenar una paxina en un fichero:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-paxina-1.json
```

Ista redirección creya u sobrescribe o fichero local. Asegura-te de que a orden s'haiga executau correctament antes d'utilizar o suyo conteniu. Os errors s'escriben en a salida d'errors (stderr); un fichero buedo no ye preba de que no i haiga datos. O fichero exportau puede contener información personal: mantén-lo privau.

## Zarrar sesión

```sh
omi auth logout
```

Ista orden borra as credencials almagazenadas localment. Pa revocar una clau en o servidor, fa servir a chestión de claus de desembolicador d'a tuya cuenta.

Pa atras ordens y más opcions, consulta a [guía prencipal en anglés](../README.md) y `omi --help`.
