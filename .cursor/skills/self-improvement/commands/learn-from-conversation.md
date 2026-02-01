# Learn from Conversation

Analyze the current conversation to extract lessons learned from user corrections, feedback, and interactions.

## Usage

```
/learn-from-conversation
```

Run at the end of a conversation or when user provides feedback.

## Process

1. **Analyze conversation**
   - Review entire conversation
   - Identify user corrections
   - Find rejected suggestions
   - Note clarification requests
   - Track preference patterns

2. **Extract lessons**
   - What mistakes were made?
   - What feedback was given?
   - What patterns emerged?
   - What gaps were identified?

3. **Identify rule updates**
   - Which rules need updating?
   - What new rules are needed?
   - What patterns should be encoded?

4. **Update rules**
   - Update existing rules with new examples
   - Create new rules if needed
   - Update user preference profile

5. **Report findings**
   - Summarize lessons learned
   - List rules updated/created
   - Provide recommendations

## What to Extract

### User Corrections

**Look for**:
- "No, don't..."
- "That's wrong..."
- "You misunderstood..."
- "That's not how..."

**Extract**:
- What was wrong
- Why it was wrong
- What should be done instead
- What rule/skill was missing

**Example**:
```
User: "No, don't use postprocess_conversation, it's deprecated"

Extract:
- Mistake: Used deprecated function
- Lesson: Always check for deprecated functions
- Update: common-mistakes.mdc rule
```

### Rejected Suggestions

**Look for**:
- "No, do it differently"
- "That's not what I meant"
- "Can you try another approach?"

**Extract**:
- What approach was rejected
- Why it was rejected
- What user actually wants
- Pattern in rejections

**Example**:
```
User: "That's not what I meant - I need more context first"

Extract:
- Rejection: Started implementing too quickly
- Lesson: User prefers planning phase
- Update: user preference profile, pre-implementation-checklist.mdc
```

### Clarification Requests

**Look for**:
- "I need more..."
- "You're missing..."
- "Don't forget..."
- "Can you explain..."

**Extract**:
- What was missing
- What rule/skill should have covered it
- Gap in understanding
- What to add to rules

**Example**:
```
User: "You're missing the architecture understanding - read the docs first"

Extract:
- Gap: Didn't understand architecture before implementing
- Lesson: Must read architecture docs first
- Update: pre-implementation-checklist.mdc
```

### Preference Patterns

**Look for**:
- Consistent approvals/rejections
- Repeated requests
- Stated preferences

**Extract**:
- User's preferences
- Communication style
- Workflow preferences
- Coding style preferences

**Example**:
```
Pattern: User consistently asks for reasoning

Extract:
- Preference: Wants reasoning, not just implementation
- Update: user preference profile, context-communication.mdc
```

### Success Patterns

**Look for**:
- User approvals
- "Perfect!"
- "That's exactly what I wanted"

**Extract**:
- What worked
- Why it worked
- Pattern in approvals
- What to reinforce

**Example**:
```
User: "Perfect! This plan is exactly what I needed"

Extract:
- Success: Provided plan first
- Pattern: User prefers planning phase
- Reinforce: Always provide plan for this user
```

## Rule Updates

### Updating Existing Rules

**When**: Lesson fits existing rule

**How**:
1. Identify the rule to update
2. Add example from conversation
3. Reference the conversation
4. Enhance guidance if needed

**Example**:
```markdown
### Using Deprecated Functions

**Example from conversation**:
- User: "No, don't use postprocess_conversation, it's deprecated"
- Lesson: Always check for deprecated functions before using
```

### Creating New Rules

**When**: New pattern emerges

**How**:
1. Identify the pattern category
2. Collect examples from conversation
3. Create new rule file
4. Link from related rules

## User Preference Profile Updates

**What to update**:
- Communication preferences
- Coding style preferences
- Workflow preferences

**How to update**:
1. Identify preference from conversation
2. Update user preference profile
3. Adapt future interactions
4. Emphasize preferred approaches

**Example**:
```yaml
user_preferences:
  communication:
    prefers_planning_phase: true  # Learned from conversation
    wants_detailed_explanations: true  # Learned from conversation
```

## Output Format

After analyzing conversation, provide:

1. **Summary**
   - Conversation length
   - Key interactions
   - Main findings

2. **Lessons Learned**
   - Corrections extracted
   - Patterns identified
   - Gaps found

3. **Rules Updated**
   - Which rules were updated
   - What was added
   - New rules created (if any)

4. **User Preferences**
   - Preferences learned
   - Profile updates
   - Future adaptations

5. **Recommendations**
   - How to improve
   - What to emphasize
   - Patterns to watch

## Example Output

```
Conversation Analysis

## Summary
- Conversation length: 15 messages
- User corrections: 2
- Clarification requests: 1
- Preferences identified: 1

## Lessons Learned

1. **Deprecated Functions**
   - User: "No, don't use postprocess_conversation, it's deprecated"
   - Lesson: Always check for deprecated functions before using
   - Update: common-mistakes.mdc rule

2. **Planning Preference**
   - User: "I need more context before you start coding"
   - Lesson: User prefers planning phase
   - Update: user preference profile, pre-implementation-checklist.mdc

3. **Architecture Understanding**
   - User: "You're missing the architecture understanding"
   - Lesson: Must read architecture docs first
   - Update: pre-implementation-checklist.mdc

## Rules Updated

- `.cursor/rules/common-mistakes.mdc`
  - Added: Example from conversation about deprecated functions
  
- `.cursor/rules/pre-implementation-checklist.mdc`
  - Enhanced: Architecture understanding requirement
  - Added: Planning phase emphasis

## User Preferences

- Prefers planning phase: true
- Wants detailed explanations: true
- Likes reasoning: false (not yet determined)

## Recommendations

1. Always check for deprecated functions before using
2. Provide more context upfront for this user
3. Read architecture docs before implementing
```

## Related Cursor Resources

### Rules
- `.cursor/rules/user-feedback-integration.mdc` - Guidelines for learning from interactions
- `.cursor/rules/common-mistakes.mdc` - Common mistakes (updated from interactions)
- `.cursor/rules/pre-implementation-checklist.mdc` - Checklist (updated from interactions)

### Skills
- `.cursor/skills/self-improvement/SKILL.md` - Self-improvement meta-skill
- `.cursor/skills/rule-updater/SKILL.md` - Rule updater skill

### Commands
- `/learn-from-pr` - Analyze a specific PR
- `/self-improve` - Analyze patterns and update rules

### Documentation
- `.cursor/docs/user-interaction-learning.md` - User interaction learning system
- `.cursor/docs/feedback-loop.md` - Feedback loop system

## Best Practices

1. **Run regularly**: After significant conversations
2. **Extract thoroughly**: Don't miss lessons
3. **Update promptly**: Update rules when patterns emerge
4. **Track preferences**: Build user preference profile
5. **Test updates**: Verify rule updates improve behavior
