# Plan Mode

Use Plan Mode to create detailed implementation plans before writing code.

## When to Use Plan Mode

Use Plan Mode for:
- Complex features with multiple valid approaches
- Tasks touching many files or systems
- Unclear requirements needing exploration
- Architectural decisions requiring review

## How to Use

1. Press `Shift+Tab` to switch to Plan Mode
2. Describe your task or feature
3. Answer clarifying questions from agent
4. Review the generated plan
5. Edit plan if needed
6. Click "Build" when ready

## Plan Mode Workflow

**Agent will:**
1. Ask clarifying questions (max 3)
2. Research codebase to gather context
3. Create comprehensive implementation plan
4. Present plan for your review

**You can:**
- Edit plan through chat
- Edit plan markdown file directly
- Save plan to `.cursor/plans/` for reference
- Build plan when satisfied

## Example

```
User: Add user preferences system

Agent asks:
- Should preferences be per-user or global?
- What types of preferences? (theme, notifications, etc.)
- Where should preferences be stored?

Agent creates plan:
- Backend: Create preferences API endpoints
- Flutter: Create preferences UI
- Database: Add preferences collection
- Tests: Add preference tests

User reviews and edits plan
User clicks "Build"
```

## Best Practices

1. **Answer questions thoroughly**: More context = better plan
2. **Review before building**: Ensure plan matches your vision
3. **Save good plans**: Click "Save to workspace" for reference
4. **Start over if needed**: Revert and refine plan if implementation doesn't match

## Related Resources

- Rule: `.cursor/rules/agent-modes.mdc`
- Skill: `.cursor/skills/agent-modes/SKILL.md`
