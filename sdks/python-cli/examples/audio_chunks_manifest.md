# Audio Chunks → Manifest Recipe

This recipe demonstrates how to turn a directory of raw audio chunk files into a
validated SHA‑256 manifest JSON file using the provided `audio_chunks_to_manifest.py`
script.

## What the script does

* Recursively walks the supplied directory.
* Computes a SHA‑256 hash and records the size (in bytes) for **every regular file**.
* Emits a JSON document with the following top‑level keys:
  * `version` – manifest format version (currently `1`).
  * `generated_at` – UTC timestamp of creation.
  * `files` – a mapping of *relative file path* → `{ "sha256": "...", "size": N }`.

The manifest is written **atomically**: a temporary file is created in the same
directory as the target and then renamed, guaranteeing that a partially‑written
file never appears on disk.

## Usage

