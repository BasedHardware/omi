# omi-cli — брз почеток на македонски

> Практичен водич за работа со Omi од терминал. Погоден и за човек и за AI агент.

`omi-cli` е официјалниот интерфејс на командна линија за развојниот API на [Omi](https://omi.me).
Дава брз и скрипт-friendly пристап до четирите главни ентитети на Omi:
спомени (memories), разговори (conversations), задачи (action items) и цели (goals).

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Документација:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **Изворен код:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Инсталација

Препорачаниот начин е `pipx`: ја инсталира алатката во изолирана околина,
па нејзините зависности не се судираат со вашите проекти.

```bash
# препорачано: инсталација преку pipx
pipx install omi-cli

# или преку pip
pip install omi-cli
```

> **Важно: името на пакетот и името на командата се разликуваат.**
> * Се инсталира пакетот **`omi-cli`** (засебниот пакет `omi` е друг, неповрзан проект).
> * По инсталацијата се извршува командата **`omi`**.

Проверете дека инсталацијата поминала:

```bash
omi --version
omi --help
```

---

## 2. Најава

`omi-cli` поддржува два начина на најава.

| Начин | Кога одговара | Команда |
| :--- | :--- | :--- |
| **Развоен клуч (`omi_dev_*`)** | CI/CD, скрипти, AI агенти | `omi auth login --api-key ...` или променлива на околината |
| **Најава преку прелистувач (Google/Apple)** | Работа на сопствениот компјутер | `omi auth login --browser` |

### Интерактивна најава

Без знаменца, командата сама ќе ве праша на кој начин сакате да се најавите:

```bash
omi auth login
# 1) Browser — најава преку Google или Apple (згодно за човек)
# 2) API key — вметнете развоен клуч од app.omi.me (згодно за агенти и CI)
```

При избор на клуч, внесот се маскира, па клучот не останува во историјата на терминалот.

### Директно преку прелистувач

```bash
omi auth login --browser
```

### Со развоен клуч

Клучот се зема од [app.omi.me](https://app.omi.me) во делот **Developer → API Keys**.

```bash
# зачувајте го клучот во конфигурацијата
omi auth login --api-key omi_dev_...

# или пренесете го преку околината — подобро за CI/CD и контејнери
export OMI_API_KEY=omi_dev_...
```

Променливата `OMI_API_KEY` се користи кога активниот профил нема зачувано клуч,
па во контејнер не треба ништо да се запишува на диск. Ако клучот веќе е
зачуван во профилот, тој има предност пред променливата на околината.

### Проверка на најавата

Две команди одговараат на различни прашања и не треба да се мешаат:

* `omi auth status` — што е зачувано **локално**: профил, маскиран клуч, важност.
  Работи без мрежа.
* `omi auth whoami` — барање **до серверот на Omi**: проверува дали серверот
  навистина го прифаќа клучот. Потребна е мрежа.

```bash
omi auth status    # локална проверка, офлајн
omi auth whoami    # проверка на серверот
```

Обновете го клучот со близок рок на важност без повторна најава:

```bash
omi auth refresh
```

Одјава:

```bash
omi auth logout
```

---

## 3. Основни команди

### Спомени (memories)

Факти и знаења што системот ги запомнил за вас.

```bash
# список на спомени
omi memory list

# креирајте нов
omi memory create "Корисникот претпочита темна тема" --category lifestyle

# прегледајте конкретен
omi memory get <MEMORY_ID>
```

### Разговори (conversations)

Историја на говор и текст од уредот или од апликацијата.

```bash
# последните 5 разговори
omi conversation list --limit 5

# цел разговор со транскрипција
omi conversation get <CONVERSATION_ID> --include-transcript
```

### Задачи (action items)

Задачи што Omi ги издвоил од разговорите.

```bash
# само незавршените
omi action-item list --open

# означете ја како завршена
omi action-item complete <ACTION_ITEM_ID>
```

### Цели (goals)

```bash
# список на цели
omi goal list

# запишете нова вредност на напредокот (потребни се ДВАТА аргумента: цел и вредност)
omi goal progress <GOAL_ID> 25

# историја на промени
omi goal history <GOAL_ID>
```

---

## Прашање со свои зборови (`ask`)

Посебна команда на највисоко ниво: поставува прашање на природен јазик,
одговорот се гради од вашите сопствени разговори.

```bash
omi ask "што решив околу преселбата"
omi --json ask "кои задачи ветив дека ќе ги завршам оваа недела"
```

---

## 4. JSON и скрипти (`--json`)

`omi-cli` знае да врати машински читлив JSON. Знаменцето `--json` е **глобално**,
па се става **пред** подкомандата.

```bash
# спомени: извлечете id, текст и категорија
omi --json memory list | jq '.[] | {id, content, category}'

# наслови на последните разговори
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# незавршени задачи
omi --json action-item list --open | jq '.'
```

> **Честа грешка.** `--json` оди пред подкомандата, а не после неа.
> * Точно: `omi --json memory list`
> * Неточно: `omi memory list --json`

Во режимот `--json` на стандардниот излез не доаѓа ништо освен самиот JSON —
на тоа може да се потпрете во скриптите.

---

## 5. Излезни кодови

Кодовите се стабилни, па по нив може да се грани логиката во скриптите и CI.

| Код | Значење | Кога настанува |
| :---: | :--- | :--- |
| `0` | Успех | Командата заврши |
| `1` | Грешка при повик | Невалидно знаменце, недостасува аргумент |
| `2` | Грешка при пристап | Не сте најавени, клучот е невалиден или истечен |
| `3` | Грешка на сервер | Одговор 5xx, timeout, нема врска |
| `4` | Премногу барања | 429 Too Many Requests |
| `5` | Не е пронајдено | 404, наведениот идентификатор не постои |

Пример за проверка во Bash:

```bash
if omi --json auth whoami > /dev/null 2>&1; then
  echo "клучот работи"
else
  code=$?
  [ "$code" -eq 2 ] && echo "потребна е повторна најава"
  [ "$code" -eq 3 ] && echo "серверот е недостапен, обидете се подоцна"
fi
```

---

## 6. Променливи на околината

### Bash / Zsh (Linux, macOS)

```bash
export OMI_API_KEY="omi_dev_vas_kluc"

omi --json memory list --limit 10
```

За клучот да се вчитува во нови сесии, додадете го редот во `~/.bashrc` или `~/.zshrc`.

### PowerShell (Windows)

```powershell
$env:OMI_API_KEY = "omi_dev_vas_kluc"

# обработка на JSON со PowerShell
(omi --json memory list | ConvertFrom-Json) | Select-Object id, content
```

Трајна поставка:

```powershell
[Environment]::SetEnvironmentVariable("OMI_API_KEY", "omi_dev_vas_kluc", "User")
```

---

## 7. Локална апликација Omi Desktop

Ако работи десктоп апликацијата Omi, дел од податоците е достапен директно,
без заобиколување на облакот.

```bash
# поставете адреса на локалниот API
omi local configure --url http://127.0.0.1:47778 --token VAS_TOKEN

# проверете дали одговара
omi --json local status

# пребарување во историјата на екранот
omi --json local search-screen "тарифи" --days 7 --app Safari

# слика од екранот по идентификатор
omi --json local screenshot 123 --output /tmp/omi-shot.jpg

# произволен SQL барање врз локалната база
omi --json local sql "SELECT appName, COUNT(*) FROM screenshots GROUP BY appName"
```

Редослед на работа: прво `local status`, потоа `local tools` — за да ги дознаете
достапните алатки и нивните параметри — и дури потоа повиците.

---

## 8. Профили

Ако имате повеќе сметки или околини, разделете ги со профили.
Поставките се чуваат во `~/.omi/config.toml`.

```bash
# најава во личниот профил
omi --profile personal auth login

# најава во работниот
omi --profile work auth login

# извршете команда во конкретен профил
omi --profile work memory list
```

Преглед и промена на самата конфигурација:

```bash
# што е моментално подесено
omi config show

# каде лежи конфигурацискиот фајл
omi config path

# променете вредност
omi config set api_base https://api.omi.me
```

---

## 9. Што следи

* [`agent_quickstart.md`](./agent_quickstart.md) — како да го поврзете `omi-cli` со AI агент.
* [`shell_examples.sh`](./shell_examples.sh) — готови примери за школка.
* [Документација на Omi](https://docs.omi.me/doc/developer/cli/introduction) — целосен преглед на командите.
