---
name: agent-modes
description: "Guidance on choosing and using Cursor agent modes: Agent, Ask, Plan, and Debug. Use when selecting the right mode for a task or when explaining mode capabilities."
---

# Agent Modes Skill

Guidance on choosing and using the right agent mode for your task.

## When to Use

Use this skill when:
- Selecting the right mode for a task
- Explaining mode capabilities
- Switching between modes
- Understanding mode-specific workflows

## Mode Selection

### Agent Mode (Default)

**Best for:** Complex features, refactoring, autonomous exploration

**Use when:**
- Implementing features requiring multiple file changes
- Refactoring across codebase
- Clear, well-defined tasks
- Need autonomous exploration and fixes

**Example:**
- "Add a new API endpoint for goals"
- "Refactor authentication system"
- "Update components to new design system"

### Ask Mode

**Best for:** Learning, planning, read-only exploration

**Use when:**
- Learning about unfamiliar code
- Understanding system architecture
- Planning before implementation
- Exploring codebase structure

**Example:**
- "How does authentication work?"
- "Explain memory extraction flow"
- "What happens when user submits form?"

### Plan Mode

**Best for:** Complex features requiring planning

**Use when:**
- Complex features with multiple approaches
- Tasks touching many files/systems
- Unclear requirements
- Architectural decisions need review

**Example:**
- "Add user preferences system"
- "Implement real-time notifications"
- "Refactor data layer"

**Workflow:**
1. Agent asks clarifying questions
2. Researches codebase
3. Creates implementation plan
4. You review and edit plan
5. Click to build when ready

### Debug Mode

**Best for:** Tricky bugs, regressions

**Use when:**
- Bugs you can reproduce but can't figure out
- Race conditions and timing issues
- Performance problems
- Regressions

**Example:**
- "Audio streaming stops after 30 seconds"
- "Memory extraction fails for some conversations"
- "BLE connection drops intermittently"

**Workflow:**
1. Explore and hypothesize
2. Add instrumentation
3. Reproduce bug
4. Analyze logs
5. Make targeted fix
6. Verify and clean up

## Mode Switching

- Use mode picker dropdown
- Press `Cmd+.` (Mac) or `Ctrl+.` (Windows/Linux)
- Set keyboard shortcuts in settings

## Related Resources

- Rule: `.cursor/rules/agent-modes.mdc`
- Commands: `/plan`, `/ask`, `/debug`
