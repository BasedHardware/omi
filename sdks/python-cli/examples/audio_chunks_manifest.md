# Generate audio chunks manifest

Use this recipe to index and catalog raw audio chunks or recordings from Omi hardware and local recordings into a structured JSON manifest with SHA-256 verification hashes, exact byte sizes, and formats.

Generate manifest:

```sh
python audio_chunks_to_manifest.py ./recordings audio_manifest.json
```
