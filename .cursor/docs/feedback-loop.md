# Feedback Loop System

This document describes the self-improvement feedback loop system that learns from GitHub PRs, issues, discussions, and user interactions to continuously improve Cursor guidance.

## Overview

The feedback loop system:
- Tracks PR outcomes (merged/rejected)
- Analyzes review comments for patterns
- Tracks user interactions (corrections, clarifications, rejections, preferences)
- Updates rules based on what worked
- Maintains a knowledge base of "what not to do"
- Identifies when rules need updating
- Personalizes guidance based on user patterns

## Components

### 1. PR Analysis

**What it tracks**:
- PR status (merged/rejected)
- Review comments and feedback
- Rejection reasons
- Code changes
- Review cycle time

**How it works**:
1. Fetch PR data from GitHub API or web fetch
2. Parse review comments for actionable feedback
3. Identify patterns in rejections vs. acceptances
4. Extract specific mistakes and success patterns
5. Map to existing rules or identify gaps

**Tools**:
- GitHub API (if available)
- `mcp_web_fetch` for fetching PR pages
- Pattern matching for common feedback themes

### 2. Issue Pattern Extraction

**What it tracks**:
- Issue descriptions and labels
- Common bug patterns
- Feature requests revealing gaps
- User-reported issues indicating misunderstandings
- Triage patterns (what gets prioritized)

**How it works**:
1. Analyze issue descriptions and labels
2. Identify recurring themes
3. Map to Omi layers (Capture/Understand/Memory/etc.)
4. Extract lessons about what not to do

**Tools**:
- Web fetch for issue pages
- Pattern analysis for common issues
- Mapping to Omi architecture layers

### 3. User Interaction Learning

**What it tracks**:
- **User corrections**: When user fixes agent's mistakes or misunderstandings
- **Rejected suggestions**: When user says "no, do it differently" or "that's not what I meant"
- **Clarification requests**: When user needs to explain something the agent missed
- **Preference patterns**: User's coding style, preferred approaches, common needs
- **Success patterns**: What approaches the user consistently approves
- **Failure patterns**: What consistently needs correction

**How it works**:
1. Monitor conversation for corrections and feedback
2. Extract the lesson from each correction
3. Identify patterns across multiple interactions
4. Update rules or create new ones based on patterns
5. Build user preference profile

**Learning mechanisms**:
- **Correction analysis**: When user corrects, extract what was wrong and why
- **Pattern detection**: Identify recurring issues in agent's understanding
- **Preference learning**: Build profile of user's preferences
- **Gap identification**: When user clarifies, identify what rule/skill was missing
- **Success reinforcement**: When user approves, identify what worked

### 4. Rule Updates

**What it does**:
- Updates existing rules with new examples
- Creates new rules for emerging patterns
- Removes outdated guidance (if applicable)
- Organizes rules for easy navigation

**How it works**:
1. Identify patterns from PRs/issues/interactions
2. Check if existing rule covers it
3. If yes, update the rule with new information
4. If no, create a new rule
5. Test rule effectiveness

**Tools**:
- Rule updater skill (`.cursor/skills/rule-updater/SKILL.md`)
- File editing tools
- Pattern matching for rule categorization

## Implementation Approach

### Data Sources

1. **GitHub PRs**
   - Use GitHub API or web fetch
   - Parse PR pages for status, comments, changes
   - Extract review feedback

2. **GitHub Issues**
   - Fetch issue pages
   - Analyze descriptions and labels
   - Map to Omi layers

3. **User Interactions**
   - Monitor conversation for corrections
   - Track user feedback patterns
   - Learn from clarifications

### Pattern Extraction

**Common patterns to extract**:

**From rejected PRs**:
- Used deprecated functions
- Didn't understand architecture
- Missing context in PR description
- Didn't test end-to-end
- Assumed system state incorrectly

**From merged PRs**:
- Complete PR descriptions
- Proper testing and verification
- Followed architecture patterns
- Quick response to feedback

**From user interactions**:
- User corrections revealing gaps
- Preference patterns
- Success patterns
- Failure patterns

### Rule Updates

**Update process**:
1. Identify pattern from data source
2. Check if existing rule covers it
3. Update rule or create new one
4. Reference source (PR/issue/interaction)
5. Test rule effectiveness

**Update types**:
- Add examples to existing sections
- Enhance sections with more detail
- Add new sections for new patterns
- Create new rules for new categories

## User Preference Profile

**What it builds**:
- User's coding style preferences
- Preferred approaches
- Common needs
- Communication style
- Workflow preferences

**How it learns**:
- Track what user approves/rejects
- Identify patterns in user feedback
- Learn from corrections
- Adapt to user's style

**Example profile**:
```yaml
user_preferences:
  communication:
    prefers_planning_phase: true
    wants_detailed_explanations: true
    likes_reasoning: true
  coding_style:
    prefers_small_prs: true
    wants_more_context: true
    likes_detailed_comments: false
  workflow:
    prefers_verification_before_implementation: true
    wants_end_to_end_testing: true
```

## Knowledge Base

**Maintains knowledge of**:
- What not to do (common mistakes)
- What to do (success patterns)
- How to do it (best practices)
- When to do it (context-specific guidance)

**Organization**:
- Rules organized by category
- Examples linked to sources
- Cross-references between rules
- Regular updates based on new data

## Effectiveness Tracking

**Metrics to track**:
- Reduction in PR rejection rate after rule creation
- Frequency of mistakes after rule updates
- Rule coverage (how many scenarios covered)
- User correction frequency
- Rule effectiveness over time

**Questions to answer**:
- Are rules preventing mistakes?
- Which rules are most effective?
- What gaps remain?
- What rules need improvement?

## Usage

### Manual Triggers

**Commands**:
- `/learn-from-pr <PR_NUMBER>` - Analyze specific PR
- `/learn-from-conversation` - Learn from current conversation
- `/self-improve [days]` - Analyze patterns and update rules

### Automatic Learning

**When it happens**:
- After user corrections
- When patterns emerge
- Periodically (weekly/monthly analysis)
- When gaps are identified

## Example Workflow

1. **PR gets rejected**
   - System analyzes PR
   - Extracts rejection reasons
   - Identifies patterns

2. **Pattern identified**
   - "Missing context" is common
   - Check if rule exists
   - Update or create rule

3. **Rule updated**
   - Add example from PR
   - Enhance guidance
   - Reference PR number

4. **Future prevention**
   - Rule prevents similar mistakes
   - Agent follows updated guidance
   - Fewer rejections

## Related Resources

### Rules
- `.cursor/rules/common-mistakes.mdc` - Common mistakes to avoid
- `.cursor/rules/context-communication.mdc` - Communication best practices
- `.cursor/rules/pre-implementation-checklist.mdc` - Pre-implementation verification
- `.cursor/rules/user-feedback-integration.mdc` - Learning from user interactions

### Skills
- `.cursor/skills/self-improvement/SKILL.md` - Self-improvement meta-skill
- `.cursor/skills/rule-updater/SKILL.md` - Rule updater skill

### Commands
- `/learn-from-pr` - Analyze a specific PR
- `/learn-from-conversation` - Learn from user interactions
- `/self-improve` - Analyze patterns and update rules

### Documentation
- `.cursor/user-interaction-learning.md` - User interaction learning system

## Best Practices

1. **Regular analysis**: Run periodically to catch trends
2. **Track effectiveness**: Monitor if rules are working
3. **Update proactively**: Don't wait for problems
4. **Test updates**: Verify rule updates don't break guidance
5. **Prioritize**: Focus on patterns causing most problems
6. **Document sources**: Always reference where lessons came from
