# Хуткі старт з omi-cli

Гэты даведнік паказвае, як карыстацца `omi-cli` з тэрмінала. Назвы каманд і
паведамленні праграмы пакідаюцца па-англійску, каб прыклады можна было
непасрэдна скапіяваць. Калі не пазначана іншае, прыведзеныя каманды толькі
чытаюць даныя.

## Патрабаванні і ўсталяванне

Патрэбны Python 3.10 або навейшы і ўліковы запіс Omi. Для ізаляванага
ўсталявання рэкамендуецца `pipx`:

```sh
pipx install omi-cli
omi --version
omi --help
```

Калі `pipx` недаступны, усталюйце пакет у актываваным віртуальным асяроддзі:

```sh
python -m venv .venv
. .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install omi-cli
omi --help
```

Назва пакета ў PyPI — `omi-cli`, а назва выканальнай каманды — `omi`. Калі
тэрмінал не знаходзіць `omi`, праверце актывацыю асяроддзя і шлях `PATH` для
выканальных файлаў `pipx`.

## Падключэнне ўліковага запісу Omi

Запусціце інтэрактыўны майстар:

```sh
omi auth login
```

Выберыце адзін з варыянтаў:

1. Browser — уваход праз Google або Apple для асабістай працы.
2. API key — ключ распрацоўшчыка Omi для агентаў і CI.

Каб адразу выкарыстаць уваход у браўзеры:

```sh
omi auth login --browser
```

Тэрмінал і браўзер павінны працаваць на адным камп'ютары: OAuth вяртаецца на
лакальны callback localhost. Не ўстаўляйце API-ключ у каманду, якая застанецца
ў гісторыі shell; выкарыстайце бяспечны інтэрактыўны ўвод або файл з абмежаванымі
правамі.

Праверце лакальны стан і сапраўднасць credential на серверы:

```sh
omi auth status
omi auth whoami
```

`status` паказвае толькі лакальную канфігурацыю і замаскіраваны сакрэт.
`whoami` робіць аўтэнтыфікаваны запыт і пацвярджае, што credential працуе.
Па змаўчанні канфігурацыя захоўваецца ў `~/.omi/config.toml`; гэты файл можа
ўтрымліваць сакрэты і яго нельга перадаваць іншым.

Для часовага выкарыстання API-ключа праз асяроддзе:

```sh
export OMI_API_KEY=omi_dev_...
omi memory list
```

## Чытанне памяці, размоў, задач і мэт

Асноўныя каманды:

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Каб атрымаць размову разам з транскрыптам:

```sh
omi conversation get CONVERSATION_ID --include-transcript
omi conversation list --include-transcript --limit 10
```

Пусты спіс не абавязкова азначае памылку — проста можа не быць запісаў,
якія адпавядаюць фільтру. Поўны спіс параметраў:

```sh
omi memory list --help
omi conversation list --help
omi action-item list --help
omi goal list --help
```

## JSON-выхад і старонкі вынікаў

Глабальны параметр `--json` ставіцца перад групай каманд:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Другая каманда атрымлівае наступную старонку; адна старонка не з'яўляецца
поўнай рэзервовай копіяй. Для захавання старонкі ў файл:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

Перад выкарыстаннем файла праверце код выхаду. Памылкі запісваюцца ў stderr,
таму пусты файл не даказвае адсутнасць даных. JSON можа ўтрымліваць асабістую
інфармацыю — захоўвайце экспарт прыватна.

Для скрыптоў і агентаў можна адфільтраваць JSON, напрыклад:

```sh
omi --json conversation list --include-transcript --limit 5 | jq '.[].id'
```

## Профілі і канфігурацыя

У адным файле можна мець некалькі названых профіляў; кожны мае ўласны
credential і API base:

```sh
omi config profile list
omi config profile use work
omi auth login
omi --profile personal memory list
omi config show
omi config path
omi config set api_base https://api.staging.omi.me
```

Налады лакальнага Omi Desktop таксама можна задаць для актыўнага профілю:

```sh
omi config set local_api_url http://127.0.0.1:47778
omi config set local_token TOKEN
```

## Лакальны API Omi Desktop

Калі Omi Desktop запушчаны, наладзьце доступ адзін раз:

```sh
omi local configure --url http://127.0.0.1:47778 --token TOKEN
omi --json local status
omi --json local tools
```

Каманды для чытання і пошуку:

```sh
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local recap --days-ago 1
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
omi --json local task search "taxes" --include-completed
```

Выклікаць пэўны інструмент з JSON-аргументамі можна так:

```sh
omi --json local call search_screen_history \
  --args-json '{"query":"pricing page","days":7}'
```

Спачатку праверце `local status`, затым паглядзіце жывую схему праз `local
tools`. Каманды `local task complete` і `local task delete` змяняюць даныя;
выконвайце іх толькі наўмысна.

## Стабільныя коды выхаду

| Код | Значэнне | Што зрабіць |
| --- | --- | --- |
| `0` | Поспех | Выкарыстаць вынік |
| `1` | Памылка выкарыстання або праверкі | Праверыць сцягі і аргументы |
| `2` | Памылка аўтэнтыфікацыі | Запусціць `omi auth login` |
| `3` | Памылка сервера або сеткі | Праверыць злучэнне і стан Omi |
| `4` | Абмежаванне хуткасці (429) | Паўтарыць пасля `Retry-After` |
| `5` | Не знойдзена (404) | Праверыць ID або фільтр |

У рэжыме `--json` паспяховы вынік ідзе ў stdout як JSON, а памылкі — у stderr
як JSON. Запыты на чытанне могуць паўтарацца аўтаматычна. Пасля няпэўнай
памылкі запісу спачатку праверце стан рэсурсу, каб не стварыць дублікат.

## Выхад і далейшае чытанне

Каб выдаліць захаваны credential з гэтага камп'ютара:

```sh
omi auth logout
```

Гэта не адклікае ключ на серверы; для адклікання скарыстайцеся наладамі
ўліковага запісу Omi.

- Поўная даведка: [`omi --help`](../README.md)
- Дакументацыя распрацоўшчыка: [docs.omi.me](https://docs.omi.me/doc/developer/cli/introduction)
- Пакет PyPI: [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
- Праблемы праекта: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
