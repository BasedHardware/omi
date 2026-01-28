# Learn from PR

Analyze a specific pull request to extract lessons learned and update rules accordingly.

## Usage

```
/learn-from-pr <PR_NUMBER_OR_URL>
```

Examples:
- `/learn-from-pr 3567`
- `/learn-from-pr https://github.com/BasedHardware/omi/pull/3567`

## Process

1. **Fetch PR data**
   - Get PR details from GitHub (status, comments, changes)
   - Fetch review comments and feedback
   - Get rejection reasons (if rejected)

2. **Analyze PR**
   - Extract key information:
     - Was it merged or rejected?
     - What feedback was given?
     - What mistakes were made?
     - What worked well?
   - Identify patterns:
     - Common mistakes
     - Missing context
     - Architecture misunderstandings
     - Testing gaps

3. **Extract lessons**
   - What can we learn from this PR?
   - What mistakes should be avoided?
   - What patterns should be followed?
   - What rules need updating?

4. **Update rules**
   - Check if existing rules cover the lessons
   - Update existing rules with new examples
   - Create new rules if needed
   - Reference the PR as source

5. **Report findings**
   - Summarize lessons learned
   - List rules updated/created
   - Provide recommendations

## What to Extract

### From Rejected PRs

**Common patterns**:
- Used deprecated functions
- Didn't understand architecture
- Missing context in PR description
- Didn't test end-to-end
- Assumed system state incorrectly
- Violated import hierarchy
- Didn't respect Omi patterns

**Example from PR #3567**:
- ❌ Used deprecated `postprocess_conversation` function
- ❌ Didn't understand current audio storage flow
- ❌ Didn't provide enough context upfront
- ❌ Didn't verify end-to-end flow
- ✅ Good: Provided benchmarks and test results
- ✅ Good: Addressed code review feedback promptly

### From Merged PRs

**Success patterns**:
- Good PR descriptions with all context
- Proper testing and verification
- Followed architecture patterns
- Addressed review feedback quickly
- Clear explanation of changes

### From Review Comments

**Common feedback themes**:
- "Need more context"
- "This function is deprecated"
- "This doesn't match the architecture"
- "Need to test end-to-end"
- "Missing verification"

## Rule Updates

### Updating Existing Rules

If a lesson fits an existing rule:

1. Add example to the rule
2. Reference the PR number
3. Add to relevant sections
4. Keep rule organized

**Example**:
```markdown
### Using Deprecated Functions

**Example from PR #3567**:
- Used `postprocess_conversation()` which was deprecated
- Assumed function existed without checking
```

### Creating New Rules

If a new pattern emerges:

1. Identify the pattern category
2. Create new rule file
3. Include examples from PRs
4. Link from related rules

## Output Format

After analyzing a PR, provide:

1. **Summary**
   - PR number and status
   - Key findings

2. **Lessons Learned**
   - Mistakes to avoid
   - Patterns to follow
   - Gaps identified

3. **Rules Updated**
   - Which rules were updated
   - What was added
   - New rules created (if any)

4. **Recommendations**
   - How to avoid similar mistakes
   - What to do differently

## Example Output

```
Analyzed PR #3567 (Rejected)

## Lessons Learned

1. **Deprecated Functions**
   - Used `postprocess_conversation()` which was deprecated
   - Lesson: Always verify functions exist and are current

2. **Missing Context**
   - Reviewer had to ask for more information
   - Lesson: Provide all context upfront in PR description

3. **Architecture Understanding**
   - Didn't understand current audio storage flow
   - Lesson: Study codebase before implementing

## Rules Updated

- `.cursor/rules/common-mistakes.mdc`
  - Added: "Using Deprecated Functions" section
  - Added: Example from PR #3567
  
- `.cursor/rules/context-communication.mdc`
  - Added: PR #3567 feedback example
  - Updated: PR description requirements

## Recommendations

- Always check for deprecated functions before using them
- Provide complete context in PR descriptions
- Understand architecture before implementing changes
```

## Related Cursor Resources

### Rules
- `.cursor/rules/common-mistakes.mdc` - Common mistakes to avoid
- `.cursor/rules/context-communication.mdc` - Communication best practices
- `.cursor/rules/pre-implementation-checklist.mdc` - Pre-implementation verification

### Skills
- `.cursor/skills/self-improvement/SKILL.md` - Self-improvement meta-skill

### Commands
- `/self-improve` - Analyze patterns across multiple PRs
- `/learn-from-conversation` - Learn from user interactions
