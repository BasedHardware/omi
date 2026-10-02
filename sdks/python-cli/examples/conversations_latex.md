# Export Omi Conversations to LaTeX (.tex)

Use this recipe to turn your Omi conversation exports into a clean, self-contained
**LaTeX report** (`.tex`). One `\section` per conversation carries its metadata,
summary, action-item checklist, and a timestamped transcript, and the whole thing
compiles out-of-the-box with `pdflatex`, `xelatex`, or `lualatex` into a
print-ready PDF. Every field is special-character escaped, so titles like
`C++ & Rust: 100%` can never break the build.

## Requirements

- Python 3.10+ (standard library only, no `pip install`)
- An authenticated `omi-cli` (`omi auth login`)
- A LaTeX distribution (TeX Live / MiKTeX) **only if** you want to compile to PDF;
  the exporter itself has no LaTeX dependency

## Quickstart

### Option 1: Direct Pipeline via Stdin (Recommended)

Fetch recent conversations (with full transcripts) and render one master report:

```bash
omi --json conversation list --include-transcript --limit 50 | \
  python conversations_to_latex.py - omi_conversations.tex
```

### Option 2: Export from a Saved JSON File

```bash
omi --json conversation list --include-transcript --limit 100 > conversations.json
python conversations_to_latex.py conversations.json omi_conversations.tex
```

### Option 3: One Standalone Document per Conversation

```bash
omi --json conversation list --include-transcript | \
  python conversations_to_latex.py - "" --output-dir ./tex/
```

Each file is a complete, independently compilable `.tex` named
`YYYY-MM-DD_slugified_title_shortid.tex`.

## Compile to PDF

```bash
pdflatex omi_conversations.tex
# or, for best Unicode support:
xelatex omi_conversations.tex
```

## Output Structure

### Sample Rendered Section

```latex
\section{1. AI Wearables Architecture Review}
\begin{description}
\item[ID] \texttt{conv-a1b2c3d4}
\item[Started] 2026-09-13 10:30:00 UTC
\item[Source] \texttt{omi\_necklace}
\item[Category] \texttt{engineering}
\item[Transcript] 3 segment(s), 2 speaker(s)
\end{description}

\subsection{Summary}
Discussion on reducing latency for real-time audio transcript streaming.

\subsection{Action items}
\begin{itemize}
\item \checkmark{} Benchmark on-device Opus compression vs raw PCM
\item \square{} Implement exponential backoff for Redis transcript buffer reconnects
\end{itemize}

\subsection{Transcript}
\begin{quote}
\textbf{Speaker 0} \texttt{[00:00]}: Good morning team, let's review the pipeline.\par
\textbf{Speaker 1} \texttt{[00:05]}: We ran benchmarks on the Opus codec.
\end{quote}
```

## Features

- **Compiles out of the box:** emits a full `\documentclass`/`\begin{document}`
  skeleton with a UTF-8 preamble, so `pdflatex`/`xelatex`/`lualatex` need no
  boilerplate from you.
- **Bulletproof escaping:** all ten LaTeX special characters (`\ & % $ # _ { } ~
  ^`) are escaped in a single pass over the source text, so an escape can never
  feed back into another — titles, summaries, and transcripts with `&`, `%`,
  `_`, or braces will not break the document.
- **Readable transcript:** dialogue turns are grouped in a `quote` environment
  with bold speaker attribution and `\texttt{[MM:SS]}` (or `[HH:MM:SS]`) stamps.
- **Action items as a checklist:** completed items render with `\checkmark`, open
  items with `\square` (from `amssymb`, no extra packages).
- **Pure standard library:** zero third-party Python dependencies.
- **Safe handling:** tolerates missing fields, loosely-typed values, UTF-8 BOM
  input, refuses to clobber existing files, and blocks path traversal in every
  output destination.
