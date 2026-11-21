# Datamuse Omi App

Find rhymes, synonyms, related words, and spelling suggestions from Omi conversations.

This is a standalone no-auth Omi app backed by the public Datamuse word-finding API. It does not require environment variables, OAuth, or API keys.

## Tools

- `find_rhymes`: words that rhyme with a given word.
- `find_related_words`: synonyms, rhymes, adjectives, associated nouns, common followers, or trigger words for a seed word.
- `suggest_spelling`: completions and corrections for a partial or misspelled word.

## Local Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

Health check:

```bash
curl http://localhost:8080/health
```

Tool manifest:

```bash
curl http://localhost:8080/.well-known/omi-tools.json
```

Example rhyme request:

```bash
curl -X POST http://localhost:8080/tools/find_rhymes \
  -H "Content-Type: application/json" \
  -d '{"word":"time"}'
```

Example related-words request:

```bash
curl -X POST http://localhost:8080/tools/find_related_words \
  -H "Content-Type: application/json" \
  -d '{"word":"ocean","relation":"synonym"}'
```

Example spelling request:

```bash
curl -X POST http://localhost:8080/tools/suggest_spelling \
  -H "Content-Type: application/json" \
  -d '{"partial":"eleph"}'
```

## Deployment

Deploy this folder as a standalone FastAPI service. Railway can use `railway.toml`; Heroku-style platforms can use the `Procfile`.

## Notes

- Datamuse's `/words` endpoint supports many lexical relations; this app exposes the six most useful for chat.
- Results are capped at 15 words so chat responses stay readable.
- Malformed rows in upstream responses are skipped rather than failing the whole tool call.
