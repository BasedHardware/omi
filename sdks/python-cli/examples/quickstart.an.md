# Primers pasos con omi-cli

Ista guía amuestra os primers pasos con omi-cli, escrita en aragonés. Os nombres d'as ordens y os mensaches d'o programa continan en anglés. Os eixemplos d'ista guía no cambian as tuyas memorias, conversacions, elementos d'acción ni obchectivos.

## Instalación

Necesitas Python 3.10 u posterior, y una cuenta Omi.

Si `pipx` ya ye disponible:

```sh
pipx install omi-cli
omi --help
```

U d'atra manera, puetz instalar-lo dentro d'un entorno virtual de Python activo:

```sh
python -m pip install omi-cli
omi --help
```

Si o terminal no troba `omi`, compreba si l'entorno virtual ye activo u si a carpeta de `pipx` ye en `$PATH`.

## Connectar a cuenta

Enceta o asistente interactivo d'inicio de sesión:

```sh
omi auth login
```

Puetz trigar: dentrar con o navegador u pegar una clau API de desembolicador Omi. A entrada interactiva amaga a clau; para cuenta y no la deixes en l'historial d'o terminal.

Ta dentrar directament con o navegador:

```sh
omi auth login --browser
```

Dentra en a mesma maquina an que s'executa o terminal: a respuesta d'autorización va ta una adreza local. Sigue as instruccions d'a pantalla.

Agora compreba a configuración y a clau API:

```sh
omi auth status
omi auth whoami
```

`status` amuestra l'estau local y amaga os secretos, pero no compreba con o servidor. `whoami` fa una petición autorizada; si va bien, sabrás que as tuyas credencials funcionan, pero no amuestra o tuyo nombre.

A configuración ye en `~/.omi/config.toml`. No compartas iste fichero: puet contener secretos d'acceso.

## Explorando os datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista vacía puet significar nomás que no i hai datos que coincidan. Ta aprender os filtros de cada orden, mira l'aduya:

```sh
omi memory list --help
omi action-item list --help
```

## Salida JSON y paginación

Posa a opción global `--json` **antis** d'o grupo d'ordens:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

A primera orden pide as primeras 25 memorias; a segunda pide as siguients 25. Una pachina no gosa estar plena. A salida JSON guarda totz os identificadors, mientres que as tablas d'a pantalla los acurta.

Ta escribir una pachina en un fichero:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-pachina-1.json
```

A redirección creya u substituye un fichero local. Compreba que a orden haiga funcionau antis d'usar o conteniu. Os errors van ta stderr; un fichero vuedo no quiere dicir que no i hai datos. Os ficheros exportaus pueden contener secretos: alza-los de manera segura.

## Salir

```sh
omi auth logout
```

Ista orden quita as credencials alzadas localment. Ta revocar a clau en o servidor, usa a chestión de claus de desembolicador d'a tuya cuenta.

Ta más ordens y opcions abanzadas, mira a [guía prencipal en anglés](../README.md) y `omi --help`.
