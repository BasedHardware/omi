# Омі CLI: Швидкий старт з агентом LLM

Омі CLI надає інструменти для створення агентів, що працюють з великими мовними моделями (LLM). Цей посібник покаже, як запустити простий агентний робочий процес.

---

## Встановлення

Переконайтесь, що у вас встановлено Python 3.8+ та pip:

```bash
python --version
pip --version
```

Встановіть омі CLI:

```bash
pip install omi-cli
```

---

## Створення агента

Створіть новий файл `agent.py` з наступним кодом:

```python
from omi import Agent

# Ініціалізуйте агента з вашим API ключем
agent = Agent(api_key="YOUR_API_KEY_HERE")

# Задайте завдання для агента
response = agent.run("Напишіть рецензію на книгу '1984' Джорджем Орвеллом")

print(response)
```

---

## Запуск агента

Виконайте файл через командний рядок:

```bash
python agent.py
```

---

## Додаткові параметри

Ви можете налаштувати поведінку агента через аргументи командного рядка:

```bash
python agent.py --model gpt-4 --temperature 0.7 --max_tokens 1000
```

Доступні параметри:
- `--model`: Модель LLM (за замовчуванням: gpt-3.5-turbo)
- `--temperature`: Температура вихідного тексту (0.0-1.0)
- `--max_tokens`: Максимальна кількість токенів у відповіді
- `--system_prompt`: Налаштування системи для агента

---

## Інтеграція з іншими сервісами

Омі підтримує безпосередню інтеграцію з популярними сервісами:

```python
from omi import Agent

agent = Agent(api_key="YOUR_API_KEY_HERE")

# Інтеграція з Slack
slack_response = agent.slack_integration("#general", "Нагадайте мені про зустріч о 14:00")

# Інтеграція з GitHub
github_response = agent.github_integration("owner/repo", "Створіть issue з назвою 'Fix bug'")
```

---

## Моніторинг виконання

Перевірте статус виконання завдання:

```bash
omi-cli task status YOUR_TASK_ID
```

Отримайте деталі виконання:

```bash
omi-cli task details YOUR_TASK_ID
```

---

## Документація та підтримка

- [Офіційна документація](https://docs.omihardware.com)
- [Спільнота Slack](https://slack.omihardware.com)
- [GitHub репозиторій](https://github.com/BasedHardware/omi)