# Cursor Configuration

This directory contains Cursor-specific configuration to make the codebase Cursor-compatible and help AI agents understand the entire Omi ecosystem.

## Structure

```
.cursor/
├── skills/                    # Skills organized by domain/automation
│   ├── {skill-name}/
│   │   ├── SKILL.md          # Skill definition
│   │   ├── commands/         # Related commands
│   │   │   └── {command}.md
│   │   └── agents/           # Related agents
│   │       └── {agent}.md
├── rules/                     # Rules (domain + general + automation)
├── commands/                   # Legacy symlinks (backward compatibility)
├── agents/                     # Legacy symlinks (backward compatibility)
├── docs/                      # Architecture and reference documentation
│   ├── INDEX.md              # Complete resource map
│   ├── USAGE_GUIDE.md        # Comprehensive usage guide
│   └── [other docs]
├── plans/                     # Plan Mode generated plans
├── hooks/                     # Hook scripts directory
├── mcp.json                   # MCP server configuration
├── hooks.json                 # Hooks configuration (optional)
├── worktrees.json             # Worktree setup configuration (optional)
├── BUGBOT.md                  # Bugbot review rules (optional)
└── README.md                  # This file
```

**Note**: The folder is organized by skills. Each skill contains its related commands and agents, making it easier to discover and maintain related resources. Legacy `commands/` and `agents/` directories may contain symlinks for backward compatibility.

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

### Commands

Commands are organized within skill folders at `skills/{skill}/commands/`. Type `/` in Cursor chat to see all available commands.

**Backend Commands** (`skills/omi-backend-patterns/commands/`):
- `/backend-setup` - Guide for setting up backend environment
- `/backend-test` - Run backend tests with proper environment
- `/backend-deploy` - Deploy backend to production

**Flutter Commands** (`skills/omi-flutter-patterns/commands/`):
- `/flutter-setup` - Flutter environment setup
- `/flutter-test` - Run Flutter tests
- `/flutter-build` - Build Flutter app

**Plugin Commands** (`skills/omi-plugin-development/commands/`):
- `/create-plugin` - Scaffold new plugin structure
- `/create-app` - Scaffold new Omi app
- `/test-integration` - Run integration tests

**Documentation Commands** (`skills/docs-automation/commands/`):
- `/auto-docs` - Automatically detect code changes and update documentation
- `/docs` - Generate or update documentation
- `/update-api-docs` - Update API reference documentation

**PR Commands** (`skills/pr-automation/commands/`):
- `/auto-pr` - Automatically generate PR with description and validation
- `/pr` - Summarize changes and propose PR title/description
- `/code-review` - Review code for correctness, security, quality, tests

**Other Commands**:
- `/auto-changelog` (`skills/changelog/commands/`) - Automatically generate changelog from commits
- `/auto-triage` (`skills/issue-triage/commands/`) - Automatically triage GitHub issues
- `/self-improve`, `/learn-from-pr`, `/learn-from-conversation` (`skills/self-improvement/commands/`) - Self-improvement commands
- `/format`, `/lint-and-fix`, `/security-audit`, `/fix-issue`, `/validate-docs`, `/verify-complete`, `/run-tests-and-fix` (general commands in `.cursor/commands/`)

**New Feature Commands**:
- `/plan`, `/ask`, `/debug` (`skills/agent-modes/commands/` or `.cursor/commands/`) - Agent mode workflows
- `/review-changes` (`skills/agent-review/commands/` or `.cursor/commands/`) - Use Agent Review to find issues
- `/diagram` (`skills/diagram-generation/commands/` or `.cursor/commands/`) - Generate Mermaid diagrams
- `/browser-test`, `/accessibility-audit` (`skills/browser-automation/commands/` or `.cursor/commands/`) - Browser testing and accessibility
- `/semantic-search` (`skills/context-optimization/commands/` or `.cursor/commands/`) - Semantic search guidance

### Skills (`.cursor/skills/`)

Skills are organized in `skills/{skill-name}/` folders. Each skill folder contains:
- `SKILL.md` - The skill definition
- `commands/` - Related slash commands
- `agents/` - Related specialized agents

**Domain Skills**:
- `omi-backend-patterns/` - Backend-specific patterns (conversation processing, memory extraction, chat system)
  - Commands: `/backend-setup`, `/backend-test`, `/backend-deploy`
  - Agents: `backend-api-developer`, `backend-llm-engineer`, `backend-database-engineer`
- `omi-flutter-patterns/` - Flutter-specific patterns (BLE, audio streaming, state management)
  - Commands: `/flutter-setup`, `/flutter-test`, `/flutter-build`
  - Agents: `flutter-developer`
- `omi-firmware-patterns/` - Firmware patterns (BLE services, audio codecs)
  - Agents: `firmware-engineer`
- `omi-api-integration/` - API integration patterns (Developer API, MCP, webhooks)
  - Commands: `/update-api-docs`
  - Agents: `web-developer`, `sdk-developer`
- `omi-plugin-development/` - Plugin development workflow
  - Commands: `/create-plugin`, `/create-app`, `/test-integration`
  - Agents: `plugin-developer`

**Automation Skills**:
- `docs-automation/` - Automate documentation updates when code changes
  - Commands: `/auto-docs`, `/docs`, `/update-api-docs`
  - Agents: `docs-generator`
- `pr-automation/` - Automate PR workflows and validation
  - Commands: `/auto-pr`, `/pr`, `/code-review`
  - Agents: `pr-manager`, `code-reviewer`, `test-runner`, `verifier`
- `changelog/` - Generate changelog entries from commits
  - Commands: `/auto-changelog`
  - Agents: `changelog-generator`
- `issue-triage/` - Automate GitHub issue triage using triage guide
  - Commands: `/auto-triage`
- `self-improvement/` - Learn from PRs, issues, and user interactions
  - Commands: `/self-improve`, `/learn-from-pr`, `/learn-from-conversation`
- `rule-updater/` - Programmatically update Cursor rules

**New Feature Skills**:
- `agent-modes/` - Guidance on choosing and using agent modes (Agent, Ask, Plan, Debug)
  - Commands: `/plan`, `/ask`, `/debug`
- `debug-mode/` - Debug Mode workflows for tricky bugs and regressions
  - Commands: `/debug`
  - Agents: `debug-specialist`
- `browser-automation/` - Browser testing, design-to-code, accessibility auditing
  - Commands: `/browser-test`, `/accessibility-audit`
  - Agents: `browser-automation`
- `diagram-generation/` - Mermaid diagram generation for architecture visualization
  - Commands: `/diagram`
  - Agents: `diagram-generator`
- `context-optimization/` - Context window optimization and @ mention strategies
  - Commands: `/semantic-search`
  - Agents: `context-manager`
- `agent-review/` - Agent Review workflows for catching bugs before merging
  - Commands: `/review-changes`

### Agents

Agents are organized within skill folders at `skills/{skill}/agents/`. Each agent is a `.md` file with YAML frontmatter (name, description, model, is_background) followed by the prompt.

**Backend Agents** (`skills/omi-backend-patterns/agents/`):
- `backend-api-developer.md` - FastAPI router development, endpoint patterns
- `backend-llm-engineer.md` - LLM integration, prompt engineering, LangGraph
- `backend-database-engineer.md` - Firestore, Pinecone, Redis optimization

**Frontend Agents**:
- `flutter-developer.md` (`skills/omi-flutter-patterns/agents/`) - Flutter app development, BLE integration
- `web-developer.md` (`skills/omi-api-integration/agents/`) - Next.js frontend development

**Firmware Agents**:
- `firmware-engineer.md` (`skills/omi-firmware-patterns/agents/`) - C/C++ firmware development, BLE services

**Integration Agents**:
- `plugin-developer.md` (`skills/omi-plugin-development/agents/`) - Plugin/app development, webhook integration
- `sdk-developer.md` (`skills/omi-api-integration/agents/`) - SDK development (Python, Swift, React Native)

**Automation Agents**:
- `docs-generator.md` (`skills/docs-automation/agents/`) - Automatically generate/update documentation when code changes
- `pr-manager.md`, `code-reviewer.md`, `test-runner.md`, `verifier.md` (`skills/pr-automation/agents/`) - PR automation agents
- `changelog-generator.md` (`skills/changelog/agents/`) - Generate changelog entries from commits/PRs

**New Feature Agents**:
- `debug-specialist.md` (`skills/debug-mode/agents/`) - Debug Mode workflows: hypothesis generation, log instrumentation, runtime analysis
- `browser-automation.md` (`skills/browser-automation/agents/`) - Browser testing, design-to-code, accessibility auditing
- `diagram-generator.md` (`skills/diagram-generation/agents/`) - Mermaid diagram generation for architecture visualization
- `context-manager.md` (`skills/context-optimization/agents/`) - Context window optimization, @ mention strategies, semantic search guidance

### Documentation (`.cursor/docs/`)

Architecture and reference documentation:

- `ARCHITECTURE.md` - Complete system architecture with diagrams
- `API_REFERENCE.md` - API endpoint reference
- `DATA_FLOW.md` - Data flow diagrams for key workflows
- `BACKEND_COMPONENTS.md` - Backend module reference
- `FLUTTER_COMPONENTS.md` - Flutter app structure
- `FIRMWARE_COMPONENTS.md` - Firmware architecture
- `INDEX.md` - Complete resource map and relationships (rules, commands, skills, agents)
- `USAGE_GUIDE.md` - Comprehensive usage guide with getting started, workflows, and best practices
- `feedback-loop.md` - Feedback loop system documentation
- `user-interaction-learning.md` - User interaction learning system

### Plans (`.cursor/plans/`)

Plan Mode can save generated plans to this directory for future reference and team sharing. Plans are created when you click "Save to workspace" in Plan Mode.

### Hooks (`.cursor/hooks/` and `.cursor/hooks.json`)

Hooks allow you to observe, control, and extend the agent loop using custom scripts. See [Cursor Hooks documentation](https://cursor.com/docs/agent/hooks) for details.

- `hooks.json` - Hook configuration (optional, template provided)
- `hooks/` - Directory for hook scripts

### Worktrees (`.cursor/worktrees.json`)

Configuration for worktree setup when using parallel agents. See [Cursor Worktrees documentation](https://cursor.com/docs/configuration/worktrees) for details.

- `worktrees.json` - Worktree setup commands (optional, template provided)

### Bugbot (`.cursor/BUGBOT.md`)

Review guidelines for Bugbot to automatically catch issues before they reach human reviewers. See [Cursor Bugbot documentation](https://cursor.com/docs/cookbook/bugbot-rules) for details.

- `BUGBOT.md` - Bugbot review rules (optional, template provided)

## Usage

### Rules

Rules are automatically applied based on:
- File globs (e.g., `backend/**/*.py`)
- Always applied flag (for rules like `codebase-overview.mdc`)

### Commands

Type `/` in Cursor chat to see available commands. Commands provide step-by-step guidance for common tasks.

### Skills

Skills are automatically available when working in relevant parts of the codebase. They provide domain-specific guidance and patterns.

### Agents

Agents can be invoked for specialized tasks. They have deep knowledge of their specific domain. Agents are automatically available to Agent and appear in Cursor settings. Each agent file is located in `skills/{skill}/agents/{agent}.md` with YAML frontmatter containing `name`, `description`, `model`, and `is_background`.

**Automation agents** are designed to run proactively when relevant tasks are detected, automatically handling documentation updates, PR creation, test running, code review, verification, and changelog generation.

### MCP Integration (`.cursor/mcp.json`)

Model Context Protocol (MCP) servers provide external tool integration:

- **GitHub MCP**: PR/issue automation, fetching repository data
- **Notion MCP**: Sync internal docs to Notion (if configured)
- **Figma MCP**: Reference design assets (if configured)
- **Browser MCP**: Web testing and validation

MCP servers enable automation workflows like auto-updating docs from code changes, creating PRs programmatically, and syncing with external documentation.

## Community Skills from skills.sh

[skills.sh](https://skills.sh/) is the open agent skills ecosystem that makes finding and installing skills easier for both developers and AI agents. Skills v1.1.1+ includes interactive discovery and agent support.

### Discovering Skills

**For Developers:**
```bash
# Interactive skill discovery (search as you type)
npx skills find

# Install a skill
npx skills add <owner/repo> <skill-name>

# Update existing skills
npx skills update
```

**For AI Agents:**
- Use the `find-skills` meta skill from `vercel-labs/skills` for programmatic discovery
- Skills.sh supports non-interactive mode for automated workflows
- When users ask for skills, recommend them from [skills.sh](https://skills.sh/) based on their needs

### Recommended Skills for Omi

**Frontend/Web:**
```bash
# React/Next.js best practices
npx skills add vercel-labs/agent-skills vercel-react-best-practices

# Web design guidelines
npx skills add vercel-labs/agent-skills web-design-guidelines

# TypeScript patterns
npx skills add wshobson/agents typescript-advanced-types
```

**Backend:**
```bash
# FastAPI patterns
npx skills add wshobson/agents fastapi-templates

# Python testing
npx skills add wshobson/agents python-testing-patterns

# API design principles
npx skills add wshobson/agents api-design-principles
```

**Mobile:**
```bash
# React Native best practices
npx skills add callstackincubator/agent-skills react-native-best-practices

# Expo skills
npx skills add expo/skills building-native-ui
```

**Other Useful Skills:**
```bash
# Code review excellence
npx skills add wshobson/agents code-review-excellence

# Architecture patterns
npx skills add wshobson/agents architecture-patterns

# Git workflows
npx skills add wshobson/agents git-advanced-workflows
```

### Skill Recommendations

When users ask for skills or need help with specific tasks, recommend relevant skills from [skills.sh](https://skills.sh/). Browse the [skills leaderboard](https://skills.sh/) to find popular and trending skills for your use case.

## Automation Capabilities

The `.cursor` folder includes comprehensive automation for:

### Documentation Automation
- Auto-detect API endpoint changes and update API reference docs
- Generate architecture diagrams from code structure
- Sync documentation between `.cursor/` and `docs/` directories
- Update Mermaid diagrams automatically

### PR Automation
- Generate comprehensive PR descriptions from git diff
- Validate PR requirements (tests, docs, conventions)
- Link related issues automatically
- Suggest reviewers based on changed files

### Test Automation
- Automatically run tests based on changed files
- Fix test failures and re-run until green
- Run tests in parallel where possible
- Analyze failures and suggest fixes

### Code Review Automation
- Check architecture compliance
- Verify import hierarchy
- Check for common mistakes
- Perform security audits

### Verification
- Verify completed work actually functions
- Run end-to-end tests
- Check edge cases
- Report incomplete implementations

### Changelog Generation
- Parse commit messages following conventional commits
- Categorize changes (feat/fix/docs)
- Generate formatted changelog entries
- Update CHANGELOG.md automatically

### Issue Triage
- Score issues using triage formula from ISSUE_TRIAGE_GUIDE.MD
- Assign priority levels (P0-P3)
- Suggest lane assignment
- Map issues to Omi layers

## Related Files

- **`.cursorignore`** - Files excluded from semantic search and indexing (security & performance)
- **`AGENTS.md`** - Project root file with coding guidelines and conventions
- **`CLAUDE.md`** - Additional coding guidelines
- **`.cursor/mcp.json`** - MCP server configuration for external tool integration

## Architecture Overview

Omi is a multimodal AI wearable platform with:

- **Backend**: Python/FastAPI (Firebase, Pinecone, Redis, Deepgram, OpenAI)
- **App**: Flutter/Dart (iOS, Android, macOS, Windows)
- **Firmware**: C/C++ (nRF chips, ESP32-S3, Zephyr)
- **Web**: Next.js/TypeScript (frontend, personas)
- **Plugins**: Python/Node.js apps
- **SDKs**: Python, Swift, React Native
- **MCP**: Python Model Context Protocol server

See `.cursor/docs/ARCHITECTURE.md` for detailed architecture documentation.

## Documentation References

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

All documentation is available locally in the `docs/` folder and deployed at [docs.omi.me](https://docs.omi.me/).

### Key Documentation Files

**Backend**:
- `docs/doc/developer/backend/backend_deepdive.mdx` - [Backend architecture](https://docs.omi.me/doc/developer/backend/backend_deepdive)
- `docs/doc/developer/backend/chat_system.mdx` - [Chat system](https://docs.omi.me/doc/developer/backend/chat_system)
- `docs/doc/developer/backend/StoringConversations.mdx` - [Data storage](https://docs.omi.me/doc/developer/backend/StoringConversations)
- `docs/doc/developer/backend/transcription.mdx` - [Transcription](https://docs.omi.me/doc/developer/backend/transcription)
- `docs/doc/developer/backend/Backend_Setup.mdx` - [Backend setup](https://docs.omi.me/doc/developer/backend/Backend_Setup)

**App & Protocol**:
- `docs/doc/developer/AppSetup.mdx` - [App setup](https://docs.omi.me/doc/developer/AppSetup)
- `docs/doc/developer/Protocol.mdx` - [BLE protocol](https://docs.omi.me/doc/developer/Protocol)

**API**:
- `docs/doc/developer/api/overview.mdx` - [API overview](https://docs.omi.me/doc/developer/api/overview)
- `docs/api-reference/` - [API endpoints](https://docs.omi.me/api-reference/)

**App Development**:
- `docs/doc/developer/apps/Introduction.mdx` - [Plugin development](https://docs.omi.me/doc/developer/apps/Introduction)
- `docs/doc/developer/MCP.mdx` - [MCP server](https://docs.omi.me/doc/developer/MCP)

**Complete Index**: `docs/INDEX.md` - [View online](https://docs.omi.me/llms.txt)

### Internal Cursor Documentation

- `.cursor/docs/` - Internal Cursor agent documentation (not user-facing)
- `.cursor/docs/INDEX.md` - Complete Cursor resource map and relationships

### External Resources

- [docs.omi.me](https://docs.omi.me/) - Complete online documentation
- [Cursor Docs](https://cursor.com/docs) - Cursor documentation

## Getting Help

- **New to Cursor?** Start with `.cursor/docs/USAGE_GUIDE.md` for comprehensive guidance
- **Looking for resources?** See `.cursor/docs/INDEX.md` for complete resource map and relationships
- **Need quick reference?** Check the relevant rule file for patterns
- **Common tasks?** Use commands for step-by-step guidance
- **Architecture questions?** Reference architecture documentation in `docs/` folder (source of truth)

## Cross-Referencing System

All resources (rules, commands, skills, subagents) are deeply interconnected:

- **Rules** reference related rules, skills, subagents, and commands
- **Skills** reference related rules and subagents that use them
- **Subagents** reference related rules and skills they use
- **Commands** reference related rules, skills, and subagents

This interconnected structure ensures:
- **Deep Context**: AI can navigate between related resources
- **Staying in Sync**: Cross-references help maintain consistency
- **Better Discovery**: Easy to find related resources
- **Comprehensive Help**: Full context of the ecosystem

See `.cursor/docs/INDEX.md` for the complete relationship map.
