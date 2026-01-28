# Cursor Resources Index

Complete map of all Cursor resources (rules, commands, skills, subagents) and their relationships.

## Overview

This index provides a comprehensive view of all Cursor resources in the Omi codebase, showing how rules, commands, skills, and subagents interconnect to provide deep, contextual assistance across the entire codebase.

## Folder Structure

The `.cursor` folder is organized by skills, with related commands and agents grouped within each skill folder:

```
.cursor/
├── skills/                    # Skills organized by domain/automation
│   ├── omi-backend-patterns/
│   │   ├── SKILL.md          # Skill definition
│   │   ├── commands/          # Related commands
│   │   │   ├── backend-setup.md
│   │   │   ├── backend-test.md
│   │   │   └── backend-deploy.md
│   │   └── agents/            # Related agents
│   │       ├── backend-api-developer.md
│   │       ├── backend-llm-engineer.md
│   │       └── backend-database-engineer.md
│   ├── omi-flutter-patterns/
│   ├── omi-api-integration/
│   ├── docs-automation/
│   ├── pr-automation/
│   └── [other skills...]
├── rules/                     # Rules (unchanged)
├── commands/                  # Legacy symlinks (for backward compatibility)
├── agents/                    # Legacy symlinks (for backward compatibility)
└── docs/                      # Documentation
```

**Benefits of Skill-Based Organization:**
- All related resources (skill, commands, agents) are in one place
- Easier to discover resources for a specific domain
- Clearer relationships between resources
- Better maintainability

**Path References:**
- **New paths**: `skills/{skill}/commands/{command}.md` or `skills/{skill}/agents/{agent}.md`
- **Legacy paths**: `commands/{command}.md` or `agents/{agent}.md` (via symlinks, if available)

## Resource Counts

- **Rules**: 34 files (24 domain + 1 automation + 9 new features)
- **Commands**: 30 files (17 domain + 5 automation + 8 new features)
- **Skills**: 16 files (5 domain + 4 automation + 7 new features)
- **Subagents**: 18 files (8 domain + 6 automation + 4 new features)
- **MCP Config**: 1 file
- **Total**: 99 resources

## Rules (24)

### Backend Rules (6)

1. **backend-architecture.mdc**
   - **Description**: System architecture, module hierarchy, data flow patterns
   - **Globs**: `backend/**/*.py`
   - **Related Rules**: backend-imports, backend-api-patterns, backend-database-patterns, backend-llm-patterns, backend-testing, memory-management
   - **Related Skills**: omi-backend-patterns
   - **Related Subagents**: backend-api-developer, backend-llm-engineer, backend-database-engineer
   - **Related Commands**: /backend-setup, /backend-test, /backend-deploy

2. **backend-api-patterns.mdc**
   - **Description**: FastAPI router patterns, endpoint conventions, error handling
   - **Globs**: `backend/routers/**/*.py`
   - **Related Rules**: backend-architecture, backend-database-patterns, backend-llm-patterns, backend-testing, backend-imports
   - **Related Skills**: omi-backend-patterns, omi-api-integration
   - **Related Subagents**: backend-api-developer
   - **Related Commands**: /backend-setup, /backend-test, /update-api-docs

3. **backend-database-patterns.mdc**
   - **Description**: Firestore, Pinecone, Redis usage patterns
   - **Globs**: `backend/database/**/*.py`
   - **Related Rules**: backend-architecture, backend-api-patterns, backend-llm-patterns, backend-imports
   - **Related Skills**: omi-backend-patterns
   - **Related Subagents**: backend-database-engineer
   - **Related Commands**: /backend-setup, /backend-test

4. **backend-llm-patterns.mdc**
   - **Description**: LLM client usage, prompt engineering, LangGraph
   - **Globs**: `backend/utils/llm/**/*.py`, `backend/utils/retrieval/**/*.py`
   - **Related Rules**: backend-architecture, backend-api-patterns, backend-database-patterns, backend-imports
   - **Related Skills**: omi-backend-patterns
   - **Related Subagents**: backend-llm-engineer
   - **Related Commands**: /backend-setup, /backend-test

5. **backend-testing.mdc**
   - **Description**: Test structure, mocking patterns
   - **Globs**: `backend/tests/**/*.py`, `backend/**/*test*.py`
   - **Related Rules**: testing, backend-architecture, backend-api-patterns, backend-database-patterns
   - **Related Skills**: omi-backend-patterns
   - **Related Subagents**: backend-api-developer, backend-database-engineer
   - **Related Commands**: /backend-test, /run-tests-and-fix, /test-integration

6. **backend-imports.mdc**
   - **Description**: Python import rules (no in-function imports, module hierarchy)
   - **Globs**: `backend/**/*.py`
   - **Related Rules**: backend-architecture
   - **Related Skills**: omi-backend-patterns
   - **Related Subagents**: backend-api-developer, backend-llm-engineer, backend-database-engineer
   - **Related Commands**: /backend-setup, /lint-and-fix

### Flutter Rules (5)

7. **flutter-architecture.mdc**
   - **Description**: App structure, state management, providers
   - **Globs**: `app/**/*.dart`
   - **Related Rules**: flutter-backend-integration, flutter-ble-protocol, flutter-localization, flutter-platform-specific
   - **Related Skills**: omi-flutter-patterns
   - **Related Subagents**: flutter-developer
   - **Related Commands**: /flutter-setup, /flutter-test, /flutter-build

8. **flutter-backend-integration.mdc**
   - **Description**: API client patterns, WebSocket handling
   - **Globs**: `app/lib/backend/**/*.dart`
   - **Related Rules**: flutter-architecture, backend-api-patterns, backend-architecture
   - **Related Skills**: omi-flutter-patterns, omi-api-integration
   - **Related Subagents**: flutter-developer
   - **Related Commands**: /flutter-setup, /flutter-test

9. **flutter-ble-protocol.mdc**
   - **Description**: Bluetooth Low Energy device communication
   - **Globs**: `app/lib/utils/bluetooth/**/*.dart`, `app/lib/services/**/*ble*.dart`
   - **Related Rules**: flutter-architecture, firmware-ble-service, firmware-audio-codecs
   - **Related Skills**: omi-flutter-patterns, omi-firmware-patterns
   - **Related Subagents**: flutter-developer, firmware-engineer
   - **Related Commands**: /flutter-setup, /flutter-test

10. **flutter-localization.mdc**
    - **Description**: Flutter l10n requirements
    - **Globs**: `app/**/*.dart`
    - **Related Rules**: flutter-architecture
    - **Related Skills**: omi-flutter-patterns
    - **Related Subagents**: flutter-developer
    - **Related Commands**: /flutter-setup

11. **flutter-platform-specific.mdc**
    - **Description**: Platform-specific code (iOS, Android, macOS, Windows)
    - **Globs**: `app/**/*.dart`
    - **Related Rules**: flutter-architecture, flutter-localization
    - **Related Skills**: omi-flutter-patterns
    - **Related Subagents**: flutter-developer
    - **Related Commands**: /flutter-setup, /flutter-build

### Firmware Rules (3)

12. **firmware-architecture.mdc**
    - **Description**: nRF/ESP32 structure, Zephyr patterns
    - **Globs**: `omi/**/*.{c,h}`, `omiGlass/**/*.{c,h}`
    - **Related Rules**: firmware-ble-service, firmware-audio-codecs, flutter-ble-protocol
    - **Related Skills**: omi-firmware-patterns
    - **Related Subagents**: firmware-engineer
    - **Related Commands**: /flutter-setup

13. **firmware-audio-codecs.mdc**
    - **Description**: Audio codec implementation (Opus, PCM, Mu-law)
    - **Globs**: `omi/**/*.{c,h}`, `omiGlass/**/*.{c,h}`
    - **Related Rules**: firmware-architecture, firmware-ble-service, flutter-ble-protocol
    - **Related Skills**: omi-firmware-patterns
    - **Related Subagents**: firmware-engineer
    - **Related Commands**: /flutter-setup

14. **firmware-ble-service.mdc**
    - **Description**: BLE service implementation, audio streaming
    - **Globs**: `omi/**/*.{c,h}`, `omiGlass/**/*.{c,h}`
    - **Related Rules**: firmware-architecture, firmware-audio-codecs, flutter-ble-protocol
    - **Related Skills**: omi-firmware-patterns, omi-flutter-patterns
    - **Related Subagents**: firmware-engineer, flutter-developer
    - **Related Commands**: /flutter-setup

### Web Rules (2)

15. **web-nextjs-patterns.mdc**
    - **Description**: Next.js App Router, API routes, Firebase integration
    - **Globs**: `web/**/*.{tsx,ts}`
    - **Related Rules**: web-ui-components, backend-api-patterns
    - **Related Skills**: omi-api-integration
    - **Related Subagents**: web-developer
    - **Related Commands**: /backend-setup

16. **web-ui-components.mdc**
    - **Description**: Radix UI, Shadcn/ui component patterns
    - **Globs**: `web/**/*.{tsx,ts}`
    - **Related Rules**: web-nextjs-patterns
    - **Related Skills**: omi-api-integration
    - **Related Subagents**: web-developer
    - **Related Commands**: /backend-setup

### Plugin Rules (2)

17. **plugin-development.mdc**
    - **Description**: Plugin structure, webhook patterns, OAuth flows
    - **Globs**: `plugins/**/*.{py,js}`
    - **Related Rules**: plugin-apps-js, backend-api-patterns, backend-architecture
    - **Related Skills**: omi-plugin-development, omi-api-integration
    - **Related Subagents**: plugin-developer
    - **Related Commands**: /create-plugin, /create-app

18. **plugin-apps-js.mdc**
    - **Description**: JavaScript plugin patterns
    - **Globs**: `plugins/apps-js/**/*.js`
    - **Related Rules**: plugin-development, backend-api-patterns
    - **Related Skills**: omi-plugin-development, omi-api-integration
    - **Related Subagents**: plugin-developer
    - **Related Commands**: /create-plugin

### General Rules (6)

19. **codebase-overview.mdc** (alwaysApply: true)
    - **Description**: High-level architecture, component relationships
    - **Globs**: N/A (always applied)
    - **Related Skills**: All skills
    - **Related Subagents**: All subagents
    - **Related Commands**: All commands

20. **documentation-standards.mdc**
    - **Description**: MDX documentation patterns, API docs
    - **Globs**: `docs/**/*.{mdx,md}`
    - **Related Rules**: codebase-overview, backend-architecture, flutter-architecture
    - **Related Commands**: /docs, /validate-docs, /update-api-docs

21. **formatting.mdc**
    - **Description**: Code formatting standards
    - **Globs**: N/A
    - **Related Commands**: /format, /lint-and-fix

22. **git-workflow.mdc** (alwaysApply: true)
    - **Description**: Git workflow, branching, PR process
    - **Globs**: N/A (always applied)
    - **Related Rules**: testing, formatting, documentation-standards
    - **Related Commands**: /pr, /code-review, /run-tests-and-fix

23. **memory-management.mdc**
    - **Description**: Memory management best practices
    - **Globs**: `backend/**/*.py`
    - **Related Rules**: backend-architecture
    - **Related Skills**: omi-backend-patterns
    - **Related Subagents**: backend-api-developer, backend-llm-engineer, backend-database-engineer

24. **testing.mdc** (alwaysApply: true)
    - **Description**: Always run tests before committing
    - **Globs**: N/A (always applied)
    - **Related Rules**: backend-testing, git-workflow
    - **Related Commands**: /backend-test, /flutter-test, /run-tests-and-fix, /test-integration

25. **auto-documentation.mdc**
    - **Description**: Automatically update documentation when code changes
    - **Globs**: `backend/routers/**/*.py`, `backend/utils/**/*.py`, `backend/database/**/*.py`, `app/**/*.dart`
    - **Related Rules**: documentation-standards, backend-api-patterns
    - **Related Skills**: docs-automation
    - **Related Subagents**: docs-generator
    - **Related Commands**: /auto-docs, /update-api-docs, /docs

### New Feature Rules (9)

26. **agent-modes.mdc**
    - **Description**: Guidance on when and how to use different agent modes (Agent, Ask, Plan, Debug)
    - **Globs**: N/A
    - **Related Skills**: agent-modes, debug-mode
    - **Related Commands**: /plan, /ask, /debug

27. **agent-review.mdc**
    - **Description**: How to use Agent Review effectively to catch bugs before merging
    - **Globs**: N/A
    - **Related Skills**: agent-review, pr-automation
    - **Related Commands**: /review-changes, /code-review

28. **agent-browser.mdc**
    - **Description**: Browser automation patterns for web testing, design-to-code, and accessibility auditing
    - **Globs**: `web/**/*.{tsx,ts,jsx,js}`, `app/**/*web*.dart`
    - **Related Skills**: browser-automation
    - **Related Commands**: /browser-test, /accessibility-audit
    - **Related Subagents**: browser-automation

29. **semantic-search.mdc**
    - **Description**: Effective use of semantic search for code discovery and understanding
    - **Globs**: N/A
    - **Related Skills**: context-optimization
    - **Related Commands**: /semantic-search
    - **Related Subagents**: context-manager

30. **context-management.mdc**
    - **Description**: Best practices for context management using @ mentions and context window optimization
    - **Globs**: N/A
    - **Related Skills**: context-optimization
    - **Related Commands**: /semantic-search
    - **Related Subagents**: context-manager

31. **subagents-vs-skills.mdc**
    - **Description**: Guidance on when to use subagents vs skills, decision criteria and best practices
    - **Globs**: N/A
    - **Related Skills**: All skills
    - **Related Subagents**: All subagents

32. **large-codebase-patterns.mdc**
    - **Description**: Best practices for working with large codebases in Cursor
    - **Globs**: N/A
    - **Related Skills**: context-optimization, diagram-generation
    - **Related Commands**: /plan, /semantic-search, /diagram

## Commands (30)

### Backend Commands (3)

1. **/backend-setup**
   - **Related Rules**: backend-architecture, backend-imports, formatting
   - **Related Skills**: omi-backend-patterns
   - **Related Subagents**: backend-api-developer, backend-llm-engineer, backend-database-engineer

2. **/backend-test**
   - **Related Rules**: backend-testing, testing, backend-architecture
   - **Related Skills**: omi-backend-patterns
   - **Related Subagents**: backend-api-developer, backend-database-engineer
   - **Related Commands**: /run-tests-and-fix, /test-integration

3. **/backend-deploy**
   - **Related Rules**: backend-architecture, backend-testing, memory-management
   - **Related Skills**: omi-backend-patterns
   - **Related Commands**: /backend-setup, /backend-test, /code-review

### Flutter Commands (3)

4. **/flutter-setup**
   - **Related Rules**: flutter-architecture, flutter-platform-specific, flutter-localization
   - **Related Skills**: omi-flutter-patterns, omi-firmware-patterns
   - **Related Subagents**: flutter-developer, firmware-engineer
   - **Related Commands**: /flutter-test, /flutter-build

5. **/flutter-test**
   - **Related Rules**: testing, flutter-architecture
   - **Related Skills**: omi-flutter-patterns
   - **Related Subagents**: flutter-developer
   - **Related Commands**: /run-tests-and-fix, /flutter-setup

6. **/flutter-build**
   - **Related Rules**: flutter-architecture, flutter-platform-specific, formatting
   - **Related Skills**: omi-flutter-patterns
   - **Related Subagents**: flutter-developer
   - **Related Commands**: /flutter-setup, /flutter-test, /format

### Plugin Commands (2)

7. **/create-plugin**
   - **Related Rules**: plugin-development, plugin-apps-js, backend-api-patterns
   - **Related Skills**: omi-plugin-development, omi-api-integration
   - **Related Subagents**: plugin-developer
   - **Related Commands**: /test-integration

8. **/create-app**
   - **Related Rules**: plugin-development, backend-api-patterns
   - **Related Skills**: omi-plugin-development, omi-api-integration
   - **Related Subagents**: plugin-developer
   - **Related Commands**: /create-plugin, /test-integration

### General Commands (9)

9. **/code-review**
   - **Related Rules**: backend-architecture, flutter-architecture, backend-testing, git-workflow
   - **Related Commands**: /security-audit, /run-tests-and-fix, /lint-and-fix

10. **/pr**
    - **Related Rules**: git-workflow, testing, documentation-standards
    - **Related Commands**: /code-review, /run-tests-and-fix, /security-audit

11. **/run-tests-and-fix**
    - **Related Rules**: testing, backend-testing
    - **Related Commands**: /backend-test, /flutter-test, /test-integration

12. **/security-audit**
    - **Related Rules**: backend-architecture, backend-api-patterns, plugin-development
    - **Related Commands**: /code-review, /lint-and-fix

13. **/lint-and-fix**
    - **Related Rules**: formatting, backend-imports
    - **Related Commands**: /format, /code-review

14. **/format**
    - **Related Rules**: formatting
    - **Related Commands**: /lint-and-fix

15. **/fix-issue**
    - **Related Rules**: codebase-overview, backend-architecture, flutter-architecture
    - **Related Commands**: /run-tests-and-fix, /code-review

16. **/docs**
    - **Related Rules**: documentation-standards, backend-architecture, flutter-architecture
    - **Related Commands**: /update-api-docs, /validate-docs

17. **/update-api-docs**
    - **Related Rules**: documentation-standards, backend-api-patterns
    - **Related Skills**: omi-api-integration
    - **Related Subagents**: backend-api-developer
    - **Related Commands**: /docs, /validate-docs

18. **/validate-docs**
    - **Related Rules**: documentation-standards
    - **Related Commands**: /docs, /update-api-docs

19. **/test-integration**
    - **Related Rules**: plugin-development, backend-api-patterns
    - **Related Skills**: omi-plugin-development, omi-api-integration
    - **Related Subagents**: plugin-developer
    - **Related Commands**: /create-plugin, /create-app

### Automation Commands (5)

20. **/auto-docs**
    - **Description**: Automatically detect code changes and update documentation
    - **Related Rules**: auto-documentation, documentation-standards, backend-api-patterns
    - **Related Skills**: docs-automation
    - **Related Subagents**: docs-generator
    - **Related Commands**: /update-api-docs, /docs, /validate-docs

21. **/auto-pr**
    - **Description**: Automatically generate PR with description and validation
    - **Related Rules**: git-workflow, context-communication, testing
    - **Related Skills**: pr-automation
    - **Related Subagents**: pr-manager, code-reviewer, test-runner, verifier
    - **Related Commands**: /pr, /code-review, /run-tests-and-fix

22. **/auto-changelog**
    - **Description**: Automatically generate changelog from commits
    - **Related Rules**: git-workflow, documentation-standards
    - **Related Skills**: changelog
    - **Related Subagents**: changelog-generator
    - **Related Commands**: /pr

23. **/auto-triage**
    - **Description**: Automatically triage GitHub issues using triage guide
    - **Related Rules**: omi-specific-patterns
    - **Related Skills**: issue-triage
    - **Related Documentation**: ISSUE_TRIAGE_GUIDE.MD

24. **/verify-complete**
    - **Description**: Verify that completed work actually functions
    - **Related Rules**: verification, common-mistakes, testing
    - **Related Subagents**: verifier, test-runner
    - **Related Commands**: /run-tests-and-fix

### New Feature Commands (8)

25. **/plan**
    - **Description**: Plan Mode workflow guidance
    - **Related Rules**: agent-modes, large-codebase-patterns
    - **Related Skills**: agent-modes
    - **Related Commands**: /ask, /debug

26. **/ask**
    - **Description**: Ask Mode usage guidance
    - **Related Rules**: agent-modes, semantic-search
    - **Related Skills**: agent-modes, context-optimization
    - **Related Commands**: /plan, /semantic-search

27. **/debug**
    - **Description**: Debug Mode workflow
    - **Related Rules**: agent-modes, verification
    - **Related Skills**: debug-mode, agent-modes
    - **Related Subagents**: debug-specialist
    - **Related Commands**: /plan, /ask

28. **/review-changes**
    - **Description**: Use Agent Review to find issues
    - **Related Rules**: agent-review, git-workflow
    - **Related Skills**: agent-review, pr-automation
    - **Related Commands**: /code-review, /pr

29. **/diagram**
    - **Description**: Generate Mermaid diagrams
    - **Related Rules**: large-codebase-patterns
    - **Related Skills**: diagram-generation
    - **Related Subagents**: diagram-generator

30. **/browser-test**
    - **Description**: Browser testing workflow
    - **Related Rules**: agent-browser, testing
    - **Related Skills**: browser-automation
    - **Related Subagents**: browser-automation
    - **Related Commands**: /accessibility-audit

31. **/accessibility-audit**
    - **Description**: Accessibility auditing with browser
    - **Related Rules**: agent-browser
    - **Related Skills**: browser-automation
    - **Related Subagents**: browser-automation
    - **Related Commands**: /browser-test

32. **/semantic-search**
    - **Description**: Semantic search guidance
    - **Related Rules**: semantic-search, context-management
    - **Related Skills**: context-optimization
    - **Related Subagents**: context-manager

## Skill-Based Navigation

Resources are organized by skill. Each skill folder contains:
- `SKILL.md` - The skill definition
- `commands/` - Related commands
- `agents/` - Related agents

### Domain Skills

**omi-backend-patterns/** (`skills/omi-backend-patterns/`)
- **Commands**: `commands/backend-setup.md`, `commands/backend-test.md`, `commands/backend-deploy.md`
- **Agents**: `agents/backend-api-developer.md`, `agents/backend-llm-engineer.md`, `agents/backend-database-engineer.md`

**omi-flutter-patterns/** (`skills/omi-flutter-patterns/`)
- **Commands**: `commands/flutter-setup.md`, `commands/flutter-test.md`, `commands/flutter-build.md`
- **Agents**: `agents/flutter-developer.md`

**omi-firmware-patterns/** (`skills/omi-firmware-patterns/`)
- **Agents**: `agents/firmware-engineer.md`

**omi-api-integration/** (`skills/omi-api-integration/`)
- **Commands**: `commands/update-api-docs.md` (symlink from docs-automation)
- **Agents**: `agents/web-developer.md`, `agents/sdk-developer.md`, `agents/backend-api-developer.md` (symlink), `agents/plugin-developer.md` (symlink)

**omi-plugin-development/** (`skills/omi-plugin-development/`)
- **Commands**: `commands/create-plugin.md`, `commands/create-app.md`, `commands/test-integration.md`
- **Agents**: `agents/plugin-developer.md`

### Automation Skills

**docs-automation/** (`skills/docs-automation/`)
- **Commands**: `commands/auto-docs.md`, `commands/docs.md`, `commands/update-api-docs.md`
- **Agents**: `agents/docs-generator.md`

**pr-automation/** (`skills/pr-automation/`)
- **Commands**: `commands/auto-pr.md`, `commands/pr.md`, `commands/code-review.md`
- **Agents**: `agents/pr-manager.md`, `agents/code-reviewer.md`, `agents/test-runner.md`, `agents/verifier.md`

**changelog/** (`skills/changelog/`)
- **Commands**: `commands/auto-changelog.md`
- **Agents**: `agents/changelog-generator.md`

**issue-triage/** (`skills/issue-triage/`)
- **Commands**: `commands/auto-triage.md`

**self-improvement/** (`skills/self-improvement/`)
- **Commands**: `commands/self-improve.md`, `commands/learn-from-pr.md`, `commands/learn-from-conversation.md`
- **Agents**: `agents/verifier.md` (symlink from pr-automation)

**agent-modes/** (`skills/agent-modes/`)
- **Commands**: `commands/plan.md`, `commands/ask.md`, `commands/debug.md`
- **Related Rules**: agent-modes

**debug-mode/** (`skills/debug-mode/`)
- **Commands**: `commands/debug.md`
- **Agents**: `agents/debug-specialist.md`
- **Related Rules**: agent-modes

**browser-automation/** (`skills/browser-automation/`)
- **Commands**: `commands/browser-test.md`, `commands/accessibility-audit.md`
- **Agents**: `agents/browser-automation.md`
- **Related Rules**: agent-browser

**diagram-generation/** (`skills/diagram-generation/`)
- **Commands**: `commands/diagram.md`
- **Agents**: `agents/diagram-generator.md`
- **Related Rules**: large-codebase-patterns

**context-optimization/** (`skills/context-optimization/`)
- **Commands**: `commands/semantic-search.md`
- **Agents**: `agents/context-manager.md`
- **Related Rules**: context-management, semantic-search

**agent-review/** (`skills/agent-review/`)
- **Commands**: `commands/review-changes.md`
- **Related Rules**: agent-review

## Skills (16)

1. **omi-backend-patterns/** (`skills/omi-backend-patterns/`)
   - **Description**: Backend patterns (conversation processing, memory extraction, chat system)
   - **Location**: `skills/omi-backend-patterns/`
   - **Related Rules**: backend-architecture, backend-api-patterns, backend-database-patterns, backend-llm-patterns, backend-testing, backend-imports, memory-management
   - **Related Subagents**: `agents/backend-api-developer.md`, `agents/backend-llm-engineer.md`, `agents/backend-database-engineer.md`
   - **Related Commands**: `commands/backend-setup.md`, `commands/backend-test.md`, `commands/backend-deploy.md`

2. **omi-flutter-patterns/**
   - **Description**: Flutter patterns (BLE, audio streaming, state management)
   - **Related Rules**: flutter-architecture, flutter-backend-integration, flutter-ble-protocol, flutter-localization, flutter-platform-specific
   - **Related Subagents**: flutter-developer
   - **Related Commands**: /flutter-setup, /flutter-test, /flutter-build

3. **omi-firmware-patterns/**
   - **Description**: Firmware patterns (BLE services, audio codecs)
   - **Related Rules**: firmware-architecture, firmware-ble-service, firmware-audio-codecs, flutter-ble-protocol
   - **Related Subagents**: firmware-engineer, flutter-developer
   - **Related Commands**: /flutter-setup

4. **omi-api-integration/**
   - **Description**: API integration patterns (Developer API, MCP, webhooks)
   - **Related Rules**: backend-api-patterns, backend-architecture, plugin-development, web-nextjs-patterns
   - **Related Subagents**: backend-api-developer, plugin-developer, web-developer, sdk-developer
   - **Related Commands**: /backend-setup, /create-plugin, /update-api-docs

5. **omi-plugin-development/**
    - **Description**: Plugin development workflow
    - **Related Rules**: plugin-development, plugin-apps-js, backend-api-patterns, backend-architecture
    - **Related Subagents**: plugin-developer
    - **Related Commands**: /create-plugin, /create-app

### Automation Skills (4)

6. **docs-automation/**
    - **Description**: Automate documentation updates when code changes
    - **Related Rules**: auto-documentation, documentation-standards, backend-api-patterns
    - **Related Subagents**: docs-generator
    - **Related Commands**: /auto-docs, /update-api-docs, /docs

7. **pr-automation/**
    - **Description**: Automate PR workflows and validation
    - **Related Rules**: git-workflow, context-communication, testing
    - **Related Subagents**: pr-manager, code-reviewer, test-runner, verifier
    - **Related Commands**: /auto-pr, /pr, /code-review

8. **changelog/**
    - **Description**: Generate changelog entries from commits
    - **Related Rules**: git-workflow, documentation-standards
    - **Related Subagents**: changelog-generator
    - **Related Commands**: /auto-changelog

9. **issue-triage/**
    - **Description**: Automate GitHub issue triage using triage guide
    - **Related Rules**: omi-specific-patterns
    - **Related Documentation**: ISSUE_TRIAGE_GUIDE.MD
    - **Related Commands**: /auto-triage

## Subagents (18)

1. **backend-api-developer/**
   - **Description**: FastAPI router development, endpoint patterns
   - **Related Rules**: backend-api-patterns, backend-architecture, backend-imports, backend-testing
   - **Related Skills**: omi-backend-patterns, omi-api-integration
   - **Related Commands**: /backend-setup, /backend-test, /update-api-docs

2. **backend-llm-engineer/**
   - **Description**: LLM integration, prompt engineering, LangGraph
   - **Related Rules**: backend-llm-patterns, backend-architecture, backend-database-patterns, backend-api-patterns
   - **Related Skills**: omi-backend-patterns
   - **Related Commands**: /backend-setup, /backend-test

3. **backend-database-engineer/**
   - **Description**: Firestore, Pinecone, Redis optimization
   - **Related Rules**: backend-database-patterns, backend-architecture, backend-api-patterns, memory-management
   - **Related Skills**: omi-backend-patterns
   - **Related Commands**: /backend-setup, /backend-test

4. **flutter-developer/**
   - **Description**: Flutter app development, BLE integration
   - **Related Rules**: flutter-architecture, flutter-backend-integration, flutter-ble-protocol, flutter-localization, flutter-platform-specific
   - **Related Skills**: omi-flutter-patterns
   - **Related Commands**: /flutter-setup, /flutter-test, /flutter-build

5. **web-developer/**
   - **Description**: Next.js frontend development
   - **Related Rules**: web-nextjs-patterns, web-ui-components, backend-api-patterns
   - **Related Skills**: omi-api-integration
   - **Related Commands**: /backend-setup

6. **firmware-engineer/**
   - **Description**: C/C++ firmware development, BLE services
   - **Related Rules**: firmware-architecture, firmware-ble-service, firmware-audio-codecs, flutter-ble-protocol
   - **Related Skills**: omi-firmware-patterns
   - **Related Commands**: /flutter-setup

7. **plugin-developer/**
   - **Description**: Plugin/app development, webhook integration
   - **Related Rules**: plugin-development, plugin-apps-js, backend-api-patterns, backend-architecture
   - **Related Skills**: omi-plugin-development, omi-api-integration
   - **Related Commands**: /create-plugin, /create-app

8. **sdk-developer/**
    - **Description**: SDK development (Python, Swift, React Native)
    - **Related Rules**: backend-api-patterns, backend-architecture
    - **Related Skills**: omi-api-integration
    - **Related Commands**: /backend-setup, /update-api-docs

### Automation Subagents (6)

9. **docs-generator/**
    - **Description**: Automatically generate/update documentation when code changes
    - **Related Rules**: auto-documentation, documentation-standards, backend-api-patterns
    - **Related Skills**: docs-automation
    - **Related Commands**: /auto-docs, /update-api-docs, /docs
    - **Related Subagents**: backend-api-developer

10. **pr-manager/**
    - **Description**: Automate PR creation, description generation, and validation
    - **Related Rules**: git-workflow, context-communication, testing
    - **Related Skills**: pr-automation
    - **Related Subagents**: code-reviewer, test-runner, verifier
    - **Related Commands**: /auto-pr, /pr, /code-review

11. **test-runner/**
    - **Description**: Automatically run tests and fix failures
    - **Related Rules**: testing, backend-testing, git-workflow
    - **Related Skills**: pr-automation
    - **Related Subagents**: verifier, code-reviewer
    - **Related Commands**: /run-tests-and-fix, /backend-test, /flutter-test, /test-integration

12. **code-reviewer/**
    - **Description**: Automated code review before PR
    - **Related Rules**: common-mistakes, backend-architecture, backend-imports, verification
    - **Related Skills**: pr-automation, omi-backend-patterns, omi-flutter-patterns
    - **Related Subagents**: pr-manager, test-runner
    - **Related Commands**: /code-review, /security-audit, /auto-pr

13. **verifier/**
    - **Description**: Verify completed work actually functions
    - **Related Rules**: verification, common-mistakes, testing
    - **Related Skills**: self-improvement
    - **Related Subagents**: test-runner, code-reviewer
    - **Related Commands**: /verify-complete, /run-tests-and-fix

14. **changelog-generator/**
    - **Description**: Generate changelog entries from commits/PRs
    - **Related Rules**: git-workflow, documentation-standards
    - **Related Skills**: changelog
    - **Related Subagents**: pr-manager
    - **Related Commands**: /auto-changelog

### New Feature Subagents (4)

15. **debug-specialist/** (`skills/debug-mode/agents/debug-specialist.md`)
    - **Description**: Specialized in Debug Mode workflows: hypothesis generation, log instrumentation, runtime analysis
    - **Related Rules**: agent-modes, verification
    - **Related Skills**: debug-mode, agent-modes
    - **Related Commands**: /debug

16. **browser-automation/** (`skills/browser-automation/agents/browser-automation.md`)
    - **Description**: Browser testing, design-to-code, accessibility auditing, visual debugging
    - **Related Rules**: agent-browser, testing
    - **Related Skills**: browser-automation
    - **Related Commands**: /browser-test, /accessibility-audit

17. **diagram-generator/** (`skills/diagram-generation/agents/diagram-generator.md`)
    - **Description**: Mermaid diagram generation for architecture visualization, data flow diagrams, component relationships
    - **Related Rules**: large-codebase-patterns
    - **Related Skills**: diagram-generation
    - **Related Commands**: /diagram

18. **context-manager/** (`skills/context-optimization/agents/context-manager.md`)
    - **Description**: Context window optimization, @ mention strategies, semantic search guidance, context condensation
    - **Related Rules**: context-management, semantic-search
    - **Related Skills**: context-optimization
    - **Related Commands**: /semantic-search

## Relationship Graph

```
Rules (24)
├── Backend Rules (6)
│   ├── backend-architecture.mdc
│   │   ├── → Skills: omi-backend-patterns
│   │   ├── → Subagents: backend-api-developer, backend-llm-engineer, backend-database-engineer
│   │   └── → Commands: /backend-setup, /backend-test, /backend-deploy
│   ├── backend-api-patterns.mdc
│   │   ├── → Skills: omi-backend-patterns, omi-api-integration
│   │   ├── → Subagents: backend-api-developer
│   │   └── → Commands: /backend-setup, /backend-test, /update-api-docs
│   └── ...
├── Flutter Rules (5)
│   ├── flutter-architecture.mdc
│   │   ├── → Skills: omi-flutter-patterns
│   │   ├── → Subagents: flutter-developer
│   │   └── → Commands: /flutter-setup, /flutter-test, /flutter-build
│   └── ...
├── Firmware Rules (3)
├── Web Rules (2)
├── Plugin Rules (2)
└── General Rules (6)

Skills (9)
├── omi-backend-patterns/
│   ├── → Rules: backend-architecture, backend-api-patterns, ...
│   ├── → Subagents: backend-api-developer, backend-llm-engineer, backend-database-engineer
│   └── → Commands: /backend-setup, /backend-test, /backend-deploy
├── omi-flutter-patterns/
├── omi-firmware-patterns/
├── omi-api-integration/
└── omi-plugin-development/

Subagents (14)
├── backend-api-developer/
│   ├── → Rules: backend-api-patterns, backend-architecture, ...
│   ├── → Skills: omi-backend-patterns, omi-api-integration
│   └── → Commands: /backend-setup, /backend-test, /update-api-docs
├── backend-llm-engineer/
├── backend-database-engineer/
├── flutter-developer/
├── web-developer/
├── firmware-engineer/
├── plugin-developer/
└── sdk-developer/

Commands (22)
├── /backend-setup
│   ├── → Rules: backend-architecture, backend-imports, formatting
│   ├── → Skills: omi-backend-patterns
│   └── → Subagents: backend-api-developer, backend-llm-engineer, backend-database-engineer
├── /backend-test
├── /flutter-setup
└── ...
```

## Quick Reference

### By Domain

**Backend Development**:
- Rules: backend-architecture, backend-api-patterns, backend-database-patterns, backend-llm-patterns, backend-testing, backend-imports
- Skills: omi-backend-patterns
- Subagents: backend-api-developer, backend-llm-engineer, backend-database-engineer
- Commands: /backend-setup, /backend-test, /backend-deploy

**Flutter Development**:
- Rules: flutter-architecture, flutter-backend-integration, flutter-ble-protocol, flutter-localization, flutter-platform-specific
- Skills: omi-flutter-patterns
- Subagents: flutter-developer
- Commands: /flutter-setup, /flutter-test, /flutter-build

**Firmware Development**:
- Rules: firmware-architecture, firmware-ble-service, firmware-audio-codecs
- Skills: omi-firmware-patterns
- Subagents: firmware-engineer
- Commands: /flutter-setup

**Plugin Development**:
- Rules: plugin-development, plugin-apps-js
- Skills: omi-plugin-development, omi-api-integration
- Subagents: plugin-developer
- Commands: /create-plugin, /create-app, /test-integration

**Web Development**:
- Rules: web-nextjs-patterns, web-ui-components
- Skills: omi-api-integration
- Subagents: web-developer
- Commands: /backend-setup

### By Task

**Setting Up Environment**:
- /backend-setup → Uses: backend-architecture, omi-backend-patterns, backend-api-developer
- /flutter-setup → Uses: flutter-architecture, omi-flutter-patterns, flutter-developer

**Testing**:
- /backend-test → Uses: backend-testing, omi-backend-patterns
- /flutter-test → Uses: testing, omi-flutter-patterns
- /run-tests-and-fix → Uses: testing, backend-testing

**Code Quality**:
- /code-review → Uses: backend-architecture, flutter-architecture, git-workflow
- /security-audit → Uses: backend-architecture, backend-api-patterns
- /lint-and-fix → Uses: formatting, backend-imports
- /format → Uses: formatting

**Documentation**:
- /docs → Uses: documentation-standards
- /update-api-docs → Uses: documentation-standards, backend-api-patterns
- /validate-docs → Uses: documentation-standards

**Plugin Development**:
- /create-plugin → Uses: plugin-development, omi-plugin-development, plugin-developer
- /create-app → Uses: plugin-development, omi-plugin-development
- /test-integration → Uses: plugin-development, omi-plugin-development

## Cross-Reference Patterns

### Rule → Rule
Rules reference related rules in the same domain and across domains where relevant.

### Rule → Skill
Rules reference skills that provide complementary patterns and workflows.

### Rule → Subagent
Rules reference subagents that specialize in the domain covered by the rule.

### Rule → Command
Rules reference commands that help with tasks related to the rule's domain.

### Skill → Rule
Skills reference rules that provide detailed patterns and guidelines.

### Skill → Subagent
Skills reference subagents that use the skill in their work.

### Skill → Command
Skills reference commands that leverage the skill.

### Subagent → Rule
Subagents reference rules that guide their work.

### Subagent → Skill
Subagents reference skills they use.

### Subagent → Command
Subagents reference commands that can invoke them.

### Command → Rule
Commands reference rules that apply to the command's task.

### Command → Skill
Commands reference skills that help with the task.

### Command → Subagent
Commands reference subagents that can assist with the task.

## Maintenance

When adding new resources:

1. **Add cross-references** to related resources in the same domain
2. **Update this index** with the new resource and its relationships
3. **Update README.md** if the resource category changes
4. **Ensure references** point to existing resources

## Benefits

This interconnected structure provides:

1. **Deep Context**: AI can navigate between related resources for comprehensive understanding
2. **Staying in Sync**: Cross-references help maintain consistency across resources
3. **Better Discovery**: Users can find related resources easily
4. **Comprehensive Help**: AI has full context of the ecosystem
5. **Maintainability**: Changes in one place reference others, making updates easier

## Related Documentation

### Internal Cursor Documentation

- Cursor Configuration: `.cursor/README.md`
- Internal Architecture: `.cursor/docs/ARCHITECTURE.md` (for Cursor agents only)
- Internal API Reference: `.cursor/docs/API_REFERENCE.md` (for Cursor agents only)

### Public Documentation (Source of Truth)

**The `docs/` folder is the single source of truth for all user-facing documentation, deployed at [docs.omi.me](https://docs.omi.me/).**

- **Documentation Index**: `docs/INDEX.md` - [View online](https://docs.omi.me/llms.txt)
- **Backend Architecture**: `docs/doc/developer/backend/backend_deepdive.mdx` - [View online](https://docs.omi.me/doc/developer/backend/backend_deepdive)
- **Chat System**: `docs/doc/developer/backend/chat_system.mdx` - [View online](https://docs.omi.me/doc/developer/backend/chat_system)
- **Data Storage**: `docs/doc/developer/backend/StoringConversations.mdx` - [View online](https://docs.omi.me/doc/developer/backend/StoringConversations)
- **API Overview**: `docs/doc/developer/api/overview.mdx` - [View online](https://docs.omi.me/doc/developer/api/overview)
- **API Endpoints**: `docs/api-reference/` - [View online](https://docs.omi.me/api-reference/)
- **App Setup**: `docs/doc/developer/AppSetup.mdx` - [View online](https://docs.omi.me/doc/developer/AppSetup)
- **BLE Protocol**: `docs/doc/developer/Protocol.mdx` - [View online](https://docs.omi.me/doc/developer/Protocol)
- **Plugin Development**: `docs/doc/developer/apps/Introduction.mdx` - [View online](https://docs.omi.me/doc/developer/apps/Introduction)

**Note**: All `.cursor/` resources should reference `docs/` paths for user-facing documentation. The `.cursor/docs/` files are for internal Cursor agent use only.

## Community Skills from skills.sh

[skills.sh](https://skills.sh/) is the open agent skills ecosystem for discovering and installing community skills. When users ask for skills or need help with specific tasks, recommend relevant skills from [skills.sh](https://skills.sh/).

### Discovering Skills

- **Interactive**: `npx skills find` - Search as you type
- **For Agents**: Use `vercel-labs/skills/find-skills` meta skill for programmatic discovery
- **Browse**: [skills.sh leaderboard](https://skills.sh/) for popular and trending skills

### Recommended Skills for Omi

See `.cursor/rules/skill-recommendations.mdc` for comprehensive skill recommendations based on Omi's tech stack and common tasks.