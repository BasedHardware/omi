# User Interaction Learning System

This system learns from direct user interactions to improve agent behavior and personalize guidance.

## Overview

The user interaction learning system tracks, analyzes, and learns from:
- User corrections
- Rejected suggestions
- Clarification requests
- Preference patterns
- Success patterns
- Failure patterns

## What It Tracks

### 1. User Corrections

**When**: User fixes agent's mistakes or misunderstandings

**Examples**:
- "No, don't use that function, it's deprecated"
- "That's not how the system works"
- "You misunderstood - I meant X, not Y"

**What to extract**:
- What was wrong
- Why it was wrong
- What should be done instead
- What rule/skill was missing

### 2. Rejected Suggestions

**When**: User says "no", "do it differently", or "that's not what I meant"

**Examples**:
- "No, don't do it that way"
- "That's not what I meant"
- "Can you try a different approach?"

**What to extract**:
- What approach was rejected
- Why it was rejected (if stated)
- What user actually wants
- Pattern in rejections

### 3. Clarification Requests

**When**: User needs to explain something the agent missed

**Examples**:
- "I need more context before you start coding"
- "You're missing X"
- "Don't forget about Y"

**What to extract**:
- What was missing
- What rule/skill should have covered it
- Gap in understanding
- What to add to rules

### 4. Preference Patterns

**What**: User's coding style, preferred approaches, common needs

**Examples**:
- Prefers small PRs
- Wants more context before implementation
- Likes detailed explanations
- Prefers planning phase
- Wants reasoning, not just implementation

**What to extract**:
- User's preferences
- Communication style
- Workflow preferences
- Coding style preferences

### 5. Success Patterns

**What**: Approaches the user consistently approves

**Examples**:
- User approves when agent provides plan first
- User likes when agent explains reasoning
- User approves thorough testing

**What to extract**:
- What worked
- Why it worked
- Pattern in approvals
- What to reinforce

### 6. Failure Patterns

**What**: What consistently needs correction

**Examples**:
- Agent often misses context
- Agent often assumes incorrectly
- Agent often doesn't verify assumptions

**What to extract**:
- What keeps going wrong
- Why it keeps happening
- What rule/skill is missing
- What needs improvement

## Learning Mechanisms

### 1. Correction Analysis

**Process**:
1. Detect user correction
2. Extract what was wrong
3. Identify why it was wrong
4. Determine what should be done instead
5. Find what rule/skill was missing
6. Update rules or create new ones

**Example**:
```
User: "No, don't use postprocess_conversation, it's deprecated"

Extract:
- What was wrong: Used deprecated function
- Why: Function no longer exists
- What to do: Always check for deprecated functions
- Missing rule: Check for deprecated functions before using
- Action: Update common-mistakes.mdc rule
```

### 2. Pattern Detection

**Process**:
1. Track corrections over time
2. Identify recurring issues
3. Find patterns in agent's understanding
4. Determine root causes
5. Update rules to address patterns

**Example**:
```
Pattern detected: Agent often misses context

Occurrences:
- User: "I need more context before you start coding"
- User: "You're missing some important details"
- User: "Don't forget to check X"

Root cause: Agent starts implementing too quickly
Solution: Update pre-implementation-checklist.mdc to emphasize context gathering
```

### 3. Preference Learning

**Process**:
1. Track what user approves/rejects
2. Identify patterns in preferences
3. Build user preference profile
4. Adapt guidance to user's style
5. Personalize future interactions

**Example**:
```
User preferences detected:
- Prefers planning phase (seen 5 times)
- Wants detailed explanations (seen 3 times)
- Likes reasoning (seen 4 times)

Action: 
- Update user preference profile
- Adapt future interactions
- Emphasize planning and reasoning
```

### 4. Gap Identification

**Process**:
1. When user clarifies, identify what was missing
2. Determine what rule/skill should have covered it
3. Check if rule exists
4. Update rule or create new one
5. Fill the gap

**Example**:
```
User: "That's not how the system works - you need to understand the conversation processing flow first"

Gap identified:
- Missing: Understanding of conversation processing flow
- Rule needed: Pre-implementation checklist should include understanding flow
- Action: Update pre-implementation-checklist.mdc
```

### 5. Success Reinforcement

**Process**:
1. When user approves, identify what worked
2. Extract success factors
3. Reinforce in rules
4. Apply to future interactions

**Example**:
```
User: "Perfect! This is exactly what I wanted"

Success factors:
- Provided plan first
- Explained reasoning
- Included verification steps

Action: Reinforce these patterns in rules
```

## Output

### 1. Rule Updates

**What**: Updates to existing rules based on user feedback

**Examples**:
- Add examples to common-mistakes.mdc
- Enhance pre-implementation-checklist.mdc
- Update context-communication.mdc
- Create new rules for user-specific patterns

### 2. New Rules

**What**: New rules created for emerging patterns

**Examples**:
- User-specific workflow rules
- Preference-based guidance
- Pattern-specific rules

### 3. Personalized Guidance

**What**: Guidance adapted to user's preferences

**Examples**:
- Emphasize planning for users who prefer it
- Provide more context for users who want it
- Include reasoning for users who like it

### 4. Improved Understanding

**What**: Better understanding of user's needs

**Examples**:
- Know user's coding style
- Understand user's workflow
- Recognize user's preferences

## Example Scenarios

### Scenario 1: Deprecated Function

```
User: "No, don't use that function, it's deprecated"

Learning:
- Extract: Always check for deprecated functions
- Update: common-mistakes.mdc rule
- Add: Example from this interaction
- Result: Future agents will check for deprecated functions
```

### Scenario 2: Missing Context

```
User: "I need more context before you start coding"

Learning:
- Extract: User prefers planning phase
- Update: user preference profile
- Update: pre-implementation-checklist.mdc
- Result: Future agents will provide more context upfront
```

### Scenario 3: Architecture Misunderstanding

```
User: "That's not how the system works"

Learning:
- Extract: Need to understand architecture better
- Update: pre-implementation-checklist.mdc
- Add: Architecture understanding requirement
- Result: Future agents will study architecture first
```

### Scenario 4: Preference Learning

```
User: "Can you explain why you chose this approach?"

Learning:
- Extract: User wants reasoning, not just implementation
- Update: user preference profile
- Update: context-communication.mdc
- Result: Future agents will explain reasoning
```

## User Preference Profile

**Structure**:
```yaml
user_preferences:
  communication:
    prefers_planning_phase: true/false
    wants_detailed_explanations: true/false
    likes_reasoning: true/false
    wants_context_upfront: true/false
  coding_style:
    prefers_small_prs: true/false
    wants_more_context: true/false
    likes_detailed_comments: true/false
    prefers_specific_examples: true/false
  workflow:
    prefers_verification_before_implementation: true/false
    wants_end_to_end_testing: true/false
    likes_step_by_step: true/false
```

**How it's built**:
- Track user approvals/rejections
- Identify patterns in feedback
- Learn from corrections
- Adapt over time

**How it's used**:
- Personalize guidance
- Adapt communication style
- Emphasize preferred approaches
- Avoid disliked patterns

## Integration with Feedback Loop

**Connection**:
- User interactions feed into feedback loop
- Patterns from interactions update rules
- Rules improve future interactions
- Cycle continues

**Flow**:
1. User corrects agent
2. System extracts lesson
3. Updates rules
4. Future agents follow updated rules
5. Fewer corrections needed
6. System improves

## Related Resources

### Rules
- `.cursor/rules/user-feedback-integration.mdc` - Guidelines for learning from interactions
- `.cursor/rules/common-mistakes.mdc` - Common mistakes (updated from interactions)
- `.cursor/rules/pre-implementation-checklist.mdc` - Checklist (updated from interactions)

### Skills
- `.cursor/skills/self-improvement/SKILL.md` - Self-improvement meta-skill
- `.cursor/skills/rule-updater/SKILL.md` - Rule updater skill

### Commands
- `/learn-from-conversation` - Learn from current conversation
- `/self-improve` - Analyze patterns and update rules

### Documentation
- `.cursor/feedback-loop.md` - Feedback loop system

## Best Practices

1. **Listen actively**: Pay attention to all user feedback
2. **Extract lessons**: Don't just note corrections, extract lessons
3. **Update promptly**: Update rules when patterns emerge
4. **Personalize**: Adapt to user's preferences
5. **Track patterns**: Look for recurring issues
6. **Test updates**: Verify rule updates improve behavior
