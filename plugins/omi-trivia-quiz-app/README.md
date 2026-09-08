# Open Trivia & Voice Quiz Omi App

Interactive voice trivia games, multiple choice challenges, and quick True/False brain teasers for Omi AI wearable devices.

This is a standalone, no-auth Omi chat tool integration powered by the public, open [Open Trivia Database (OpenTDB)](https://opentdb.com) API. It requires **no API keys, user accounts, or environment variables**.

---

## Features & Chat Tools

- **`get_trivia_question`**: Dynamic multiple choice trivia questions across 24 knowledge categories with selectable difficulty (`easy`, `medium`, `hard`) and question type.
- **`get_true_false_quiz`**: Fast-paced True or False voice challenges optimized for quick conversational audio responses.
- **`list_trivia_categories`**: Browse all 24 available knowledge domains (Science & Nature, History, Computers, Film, Music, Geography, Mythology, Sports, etc.).

---

## Voice Prompts Supported by Omi

Users wearing Omi smart devices can naturally ask:

- *"Omi, give me a quick science trivia question."*
- *"Ask me a history question (hard difficulty)."*
- *"Give me a True or False question."*
- *"What trivia categories can I choose from?"*
- *"Quiz me on 90s movies."*
- *"Let's play a trivia game!"*

---

## Local Development & Testing

### 1. Set Up Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the Server
```bash
uvicorn main:app --reload --port 8080
```

### 3. Check Health & Tool Manifest
```bash
# Health check
curl http://localhost:8080/health

# Omi chat tools manifest
curl http://localhost:8080/.well-known/omi-tools.json
```

### 4. Run Automated Tests
```bash
# Run hermetic unit test suite
python3 -m unittest test_main.py

# Run live integration smoke tests
python3 smoke_test.py
```

---

## Example Tool Invocations

### 1. Get Multiple Choice Trivia Question
```bash
curl -X POST http://localhost:8080/tools/get_trivia_question \
  -H "Content-Type: application/json" \
  -d '{"category": "Science", "difficulty": "medium"}'
```
**Sample Response:**
```json
{
  "result": "🎯 Trivia Question (Medium | Science & Nature):\n\"What is the chemical symbol for Gold?\"\n\nOptions:\nA) Ag\nB) Au\nC) Fe\nD) Cu\n\n💡 Correct Answer: B) Au",
  "error": null
}
```

### 2. Quick True/False Challenge
```bash
curl -X POST http://localhost:8080/tools/get_true_false_quiz \
  -H "Content-Type: application/json" \
  -d '{"difficulty": "easy"}'
```
**Sample Response:**
```json
{
  "result": "⚡ Quick True/False Challenge (Easy | Geography):\n\"The Great Wall of China is visible from space with the naked eye.\"\n\nSay 'True' or 'False' to answer!\n\n💡 Correct Answer: False",
  "error": null
}
```

### 3. List Trivia Categories
```bash
curl -X POST http://localhost:8080/tools/list_trivia_categories \
  -H "Content-Type: application/json" \
  -d '{}'
```
**Sample Response:**
```json
{
  "result": "📚 Available Trivia Categories:\n• Animals\n• Art\n• Celebrities\n• Entertainment: Books\n• Entertainment: Film\n• Entertainment: Music\n• Entertainment: Video Games\n• Geography\n• History\n• Science & Nature\n• Science: Computers & Technology\n• Sports...",
  "error": null
}
```

---

## Architecture & Reliability

- **Standard OpenTDB Integration**: Direct connection to the open OpenTDB REST API with full HTML entity unescaping.
- **Smart Category Mapping**: Fuzzy keyword matcher maps natural user topics ("movies", "tech", "coding", "geo", "animals") to official category IDs.
- **In-Memory LRU Caching**: Caches category manifests and question sets to optimize speed.
- **Omi Chat-Tool Protocol Compliant**: Exposes `/.well-known/omi-tools.json` function manifest with JSON schema validation and structured `ChatToolResponse` error handling.
- **Ready for Deployment**: Includes `railway.toml` (Nixpacks), `Procfile`, and `runtime.txt` (`python-3.11`).
