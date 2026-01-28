---
name: rule-updater
description: "Skill for programmatically reading, updating, and creating Cursor rules based on patterns and lessons learned"
---

# Rule Updater Skill

This skill enables programmatic reading, updating, and creation of Cursor rules based on patterns extracted from PRs, issues, and user interactions.

## When to Use

Use this skill when:
- Updating existing rules with new examples or patterns
- Creating new rules for emerging patterns
- Identifying when rules need updating
- Testing rule effectiveness
- Organizing and maintaining rules

## Key Capabilities

### 1. Read Existing Rules

**Read and parse rule files**:
- Read `.cursor/rules/*.mdc` files
- Parse frontmatter (description, alwaysApply, references)
- Extract content sections
- Understand rule structure

**Example**:
```python
# Read a rule file
rule_content = read_file(".cursor/rules/common-mistakes.mdc")
# Parse frontmatter
# Extract sections
# Understand structure
```

### 2. Identify When Rules Need Updating

**Detect update opportunities**:
- New patterns that fit existing rules
- Examples that should be added
- Clarifications needed
- Outdated information

**Signals**:
- Multiple PRs/issues showing same pattern
- User corrections revealing gaps
- Review feedback indicating missing guidance
- Emerging patterns not covered

### 3. Update Existing Rules

**Process for updating**:
1. Read the rule file
2. Identify where to add new content
3. Add examples or sections
4. Maintain organization
5. Update references if needed
6. Write updated rule

**Update types**:
- **Add examples**: Add new examples to existing sections
- **Enhance sections**: Expand existing sections with more detail
- **Add sections**: Add new sections for new patterns
- **Update references**: Add links to related rules/PRs/issues

**Example update**:
```markdown
### Using Deprecated Functions

**Problem**: Using functions that have been deprecated or removed.

**Examples from PR #3567**:
- ❌ Used `postprocess_conversation()` which was deprecated
- ❌ Assumed functions exist without checking current codebase state

**NEW EXAMPLE from PR #3621**:
- ❌ Used `old_function()` which was removed in PR #3400
```

### 4. Create New Rules

**Process for creating**:
1. Identify the pattern category
2. Collect 2-3 examples from PRs/issues/interactions
3. Determine rule file name and location
4. Write rule following format
5. Add frontmatter with appropriate metadata
6. Link from related rules

**Rule structure**:
```markdown
---
description: "Brief description"
alwaysApply: true/false
references:
  - related-file.md
---

# Rule Title

## Section 1
Content...

## Section 2
Content...

## Related Rules
- Link to related rules
```

**Example new rule**:
```markdown
---
description: "Guidelines for handling background operations"
alwaysApply: true
---

# Background Operations

Features should work when app is closed/backgrounded.

## Common Mistakes
- Features that only work when app is open (#4355)
- Features that require specific screen to be active

## How to Avoid
- Design features to work in background
- Test with app closed/backgrounded
- Use background services where appropriate
```

### 5. Test Rule Effectiveness

**Verify updates don't break guidance**:
- Check rule syntax is valid
- Verify frontmatter is correct
- Ensure links work
- Test rule readability

**Metrics to track**:
- How often rule prevents mistakes
- Reduction in related issues after rule creation
- Rule coverage (scenarios covered)
- User feedback on rule usefulness

## Rule File Format

### Frontmatter

```yaml
---
description: "Brief description of what the rule covers"
alwaysApply: true  # or false
references:
  - related-file.md
  - docs/doc/example.mdx
globs:
  - "backend/**/*.py"  # Optional: file patterns
---
```

### Content Structure

```markdown
# Rule Title

Brief introduction explaining the rule.

## Section 1
Content with examples, code snippets, etc.

## Section 2
More content...

## Related Rules
- `.cursor/rules/related-rule.mdc` - Description

## Related Cursor Resources
### Skills
- `.cursor/skills/related-skill/SKILL.md` - Description

### Commands
- `/related-command` - Description
```

## Update Patterns

### Adding Examples

**When**: New examples of existing patterns emerge

**How**:
1. Find relevant section
2. Add example with source (PR/issue number)
3. Maintain formatting consistency
4. Keep examples organized

**Example**:
```markdown
### Common Mistake

**Example from PR #3567**:
- ❌ Description of mistake

**Example from Issue #4394**:
- ❌ Description of mistake
```

### Enhancing Sections

**When**: Section needs more detail or clarification

**How**:
1. Expand existing content
2. Add more specific guidance
3. Include more examples
4. Add "How to avoid" subsections

### Adding Sections

**When**: New pattern category emerges

**How**:
1. Add new section with appropriate heading
2. Follow existing section format
3. Include examples
4. Add to table of contents if applicable

## Rule Organization

### Rule Categories

**Common categories**:
- Common mistakes
- Architecture patterns
- Implementation checklists
- Verification guidelines
- Communication best practices
- Domain-specific patterns (Omi, backend, Flutter, etc.)

### Naming Conventions

**Rule file names**:
- Use kebab-case: `common-mistakes.mdc`
- Be descriptive: `pre-implementation-checklist.mdc`
- Group related: `backend-architecture.mdc`, `backend-api-patterns.mdc`

### Linking Rules

**Cross-references**:
- Link related rules in "Related Rules" section
- Reference from other rules when relevant
- Keep links updated when rules are renamed

## Best Practices

1. **Be specific**: Include concrete examples, not vague patterns
2. **Reference sources**: Always note which PR/issue/interaction the lesson came from
3. **Maintain organization**: Keep rules well-organized and easy to navigate
4. **Test updates**: Verify rule updates don't break existing guidance
5. **Prioritize**: Focus on patterns that cause the most problems
6. **Iterate**: Rules should improve over time as more data is collected

## Example Workflow

**Updating a rule with new pattern**:

1. **Identify pattern**: "Multiple PRs show missing context issue"
2. **Read rule**: Read `.cursor/rules/context-communication.mdc`
3. **Find section**: Find "PR Description Requirements" section
4. **Add example**: Add example from recent PR
5. **Enhance guidance**: Expand "What to Include" subsection
6. **Update references**: Add link to new PR if relevant
7. **Write rule**: Save updated rule file
8. **Verify**: Check syntax and links

**Creating new rule**:

1. **Identify pattern**: "New pattern: Background operation issues"
2. **Collect examples**: Gather 2-3 examples from issues/PRs
3. **Determine name**: `background-operations.mdc`
4. **Write rule**: Create rule following format
5. **Add frontmatter**: Include description, alwaysApply, references
6. **Link from related**: Add link from `common-mistakes.mdc`
7. **Test**: Verify rule is valid and readable

## Related Cursor Resources

### Rules
- `.cursor/rules/common-mistakes.mdc` - Common mistakes rule
- `.cursor/rules/context-communication.mdc` - Communication rule
- `.cursor/rules/pre-implementation-checklist.mdc` - Checklist rule

### Skills
- `.cursor/skills/self-improvement/SKILL.md` - Self-improvement meta-skill

### Commands
- `/learn-from-pr` - Analyze PR for lessons
- `/self-improve` - Analyze patterns and update rules
