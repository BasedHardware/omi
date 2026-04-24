<div align="center">

# **omi**

### A 2nd brain you trust more than your 1st

Omi captures your screen and conversations, transcribes in real-time, generates summaries and action items, and gives you an AI chat that remembers everything you've seen and heard. Works on desktop, phone and wearables. Fully open source.

Trusted by 300,000+ professionals.


[![Discord](https://img.shields.io/discord/1192313062041067520?label=Discord&logo=discord&logoColor=white&style=for-the-badge)](http://discord.omi.me)&ensp;
[![GitHub Repo stars](https://img.shields.io/github/stars/BasedHardware/Omi?style=for-the-badge)](https://github.com/BasedHardware/Omi)&ensp;
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

[Website](https://omi.me/) · [Docs](https://docs.omi.me/) · [Discord](http://discord.omi.me) · [Twitter](https://x.com/kodjima33) · [DeepWiki](https://deepwiki.com/BasedHardware/omi)

</div>

## Quick Start



```bash
git clone https://github.com/BasedHardware/omi.git && cd omi/desktop && ./run.sh --yolo
```

Builds the macOS app, connects to the cloud backend, and launches. No env files, no credentials, no local backend.

> **Requirements:** macOS 14+, [Xcode](https://developer.apple.com/xcode/) (includes Swift & code signing), [Node.js](https://nodejs.org/)

<details>
  <summary>Full Installation</summary>
  
For local development with the full backend stack:

1. Install prerequisites

```bash
xcode-select --install
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

2. Clone and configure

```bash
git clone https://github.com/BasedHardware/omi.git
cd omi/desktop
cp Backend-Rust/.env.example Backend-Rust/.env
```

3. Build and run

```bash
./run.sh
```

See [desktop/README.md](desktop/README.md) for environment variables and credential setup.


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

</details>

## Documentation

### Getting Started
- [Introduction](https://docs.omi.me/)
- [Quick Start Guide](https://docs.omi.me/quickstart)
- [macOS App Development](desktop/README.md)
- [Mobile App Setup](https://docs.omi.me/doc/developer/AppSetup)
- [Backend Setup](https://docs.omi.me/doc/developer/backend/Backend_Setup)
- [Contributing](https://docs.omi.me/doc/developer/Contribution)

### Building Apps
- [App Development Guide](https://docs.omi.me/doc/developer/apps/Introduction)
- [Example Apps](https://docs.omi.me/doc/developer/apps/examples/Github) — GitHub, Slack, OmiMentor
- [Audio Streaming Apps](https://docs.omi.me/doc/developer/apps/AudioStreaming)
- [Custom Chat Tools](https://docs.omi.me/doc/developer/apps/ChatTools)
- [Submit to App Store](https://docs.omi.me/doc/developer/apps/Submitting)

### API & SDKs
- [API Reference](https://docs.omi.me/api-reference/introduction) — REST endpoints for memories, conversations, action items
- [Python SDK](sdks/python/)
- [Swift SDK](sdks/swift/)
- [React Native SDK](sdks/react-native/)
- [MCP Server](mcp/) — Model Context Protocol integration

### Architecture
- [Backend Deep Dive](https://docs.omi.me/doc/developer/backend/backend_deepdive)
- [Transcription Pipeline](https://docs.omi.me/doc/developer/backend/transcription)
- [Chat System](https://docs.omi.me/doc/developer/backend/chat_system)
- [Audio Streaming Pipeline](https://docs.omi.me/doc/developer/backend/listen_pusher_pipeline)
- [BLE Protocol](https://docs.omi.me/doc/developer/Protocol)

## Omi Hardware
![Omi](https://github.com/user-attachments/assets/7a658366-9e02-4057-bde5-a510e1f0217a)

Open-source AI wearables that pair with the mobile app for 24h+ continuous capture.

<p align="center">
  <img src="https://github.com/user-attachments/assets/834d3fdb-31b5-4f22-ae35-da3d2b9a8f59" alt="Omi Wearable" width="49%" />
  <img src="https://github.com/user-attachments/assets/fdad4226-e5ce-4c55-b547-9101edfa3203" alt="Omi Glass" width="49%" />
</p>

- [Buy Omi](https://www.omi.me/pages/product)
- [Buy Omi Glass Dev Kit](https://www.omi.me/glass) — ESP32-S3, camera + audio
- [Open Source Hardware Designs](https://docs.omi.me/doc/hardware/consumer/electronics)
- [Buying Guide](https://docs.omi.me/doc/assembly/Buying_Guide)
- [Build the Device](https://docs.omi.me/doc/assembly/Build_the_device)
- [Flash Firmware](https://docs.omi.me/doc/get_started/Flash_device)
- [Integrate Your Wearable](https://docs.omi.me/doc/integrations)
- [Hardware Specs](https://docs.omi.me/doc/hardware/DevKit2)

## License

MIT — see [LICENSE](LICENSE)
