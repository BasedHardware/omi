# Оғози кори зуд бо omi-cli

Ин дастур нишон медиҳад, ки чӣ тавр `omi-cli`-ро аз терминал истифода
баред. Номи фармонҳо ва паёмҳои барнома ба забони англисӣ мемонанд, то ки
намунаҳоро бевосита нусха карда тавонед. Фармонҳои ин саҳифа танҳо маълумот
мехонанд, агар дар матн ба таври равшан амали дигар гуфта нашуда бошад.

## Талабот ва насб

Ба Python 3.10 ё навтар ва ҳисоби Omi ниёз доред. Барои насби ҷудогона,
`pipx`-ро истифода баред:

```sh
pipx install omi-cli
omi --version
omi --help
```

Агар `pipx` надошта бошед, бастаеро дар муҳити виртуалии фаъол насб кунед:

```sh
python -m venv .venv
. .venv/bin/activate       # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install omi-cli
omi --help
```

Номи баста дар PyPI `omi-cli` аст, вале фармони терминалӣ `omi` мебошад. Агар
терминал фармонро наёбад, муҳити виртуалӣ ё роҳи иҷрои `pipx`-ро ба `PATH`
санҷед.

## Пайваст кардани ҳисоби Omi

Ёвари интерактивиро оғоз кунед:

```sh
omi auth login
```

Ёвари мазкур ду роҳ пешниҳод мекунад:

1. Браузер — воридшавӣ бо Google ё Apple барои кори шахсӣ.
2. API key — калиди таҳиягари Omi барои агентҳо ва CI.

Барои маҷбур кардани ҷараёни браузер:

```sh
omi auth login --browser
```

Терминал ва браузер бояд дар як компютер бошанд, зеро OAuth ба callback-и
маҳаллии localhost бармегардад. Калиди API-ро дар фармони дорои таърихи shell
нанависед; беҳтар аст воридкунии интерактивӣ ё файли муҳофизатшуда истифода
шавад.

Пас аз воридшавӣ ҳолат ва санҷиши воқеии серверро бинед:

```sh
omi auth status
omi auth whoami
```

`status` танҳо танзимоти маҳаллӣ ва маълумоти махфишудаи credential-ро нишон
медиҳад. `whoami` дархости тасдиқшуда мефиристад ва нишон медиҳад, ки credential
дар сервер кор мекунад. Танзимот бо нобаёнӣ дар `~/.omi/config.toml` нигоҳ
дошта мешавад; ин файл метавонад сирро дар бар гирад ва набояд мубодила шавад.

Барои истифодаи API key аз тағйирёбандаи муҳит:

```sh
export OMI_API_KEY=omi_dev_...
omi memory list
```

## Хондани хотираҳо, гуфтугӯҳо, амалҳо ва ҳадафҳо

Фармонҳои маъмул:

```sh
omi memory list --limit 5
omi conversation list --limit 5
omi action-item list --open
omi goal list
```

Барои гирифтани як гуфтугӯ бо транскрипт:

```sh
omi conversation get CONVERSATION_ID --include-transcript
omi conversation list --include-transcript --limit 10
```

Рӯйхати холӣ хатогӣ нест; мумкин аст танҳо ягон сабт ба филтр мувофиқат
накунад. Барои ҳамаи имконот кӯмакро бинед:

```sh
omi memory list --help
omi conversation list --help
omi action-item list --help
omi goal list --help
```

## JSON ва саҳифабандӣ

Опсияи глобалии `--json` бояд пеш аз гурӯҳи фармонҳо биёяд:

```sh
omi --json memory list --limit 25 --offset 0
omi --json memory list --limit 25 --offset 25
```

Фармони дуюм саҳифаи баъдиро мегирад; як саҳифа нусхаи пурраи маълумот нест.
Барои нигоҳ доштани натиҷа дар файл:

```sh
omi --json memory list --limit 25 --offset 0 > memories-page-1.json
```

Пеш аз истифодаи файл рамзи баромадро санҷед. Хатогиҳо ба stderr мераванд ва
файли холӣ кафолати набудани маълумот нест. JSON метавонад маълумоти шахсӣ
дошта бошад, бинобар ин файлро махфӣ нигоҳ доред.

JSON барои қубурҳо ва агентҳо низ мувофиқ аст:

```sh
omi --json conversation list --include-transcript --limit 5 | jq '.[].id'
```

## Профилҳо ва танзимот

Файл метавонад якчанд профил дошта бошад; ҳар профил credential ва API base-и
худро нигоҳ медорад:

```sh
omi config profile list
omi config profile use work
omi auth login
omi --profile personal memory list
omi config show
omi config path
omi config set api_base https://api.staging.omi.me
```

Барои профили фаъол URL-и API-и маҳаллии Desktop-ро низ метавон танзим кард:

```sh
omi config set local_api_url http://127.0.0.1:47778
omi config set local_token TOKEN
```

## API-и маҳаллии Omi Desktop

Агар Omi Desktop кор карда истода бошад, пайвастшавиро як бор танзим кунед:

```sh
omi local configure --url http://127.0.0.1:47778 --token TOKEN
omi --json local status
omi --json local tools
```

Фармонҳои хондан ва ҷустуҷӯ:

```sh
omi --json local search-screen "pricing page" --days 7 --app Safari
omi --json local screenshot 123 --output /tmp/omi-shot.jpg
omi --json local recap --days-ago 1
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
omi --json local task search "taxes" --include-completed
```

Барои даъвати асбоби маълум бо JSON:

```sh
omi --json local call search_screen_history \
  --args-json '{"query":"pricing page","days":7}'
```

Аввал `local status`-ро санҷед, баъд бо `local tools` schema-и зиндаро бинед.
`local task complete` ва `local task delete` маълумотро тағйир медиҳанд; онҳоро
танҳо вақте иҷро кунед, ки тағйирот қасдан бошад.

## Рамзҳои баромади устувор

| Рамз | Маъно | Амали маъмул |
| --- | --- | --- |
| `0` | Муваффақият | Натиҷаро истифода баред |
| `1` | Хатои истифода ё санҷиш | Парчамҳо ва аргументҳоро санҷед |
| `2` | Хатои authentication | `omi auth login` иҷро кунед |
| `3` | Хатои сервер ё пайвастшавӣ | Пайвастшавӣ ва ҳолати Omi-ро санҷед |
| `4` | Маҳдудияти суръат (429) | Пас аз `Retry-After` такрор кунед |
| `5` | Ёфт нашуд (404) | ID ё филтрро санҷед |

Дар ҳолати `--json` натиҷаи муваффақ ба stdout ҳамчун JSON меравад; хатогиҳо
ба stderr ҳамчун JSON мебароянд. Дархостҳои хонданӣ метавонанд автоматӣ такрор
шаванд, аммо пас аз хатои номуайяни навиштан онро фавран такрор накунед — аввал
ҳолати захираро санҷед.

## Баромадан ва маълумоти бештар

Барои нест кардани credential-и маҳаллӣ:

```sh
omi auth logout
```

Ин амал калидро дар сервер бекор намекунад; барои он аз танзимоти ҳисоби Omi
истифода баред.

- Маълумоти пурра: [`omi --help`](../README.md)
- Ҳуҷҷатҳои таҳиягар: [docs.omi.me](https://docs.omi.me/doc/developer/cli/introduction)
- Лоиҳаи PyPI: [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
- Issue-ҳо: [github.com/BasedHardware/omi/issues](https://github.com/BasedHardware/omi/issues)
