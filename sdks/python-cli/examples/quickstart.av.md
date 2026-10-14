# omi-cli — авар маҗарул тIадегIуцIин кIял

> Omi-гъод гIаргIатав терминалалда лъугьин кIял. ГIадамаздеда AI-агенттаздеда гьедин.

`omi-cli` — [Omi](https://omi.me) гIалаттаялъул API-ялда официалаб командалъул клиент.
Гьелъ Omi-ялъул щунаб аслияб ресурсазде — рикIкIун, гIацIбати, гIаргIатаялъул пунктал, максимабазде — цингун ва скриптиялда гIенав гьабулеб доступ баян кьулеб буго.

* **PyPI:** [pypi.org/project/omi-cli](https://pypi.org/project/omi-cli/)
* **Документация:** [docs.omi.me/doc/developer/cli/introduction](https://docs.omi.me/doc/developer/cli/introduction)
* **РацIкъан код:** [github.com/BasedHardware/omi/tree/main/sdks/python-cli](https://github.com/BasedHardware/omi/tree/main/sdks/python-cli)

---

## 1. Гьабин

БагIалъаб метод — `pipx`: гьелъ инструменталъул изолирован мохьазда гьабула,
гьекIа гьелъул зависимостал тIехь проекталда жугьа гIандилен.

```bash
# багIалъа: pipx-гъод гьабин
pipx install omi-cli

# вадаквал pip-гъод
pip install omi-cli
```

> **ГIажаиб: пакетъул цIар ва командалъул цIар гIемер.**
> * Гьабулеб пакет — **`omi-cli`** (гIемер пакет `omi` — цIибаб, гIансилеб проект).
> * Гьабунаб гьабиндасан гьабулеб команда — **`omi`**.

РукIине гьечIолеб лъугьараб:

```bash
omi --version
omi --help
```

---

## 2. Авторизация

`omi-cli` кIиго методалъул авторизация бекъулеб буго.

| Метод | ГIансилеб | Команда |
| :--- | :--- | :--- |
| **ГIалаттаялъул ключ (`omi_dev_*`)** | CI/CD, скрипттал, AI-агенттал | `omi auth login --api-key ...` вадаквал мохьалъул переменная |
| **Браузералъул авторизация (Google/Apple)** | ТIехь компьютералда лъугьин | `omi auth login --browser` |

### Интерактив авторизация

Опциял гьечIозул гьабулеб — гьелъ цIибаб методалъул лъугьин гьечIолеб бихьизабула.

```bash
omi auth login
# 1) Browser — Google вадаквал Apple-гъод гьаб (гIадамаздеда)
# 2) API key — app.omi.me-алда гIалаттаялъул ключ бичIчIа (агенттаздеда/CI)
```

Ключ бичIчIаниб, ввод гьаъулеб буго, гьекIа ключ терминалалъул тарихалда гьечIолеб.

### Браузералда тIадегIуцIин авторизация

```bash
omi auth login --browser
```

### ГIалаттаялъул ключалда авторизация

Ключ бичIчIа [app.omi.me](https://app.omi.me)-алда **Developer → API Keys**-алда.

```bash
# ключ конфигурациялда гьабин
omi auth login --api-key omi_dev_...

# вадаквал мохьалъул гIансалда бичIчIа — CI/CD ва контейнераздеда баянцIараб
export OMI_API_KEY=omi_dev_...
```

Мохьалъул переменная `OMI_API_KEY` гIансила, цIибаб активалъул профилалда ключ гьечIозул
гьабулеб — гьекIа контейнералда дискалда цIи лъалеб гьечIо. Профилалда гьесъ гьечIолеб
ключ бугеб, гьелъ мохьалъул переменнаялда кIудияб приоритет кьула.

### Доступалъул гьаракь гьаб

КIиго командалъул гIемер суалал гьечIо — гIемер гьечIолеб:

* `omi auth status` — **магIи** гьечIолеб: профиль, гьаъулеб ключ, тIокIаб дата.
  МрегIал гьечIозул гьабула.
* `omi auth whoami` — **Omi-сервералде** суал: ключ цин цIибаб гIанда гьечIолеб гьаракь.
  МрегIал багIалъулеб.

```bash
omi auth status    # магIи гьаракь, оффлайн
omi auth whoami    # сервералъул гьаракь
```

ТIокIаб токеналъул гIацIбазда гьечIолеб цингун авторизация — гьеб команда гIаргIатаб
**браузералъул/OAuth-сессияздеда гIансила**. API-ключ (`omi_dev_*`)-гъод авторизирован
профилалде `omi auth refresh` лъугьин гIандалъул цIихIиналда (код 1) факIула: токен
гьечIо цингун — багIалъа, Omi-вебприложениялда ключ илъин:

```bash
omi auth refresh
```

Гьабухъвахъ:

```bash
omi auth logout
```

---

## 3. Аслияб командал

### РикIкIун (memories)

Системалъ тIехь рикIкIун гьечIолеб фактал ва гIалам.

```bash
# рикIкIун цIараб
omi memory list

# цIибаб гьаб
omi memory create "ГIансилеб тIехь кIудияб тема босIиб" --category lifestyle

# цIибаб цIибабалъул рагI
omi memory get <MEMORY_ID>
```

### ГIацIбати (conversations)

Устройства вадаквал приложениялъул гIуцIи ва тексталъул тарих.

```bash
# гIандалаб 5 гIацIбат
omi conversation list --limit 5

# транскрипциялда гьечIолеб гIацIбат
omi conversation get <CONVERSATION_ID> --include-transcript
```

### ГIаргIатаялъул пунктал (action items)

Omi-алъ гIацIбаталда тIекIараб лъугьинал.

```bash
# гIаргIатаб гьечIолеб
omi action-item list --open

# гIаргIатаб гьечIолеб цIибаб
omi action-item complete <ACTION_ITEM_ID>
```

### Максимабал (goals)

```bash
# максимабал цIараб
omi goal list

# цIибаб прогрессалъул гIанс гьаб (КIИГО аргумент багIалъулеб: максим ва гIанс)
omi goal progress <GOAL_ID> 25

# илъиналъул тарих
omi goal history <GOAL_ID>
```

---

## ЦIибаб мацIалда суал (`ask`)

ГIемер кIудияб команда: цIибаб мацIалда суал бокьула,
ва гьеб суал тIехь гIацIбаталда гьечIолеб.

```bash
omi ask "къварилъин гьечIолеб цIибаб гьечIин"
omi --json ask "гьеб гьудулалда цIибаб гIаргIатаялъул пунктал гьечIин"
```

---

## 4. JSON ва скрипттал (`--json`)

`omi-cli` машиналъул рагIулеб JSON гьечIолеб. `--json` опция **глобалаб**
гьечIо гьеб субкомандалда **къварилъин** гьечIолеб багIалъулеб.

```bash
# рикIкIун: id, текст ва категория рагI
omi --json memory list | jq '.[] | {id, content, category}'

# гIандалаб гIацIбаталъул саргIалал
omi --json conversation list --limit 5 | jq '.[] | {id, title: .structured.title, started_at}'

# гIаргIатаб гьечIолеб пунктал
omi --json action-item list --open | jq '.'
```

> **ГIажаиб цIихIи.** `--json` субкомандалда къварилъин, гьесул бакIалда гьечIо.
> * ЦIи: `omi --json memory list`
> * ЦIихIи: `omi memory list --json`

`--json`-режималда гIадамаздеда прогрессалъул месэджал ва спиннерал гьечIолеб —
stdout гIаргIатаб JSON-документ гIансила. ЦIихIинал stderr-алде
`{"error": "...", "detail": "..."}` формалда гьечIолеб.

---

## 5. Гьабухъалъул кодал

Скрипттал гьечIолеб стабилалъул гьабухъалъул кодал.

| Код | Манал |
| :--- | :--- |
| `0` | ЦIи |
| `1` | Лъугьиналъул цIихIи (цIихIи флаг, багIалъулеб аргумент гьечIо) |
| `2` | Авторизация факIула — авторизация багIалъулеб |
| `3` | Сервералъул/мрегIалъул цIихIи |
| `4` | ТIаде гIанс — гьесул бакIалда цингун |
| `5` | Ресурс гьечIо |

```bash
if ! omi memory get "$MEMO_ID" --json > /tmp/m.json; then
  code=$?
  case $code in
    2) omi auth login --browser ;;
    5) echo "гьеб рикIкIун гьечIо" ;;
    *) echo "цIихIи $code" ;;
  esac
fi
```

---

## 6. Профилал ва конфигурация

Кьезда бикьигIел аккаунтал вадаквал мохьал бугеб, профилалда гIемер гьаб.
ГьечIолеб `~/.omi/config.toml`-алда гьечIолеб.

```bash
# цIибаб профилалда авторизация
omi --profile personal auth login

# лъугьиналъул профилалда авторизация
omi --profile work auth login

# цIибаб профилалда команда гьаб
omi --profile work memory list
```

Лъугьараб профиль гьеб равзарсталъул гьаракь: `--profile` опция (вадаквал `-p`)
цIибаб гьечIолеб; гьесул `OMI_PROFILE` мохьалъул переменная; гьесул `~/.omi/config.toml`-алъул
активалъул профиль; ва гьесул `default` профиль резервалъул.

ТIехь конфигурация рагI ва илъин:

```bash
# цIибаб гьечIолеб
omi config show

# конфигурациялъул файл цIибаб
omi config path

# гIанс илъин
omi config set api_base https://api.omi.me
```

---

## 7. Гьесул къахтал

* [`agent_quickstart.md`](./agent_quickstart.md) — `omi-cli` AI-агенталде гьедин къварилъин.
* [`shell_examples.sh`](./shell_examples.sh) — гьечIолеб shell-накъал.
* [Omi-документация](https://docs.omi.me/doc/developer/cli/introduction) — гIаргIатаб командалъул ссылка.
