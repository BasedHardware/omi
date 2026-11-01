<div align="center">

# **omi**

### A 2nd brain you trust more than your 1st

Omi captures your screen and conversations, transcribes in real-time, generates summaries and action items, and gives you an AI chat that remembers everything you've seen and heard. Works on desktop, phone and wearables.

[![Discord](https://img.shields.io/discord/1192313062041067520?label=Discord&logo=discord&logoColor=white&style=for-the-badge)](http://discord.omi.me)&ensp;
[![GitHub Repo stars](https://img.shields.io/github/stars/BasedHardware/Omi?style=for-the-badge)](https://github.com/BasedHardware/Omi)&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

[Website](https://omi.me/) · [Developer Docs](https://docs.omi.me/) · [Help Center](https://help.omi.me) · [Discord](http://discord.omi.me)

</div>

## What is Omi?

Omi is an open-source AI wearable platform: a necklace that captures conversations, apps for phone and desktop, and a backend that turns what you say into memory you can search and chat with. The mobile apps, desktop apps, backend, firmware, and hardware designs are all open source in this repository (MIT); the hosted Omi Cloud service and paid plans are described at [omi.me](https://www.omi.me/).

## Quick Start

### macOS

```sh
git clone https://github.com/BasedHardware/omi.git && cd omi/desktop/macos && ./run.sh --yolo
```

Builds the macOS app, connects to the cloud backend, and launches. No env files, no credentials, no local backend.

> **Requirements:** macOS 14+, [Xcode](https://developer.apple.com/xcode/) (includes Swift & code signing), [Node.js](https://nodejs.org/)

### Windows

```powershell
git clone https://github.com/BasedHardware/omi.git
cd omi\desktop\windows
npm install
copy .env.example .env
npm run dev
```

Starts the Windows desktop app from source using the public config in `.env.example`.

> **Requirements:** [Node.js](https://nodejs.org/)

In a development worktree, run `make setup` once. It installs the Git hooks and syncs the pinned backend Python environment that some pre-push checks use. Mobile and desktop environments stay opt-in.

```bash
make setup
```

<details>
<summary>Full Installation</summary>

For local development with the full backend stack:

1. Install prerequisites

```bash
xcode-select --install
uv --version
```

2. Clone and configure

```bash
git clone https://github.com/BasedHardware/omi.git
cd omi/desktop/macos
cp ../../backend/.env.template ../../backend/.env
```

3. Build and run

```bash
./run.sh
```

See [desktop/macos/README.md](desktop/macos/README.md) for environment variables and credential setup.

### Mobile App

```bash
cd app && bash setup.sh ios    # or: bash setup.sh android
```

</details>

<p align="center">
  <a href="https://macos.omi.me"><img src="docs/assets/readme/download-macos-badge.png" alt="Download for macOS" height="50"></a>
  <a href="https://apps.apple.com/us/app/friend-ai-wearable/id6502156163"><img src="docs/assets/readme/download-appstore-badge.png" alt="Download on the App Store" height="50"></a>
  <a href="https://play.google.com/store/apps/details?id=com.friend.ios"><img src="docs/assets/readme/download-gplay-badge.png" alt="Get it on Google Play" height="50"></a>
</p>

<p align="center">
  <a href="https://app.omi.me">Try in Browser</a>
</p>

<details>
<summary>How it works</summary>


```
┌─────────────────────────────────────────────────────────┐
│                      Your Devices                       │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Omi      │  │ macOS App    │  │ Mobile App        │  │
│  │ Wearable │  │ (Swift/Python) │  │ (Flutter)         │  │
│  └────┬─────┘  └──────┬───────┘  └────────┬──────────┘  │
│       │    BLE         │   HTTPS/WS        │             │
└───────┼────────────────┼───────────────────┼─────────────┘
        │                │                   │
        ▼                ▼                   ▼
┌─────────────────────────────────────────────────────────┐
│                    Omi Backend (Python)                  │
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐  │
│  │ Listen  │  │ Pusher   │  │ VAD     │  │ Diarizer │  │
│  │ (REST)  │  │ (WS)     │  │ (GPU)   │  │ (GPU)    │  │
│  └─────────┘  └──────────┘  └─────────┘  └──────────┘  │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐  │
│  │ STT     │  │ Firestore│  │ Redis   │  │ LLMs     │  │
│  │         │  │ (DB)     │  │ (Cache) │  │ (AI)     │  │
│  └─────────┘  └──────────┘  └─────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

| Component | Path | Stack |
|-----------|------|-------|
| **macOS app** | [`desktop/macos/`](desktop/macos/) | Swift, SwiftUI, Python desktop backend |
| Mobile app | [`app/`](app/) | Flutter (iOS & Android) |
| Backend API | [`backend/`](backend/) | Python, FastAPI, Firebase |
| Firmware | [`omi/`](omi/) | nRF, Zephyr, C |
| Omi Glass | [`omiGlass/`](omiGlass/) | ESP32-S3, C |
| SDKs | [`sdks/`](sdks/) | Device (Python/Swift/RN + multi-lang protocol) |
| AI Personas | [`web/personas-open-source/`](web/personas-open-source/) | Next.js |

</details>

## Documentation

Everything for builders lives at **[docs.omi.me](https://docs.omi.me)**: apps and webhooks, the Developer API, the MCP server, the CLI, SDKs, hardware, and how Omi works. End-user guides live in the [help center](https://help.omi.me).

- [What is Omi](https://docs.omi.me/doc/get_started/what-is-omi) · [Choose your path](https://docs.omi.me/doc/get_started/choose-your-path)
- [Developer API](https://docs.omi.me/doc/developer/api/overview) · [API reference](https://docs.omi.me/api-reference/introduction)
- [Build apps](https://docs.omi.me/doc/developer/apps/Introduction) · [MCP server](https://docs.omi.me/doc/developer/mcp/introduction) · [CLI](https://docs.omi.me/doc/developer/cli/introduction) · [SDKs](https://docs.omi.me/doc/developer/sdk/sdk)
- [Hardware & firmware](https://docs.omi.me/doc/hardware/OmiConsumer) · [Open hardware files](https://docs.omi.me/doc/hardware/consumer/index)
- [Developer changelog](https://docs.omi.me/doc/reference/changelog)

## Omi Hardware

![Omi](https://github.com/user-attachments/assets/7a658366-9e02-4057-bde5-a510e1f0217a)

Open-source AI wearables that pair with the mobile app for continuous capture.

<p align="center">
  <img src="https://github.com/user-attachments/assets/834d3fdb-31b5-4f22-ae35-da3d2b9a8f59" alt="Omi Wearable" width="49%" />
  <img src="https://github.com/user-attachments/assets/fdad4226-e5ce-4c55-b547-9101edfa3203" alt="Omi Glass" width="49%" />
</p>

- [Buy Omi](https://www.omi.me/pages/product) · [Buy Omi Glass Dev Kit](https://www.omi.me/glass)
- [Hardware docs](https://docs.omi.me/doc/hardware/OmiConsumer) · [Open hardware files](https://docs.omi.me/doc/hardware/consumer/index)
- [Flash firmware](https://docs.omi.me/doc/get_started/Flash_device) · [Integrate your own wearable](https://docs.omi.me/doc/integrations)

## Contributing

Contributions are welcome: bug reports with reproductions, apps and integrations built on the platform, community ports, and core PRs. Read the [contribution guide](https://docs.omi.me/doc/developer/Contribution) and [`CONTRIBUTING.md`](CONTRIBUTING.md) first; [`PRODUCT.md`](PRODUCT.md) describes the product direction and invariants. Paid, team-posted [bounties](https://docs.omi.me/doc/contribute/bounties) appear on issues labeled "Paid Bounty 💰".

Community: [Discord](http://discord.omi.me) · [Code of Conduct](CODE_OF_CONDUCT.md). User support: [help.omi.me](https://help.omi.me). Business and legal: [team@basedhardware.com](mailto:team@basedhardware.com).

## License

MIT. See [LICENSE](LICENSE).
