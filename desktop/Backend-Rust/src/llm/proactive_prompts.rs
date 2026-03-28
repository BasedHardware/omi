// Proactive assistant prompts — migrated from Swift client-side services.
// Issue #6098 L3: server-side proactive Gemini calls.

// ============================================================================
// AI USER PROFILE
// ============================================================================

/// Stage 1: Generate raw user profile from context data.
pub const USER_PROFILE_GENERATE: &str = r#"You are generating a structured user profile that will be injected as context into AI pipelines.

OUTPUT FORMAT: Flat list of factual statements, one per line, prefixed with "- "

WHAT TO INCLUDE (only if clearly supported by the data):
- Full name, role, company, industry
- Current projects and tools/apps
- Key people they interact with
- Active goals and progress
- Recurring meetings, deadlines, routines
- Communication platforms
- Technical stack, programming languages
- Topics they frequently discuss/research
- Pending tasks and commitments
- Time zone, work schedule patterns

CRITICAL RULES:
- Only include facts evidenced in the provided data
- NO hallucination or speculation
- NO personality descriptions or subjective assessments
- Maximum 2000 characters

USER DATA:

{user_data}"#;

/// Stage 2: Consolidate new profile with historical profiles.
pub const USER_PROFILE_CONSOLIDATE: &str = r#"You are merging a new user profile with historical profiles to create a holistic, up-to-date view.

MERGE RULES:
- NEW profile has priority for current state
- Past profiles provide historical context
- Remove outdated info (completed tasks, past deadlines)
- Keep stable facts (name, role, company, relationships, tech stack)
- Accumulate knowledge from past profiles

OUTPUT FORMAT: Flat list of factual statements, one per line, prefixed with "- "
Maximum 2000 characters.

NEW PROFILE:
{new_profile}

HISTORICAL PROFILES:
{history}"#;

// ============================================================================
// TASK PRIORITIZATION
// ============================================================================

/// Re-rank staged tasks by relevance.
pub const TASK_PRIORITIZE: &str = r#"You are a task prioritization assistant. You review a ranked task list and identify tasks that are misranked. Be selective — only return tasks that genuinely need to move. If the ranking looks reasonable, return an empty list. Be decisive about pushing noise and vague tasks down and promoting urgent, goal-aligned tasks up.

CONTEXT:
{context}

CURRENT TASK LIST (ordered by current rank, 1 = most important):
{task_list}"#;

// ============================================================================
// TASK DEDUPLICATION
// ============================================================================

/// Identify semantically duplicate tasks.
pub const TASK_DEDUPLICATE: &str = r#"You are a task deduplication assistant. You identify semantically duplicate tasks and choose the best one to keep. Be conservative - only flag clear duplicates. Return has_duplicates: false if no duplicates are found.

Two tasks are duplicates if they refer to the same action, even if worded differently.

When choosing which task to keep, prefer:
1. Most descriptive/specific wording
2. Has due date over one without
3. Higher priority (high > medium > low > none)
4. More reliable source (manual > transcription > screenshot)
5. Most recently created

TASKS:
{task_list}"#;

// ============================================================================
// GOALS AI
// ============================================================================

/// Generate a goal suggestion from user context.
pub const GOAL_GENERATE: &str = r#"You are generating a personal goal for a user. Your job is to reason deeply about WHO this person is and what they're trying to ACHIEVE — not just what they talk about day-to-day.

STEP 1: Understand the user at a high level (persona, ambitions, life direction)
STEP 2: Look at what they're actively working on (unmet needs, gaps)
STEP 3: Review goal history (don't repeat completed/abandoned goals)
STEP 4: Synthesize ONE specific, measurable goal that:
  1. Reflects what user is STRIVING for at deeper level
  2. Addresses unmet need or gap
  3. NOT duplicate of active/completed/abandoned goal
  4. Has clear numeric target and timeframe
  5. Would genuinely excite this specific person
STEP 5: Link relevant tasks (by [task_id]) that contribute to goal

CONTEXT:
{context}"#;

/// Get actionable advice for a specific goal.
pub const GOAL_ADVICE: &str = r#"You are a strategic advisor. Based on the user's goal and their context, give ONE specific actionable step they should take THIS WEEK.

GOAL: "{goal_title}"
PROGRESS: {current_value} / {target_value} ({progress_pct}%)

RECENT CONTEXT:
{context}

Give ONE specific action in 1-2 sentences. Be concise but complete. No generic advice."#;

/// Extract progress toward a goal from user text.
pub const GOAL_EXTRACT_PROGRESS: &str = r#"Analyze this message to see if it mentions progress toward this goal:

Goal: "{goal_title}"
Goal Type: {goal_type}
Current Progress: {current_value} / {target_value}

User Message: "{text}"

If the message mentions NEW progress value for this SPECIFIC goal, extract it.
Only return found=true if confident this is about the SPECIFIC goal."#;
