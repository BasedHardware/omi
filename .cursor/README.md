# Cursor Configuration

This directory contains Cursor-specific configuration to make the codebase Cursor-compatible and help AI agents understand the entire Omi ecosystem.

## Structure

### Rules (`.cursor/rules/`)

Project-specific rules that guide AI behavior based on file context:

**Backend Rules**:
- `backend-imports.mdc` - Python import rules (no in-function imports, module hierarchy)
- `backend-architecture.mdc` - System architecture, module hierarchy, data flow
- `backend-api-patterns.mdc` - FastAPI patterns, router conventions, error handling
- `backend-database-patterns.mdc` - Firestore, Pinecone, Redis usage patterns
- `backend-llm-patterns.mdc` - LLM client usage, prompt engineering, LangGraph
- `backend-testing.mdc` - Test structure, mocking patterns

**Flutter Rules**:
- `flutter-localization.mdc` - Flutter l10n requirements
- `flutter-architecture.mdc` - App structure, state management, providers
- `flutter-backend-integration.mdc` - API client patterns, WebSocket handling
- `flutter-ble-protocol.mdc` - Bluetooth Low Energy device communication

**Firmware Rules**:
- `firmware-architecture.mdc` - nRF/ESP32 structure, Zephyr patterns
- `firmware-ble-service.mdc` - BLE service implementation, audio streaming

**Web Rules**:
- `web-nextjs-patterns.mdc` - Next.js App Router, API routes, Firebase integration

**Plugin Rules**:
- `plugin-development.mdc` - Plugin structure, webhook patterns, OAuth flows

**General Rules**:
- `codebase-overview.mdc` - High-level architecture, component relationships (always applied)
- `documentation-standards.mdc` - MDX documentation patterns, API docs
- `formatting.mdc` - Code formatting standards
- `memory-management.mdc` - Memory management best practices
- `testing.mdc` - Always run tests before committing

### Commands (`.cursor/commands/`)

Slash commands available in Cursor chat:

**General Commands**:
- `/code-review` - Review code for correctness, security, quality, tests
- `/pr` - Summarize changes and propose PR title/description
- `/run-tests-and-fix` - Run tests, fix failures, re-run until green
- `/security-audit` - Security-focused code review
- `/lint-and-fix` - Run linter, auto-fix issues
- `/format` - Format code according to project standards
- `/fix-issue` - Fix bug or implement feature from issue
- `/docs` - Generate or update documentation

**Domain-Specific Commands**:
- `/backend-setup` - Guide for setting up backend environment
- `/backend-test` - Run backend tests with proper environment
- `/flutter-setup` - Flutter environment setup
- `/flutter-test` - Run Flutter tests
- `/create-plugin` - Scaffold new plugin structure
- `/create-app` - Scaffold new Omi app
- `/update-api-docs` - Update API reference documentation
- `/validate-docs` - Check documentation links and formatting

### Skills (`.cursor/skills/`)

Reusable skills for Omi-specific patterns:

- `omi-backend-patterns/` - Backend-specific patterns (conversation processing, memory extraction, chat system)
- `omi-flutter-patterns/` - Flutter-specific patterns (BLE, audio streaming, state management)
- `omi-firmware-patterns/` - Firmware patterns (BLE services, audio codecs)
- `omi-api-integration/` - API integration patterns (Developer API, MCP, webhooks)
- `omi-plugin-development/` - Plugin development workflow

### Agents (`.cursor/agents/`)

Specialized subagents for different domains:

**Backend Subagents**:
- `backend-api-developer/` - FastAPI router development, endpoint patterns
- `backend-llm-engineer/` - LLM integration, prompt engineering, LangGraph
- `backend-database-engineer/` - Firestore, Pinecone, Redis optimization

**Frontend Subagents**:
- `flutter-developer/` - Flutter app development, BLE integration
- `web-developer/` - Next.js frontend development

**Firmware Subagents**:
- `firmware-engineer/` - C/C++ firmware development, BLE services

**Integration Subagents**:
- `plugin-developer/` - Plugin/app development, webhook integration
- `sdk-developer/` - SDK development (Python, Swift, React Native)

### Documentation (`.cursor/`)

Architecture and reference documentation:

- `ARCHITECTURE.md` - Complete system architecture with diagrams
- `API_REFERENCE.md` - API endpoint reference
- `DATA_FLOW.md` - Data flow diagrams for key workflows
- `BACKEND_COMPONENTS.md` - Backend module reference
- `FLUTTER_COMPONENTS.md` - Flutter app structure
- `FIRMWARE_COMPONENTS.md` - Firmware architecture

## Usage

### Rules

Rules are automatically applied based on:
- File globs (e.g., `backend/**/*.py`)
- Always applied flag (for rules like `codebase-overview.mdc`)

### Commands

Type `/` in Cursor chat to see available commands. Commands provide step-by-step guidance for common tasks.

### Skills

Skills are automatically available when working in relevant parts of the codebase. They provide domain-specific guidance and patterns.

### Subagents

Subagents can be invoked for specialized tasks. They have deep knowledge of their specific domain.

## Community Skills

Recommended community skills from [skills.sh](https://skills.sh/) to install:

```bash
# React/Next.js patterns
npx skills add vercel-labs/agent-skills vercel-react-best-practices

# FastAPI patterns
npx skills add wshobson/agents fastapi-templates

# Python testing
npx skills add wshobson/agents python-testing-patterns

# TypeScript patterns
npx skills add wshobson/agents typescript-advanced-types
```

## Related Files

- **`.cursorignore`** - Files excluded from semantic search and indexing (security & performance)
- **`AGENTS.md`** - Project root file with coding guidelines and conventions
- **`CLAUDE.md`** - Additional coding guidelines

## Architecture Overview

Omi is a multimodal AI wearable platform with:

- **Backend**: Python/FastAPI (Firebase, Pinecone, Redis, Deepgram, OpenAI)
- **App**: Flutter/Dart (iOS, Android, macOS, Windows)
- **Firmware**: C/C++ (nRF chips, ESP32-S3, Zephyr)
- **Web**: Next.js/TypeScript (frontend, personas)
- **Plugins**: Python/Node.js apps
- **SDKs**: Python, Swift, React Native
- **MCP**: Python Model Context Protocol server

See `.cursor/ARCHITECTURE.md` for detailed architecture documentation.

## Documentation References

External documentation is available at:
- [docs.omi.me](https://docs.omi.me/) - Complete Omi documentation
- [Cursor Docs](https://cursor.com/docs) - Cursor documentation

Key documentation files in this repo:
- `docs/doc/developer/backend/backend_deepdive.mdx` - Backend architecture
- `docs/doc/developer/backend/chat_system.mdx` - Chat system
- `docs/doc/developer/backend/StoringConversations.mdx` - Data storage
- `docs/doc/developer/AppSetup.mdx` - App setup
- `docs/doc/developer/Protocol.mdx` - BLE protocol
- `docs/doc/developer/api/overview.mdx` - API reference
- `docs/doc/developer/apps/Introduction.mdx` - Plugin development
- `docs/doc/developer/MCP.mdx` - MCP server

## Getting Help

- Check the relevant rule file for patterns
- Use commands for step-by-step guidance
- Reference architecture documentation
- Consult external docs at docs.omi.me
