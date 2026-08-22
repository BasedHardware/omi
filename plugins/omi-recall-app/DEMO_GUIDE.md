# Guía: cómo presentar Omi Recall (Track 3)

## El pitch de 20 segundos (dilo tú, en la llamada o en el video)

> "Omi remembers everything for you — but remembering *for* you isn't the same as you learning it. Recall closes that loop: every conversation becomes flashcards, Omi quizzes you in chat with real spaced repetition, and one link exports to Anki. It turns Omi from external memory into a personal tutor — which is literally the mission: the 14-year-old with no mentor."

## Demo de < 2 minutos (guion)

Graba la pantalla de tu terminal + navegador. Pasos:

**0:00 — Setup (ya corriendo antes de grabar)**
```bash
cd plugins/omi-recall-app && pip install -r requirements.txt && uvicorn main:app --port 8080
```

**0:05 — "Una conversación termina"** (simula el webhook de Omi):
```bash
curl -s -X POST "http://localhost:8080/webhook?uid=demo" \
  -H "Content-Type: application/json" \
  -d @sample_conversation.json
# → {"status":"ok","cards_created":5}
```
Di: *"Omi fires this webhook automatically when any conversation ends. No user action."*

**0:25 — "quiz me"** (esto es lo que el chat de Omi llama por detrás):
```bash
curl -s -X POST http://localhost:8080/tools/quiz_me \
  -H "Content-Type: application/json" -d '{"uid":"demo","limit":2}'
```
Muestra las preguntas generadas. Di: *"These are the exact tools Omi chat discovers via the omi-tools manifest — same pattern as the Hacker News and Wikipedia apps in the repo."*

**0:50 — Calificar y mostrar SM-2:**
```bash
curl -s -X POST http://localhost:8080/tools/grade_card \
  -H "Content-Type: application/json" \
  -d '{"uid":"demo","card_id":"<id>","grade":"good"}'
# → "Recorded 'good'. Next review in 1 day(s)."
```
Di: *"Real SM-2: 1 day, then 6, then growing intervals. Fail a card and it's back in 10 minutes."*

**1:15 — Export a Anki:** abre en el navegador `http://localhost:8080/deck/demo.apkg`, e importa el archivo en Anki en cámara. Ver las cards dentro de Anki es el momento "wow".

**1:40 — Cierre:** muestra la landing (`http://localhost:8080/`) y di el pitch de misión.

## Cómo subir el PR

```bash
# 1. Haz fork de github.com/BasedHardware/omi (botón Fork)
git clone https://github.com/TU_USUARIO/omi.git && cd omi
git checkout -b add-omi-recall-app

# 2. Copia la carpeta omi-recall-app/ dentro de plugins/
git add plugins/omi-recall-app/
git commit -m "feat: add omi-recall-app plugin (spaced-repetition flashcards from conversations)"
git push origin add-omi-recall-app

# 3. Abre el PR desde GitHub hacia BasedHardware/omi
```

pytest plugins/omi-recall-app/test_main.py -v

## Respuestas a preguntas probables de Nik

- **"Why not just ask Omi chat to quiz you?"** — Chat has no scheduling state. Recall persists SM-2 per card: what you got wrong comes back sooner. That's the difference between a chat trick and a learning system.
- **"Does it need OpenAI?"** — No. LLM extraction is optional; there's a heuristic fallback, so it runs with zero external services.
- **"Why SQLite?"** — Simplest thing that works; matches your 'implemented as simple as possible' criterion. Swapping to Firestore/Redis later is trivial — storage is isolated behind 6 small queries.
