<div align="center">

# **omi**

### A 2nd brain you trust more than your 1st

Omi captures your screen and conversations, transcribes in real-time, generates summaries and action items, and gives you an AI chat that remembers everything you've seen and heard. Works on desktop, phone and wearables. Fully open source.

Trusted by 300,000+ professionals.

<br>

[<img src="https://img.shields.io/badge/Download-macOS_App-000000?style=for-the-badge&logo=apple&logoColor=white" height="40">](https://omi.me/download)

<br>

[![Discord](https://img.shields.io/discord/1192313062041067520?label=Discord&logo=discord&logoColor=white&style=for-the-badge)](http://discord.omi.me)&ensp;
[![GitHub Repo stars](https://img.shields.io/github/stars/BasedHardware/Omi?style=for-the-badge)](https://github.com/BasedHardware/Omi)&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

[Website](https://omi.me/) · [Docs](https://docs.omi.me/) · [Discord](http://discord.omi.me) · [Twitter](https://x.com/kodjima33) · [DeepWiki](https://deepwiki.com/BasedHardware/omi)

</div>

---

## Quick Start

```bash
git clone https://github.com/BasedHardware/omi.git && cd omi/desktop && ./run.sh --yolo
```

Builds the macOS app, connects to the cloud backend, and launches. No env files, no credentials, no local backend.

> **Requirements:** macOS 14+, [Xcode](https://developer.apple.com/xcode/) (includes Swift & code signing), [Node.js](https://nodejs.org/)

### Full Installation

For local development with the full backend stack:

```bash
# 1. Install prerequisites
xcode-select --install
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 2. Clone and configure
git clone https://github.com/BasedHardware/omi.git
cd omi/desktop
cp Backend-Rust/.env.example Backend-Rust/.env

# 3. Build and run (starts Rust backend + auth + Cloudflare tunnel + Swift app)
./run.sh
```

See [desktop/README.md](desktop/README.md) for environment variables and credential setup.

### Mobile App

```bash
cd app && bash setup.sh ios    # or: bash setup.sh android
```

[<img src='https://upload.wikimedia.org/wikipedia/commons/3/3c/Download_on_the_App_Store_Badge.svg' alt="Download on the App Store" height="50px" width="180px">](https://apps.apple.com/us/app/friend-ai-wearable/id6502156163)
[<img src='https://upload.wikimedia.org/wikipedia/commons/7/78/Google_Play_Store_badge_EN.svg' alt='Get it on Google Play' height="50px" width="180px">](https://play.google.com/store/apps/details?id=com.friend.ios)
· [Try in Browser](https://app.omi.me)

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│                      Your Devices                       │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Omi      │  │ macOS App    │  │ Mobile App        │  │
│  │ Wearable │  │ (Swift/Rust) │  │ (Flutter)         │  │
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
│                                                         │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────────┐  │
│  │ Deepgram│  │ Firestore│  │ Redis   │  │ LLMs     │  │
│  │ (STT)   │  │ (DB)     │  │ (Cache) │  │ (AI)     │  │
│  └─────────┘  └──────────┘  └─────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────┘
```

| Component | Path | Stack |
|-----------|------|-------|
| **macOS app** | [`desktop/`](desktop/) | Swift, SwiftUI, Rust backend |
| Mobile app | [`app/`](app/) | Flutter (iOS & Android) |
| Backend API | [`backend/`](backend/) | Python, FastAPI, Firebase |
| Firmware | [`omi/`](omi/) | nRF, Zephyr, C |
| Omi Glass | [`omiGlass/`](omiGlass/) | ESP32-S3, C |
| SDKs | [`sdks/`](sdks/) | React Native, Swift, Python |
| AI Personas | [`web/personas-open-source/`](web/personas-open-source/) | Next.js |

## Create Your Own App (1 min)

1. Download the Omi app and create a webhook at [webhook.site](https://webhook.site)
2. In the app: **Explore → Create an App → Select Capability → Paste Webhook URL → Install**
3. Start speaking — real-time transcript appears on webhook.site

See the [full guide](https://docs.omi.me/doc/developer/apps/Introduction).

## Documentation

### Getting Started
- [Introduction](https://docs.omi.me/)
- [Quick Start Guide](https://docs.omi.me/quickstart)
- [macOS App Development](desktop/README.md)
- [Mobile App Setup](https://docs.omi.me/doc/developer/AppSetup)
- [Backend Setup](https://docs.omi.me/doc/developer/backend/Backend_Setup)
- [Contributing](https://docs.omi.me/doc/developer/Contribution)

### API & SDKs
- [API Reference](https://docs.omi.me/api-reference/introduction) — REST endpoints for memories, conversations, action items
- [Python SDK](sdks/python/)
- [Swift SDK](sdks/swift/)
- [React Native SDK](sdks/react-native/)
- [MCP Server](mcp/) — Model Context Protocol integration

### Building Apps
- [App Development Guide](https://docs.omi.me/doc/developer/apps/Introduction)
- [Example Apps](https://docs.omi.me/doc/developer/apps/examples/Github) — GitHub, Slack, OmiMentor
- [Audio Streaming Apps](https://docs.omi.me/doc/developer/apps/AudioStreaming)
- [Custom Chat Tools](https://docs.omi.me/doc/developer/apps/ChatTools)
- [Submit to App Store](https://docs.omi.me/doc/developer/apps/Submitting)

### Architecture
- [Backend Deep Dive](https://docs.omi.me/doc/developer/backend/backend_deepdive)
- [Transcription Pipeline](https://docs.omi.me/doc/developer/backend/transcription)
- [Chat System](https://docs.omi.me/doc/developer/backend/chat_system)
- [Audio Streaming Pipeline](https://docs.omi.me/doc/developer/backend/listen_pusher_pipeline)
- [BLE Protocol](https://docs.omi.me/doc/developer/Protocol)

### Hardware
- [Buying Guide](https://docs.omi.me/doc/assembly/Buying_Guide)
- [Build the Device](https://docs.omi.me/doc/assembly/Build_the_device)
- [Flash Firmware](https://docs.omi.me/doc/get_started/Flash_device)
- [Integrate Your Wearable](https://docs.omi.me/doc/integrations)
- [Hardware Specs](https://docs.omi.me/doc/hardware/DevKit2)

## Omi Hardware

Open-source AI wearables that pair with the mobile app for 24h+ continuous capture.

- [Buy Omi Dev Kit](https://www.omi.me/products/omi-dev-kit-2) — nRF, BLE, coin cell battery
- [Buy Omi Glass Dev Kit](https://www.omi.me/glass) — ESP32-S3, camera + audio
- [Open Source Hardware Designs](https://docs.omi.me/doc/hardware/consumer/electronics)

<p align="center">
  <img src="https://github.com/user-attachments/assets/834d3fdb-31b5-4f22-ae35-da3d2b9a8f59" alt="Omi Wearable" width="49%" />
  <img src="https://github.com/user-attachments/assets/fdad4226-e5ce-4c55-b547-9101edfa3203" alt="Omi Glass" width="49%" />
</p>

![Omi](https://github.com/user-attachments/assets/7a658366-9e02-4057-bde5-a510e1f0217a)

## License

MIT — see [LICENSE](LICENSE)
