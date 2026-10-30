# Fina na pasu siha yan omi-cli

Kao guaha na tinige' put fina na pasu siha (commands) gi omi-cli gi fino' Chamoru. I na'an i commands siha yan i mensahe siha gi programa, manot gui' gi fino' Englis. I ehemplu siha gi inaligao gi tinige' este, ti ma na' tinago' i memorias (memories), i kumentos (conversations), i che'cho' (action items), pat i ineyak (goals) mu.

## Inatala

Malago': Python 3.10 pat mas takhilo', yan un Omi akkount.

Yanggen guaha `pipx`:

```sh
pipx install omi-cli
omi --help
```

Siña lokkue' un inatala gi un Python virtual environment:

```sh
python -m pip install omi-cli
omi --help
```

Yanggen ti ha sodda' i terminal i `omi`, na' siguru na mama'ta' i virtual environment pat guaha i `pipx` na folledu gi `$PATH`.

## Na' fanhasso i akkount mu

Tutuhon i assistantsai:

```sh
omi auth login
```

Pili para un fanhuyong gi browser pat un pega un Omi developer API key. I interaktibu na inentrada ha na' atok i key; chomma' un tuge' i key gi un command ni para u fanmanhasso gi terminal history.

Para un fanhuyong direktamente gi browser:

```sh
omi auth login --browser
```

Fanhuyong gi padron na komputadora yan i terminal: i autentikasion na tinimbo' gui' para i local address. Tati i tinago' siha gi screen.

Despues, chek i konfigurasion yan i API access:

```sh
omi auth status
omi auth whoami
```

I `status` ha na' hinasso i local na estado ya ha na' atok i sekretu, lao ti ha chek i balido gi server. I `whoami` ha fatinas un autentikado na inaligao; yanggen masusesedi, klaru na manmanfunksiona i kredensial siha, sin ma na' hinasso i na'an mu.

I konfigurasion manmanhasso gi `~/.omi/config.toml`. Chamo un dibidi este na faylu: siña guaha private na kredensial.

## Espia i data mu

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

I un list ni taya' gui' ha ipok klaru na taya' nifen ni ha aksidenti i inaligao. Taitai i ayudu para un sodda' i filters gi kada command:

```sh
omi memory list --help
omi action-item list --help
```

## JSON yan i pahina siha

Na' para i global na opsion `--json` **a'ntes di** i command group:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

I fina na command ha inaligao i fina 25 na memorias; i sigundu i manmanmaga na 25. Ti kompletto na kopia i un pahina. I JSON ha na' fanhasso i enteru na numiru siha, lao i table siha gi screen siña ma diklara.

Para un na' fanhasso un pahina gi un faylu:

```sh
omi --json memory list --limit 25 --offset 0 > memorias-pahina-1.json
```

Este na redirect ha funas pat ha tuge' tatte gi un local na faylu. Na' siguru na monhayan i command antes di un u'usa' i lina'la'. I tinanom gui' gi error output (stderr); i taya' na faylu ti ebidensia na taya' data. I un faylu ni ma espot siña guaha personal na infotmasion: na' fanhasso private.

## Fanhuyong

```sh
omi auth logout
```

Este na command ha na' fanhuyong i kredensial siha ni manmanhasso gi local. Para un na' ti balido un key gi server, u'usa' i developer key management gi iyo mu na akkount.

Para mas na commands yan opsion siha, atan i [English na guide](../README.md) yan `omi --help`.
