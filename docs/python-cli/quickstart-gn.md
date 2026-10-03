# Guarani (`gn`) AI Agent Quickstart — OMI Python CLI

This guide gets you from zero to a running OMI AI agent configured for **Guarani (`gn`)**, the indigenous language of Paraguay and neighbouring regions (ISO 639-1 `gn`, ISO 639-3 `gug`).

## 1. Install the OMI Python CLI

```bash
pip install omi-cli
```

## 2. Create a Guarani agent

```bash
omi init my-gn-agent --language gn
cd my-gn-agent
```

## 3. Configure the language

Edit `omi.config.toml`:

```toml
[agent]
name = "my-gn-agent"

[language]
code = "gn"          # ISO 639-1
iso3 = "gug"         # ISO 639-3
name = "Guarani"
script = "Latn"      # Latin script
locale = "gn_PY"     # Paraguay
```

## 4. Run the agent

```bash
omi run
```

## 5. Verify

```bash
omi agent info
# Expected: language=gn (Guarani), locale=gn_PY
```

## Dialect & script notes

- Guarani is written in the **Latin script** with diacritics (`ã`, `ẽ`, `ĩ`, `õ`, `ũ`, `ỹ`) and the glottal stop `'` (puso).
- Ensure your terminal uses UTF-8 (`export LANG=en_US.UTF-8`) so nasal vowels render correctly.
- The `gn_PY` locale is the standard CLDR locale for Paraguayan Guarani.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Diacritics show as `?` | Terminal not UTF-8 | `export LANG=en_US.UTF-8` |
| `Unknown language code` | Old CLI version | `pip install -U omi-cli` |
| Wrong locale | `locale` not set | Set `locale = "gn_PY"` in config |
| Model replies in Spanish | Fallback language | Confirm `code = "gn"` and restart |

## Next steps

- Add a custom Guarani corpus under `data/gn/`.
- See `docs/python-cli/quickstart.md` for the base workflow.
