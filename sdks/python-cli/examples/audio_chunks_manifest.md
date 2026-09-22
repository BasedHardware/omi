# Index raw audio chunk directories into a verified SHA-256 JSON manifest

Use this recipe when you want to inventory, audit, or verify raw audio chunks
recorded by Omi hardware or synced to your local machine. It computes streaming
SHA-256 checksums, byte sizes, and format tags for all audio files in a directory tree,
emitting an atomic JSON manifest. This complements [`conversations_sqlite.md`](conversations_sqlite.md)
and [`conversations_csv.md`](conversations_csv.md) by operating on the raw acoustic
recording layer rather than transcript text exports.

You need Python 3.10+ (standard library only; no third-party dependencies required).

## Where audio chunks come from

Raw audio files typically originate from:
1. **Omi SD card / Mass Storage:** When mounting an Omi hardware device or inserting its SD card, raw recordings are stored in segmented directories (such as `recordings/`, `chunks/`, or timestamped folders containing `.wav`, `.pcm`, or `.opus` chunks).
2. **Local companion app cache:** When the Omi device syncs recording sessions over Bluetooth or Wi-Fi to a local desktop or mobile daemon, audio chunks are buffered locally in temporary directories before being uploaded or transcribed.
3. **Session archive directories:** Stored collections of audio files prior to cloud synchronization, cold archival, or model fine-tuning.

## Generate a manifest

To index a directory of audio chunks:

```sh
python sdks/python-cli/examples/audio_chunks_to_manifest.py /path/to/recordings -o audio_manifest.json
```

The script searches recursively (`rglob`) across subdirectories, case-insensitively recognizing all standard audio extensions (`.wav`, `.pcm`, `.mp3`, `.m4a`, `.opus`, `.flac`, `.ogg`, `.aac`).

## Safe atomic writes and collision prevention

- **Atomic write:** The manifest is written to a temporary `.partial` file and atomically renamed via `os.replace()`. If interrupted, no half-written or corrupted manifest remains on disk.
- **Overwrite guard:** If the destination file already exists, the script raises `FileExistsError` to prevent accidental overwrites of existing audit records.

## Manifest format

The resulting JSON manifest provides full file metadata:

```json
{
  "source_directory": "/path/to/recordings",
  "total_files": 42,
  "total_bytes": 10485760,
  "chunks": [
    {
      "filename": "chunk_001.wav",
      "relative_path": "2026-09-22/chunk_001.wav",
      "size_bytes": 249600,
      "modified_at": 1758547200,
      "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "format": "wav"
    }
  ]
}
```

## Primary Use Cases

- **Pre-upload integrity verification:** Validate that uploaded audio batches match on-disk SHA-256 checksums without data corruption.
- **Deduplication:** Detect identical chunks across disparate recording sessions using the computed `sha256` digest.
- **Offline auditing & archival:** Archive conversation transcripts alongside verifiable hashes of the original hardware audio captures.
