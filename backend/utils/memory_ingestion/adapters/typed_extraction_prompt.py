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

=== OUTPUT GUIDANCE ===

• Extract AT MOST 2-3 facts per conversation (most will have 0-2)
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
