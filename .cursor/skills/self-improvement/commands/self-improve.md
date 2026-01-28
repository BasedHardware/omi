# Self-Improve

Analyze recent closed PRs, issues, and patterns to identify trends and update rules automatically.

## Usage

```
/self-improve [days]
```

Examples:
- `/self-improve` - Analyze last 30 days (default)
- `/self-improve 7` - Analyze last 7 days
- `/self-improve 90` - Analyze last 90 days

## Process

1. **Fetch recent PRs**
   - Get closed PRs from last N days
   - Fetch merged and rejected PRs
   - Get review comments and feedback

2. **Analyze patterns**
   - Compare merged vs. rejected PRs
   - Identify common rejection reasons
   - Find success patterns in merged PRs
   - Detect emerging patterns

3. **Identify rule updates**
   - Which rules need updating?
   - What new rules are needed?
   - What patterns are missing?

4. **Update rules**
   - Update existing rules with new patterns
   - Create new rules for emerging patterns
   - Remove outdated guidance (if applicable)

5. **Report findings**
   - Summary of analysis
   - Patterns identified
   - Rules updated/created
   - Recommendations

## Analysis Focus

### Rejection Patterns

**What to look for**:
- Common rejection reasons
- Recurring mistakes
- Missing context issues
- Architecture violations
- Testing gaps

**Metrics**:
- Most common rejection reason
- Frequency of each mistake type
- Trends over time

### Success Patterns

**What to look for**:
- What made PRs get merged?
- Common patterns in successful PRs
- What reviewers appreciate?
- Effective communication patterns

**Metrics**:
- Average time to merge
- Review cycle length
- Common success factors

### Emerging Patterns

**What to look for**:
- New types of mistakes
- Changing requirements
- New patterns to encode
- Gaps in current rules

## Rule Updates

### Updating Existing Rules

**When to update**:
- New examples of existing mistakes
- More specific guidance needed
- Patterns becoming more common
- Clarification needed

**How to update**:
1. Identify the rule to update
2. Add new examples
3. Reference PRs/issues
4. Keep organization clear

### Creating New Rules

**When to create**:
- New pattern emerges
- Existing rules don't cover it
- Pattern is significant enough
- Multiple examples exist

**How to create**:
1. Identify the pattern category
2. Collect 2-3 examples
3. Write the rule
4. Link from related rules

## Output Format

After analysis, provide:

1. **Summary**
   - Time period analyzed
   - Number of PRs analyzed
   - Key statistics

2. **Patterns Identified**
   - Most common mistakes
   - Success patterns
   - Emerging trends

3. **Rules Updated**
   - Which rules were updated
   - What was added/changed
   - New rules created

4. **Recommendations**
   - Focus areas for improvement
   - Rules to emphasize
   - Patterns to watch

## Example Output

```
Self-Improvement Analysis (Last 30 Days)

## Summary
- PRs analyzed: 45
- Merged: 32 (71%)
- Rejected: 13 (29%)
- Average review time: 2.3 days

## Patterns Identified

### Most Common Rejection Reasons
1. **Missing context** (38% of rejections)
   - PR descriptions lack sufficient detail
   - Reviewers need to ask questions
   - Pattern: PR #3567, #3621, #3634

2. **Deprecated functions** (23% of rejections)
   - Using functions that no longer exist
   - Not checking current codebase state
   - Pattern: PR #3567, #3598

3. **Architecture violations** (15% of rejections)
   - Import hierarchy violations
   - Module boundary issues
   - Pattern: PR #3612, #3639

### Success Patterns
- Complete PR descriptions (95% of merged PRs)
- End-to-end testing (87% of merged PRs)
- Quick response to feedback (avg 4 hours)

## Rules Updated

- `.cursor/rules/common-mistakes.mdc`
  - Enhanced "Missing Context" section
  - Added examples from recent PRs
  
- `.cursor/rules/context-communication.mdc`
  - Added PR description template
  - Expanded "What to Include" section

## Recommendations

1. **Emphasize context**: Most rejections due to missing context
2. **Check deprecations**: Common mistake, add to checklist
3. **Architecture review**: Add architecture verification step
```

## Effectiveness Tracking

Track rule effectiveness over time:

**Metrics**:
- Reduction in rejection rate after rule creation
- Frequency of mistakes after rule updates
- Rule coverage (how many scenarios covered)
- User correction frequency

**Questions to answer**:
- Are rules preventing mistakes?
- Which rules are most effective?
- What gaps remain?
- What rules need improvement?

## Related Cursor Resources

### Rules
- `.cursor/rules/common-mistakes.mdc` - Common mistakes to avoid
- `.cursor/rules/context-communication.mdc` - Communication best practices
- `.cursor/rules/pre-implementation-checklist.mdc` - Pre-implementation verification

### Skills
- `.cursor/skills/self-improvement/SKILL.md` - Self-improvement meta-skill
- `.cursor/skills/rule-updater/SKILL.md` - Rule updater skill

### Commands
- `/learn-from-pr` - Analyze a specific PR
- `/learn-from-conversation` - Learn from user interactions

## Best Practices

1. **Regular analysis**: Run periodically (weekly/monthly)
2. **Track trends**: Look for patterns over time
3. **Update proactively**: Don't wait for problems
4. **Test updates**: Verify rule updates don't break guidance
5. **Prioritize**: Focus on patterns causing most problems
