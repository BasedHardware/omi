# pCloud Omi Backup App

Extensible cloud-backup destination for conversation summaries,
transcripts, and audio supporting **pCloud** storage with multi-region
data center support (United States and Europe).

Addresses [BasedHardware/omi #20213](https://github.com/BasedHardware/omi/issues/20213).

## Features

- **Extensible Architecture**: Implements `CloudBackupProvider` protocol,
  designed to establish a unified interface for modular cloud storage
  destinations (with pCloud provided as the first implementation).
- **Multi-Region Routing**:
  - Global / US: `https://api.pcloud.com` (`location_id: 1`)
  - European Union: `https://eapi.pcloud.com` (`location_id: 2`)
- **Selective Backups**: Independent user preferences for `save_summary`,
  `save_transcript`, and `save_audio`.
- **Idempotent Storage**: Prevents duplicate uploads on network retry.
- **Hermetic Test Suite**: 100% mocked unit tests with zero external
  network dependencies.

