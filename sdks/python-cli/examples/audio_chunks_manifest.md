# Audio Chunks → Manifest Recipe

This recipe converts a directory of raw audio chunk files into a validated
SHA‑256 JSON manifest.  The manifest can be used by downstream services
to verify file integrity, deduplicate uploads, or feed into a
transcription pipeline.

## Prerequisites

- Python 3.8+ installed.
- The `sdks/python-cli` package installed in your environment
  (e.g. `pip install -e .` from the repository root).

## Usage

