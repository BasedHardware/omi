# Ulongozi Wachangu wa omi-cli

Ulongozi uwu ukulongosola malango ghakwamba mu chiTumbuka (Tumbuka) ghakukhwaskana na `omi-cli`. Mazina gha malango na mauthenga gha pulogalamu ghakhalenge mu Chingelezi. Viyelezgero vyakusanda ivyo vyalongoreka pano visinthenge yayi vikumbusko vinu (memories), madumbirano ghinu (conversations), milimo yakuchita (action items), panji vilato vyinu (goals).

## Kunjizga Pulogalamu (Installation)

Vyakukhumbikwa: Python 3.10 panji yiphya chomene pamoza na akaunti ya Omi.

Usange muli na `pipx`:

```sh
pipx install omi-cli
omi --help
```

Munganjizgaso mukati mwa malo ghakugwira ntchito gha Python (virtual environment):

```sh
python -m pip install omi-cli
omi --help
```

Usange dango la `omi` landika yayi mu theminolo, wonani usange virtual environment yikugwira ntchito panji usange nthowa ya `pipx` yili mu `$PATH` yinu.

## Kukakiliza Akaunti Yinu (Authentication)

Yambani movwiri wakudumbirana:

```sh
omi auth login
```

Sankhani kunjilira mu browser panji kulemba Omi developer API key yinu. Movwiri uwu ukubisa kiyi iyi; lekani kuyilemba mu malango agho ghangakhala mu mbiri ya theminolo.

Kuluta ku browser mwaluŵiro:

```sh
omi auth login --browser
```

Njirani pa kompyuta yeneyiyo iyo theminolo yikugwirapo ntchito: zgolo la chigomezgo likugwiritsa ntchito adiresi yamuno. Londezgani ulongozi uwo uli pa sikilini.

Pamanyuma pa icho, sandani vyakulongosoka na kufikapo pa API:

```sh
omi auth status
omi auth whoami
```

`status` yikulongora umo viliri kwamuno na kubisa chisisi, kweni yikusanda yayi usange yikugwira ntchito ku seva (server). `whoami` yikutuma pempho lakugomezgeka; usange yendeka makora, yikupanikizga kuti makalata ghakugwira ntchito kwambura kulongora zina linu.

Vyakulongosoka kanandi vikusungika mu `~/.omi/config.toml`. Lekani kugaŵana fayilo iyi na ŵanthu ŵanyake: yingaŵa na makalata ghachisisi.

## Kusanda Data Yinu (Inspection)

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Mndandanda wambura kanthu ungang'anamura waka kuti palije data iyo yikukolerana na ivyo mwapenja. Gwiritsani ntchito wovwiri kuti musange vyakusankha mu dango lililose:

```sh
omi memory list --help
omi action-item list --help
```

## Kupokera JSON na Kugaŵa Masamba (Pagination)

Ikani chosankha cha charu chose cha `--json` **panthazi** pa gulu la malango:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Dango lakwamba likupempha vikumbusko 25 vyakwamba; lachiŵiri likupempha 25 vyakulondezgapo. Samba limoza ndilo kusunga vyose yayi (backup). Ivyo vyalembeka na JSON vikusunga vimanyikwiro vyose, nangauli thebulo la pa sikilini lingachepeska kuti viwoneke makora.

Kusunga samba mu fayilo:

```sh
omi --json memory list --limit 25 --offset 0 > vikumbusko-samba-1.json
```

Nthowa iyi yikupanga panji kusintha fayilo yamuno. Wonani kuti dango lamara makora pambere mundagwiritse ntchito ivyo vili mukati. Maubudi ghakulembeka mu malo gha maubudi (stderr); fayilo yambura kanthu yikung'anamura kuti palije data yayi. Fayilo iyo yafumamo yingaŵa na uthenga winu wachisisi: yisungani makora chomene.

## Kufuma mu Akaunti (Logout)

```sh
omi auth logout
```

Dango ili likufumyamo makalata agho ghasungika kwamuno. Kuti muwuskepo kiyi ku seva, gwiritsani ntchito ulongozi wa developer key mu akaunti yinu.

Kuti musange malango ghanyake na vyakusankha vinyake vyakusazgikira, wonani [ulongozi ukuru wa Chingelezi](../README.md) na `omi --help`.
