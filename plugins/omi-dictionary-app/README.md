# Omi English Dictionary

A standalone Omi chat-tool service for questions such as “What does serendipity
mean?” and “How do you pronounce that word?” It uses [Free Dictionary API](https://dictionaryapi.dev/)
without an API key or a user account.

## Tools

- `get_word_definition`: up to five definitions (three by default), available
  usage examples and synonyms, with source and license attribution.
- `get_word_pronunciation`: phonetic spellings and available pronunciation audio
  links, including their source and license. It returns links; it does not play audio.

Both tools accept `word`, an English word or short phrase up to 80 characters.
The definition tool also accepts `max_definitions` (1–5). Coverage varies by word;
missing entries and unavailable pronunciation are reported explicitly. This is
an English dictionary, not a translation service. Definition and example text
is shortened for chat; follow the returned source links for full entries.

Only the requested word is sent to the dictionary provider. Extra Omi fields
such as `uid` are not forwarded. The service stores no conversation history,
credentials, lookup results or audio. Hosting access logs remain the operator's
responsibility. `/health` checks the local service, not provider availability.

## Run locally

From this directory, with Python 3.11:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8080
```

```sh
curl http://127.0.0.1:8080/.well-known/omi-tools.json
curl http://127.0.0.1:8080/tools/get_word_definition \
  -H 'Content-Type: application/json' -d '{"word":"serendipity","max_definitions":2}'
curl http://127.0.0.1:8080/tools/get_word_pronunciation \
  -H 'Content-Type: application/json' -d '{"word":"hello"}'
```

Tool responses follow Omi's `{"result": "...", "error": null}` contract. Invalid
requests, missing words and provider failures return HTTP 200 with a non-null
`error` and null `result`, so the assistant can explain the failure.

## Verification

Hermetic tests replace the provider with `httpx.MockTransport`; no network calls
are made. They exercise the actual FastAPI routes, validation, manifest and error
responses. From the repository root, run the same command registered for CI:

```sh
uv run --isolated --no-project --python 3.11 \
  --with-requirements plugins/omi-dictionary-app/requirements.txt \
  python -m unittest discover -s plugins/omi-dictionary-app -p test_main.py
```

For a live check, start the server and run the curl examples above. Also look up
a nonexistent word and confirm it returns a clear error. Live provider checks
are deliberately separate from the hermetic test suite.

## Deployment and Omi setup

Deploy this directory as an independent service, with it as the build root. The
Dockerfile runs as an unprivileged user; `PORT` defaults to 8080. Railway can use
the included `railway.toml`. A public HTTPS base URL is required for Omi to reach
the service. Hosting may cost money; this repository does not provision it.

The tool manifest is at `/.well-known/omi-tools.json`. Register the two POST chat
tools in Omi using their manifest parameter schemas and your service's HTTPS
endpoints and enable the `external_integration` capability. See the
[Omi chat-tools guide](https://docs.omi.me/doc/developer/apps/ChatTools).
No OAuth callback or user-specific setup flow is required.

The dictionary content and audio have their own licenses, separate from this
service's code. Preserve the attribution returned with each tool result. Audio
is served by the upstream host and is neither copied nor cached here.
