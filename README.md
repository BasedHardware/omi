<div align="center">

# **Cortex**

### The agentic AI that lives on your PC

Cortex sees your screen, understands what you're doing, and **acts on your computer** — clicking, typing and navigating your apps when you ask (you approve each action). It runs on **the model you choose**: a private local model on your own machine, or any major cloud provider with your own key. It remembers what you've seen and heard, and gives you a chat that knows your context. Fully open source, with an optional Pro tier.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

[Website / Waitlist](https://cortex.apym.io)

</div>

## Quick Start

```bash
git clone <your-fork-url> cortex && cd cortex/desktop/windows
npm install
cp .env.example .env   # ships with working public defaults
npm run dev
```

Then open **Settings → Models** to point Cortex at a local model (Ollama / LM Studio) or a cloud provider, and **Settings → Cortex Pro** to start your trial.

> **Requirements:** Windows 10/11, [Node.js](https://nodejs.org/). Packaged installer: `npm run build:win`.

See [desktop/windows/README.md](desktop/windows/README.md) for environment variables, the optional Google integration, and build details.

## What Cortex does

- **Controls your PC** — an agent that takes real UI actions in your apps (click, type, navigate), each one approved by you. The Windows automation layer (bridge + planner + approval dialog) lives in [`desktop/windows`](desktop/windows).
- **Runs on your model of choice** — local (private, no key) or cloud (bring your own key); you decide where your data is processed.
- **Remembers** — captures screen/conversation context, builds memories and a knowledge graph, and gives you a chat that knows what you've seen.
- **Open core** — the app is free and open source; a Pro tier (14-day trial) adds cloud sync and higher automation limits.

## AI engine — local or cloud, your choice

Pick your engine in **Settings → Models**. Providers are grouped by region so you control where your data goes (full lineup in [`desktop/windows/src/shared/providers.ts`](desktop/windows/src/shared/providers.ts)):

| Region | Providers |
|--------|-----------|
| **On your computer** (private, no key) | Ollama, LM Studio |
| **North America** | OpenAI, Anthropic, xAI, Groq, Together AI |
| **Europe** | Mistral AI |
| **China** | Alibaba DashScope (Qwen), Zhipu/Z.ai (GLM), Moonshot (Kimi), DeepSeek *(text-only)*, Tencent Hunyuan, Baidu ERNIE, Volcengine (Doubao) |
| **Global / aggregators** | Ollama Cloud (`-cloud` models), OpenRouter, Google (Gemini), Custom (any OpenAI-compatible endpoint) |

Cloud providers use your own API key, stored locally on your device only.

<details>
  <summary>How it works</summary>

```
┌──────────────────────────────────────────────────────────┐
│                        Your PC                           │
│                                                          │
│   ┌──────────────────────────────────────────────────┐  │
│   │            Cortex (Electron + React)             │  │
│   │                                                  │  │
│   │  Agent loop ──► Automation layer (control PC)    │  │
│   │     │            click · type · navigate         │  │
│   │     │            (you approve each action)       │  │
│   │     ▼                                            │  │
│   │  Model router                                    │  │
│   └─────┬───────────────────────────────┬───────────┘  │
│         │                               │              │
│         ▼ local (private)               ▼ cloud (BYOK) │
│   ┌────────────┐                  ┌──────────────────┐ │
│   │ Ollama /   │                  │ OpenAI·Anthropic·│ │
│   │ LM Studio  │                  │ Mistral·Qwed·GLM·│ │
│   └────────────┘                  │ Kimi·Gemini·…    │ │
│                                   └──────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

| Component | Path | Stack |
|-----------|------|-------|
| **Windows app** (Cortex) | [`desktop/windows/`](desktop/windows/) | Electron, React, TypeScript |
| Desktop app (macOS) | [`desktop/macos/`](desktop/macos/) | Swift, SwiftUI, Rust backend |
| Mobile app | [`app/`](app/) | Flutter (iOS & Android) |
| Backend API | [`backend/`](backend/) | Python, FastAPI, Firebase |
| SDKs | [`sdks/`](sdks/) | React Native, Swift, Python |
| MCP Server | [`mcp/`](mcp/) | Model Context Protocol integration |

</details>

## Cortex Pro

Cortex is open source and fully usable for free. **Pro** (14-day trial, no card) adds:

- **Cloud sync** — encrypted sync of conversations, memories and settings across devices
- **Unlimited PC control** — removes the free-tier daily cap on agent actions
- **Priority models** — pin premium cloud models with priority routing

Reserve your spot at **[cortex.apym.io](https://cortex.apym.io)**.

## Contributing

Agent and contributor guidelines live in [AGENTS.md](AGENTS.md); component-specific notes are in each component's `AGENTS.md` / `CLAUDE.md`.

## License

MIT — see [LICENSE](LICENSE)
