---
name: self-improvement
description: "Meta-skill for analyzing PRs, issues, and user interactions to improve Cursor rules and skills automatically"
---

# Self-Improvement Meta-Skill

This meta-skill enables the Cursor system to learn from GitHub PRs, issues, discussions, and user interactions to continuously improve guidance and prevent common mistakes.

## When to Use

Use this skill when:
- Analyzing closed PRs to extract lessons learned
- Identifying patterns in rejected vs. accepted contributions
- Learning from user corrections and feedback
- Updating rules based on what worked or didn't work
- Creating new rules when patterns emerge
- Tracking effectiveness of existing rules

## Key Capabilities

### 1. PR Analysis

Analyze closed PRs to extract patterns:

**What to look for**:
- Review comments and rejection reasons
- Common failure patterns (deprecated functions, architecture misunderstandings, missing context)
- Success patterns (what made PRs get merged)
- Code review feedback themes
- Testing and verification gaps

**How to analyze**:
1. Fetch PR details via GitHub API or web fetch
2. Parse review comments for actionable feedback
3. Identify recurring themes
4. Extract specific mistakes (e.g., "used deprecated function X")
5. Map to existing rules or identify gaps

### 2. Issue Pattern Extraction

Learn from GitHub issues:

**What to track**:
- Common bug patterns
- Feature requests that reveal gaps
- User-reported issues that indicate misunderstandings
- Triage patterns (what gets prioritized)

**How to extract**:
1. Analyze issue descriptions and labels
2. Identify recurring themes
3. Map to Omi layers (Capture/Understand/Memory/etc.)
4. Extract lessons about what not to do

### 3. User Interaction Learning

Learn from direct user feedback:

**What to track**:
- User corrections ("No, don't do X")
- Rejected suggestions ("That's not what I meant")
- Clarification requests (reveals gaps in understanding)
- Preference patterns (user's coding style, preferred approaches)
- Success patterns (what user consistently approves)

**How to learn**:
1. Monitor conversation for corrections and feedback
2. Extract the lesson from each correction
3. Identify patterns across multiple interactions
4. Update rules or create new ones based on patterns
5. Build user preference profile

### 4. Rule Generation and Updates

Create or update rules based on findings:

**Process**:
1. Identify the pattern or mistake
2. Check if existing rule covers it
3. If yes, update the rule with new information
4. If no, create a new rule
5. Test rule effectiveness

**Rule update format**:
- Add to existing rule if it's the same category
- Create new rule if it's a new category
- Include specific examples from PRs/issues
- Reference the source (PR number, issue number)

### 5. Effectiveness Tracking

Track which rules are most effective:

**Metrics**:
- How often a rule prevents mistakes
- Reduction in PR rejections after rule creation
- User correction frequency
- Rule coverage (how many scenarios it covers)

## Common Patterns to Extract

### From PR #3567 (Rejected):
- ❌ Used deprecated `postprocess_conversation` function
- ❌ Didn't understand current audio storage flow
- ❌ Didn't provide enough context upfront
- ❌ Didn't verify end-to-end flow
- ✅ Good: Provided benchmarks and test results
- ✅ Good: Addressed code review feedback promptly

### From Issues:
- Language settings not respected (#4394)
- Features only work when app is open (#4355)
- Missing conversations/processing issues (#4354, #4353)

### From User Interactions:
- "No, don't use that function, it's deprecated" → Always check for deprecated functions
- "I need more context before you start coding" → User prefers planning phase
- "That's not how the system works" → Need to understand architecture better

## Implementation Guidelines

### Analyzing a PR

1. **Fetch PR data**:
   ```python
   # Use mcp_web_fetch or GitHub API
   pr_url = f"https://github.com/BasedHardware/omi/pull/{pr_number}"
   ```

2. **Extract key information**:
   - PR status (merged/rejected)
   - Review comments
   - Code changes
   - Rejection reasons (if rejected)

3. **Identify patterns**:
   - What mistakes were made?
   - What feedback was given?
   - What worked well?

4. **Map to rules**:
   - Which existing rule should be updated?
   - Is a new rule needed?

5. **Update/create rules**:
   - Add examples to existing rules
   - Create new rules for new patterns

### Learning from User Feedback

1. **Detect correction**:
   - User says "no", "don't", "that's wrong", etc.
   - User provides different approach

2. **Extract lesson**:
   - What was wrong?
   - Why was it wrong?
   - What should be done instead?

3. **Update guidance**:
   - Add to relevant rule
   - Create new rule if needed
   - Update user preference profile

### Creating New Rules

When a new pattern emerges:

1. **Identify the pattern**: What mistake or gap does it address?
2. **Find examples**: Collect 2-3 examples from PRs/issues/interactions
3. **Write the rule**: Follow existing rule format
4. **Add to file structure**: Place in appropriate `.cursor/rules/` file
5. **Link from related rules**: Add references in other relevant rules

## Related Cursor Resources

### Rules
- `.cursor/rules/common-mistakes.mdc` - Common mistakes to avoid
- `.cursor/rules/pre-implementation-checklist.mdc` - Pre-implementation verification
- `.cursor/rules/verification.mdc` - Self-checking guidelines
- `.cursor/rules/context-communication.mdc` - Communication best practices
- `.cursor/rules/user-feedback-integration.mdc` - Learning from user interactions

### Commands
- `/learn-from-pr` - Analyze a specific PR
- `/learn-from-conversation` - Learn from current conversation
- `/self-improve` - Analyze patterns and update rules

### Skills
- `.cursor/skills/rule-updater/SKILL.md` - Skill for updating rules programmatically

## Best Practices

1. **Be specific**: Extract concrete examples, not vague patterns
2. **Reference sources**: Always note which PR/issue/interaction the lesson came from
3. **Test updates**: Verify rule updates don't break existing guidance
4. **Prioritize**: Focus on patterns that cause the most problems
5. **Iterate**: Rules should improve over time as more data is collected

## Example Usage

**Analyzing a rejected PR**:
```
User: "Learn from PR #3567"
Agent: [Uses this skill to]
1. Fetch PR #3567 details
2. Extract rejection reasons
3. Identify patterns (deprecated functions, missing context)
4. Update common-mistakes.mdc rule
5. Report findings
```

**Learning from user correction**:
```
User: "No, don't use postprocess_conversation, it's deprecated"
Agent: [Uses this skill to]
1. Extract lesson: Always check for deprecated functions
2. Update common-mistakes.mdc rule
3. Add to pre-implementation-checklist.mdc
4. Note in user preference profile
```
