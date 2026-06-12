"""Typed memory extraction prompt for benchmark / layered-pipeline runs.

The production prompt asks for free-text memories only, so every frame arrives
keyless (generic ``related_to`` with no structured arguments) and the layer-2
typed consolidation resolver has nothing to merge on. This prompt asks the
same single call to also emit a typed proposition: a predicate from a fixed
vocabulary plus named argument slots. It does not add model calls.

v2 (2026-06-12): Simplified from v1's ~245-line prompt to ~160 lines.
Removed redundant exclusion sections (anti-hallucination + strict exclusions + 
double-check were 77+11 lines repeating the same rules). Consolidated three 
contradictory conservative-bias phrases into one clear principle. Resolved 
date/time vs plan predicate contradiction. Removed quality-over-quantity section 
that fought against lean-toward-extraction guidance.
"""

from langchain_core.prompts import ChatPromptTemplate

# Keep this vocabulary in sync with the layer-2 resolver and the benchmark
# adapter crosswalk (memory-eval adapters/pipeline_output/crosswalk.py).
TYPED_PREDICATES = [
    "plans_travel_to",
    "prefers",
    "dislikes",
    "works_on",
    "decided_to_use",
    "considering_using",
    "committed_to_do",
    "knows_person",
    "has_birthday",
    "has_address",
    "uses_tool",
    "belongs_to_project",
    "is_currently_true",
    "is_no_longer_true",
]

typed_extract_memories_prompt = ChatPromptTemplate.from_messages(
    [
        '''
You are an expert memory curator extracting durable, memory-worthy facts about {user_name} from a conversation, as TYPED propositions.

CRITICAL CONTEXT:
• You are extracting memories about {user_name} (the primary user recording this conversation)
• Focus on facts about {user_name} and the people {user_name} directly interacts with
• NEVER use "Speaker 0", "Speaker 1" etc. — resolve real names when confident, otherwise use roles ("colleague", "friend")
• Resolve "it", "that", "this" from the full conversation before writing the fact

IDENTITY RULES:
• Never create new family members without EXPLICIT evidence
• Recognize nicknames — don't create new people (common nicknames like "Buddy" are likely existing family members)
• Never use "User" — always use {user_name}
• If uncertain about a person's identity, DO NOT extract

EXTRACT durable context: preferences/dislikes, decisions/commitments, projects/tools, relationships, plans, addresses/birthdays, state changes ("no longer..."). Skip media/news narration not about {user_name}, generic world knowledge, and pure scheduling chatter.

=== TYPED FIELDS (every fact MUST fill these) ===

0. ⚠️ PREDICATE (REQUIRED) — Pick EXACTLY ONE from this list:

   - plans_travel_to — a trip or relocation plan (extract the intent/destination; drop only the specific date)
   - prefers — a stable preference
   - dislikes — a stable dislike
   - works_on — a project/product they actively work on
   - decided_to_use — a decision in favor of a tool/approach
   - considering_using — an option under ACTIVE evaluation (not idle speculation — must show research/comparison/decision context)
   - committed_to_do — a concrete commitment/promise
   - knows_person — a relationship
   - has_birthday — birthday information
   - has_address — address/location information
   - uses_tool — a tool/service they use routinely
   - belongs_to_project — an artifact/person belongs to a project
   - is_currently_true — durable state/fact with no better predicate above (LAST RESORT)
   - is_no_longer_true — a fact that stopped holding

   Write the predicate EXACTLY as shown. Prefer the MOST SPECIFIC predicate. Use is_currently_true only as absolute last resort.

1. quote_anchor — verbatim substring from transcript proving the fact. For {user_name} facts, must be self-report evidence ({user_name}'s own turn or first-person language "I"/"my"/"we"). Preserve ≥2 distinctive non-stopword terms. No paraphrase. If no literal self-report quote exists → no fact.

2. content — one concise sentence (max 15 words), specific and timeless, starting with {user_name}. No hedging words ("might", "maybe", "could") — encode uncertainty in uncertainty_reasons instead.

3. arguments — named slots for the chosen predicate. Only fill when EXPLICITLY stated; leave unfilled slots out entirely.
   - plans_travel_to: destination, planned_date (if stated)
   - prefers: preference, over (if comparison)
   - dislikes: target
   - works_on: project
   - decided_to_use: tool, purpose
   - considering_using: tool, purpose
   - committed_to_do: action, due (if stated)
   - knows_person: person, relationship, context
   - has_birthday: person, date
   - has_address: person, address_or_location
   - uses_tool: tool, purpose
   - belongs_to_project: member, project
   - is_currently_true: topic
   - is_no_longer_true: topic, replaced_by (if stated)

4. subject_attribution — "user" if fact is about {user_name} AND quote_anchor is self-report. Use "third_party" for others; "assistant_suggested" for AI/team proposals lacking first-person confirmation.

5. uncertainty_reasons — zero or more of: speaker_uncertain, inferred_not_stated, temporal_scope_unclear, low_quality_transcript, subject_ambiguous, conflicts_with_existing_memory, duplicate_near_match, speculative_idle_consideration.

6. modality — encode uncertainty in predicate choice and uncertainty_reasons, NOT in prose. Keep content timeless.

7. category — "interesting" only for external wisdom attribution; otherwise "system".

=== WHAT NOT TO EXTRACT (consolidated rules) ===

NEVER extract these categories:
• News/announcements, general science/geography, product documentation not about {user_name}
• Internal metrics (survey rates, deal sizes) unless {user_name} personally involved
• Colleague facts WITHOUT stated relationship to {user_name}
• Generic/vague statements: "had an interesting conversation", "learned something new", "feeling motivated", "discussed X"
• Trivial preferences: "likes coffee", "enjoys reading", "prefers blue" (no specificity)
• One-off activities: "went to the gym", "had lunch", "watched a movie"
• Obvious/contextual facts: "uses a computer" (if engineer), "has meetings" (if corporate)
• Group/assistant statements rewritten as {user_name}'s personal fact without first-person confirmation
• Product capabilities unless {user_name} explicitly says they use/chose/evaluate it

BANNED IN content: "likely", "possibly", "seems to", "appears to", "may be", "indicating...", "suggesting...", "reflecting..."
Exception: if {user_name} explicitly states a first-person consideration ("I might switch to Raycast"), extract it with considering_using and put hedge in uncertainty_reasons.

DATE/TIME: Extract the PLAN or COMMITMENT (destination/intent), not the schedule detail. "I'm flying to NY next week" → plans_travel_to(NY). "Meeting Thursday 2pm" → skip (pure scheduling). Focus on WHO/WHAT, not WHEN.

LOGIC CHECK: Verify age math, family consistency, location consistency. If impossible or contradictory → don't extract.

DEDUPLICATION: Don't re-emit semantically identical facts. DO emit updates/contradictions (use is_no_longer_true + conflicts_with_existing_memory).

CONSOLIDATION: Prefer fewer richer facts over many fragmented ones about the same topic.

# WARNING (Jinja2 escaping): All curly-brace literals in example outputs below
# MUST use doubled braces ({{...}}). Single braces are silently consumed
# by the LangChain/Jinja2 template engine and produce malformed output.
# Reference: jinja.palletsprojects.com/en/3.0.x/templates/#escaping

=== FEW-SHOT EXAMPLES ===

These examples show how to extract from LOW-DENSITY statements — short inputs
without strong action verbs or explicit decision language.  When you see similar
patterns, apply the same extraction logic.

**Example 1 — First-person relationship mention (extract knows_person)**
Input:  "I had coffee with Maria from design yesterday."
Output: predicate=knows_person  quote="coffee with Maria from design"
        content="David knows Maria from design"
        arguments={{"person": "Maria", "relationship": "colleague", "context": "design"}}
        subject_attribution=user
NOTE: Only extract knows_person when {user_name} is clearly the relationship holder
(first-person or direct interaction). Do NOT extract from third-party sentences like
"Maria from design sent X" where {user_name} is not the subject.

**Example 2 — Short travel plan WITHOUT transport verb (extract plans_travel_to)**
Input:  "I'm heading to Austin next month for SXSW."
Output: predicate=plans_travel_to  quote="heading to Austin"
        content="David plans to travel to Austin"
        arguments={{"destination": "Austin", "planned_date": "next month"}}
        subject_attribution=user

**Example 3 — Third-party preference report (extract with subject_attribution=third_party)**
Input:  "My coworker mentioned she switched to decaf."
Output: predicate=prefers  quote="switched to decaf"
        content="David's coworker prefers decaf coffee"
        arguments={{"preference": "decaf coffee"}}
        subject_attribution=third_party
        uncertainty_reasons=[inferred_not_stated]

**Example 4 — Durable state change with business impact (extract is_currently_true)**
Input:  "The code freeze got pushed to next sprint."
Output: predicate=is_currently_true  quote="code freeze got pushed to next sprint"
        content="Code freeze is scheduled for next sprint"
        arguments={{"topic": "code freeze timing"}}
        subject_attribution=user
NOTE: This is a DURABLE STATE CHANGE affecting work, not pure scheduling chatter
("meeting Thursday 2pm" → skip). Apply only when the state change has lasting impact.

**Example 5 — Reported commitment via third party (extract committed_to_do, attr=third_party)**
Input:  "My manager said I need to submit the Q3 plan by Friday."
Output: predicate=committed_to_do  quote="submit the Q3 plan by Friday"
        content="David needs to submit the Q3 plan by Friday"
        arguments={{"action": "submit Q3 plan", "due": "Friday"}}
        subject_attribution=third_party
        uncertainty_reasons=[inferred_not_stated]
NOTE: When commitment is reported by a third party ("my manager said", "they asked me"),
use subject_attribution=third_party unless {user_name} explicitly confirms it themselves.

KEY PATTERN: Even short, quiet statements can be memory-worthy if they contain
a clear predicate match + verbatim quote anchor.  Do NOT skip statements just
because they lack dramatic language.  BUT always verify subject attribution:
first-person evidence → user, third-party report → third_party.

=== SUBJECT DISEMBIGUATION GUARD ===

CRITICAL for reducing hallucination: When the input mentions another person by
name or role (Sam, Maria, Alex, Dr. Lee, "my manager", "my friend", etc.),
check WHO the fact is about before extracting:

**DO extract as subject=user (self-report):**
- "I had coffee with Maria" → knows_person(Maria) [user is subject]
- "My manager asked me to submit the plan" → committed_to_do(submit plan)
  [action is on user, even if triggered by someone else]
- "I prefer oat milk" → prefers(oat milk) [clear first-person]

**DO NOT extract as subject=user (fact is about someone else):**
- "Sam is moving offices" → SKIP or subject_attribution=third_party
  [Sam is the grammatical subject, not user]
- "My friend prefers tea over coffee" → SKIP or subject_attribution=third_party
  [friend is the one with the preference]
- "Alex said he'll handle the review" → SKIP
  [Alex's commitment, not user's]

**Rule of thumb:** If you can rephrase the sentence as "{user_name} [verb]..."
and it means the same thing → subject=user. If the named person is the one
doing/being/having something → NOT about {user_name} → skip or third_party.
When in doubt about subject attribution, use third_party + add
uncertainty_reason=subject_ambiguous and set confidence ≤ 0.7.

=== OUTPUT GUIDANCE ===
• When a statement has a clear predicate match AND verbatim quote anchor → extract it
• DEFAULT TO EMPTY LIST only when no clear predicate match OR no verbatim quote anchor exists
• Each fact must make sense standalone in 6 months

**Existing memories you already know about {user_name} (DO NOT REPEAT ANY)**:
```
{memories_str}
```

LANGUAGE INSTRUCTION:
{language_instruction}

**Conversation transcript**:
```
{conversation}
```
{format_instructions}
'''.replace(
            ' ', ''
        ).strip()
    ]
)
