# Os primers pasos con omi-cli

Ista guía explica os primers comandos (commands) d'omi-cli en aragonés. Os nombres d'os comandos y os mensaches d'o programa quedan en anglés. Os eixemplos de busca que se amuestran aquí no cambian as tuyas memorias (memories), as tuyas conversacions (conversations), as tuyas fainas (action items) ni os tuyos obchectivos (goals).

## Instalación

Cal: Python 3.10 u mas nuevo, y una cuenta Omi.

Si tiens `pipx`:

```sh
pipx install omi-cli
omi --help
```

Tamién puetz instalar-lo en un entorno virtual de Python activo:

```sh
python -m pip install omi-cli
omi --help
```

Si o terminal no troba `omi`, asegura-te que l'entorno virtual sía activo u que a carpeta de `pipx` sía en `$PATH`.

## Conectar a tuya cuenta

Empecipia l'asistent interactivo:

```sh
omi auth login
```

Tría dentrar por o navegador u pegar una clau API de desembolicador Omi. L'enta interactiva amaga a clau; evita escribir-la en un comando que quede en l'historial d'o terminal.

Pa ir dreitament a lo navegador:

```sh
omi auth login --browser
```

Dentra en o mesmo ordinador que o terminal: a respuesta d'autenticación va a l'adreza local. Sigue as instruccions en a pantalla.

Dimpués, verifica a configuración y l'acceso API:

```sh
omi auth status
omi auth whoami
```

`status` amuestra l'estau local y amaga o secreto, pero no verifica a valideza en o servidor. `whoami` fa una petición autenticada; si funciona, ye claro que as credencials funcionan, sin amostrar o tuyo nombre.

A configuración se guarda por defecto en `~/.omi/config.toml`. No compartas iste fichero: puet contener credencials privadas.

## Explorar os tuyos datos

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Una lista vueda normalment significa nomás que no bi ha cosa que coincida con a busca. Usa l'aduya pa trobar os filtros de cada comando:

```sh
omi memory list --help
omi action-item list --help
```

## JSON y pachinas

Posa a opción global `--json` **antes** d'o grupo de comandos:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

O primer comando pide as primeras 25 memorias; o segundo as 25 siguients. Una pachina sola no ye una copia completa. A salida JSON conserva os numeros enters, mientres que as tablas en a pantalla puet achiquir-los.

Pa alzar una pachina en un fichero:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-pachina-1.json
```

Ista redirección creya u sobreescribe un fichero local. Asegura-te que o comando remató antis d'usar o conteniu. Os errors s'escriben en a salida d'error (stderr); un fichero vuedo no ye una preva que no bi haiga datos. Un fichero exportau puet contener información personal: guarda-lo privau.

## Salir

```sh
omi auth logout
```

Iste comando borra as credencials alzadas localment. Pa invalidar una clau en o servidor, usa a chestión de claus de desembolicador en a tuya propia cuenta.

Pa mas comandos y opcions, mira la [guía prencipal en anglés](../README.md) y `omi --help`.
