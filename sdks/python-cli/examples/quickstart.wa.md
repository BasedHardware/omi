# Cminceu roehté avou omi-cli

Çou ci guide esplike les comandes di båze e walon. Les noes des comandes et les
messaedjes do programme dmornnut e-n inglès. Les comandes d'exemple ci-dzo n'
candjnut nén vos sovenances, coversåcions, cayès d'action ni bokeas.

## Astaler l' programme

I fåt: Python 3.10 ou pus reveléye èt èn conte Omi.

Si `pipx` est dedja astalé:

```sh
pipx install omi-cli
omi --help
```

Oubén astalez dins èn avironnmint virtyel Python k' a stî enondé:

```sh
python -m pip install omi-cli
omi --help
```

Si l' terminal ni trouve nén `omi`, vérifiez ki l' avironnmint virtyel soit
enondé, ou ki l' ridante åwé `pipx` astale les fitchîs k' couhnut est dins
`PATH`.

## Ralfaetî vosse conte

Enondez l' guide nteractif:

```sh
omi auth login
```

Tchoezi li login på browser ou aclåpez ène clé API d' divlôpeu Omi. L' intrêye
nteractive cache li clé; ni l' scrîve nén dins des comandes k' restèt dins l'
istwere do terminal.

Poûser l' browser tot droet:

```sh
omi auth login --browser
```

Raloyîz so l' minme copiåtire ki l' terminal, pårceki l' otantifiaedje eploye
ène adresse callback locåle. Shûwez les instrucsions ki s' mounstnut å-s screen.

Dispoy l' login, vérifiez li configuråcion èt l' accès API:

```sh
omi auth status
omi auth whoami
```

`status` mounstre li ståt locål èt cache les secrets, mins ni vérifie nén si
il sont valides so l' sèrveu. `whoami` evoye ène dmande otantifiêye; si çou
måtche, vos credéntieles fonctionnèt sins mostrer vosse no.

Li configuråcion est sovêye pa default dins `~/.omi/config.toml`. Ni pårtaedjîz
nén çou fitchî — i pout contini des credéntieles.

## Léjhi vos données

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Ène liste vude pout voleur di ki nosse cayè ni rindoedje li filte. Voyîz les
opçons di tchåke comande dins l' aiwe:

```sh
omi memory list --help
omi action-item list --help
```

## Avey dî JSON èt tournî les pådjes

Metoz l' opçon globåle `--json` **davant** li groupe di comandes:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Li prumîre comande dmande les 25 prumîres sovenances; li deujhinme les 25
shuvantes. Ène pådje n' est nén ène backup complete. Li rexhowa JSON garde les
IDs complets, pindant ki l' tåvleu pout les ascourtî po l' måde.

Po sovêy ène pådje dins èn fitchî:

```sh
omi --json memory list --limit 25 --offset 0 > memory-pådje-1.json
```

Çou redirect crèye ou réscrit èn fitchî locål. Vérifiez ki li comande a fini
bons ôr avant d' eployî l' contnou. Les årôrs sont scrîtes so stderr; èn
fitchî vude ni pruve nén ki gn a pont d' données. Li fitchî d' export pout
contini d' l' infôrmåcion personåle — gardîz-l privé.

## Eployî les profîs

Li ståt est sovéy dins `~/.omi/config.toml` (pout esse candjî avou
`$OMI_CONFIG`). Tchåke profî a s' prope mådjo d' otantifiaedje èt s' prope
adresse API. Candjîz di profî avou `--profile`:

```sh
omi config profile use ovraedje
omi auth login
omi --profile privé memory list
```

Comandes di configuråcion usweles:

```sh
omi config show
omi config path
omi config profile list
```

## Codes di rexhowa

Ces codes di rexhowa sont ståbes èt utiles po les scripts ou les agents:

| Code | Sinifiaedje | Exemple di situåcion |
| ---: | --- | --- |
| 0 | å bon | Comande finie |
| 1 | årôr d' eployaedje | Foûsse flag, argument ki månke ou validåcion ratêye |
| 2 | årôr d' otantifiaedje | Pont d' credéntieles, token expiré ou permissions ki månkèt |
| 3 | årôr do sèrveu | Sèrveu 5xx ou conneccion ratêye |
| 4 | rate limited | Li sèrveu a rtourné HTTP 429 |
| 5 | nén trové | Li sèrveu a rtourné HTTP 404 |

## Dislôgî

```sh
omi auth logout
```

Çou rsaite les credéntieles sovêyes locålmint. Po revokî li clé so l' sèrveu,
eployîz li manaedjmint des clés d' divlôpeu di vosse conte.

Po pus di comandes èt d' opçons, voyîz li [README principål e-n inglès](../README.md)
èt enondez `omi --help`.
