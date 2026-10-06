# pCloud Omi Backup App

Turnkey cloud-backup integration for Omi conversations supporting **pCloud** storage
with multi-region data center support (United States and Europe), encrypted token storage,
and an extensible provider protocol.

Addresses [BasedHardware/omi #20213](https://github.com/BasedHardware/omi/issues/20213).

## Features

- **Extensible Architecture**: Implements `CloudBackupProvider` protocol, establishing
  a unified interface for modular cloud storage destinations.
- **Multi-Region Routing**:
  - Global / US: `https://api.pcloud.com` (Auth: `https://my.pcloud.com/oauth2/authorize`, `location_id: 1`)
  - European Union: `https://eapi.pcloud.com` (Auth: `https://e-my.pcloud.com/oauth2/authorize`, `location_id: 2`)
- **Least-Privilege OAuth & Account Isolation**:
  - Secure authorization flow with per-account token encryption at rest.
  - One-time CSRF state expiration.
  - Complete credential revocation on disconnect.
- **Automated Conversation Synchronization**:
  - `/conversation` webhook automatically exports finalized conversations.
  - Supports `summary.md`, `transcript.md`, and raw audio WAV (`audio.wav`).
- **Explicit Privacy & Consent Gates**:
  - Independent user preferences for summary, transcript, and audio export.
  - Private transcripts and audio require explicit opt-in consent before export.
- **Idempotent Storage & Sequential Folder Management**:
  - Creates parent folder hierarchies sequentially to prevent pCloud API error 2002.
  - Rejects relative directory traversal (`.` and `..`).
  - Safe overwrite retries (`renameifexists=0`) to eliminate duplicate numbered files.
- **Hermetic Test Suite**: 25 mocked unit and integration tests with zero external
  network or server dependencies.

## Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Health check confirming service readiness |
| `GET` | `/setup/pcloud?uid={uid}` | Webview setup interface showing connection status & settings |
| `GET` | `/auth/pcloud?uid={uid}` | Initiates OAuth 2.0 flow with pCloud |
| `GET` | `/auth/pcloud/callback` | Exchanges code for access token and saves encrypted credentials |
| `GET` | `/disconnect?uid={uid}` | Revokes access and erases local user credentials |
| `POST` | `/settings?uid={uid}` | Saves folder name, region, and privacy consent preferences |
| `POST` | `/conversation?uid={uid}` | Webhook invoked by Omi to export finalized conversation |
| `POST` | `/audio?uid={uid}` | Buffers raw conversation audio chunks |

## Privacy & Retention Policy

- **Token Storage**: Credentials are encrypted at rest using per-account authenticated keystreams.
- **Disconnect Behavior**: Disconnecting deletes all local tokens and revokes OAuth access.
- **Remote File Retention**: Existing files already uploaded to pCloud remain permanently preserved
  in the user's private personal storage and are never deleted by Omi.
