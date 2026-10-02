# conversations → LaTeX report (.tex)

Convert Omi conversation JSON exports into a self-compiling LaTeX report —
one `\section` per conversation with metadata, summary, action-item
checklist (`\checkmark`/`$\square$`), and a timestamped transcript.

stdlib-only. All ten LaTeX special characters are escaped in a single pass,
so titles like `C++ & Rust: 100%` cannot break the build.

## One master document

```bash
python conversations_to_latex.py input.json --output report.tex
omi --json conversation list --include-transcript | python conversations_to_latex.py - report.tex
```

Compiles out of the box with `pdflatex`, `xelatex`, or `lualatex`.

## One standalone document per conversation

```bash
python conversations_to_latex.py input.json --output-dir ./reports/
```

Filenames follow `<YYYY-MM-DD>_<slug>_<id-prefix>.tex`; collisions are
resolved deterministically with `-2`, `-3`, ... suffixes.

## Flags

| Flag | Meaning |
|---|---|
| `input` | JSON file path, or `-` for stdin |
| `output` / `--output` / `-o` | master `.tex` output path (default `conversations_report.tex`) |
| `--output-dir` | one standalone `.tex` per conversation |
| `--overwrite` | overwrite on filename collision (default: exclusive-creation) |

Envelope unwrapping supports bare arrays, `conversations`/`items`/`data`/`results`
keys, and single conversation objects. UTF-8 BOM tolerated. Output paths are
guarded against traversal.

Tests: `python -m unittest sdks/python-cli/tests/test_conversations_to_latex.py` (from repo root) or run inside `tests/`.