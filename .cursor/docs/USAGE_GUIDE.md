# Cursor Configuration Usage Guide

Comprehensive guide to using the `.cursor` folder for AI-assisted development in the Omi codebase.

## Table of Contents

1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Skills System](#skills-system)
4. [Commands System](#commands-system)
5. [Agents System](#agents-system)
6. [Rules System](#rules-system)
7. [Common Workflows](#common-workflows)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)
10. [Adding New Resources](#adding-new-resources)

## Introduction

The `.cursor` folder contains Cursor-specific configuration that makes the Omi codebase "AI-aware." It provides structured guidance, automation, and domain expertise to help AI agents understand the entire Omi ecosystem and generate consistent, high-quality code.

### What is the .cursor Folder?

The `.cursor` folder is a configuration directory that:

- **Makes the codebase AI-aware**: Helps AI agents understand Omi's architecture, patterns, and conventions
- **Provides structured guidance**: Rules, commands, skills, and agents guide AI behavior
- **Enables automation**: Automates repetitive tasks like documentation, PR creation, and testing
- **Ensures consistency**: Enforces coding standards and best practices across the codebase

### Folder Structure

```
.cursor/
├── skills/              # Skills organized by domain/automation
│   ├── {skill-name}/
│   │   ├── SKILL.md     # Skill definition
│   │   ├── commands/    # Related commands
│   │   └── agents/      # Related agents
├── rules/               # Context-aware coding guidelines
├── commands/            # Legacy symlinks (backward compatibility)
├── agents/              # Legacy symlinks (backward compatibility)
├── docs/                # Internal architecture documentation
├── hooks/               # Hook scripts
├── plans/               # Saved Plan Mode plans
├── hooks.json           # Hook configuration
├── worktrees.json       # Worktree configuration
├── mcp.json             # MCP server configuration
├── BUGBOT.md            # Bugbot review rules
└── README.md            # Overview and reference
```

## Getting Started

### For New Developers

1. **Understand the structure**: Read this guide and `.cursor/README.md`
2. **Trust the rules**: Let rules guide AI code generation automatically
3. **Use commands**: Start with `/code-review` and `/run-tests-and-fix`
4. **Explore skills**: Skills provide domain expertise automatically
5. **Review AI suggestions**: Always review but leverage AI assistance

### Quick Start Checklist

- [ ] Read this usage guide
- [ ] Try `/backend-setup` or `/flutter-setup` for your environment
- [ ] Make a small change and see rules activate
- [ ] Use `/code-review` on your first PR
- [ ] Explore commands with `/` in Cursor chat

## Skills System

### What are Skills?

Skills are reusable domain expertise packages that:

- **Provide deep knowledge** of Omi-specific patterns
- **Activate automatically** when working in relevant code
- **Encode best practices** for specific domains
- **Group related resources** (commands and agents) together

### How Skills Work

Skills are organized in `skills/{skill-name}/` folders, each containing:

- `SKILL.md` - The skill definition and capabilities
- `commands/` - Related slash commands
- `agents/` - Related specialized agents

### Available Skills

#### Domain Skills

**omi-backend-patterns** (`skills/omi-backend-patterns/`)
- Backend-specific patterns (conversation processing, memory extraction, chat system)
- Commands: `/backend-setup`, `/backend-test`, `/backend-deploy`
- Agents: `backend-api-developer`, `backend-llm-engineer`, `backend-database-engineer`

**omi-flutter-patterns** (`skills/omi-flutter-patterns/`)
- Flutter-specific patterns (BLE, audio streaming, state management)
- Commands: `/flutter-setup`, `/flutter-test`, `/flutter-build`
- Agents: `flutter-developer`

**omi-firmware-patterns** (`skills/omi-firmware-patterns/`)
- Firmware patterns (BLE services, audio codecs)
- Agents: `firmware-engineer`

**omi-api-integration** (`skills/omi-api-integration/`)
- API integration patterns (Developer API, MCP, webhooks)
- Commands: `/update-api-docs`
- Agents: `web-developer`, `sdk-developer`

**omi-plugin-development** (`skills/omi-plugin-development/`)
- Plugin development workflow
- Commands: `/create-plugin`, `/create-app`, `/test-integration`
- Agents: `plugin-developer`

#### Automation Skills

**docs-automation** (`skills/docs-automation/`)
- Automate documentation updates when code changes
- Commands: `/auto-docs`, `/docs`, `/update-api-docs`
- Agents: `docs-generator`

**pr-automation** (`skills/pr-automation/`)
- Automate PR workflows and validation
- Commands: `/auto-pr`, `/pr`, `/code-review`
- Agents: `pr-manager`, `code-reviewer`, `test-runner`, `verifier`

**changelog** (`skills/changelog/`)
- Generate changelog entries from commits
- Commands: `/auto-changelog`
- Agents: `changelog-generator`

**issue-triage** (`skills/issue-triage/`)
- Automate GitHub issue triage
- Commands: `/auto-triage`

**self-improvement** (`skills/self-improvement/`)
- Learn from PRs, issues, and user interactions
- Commands: `/self-improve`, `/learn-from-pr`, `/learn-from-conversation`

**agent-modes** (`skills/agent-modes/`)
- Guidance on choosing and using agent modes (Agent, Ask, Plan, Debug)
- Commands: `/plan`, `/ask`, `/debug`

**debug-mode** (`skills/debug-mode/`)
- Debug Mode workflows for tricky bugs and regressions
- Commands: `/debug`
- Agents: `debug-specialist`

**browser-automation** (`skills/browser-automation/`)
- Browser testing, design-to-code, accessibility auditing
- Commands: `/browser-test`, `/accessibility-audit`
- Agents: `browser-automation`

**diagram-generation** (`skills/diagram-generation/`)
- Mermaid diagram generation for architecture visualization
- Commands: `/diagram`
- Agents: `diagram-generator`

**context-optimization** (`skills/context-optimization/`)
- Context window optimization and @ mention strategies
- Commands: `/semantic-search`
- Agents: `context-manager`

**agent-review** (`skills/agent-review/`)
- Agent Review workflows for catching bugs before merging
- Commands: `/review-changes`

### Using Skills

Skills activate automatically when you work in relevant parts of the codebase. For example:

- Working on `backend/routers/` → `omi-backend-patterns` skill activates
- Working on `app/lib/` → `omi-flutter-patterns` skill activates
- Creating a PR → `pr-automation` skill activates

You don't need to manually activate skills - they work automatically based on context.

## Commands System

### What are Commands?

Commands are slash commands (`/command`) available in Cursor chat that provide:

- **Step-by-step guidance** for common tasks
- **Automation** for repetitive workflows
- **Domain-specific help** for different parts of the codebase

### How to Use Commands

1. Type `/` in Cursor chat to see all available commands
2. Select a command or type the command name
3. Follow the step-by-step guidance provided
4. Commands may invoke related agents or skills automatically

### Command Categories

#### General Commands

- `/code-review` - Review code for correctness, security, quality, tests
- `/pr` - Summarize changes and propose PR title/description
- `/run-tests-and-fix` - Run tests, fix failures, re-run until green
- `/security-audit` - Security-focused code review
- `/lint-and-fix` - Run linter, auto-fix issues
- `/format` - Format code according to project standards
- `/fix-issue` - Fix bug or implement feature from issue
- `/docs` - Generate or update documentation
- `/validate-docs` - Check documentation links and formatting
- `/verify-complete` - Verify that completed work actually functions

#### Automation Commands

- `/auto-docs` - Automatically detect code changes and update documentation
- `/auto-pr` - Automatically generate PR with description and validation
- `/auto-changelog` - Automatically generate changelog from commits
- `/auto-triage` - Automatically triage GitHub issues using triage guide

#### Domain-Specific Commands

**Backend:**
- `/backend-setup` - Guide for setting up backend environment
- `/backend-test` - Run backend tests with proper environment
- `/backend-deploy` - Deploy backend to production

**Flutter:**
- `/flutter-setup` - Flutter environment setup
- `/flutter-test` - Run Flutter tests
- `/flutter-build` - Build Flutter app

**Plugin Development:**
- `/create-plugin` - Scaffold new plugin structure
- `/create-app` - Scaffold new Omi app
- `/test-integration` - Run integration tests

**API Documentation:**
- `/update-api-docs` - Update API reference documentation

**Agent Modes:**
- `/plan` - Plan Mode workflow guidance
- `/ask` - Ask Mode usage
- `/debug` - Debug Mode workflow

**Browser & Testing:**
- `/browser-test` - Browser testing workflow
- `/accessibility-audit` - Accessibility auditing

**Context & Search:**
- `/semantic-search` - Semantic search guidance
- `/diagram` - Generate Mermaid diagrams

**Review:**
- `/review-changes` - Use Agent Review to find issues

### Command Examples

**Example 1: Creating a PR**
```
Developer: /pr

AI Response:
- Analyzes git diff
- Generates PR title: "feat(backend): add goals API endpoints"
- Creates PR description with:
  - What changed and why
  - Testing performed
  - Breaking changes (if any)
  - Related issues
- Suggests reviewers based on changed files
```

**Example 2: Running Tests**
```
Developer: /run-tests-and-fix

AI Response:
- Runs backend tests (detects backend/ changes)
- Identifies failures
- Fixes issues automatically
- Re-runs tests until green
- Reports final status
```

**Example 3: Code Review**
```
Developer: /code-review

AI Response:
- Reviews code for correctness
- Checks security issues
- Verifies architecture compliance
- Checks test coverage
- Provides categorized feedback:
  - Critical: Must fix
  - Suggestion: Should fix
  - Nice to have: Optional improvements
```

## Agents System

### What are Agents?

Agents are specialized AI subagents that:

- **Have deep expertise** in specific domains
- **Can be invoked automatically** or manually
- **Provide specialized guidance** for complex tasks
- **Work together** with skills and commands

### How Agents Work

Agents are organized within skill folders at `skills/{skill}/agents/{agent}.md`. Each agent:

- Has YAML frontmatter (name, description, model, is_background)
- Contains specialized prompts and instructions
- Automatically activates when relevant tasks are detected
- Can be manually invoked for specific tasks

### Available Agents

#### Domain Agents

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

#### Automation Agents

**Documentation** (`skills/docs-automation/agents/`):
- `docs-generator.md` - Automatically generate/update documentation when code changes

**PR Management** (`skills/pr-automation/agents/`):
- `pr-manager.md` - Automate PR creation, description generation, and validation
- `code-reviewer.md` - Automated code review before PR
- `test-runner.md` - Automatically run tests and fix failures
- `verifier.md` - Verify completed work actually functions

**Other Automation**:
- `changelog-generator.md` (`skills/changelog/agents/`) - Generate changelog entries from commits/PRs

### Using Agents

Agents activate automatically when:
- Working in relevant code (domain agents)
- Performing relevant tasks (automation agents)
- Invoked by commands

You can also manually invoke agents through Cursor settings or by using related commands.

## Rules System

### What are Rules?

Rules are context-aware coding guidelines that apply automatically based on:

- **File globs**: Rules activate when editing matching files (e.g., `backend/**/*.py`)
- **Always-applied flag**: Critical rules apply to all files (e.g., `codebase-overview.mdc`)

### How Rules Work

When you edit a file, relevant rules automatically activate:

**Example: Editing `backend/routers/conversations.py`**

The AI automatically applies:
- `backend-api-patterns.mdc` - FastAPI router patterns
- `backend-imports.mdc` - Import hierarchy rules
- `backend-architecture.mdc` - Architecture patterns
- `codebase-overview.mdc` - System overview (always applied)

### Rule Categories

**Backend Rules** (`rules/backend-*.mdc`):
- Import hierarchy, architecture, API patterns, database patterns, LLM patterns, testing

**Flutter Rules** (`rules/flutter-*.mdc`):
- Architecture, localization, BLE protocol, backend integration, platform-specific

**Firmware Rules** (`rules/firmware-*.mdc`):
- Architecture, BLE service, audio codecs

**Web Rules** (`rules/web-*.mdc`):
- Next.js patterns, UI components

**Plugin Rules** (`rules/plugin-*.mdc`):
- Plugin development, JavaScript plugins

**General Rules** (`rules/*.mdc`):
- Codebase overview, documentation standards, formatting, git workflow, testing, memory management

## Common Workflows

### Workflow 1: Adding a New API Endpoint

1. **Rules activate automatically** when editing `backend/routers/`
2. **Skill activates**: `omi-backend-patterns` provides patterns
3. **Agent activates**: `backend-api-developer` provides guidance
4. **AI generates code** following all patterns
5. **Use commands**:
   - `/code-review` - Review generated code
   - `/update-api-docs` - Update API documentation
   - `/run-tests-and-fix` - Run and fix tests

### Workflow 2: Creating a Flutter Feature

1. **Rules activate**: Flutter architecture, localization, BLE protocol
2. **Skill activates**: `omi-flutter-patterns` provides patterns
3. **Agent activates**: `flutter-developer` provides guidance
4. **AI generates code** following Flutter patterns
5. **Use commands**:
   - `/flutter-test` - Run Flutter tests
   - `/code-review` - Review code

### Workflow 3: Creating a PR

1. **Complete your changes**
2. **Use `/auto-pr`** to:
   - Generate PR description
   - Validate requirements (tests, docs, conventions)
   - Link related issues
   - Suggest reviewers
3. **Review generated PR** and make adjustments
4. **Create PR** on GitHub

### Workflow 4: Setting Up Development Environment

**Backend:**
```
Developer: /backend-setup

AI Response:
- Guides through Python virtual environment setup
- Helps configure environment variables
- Sets up Google Cloud credentials
- Verifies all dependencies are installed
```

**Flutter:**
```
Developer: /flutter-setup

AI Response:
- Guides through Flutter SDK setup
- Helps configure platform-specific settings
- Sets up Firebase
- Verifies app can run
```

## Best Practices

### For Developers

**Trust the Rules**
- Rules encode best practices learned from the codebase
- Let rules guide AI code generation
- Review AI suggestions but leverage them

**Use Commands**
- Use commands for common tasks instead of asking manually
- Commands provide structured, repeatable workflows
- Commands ensure consistency across the team

**Let Automation Handle Repetitive Work**
- Use `/auto-docs` for documentation updates
- Use `/auto-pr` for PR creation
- Use `/run-tests-and-fix` for test automation

**Review AI Suggestions**
- AI suggestions are helpful but should be reviewed
- Verify that generated code follows your intent
- Test generated code before committing

### For Maintainers

**Keep Rules Up-to-Date**
- Update rules when codebase patterns change
- Add new rules when new patterns emerge
- Remove outdated rules

**Add New Rules When Patterns Emerge**
- If a pattern appears multiple times, encode it in a rule
- Rules help maintain consistency
- Rules reduce need for manual guidance

**Document New Commands and Skills**
- Document purpose and usage
- Add examples and use cases
- Update cross-references

**Update Cross-References**
- When adding resources, update related resources
- Cross-references help AI navigate the ecosystem
- Maintains consistency across resources

## Troubleshooting

### Rules Not Activating

**Problem**: Rules don't seem to be applying when editing files.

**Solutions:**
- Check file globs match your file path (e.g., `backend/**/*.py` matches `backend/routers/test.py`)
- Verify rule file exists in `.cursor/rules/`
- Check rule has correct YAML frontmatter
- Restart Cursor if rules were just added

### Commands Not Available

**Problem**: Slash commands don't appear in Cursor chat.

**Solutions:**
- Verify command file exists in `skills/{skill}/commands/` or `.cursor/commands/`
- Check command file has correct format
- Type `/` in Cursor chat to see all available commands
- Restart Cursor if commands were just added

### Skills Not Providing Context

**Problem**: Skills don't seem to be providing expected patterns.

**Solutions:**
- Verify skill file exists in `skills/{skill}/SKILL.md`
- Check skill has correct YAML frontmatter
- Ensure you're working in relevant code (skills activate based on context)
- Check `.cursor/docs/INDEX.md` for skill relationships

### Agents Not Activating

**Problem**: Expected agents don't activate automatically.

**Solutions:**
- Verify agent file exists in `skills/{skill}/agents/`
- Check agent has correct YAML frontmatter (name, description, model, is_background)
- Some agents only activate for specific tasks
- Check agent description matches your use case

## Adding New Resources

### Adding a New Skill

1. Create directory: `skills/{skill-name}/`
2. Create `SKILL.md` with YAML frontmatter (name, description)
3. Create `commands/` and `agents/` subdirectories
4. Add related commands and agents to subdirectories
5. Update `.cursor/docs/INDEX.md` with new skill
6. Update `.cursor/README.md` if needed

### Adding a New Command

1. Determine which skill it belongs to
2. Create file: `skills/{skill}/commands/{command-name}.md`
3. Add command description and usage
4. Add step-by-step guidance
5. Add cross-references to related rules, skills, agents
6. Update `.cursor/docs/INDEX.md` with new command

### Adding a New Agent

1. Determine which skill it belongs to
2. Create file: `skills/{skill}/agents/{agent-name}.md`
3. Add YAML frontmatter:
   - `name`: Agent name
   - `description`: What the agent does
   - `model`: Model to use (usually `inherit`)
   - `is_background`: Whether agent runs in background
4. Add agent prompt/instructions
5. Add cross-references to related rules and skills
6. Update `.cursor/docs/INDEX.md` with new agent

### Adding a New Rule

1. Create file in `.cursor/rules/` with `.mdc` extension
2. Add YAML frontmatter with `description` and `globs` (if file-specific)
3. Set `alwaysApply: true` if rule should always apply
4. Add content explaining the rule
5. Add cross-references to related rules, skills, agents, commands
6. Update `.cursor/docs/INDEX.md` with new rule

## Community Skills from skills.sh

[skills.sh](https://skills.sh/) is the open agent skills ecosystem that makes finding and installing skills easier for both developers and AI agents.

### Discovering Skills

**Interactive Discovery:**
```bash
# Search and discover skills interactively
npx skills find
```

**Install Skills:**
```bash
# Install a specific skill
npx skills add <owner/repo> <skill-name>

# Example: Install React best practices
npx skills add vercel-labs/agent-skills vercel-react-best-practices
```

**Update Skills:**
```bash
# Update all installed skills
npx skills update
```

### For AI Agents

When users ask for skills or need help with specific tasks:

1. **Recommend skills from skills.sh** based on their needs
2. **Use the find-skills meta skill** (`vercel-labs/skills/find-skills`) for programmatic discovery
3. **Browse the skills leaderboard** at [skills.sh](https://skills.sh/) to find popular skills
4. **Suggest relevant skills** based on:
   - Technology stack (React, Python, TypeScript, etc.)
   - Task type (testing, design, architecture, etc.)
   - Popularity and install count

**Example Recommendations:**
- Working with React/Next.js → `vercel-react-best-practices`
- FastAPI development → `fastapi-templates`
- Python testing → `python-testing-patterns`
- TypeScript → `typescript-advanced-types`
- Code review → `code-review-excellence`

### Popular Skills for Omi Stack

Based on Omi's tech stack (Python/FastAPI, Flutter, Next.js, TypeScript):

**Backend:**
- `wshobson/agents/fastapi-templates` - FastAPI patterns
- `wshobson/agents/python-testing-patterns` - Python testing
- `wshobson/agents/api-design-principles` - API design

**Frontend:**
- `vercel-labs/agent-skills/vercel-react-best-practices` - React/Next.js
- `vercel-labs/agent-skills/web-design-guidelines` - Web design
- `wshobson/agents/typescript-advanced-types` - TypeScript

**Mobile:**
- `callstackincubator/agent-skills/react-native-best-practices` - React Native
- `expo/skills/building-native-ui` - Expo/React Native UI

**General:**
- `wshobson/agents/code-review-excellence` - Code review
- `wshobson/agents/architecture-patterns` - Architecture
- `wshobson/agents/git-advanced-workflows` - Git workflows

## Reference

### Documentation Files

- **This Guide**: `.cursor/docs/USAGE_GUIDE.md` - Comprehensive usage guide
- **Index**: `.cursor/docs/INDEX.md` - Complete resource map and relationships
- **Overview**: `.cursor/README.md` - Quick reference and structure
- **Architecture**: `.cursor/docs/ARCHITECTURE.md` - Internal architecture (for agents)

### External Resources

- [Cursor Documentation](https://cursor.com/docs) - Official Cursor documentation
- [skills.sh](https://skills.sh/) - Open agent skills ecosystem for discovering and installing skills
- [Skills v1.1.1 Changelog](https://vercel.com/changelog/skills-v1-1-1-interactive-discovery-open-source-release-and-agent-support) - Interactive discovery and agent support
- [Cursor Hooks](https://cursor.com/docs/agent/hooks) - Hooks documentation
- [Cursor Worktrees](https://cursor.com/docs/configuration/worktrees) - Worktrees documentation
- [Cursor Bugbot](https://cursor.com/docs/cookbook/bugbot-rules) - Bugbot documentation

### Getting Help

- Check the relevant rule file for patterns
- Use commands for step-by-step guidance
- Reference architecture documentation in `docs/` folder (source of truth)
- See `.cursor/docs/INDEX.md` for complete Cursor resource map and relationships
- **Discover community skills**: Browse [skills.sh](https://skills.sh/) or use `npx skills find` for interactive discovery
