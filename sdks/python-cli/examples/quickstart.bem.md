# Icitabo ca Kwangufyanya pa omi-cli

Ici citabo cilelondolola amalyashi ya kutendekelapo muli `omi-cli` mu lulimi lwa Cibemba (Ichibemba). Amashina ya fipope (commands) na mashiwi ya programu fikashala mu Cisungu. Ifilangililo fya kuloleshamo ifiliko tafyakalule ifibukisho fyenu (memories), amalyashi yenu (conversations), ifya kucita (action items), nelyo amapange yenu (goals).

## Ukubika programu pa mashini (Installation)

Ifikabilwa: Python 3.10 nelyo iipya ukucilapo, pamo na akaunti ya Omi.

Nga mwalikwata `pipx` pa mashini:

```sh
pipx install omi-cli
omi --help
```

Kabili kuti mwaibikapo mukati ka Python virtual environment iilebomba:

```sh
python -m pip install omi-cli
omi --help
```

Nga ca kuti `omi` tailangile muli kompyuta yenu, shininkisheni ukuti virtual environment ilebomba nelyo ukuti incende ya `pipx` yaba mu `$PATH` yenu.

## Ukukakila akaunti yenu (Authentication)

Tendekeni ukubomfya akafwilisha:

```sh
omi auth login
```

Saleni ukwingilila mu browser nelyo ukubomfya Omi developer API key yenu. Ukwingisha kuli akafwilisha kulafisa ici fungulo; mwilalemba ici fungulo mu fipope ifingashala mu mulongo wa fyo mubomfeshe.

Pa kuya ukwabula ukupita kumbi ku browser:

```sh
omi auth login --browser
```

Ingilileni pa kompyuta imo ine apo mulebomfesha: amasuko ya kwingila yabomfya kapepala ka pa kompyuta yenu. Konkeni ifyebo fyamoneka pa screen.

Panyuma ya ico, shininkisheni ukukonka ifipope na bupe bwa API:

```sh
omi auth status
omi auth whoami
```

Icipope ca `status` cilanga imibele ya pa mashini no kufisa ifyebo fya nkama, lelo tacilinganya ubupilibulo kuli kasebanya (server). Icipope ca `whoami` cituma ukwipusha kuli kasebanya; nga caenda bwino, cileshibisha ukuti ifipeleleko filebomba bwino ukwabula ukulanga ishina lyenu.

Ifyalembwa fikonkanyapo fibikwa mu cifulo ca `~/.omi/config.toml`. Mwisalanganitsa ili ibumba lya fyalembwa: kuti lyakwata ifya nkama ifishingasangwa fye konse konse.

## Ukulolesha pa fyalembwa fyenu (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Umutande uushili na kantu kuti capilibula fye ukuti takwali ifyasangilwe pa kufwaya. Bomfyeni ukwafwa pa kusanga ifya kusala pa cila cipope:

```sh
omi memory list --help
omi action-item list --help
```

## Ukusenda JSON no Kwananya Amabula (Pagination)

Bikeni akasankano ka `--json` **ilyo mucili tamwalemba** amabumba ya fipope:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Icipope ca kubalilapo cilepeta ifibukisho 25 fya ntanshi; ica cibili, 25 ifikonkelepo. Ibula limo talili kusunga fyonse ifyabapo. Ifyafumamo mu JSON filalinda ifishibilo fyonse, nangula amatebulo ya pa screen yengacefya ifi fintu pa kulangilila.

Pa kusunga ibula muli failo:

```sh
omi --json memory list --limit 25 --offset 0 > ifibukisho-ibula-1.json
```

Uku kwalula kupanga nelyo kubika cipya failo pa mashini. Shininkisheni ukuti icipope capwa bwino ilyo mucili tamwabomfya ifyabamo. Ifilubo filembwa pa cisebanya ca filubo (stderr); failo iishili na kantu tailangilila ukuti tapali ifyebo. Failo yafumamo kuti yakwata ifyebo fya mutwe: fisungeni bwino mu nkama.

## Ukufuma muli akaunti (Logout)

```sh
omi auth logout
```

Ici cipope cifumyamo ifilembo fya kwingilila ifyasungwa pa mashini. Pa kufumyapo ifungulo kuli kasebanya, bomfyeni amalembo ya developer key muli akaunti yenu.

Pa fipope fimbi no kwishiba ifyacilapo, moneni [icipande ca Cisungu icikalamba](../README.md) na `omi --help`.
