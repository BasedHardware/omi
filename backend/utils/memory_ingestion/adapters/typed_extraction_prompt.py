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

v3 (2026-06-13): Diagnostic-driven overhaul. Root causes of H=75%/F1=0.162:
  (1) No negative few-shots → model never learns [] output → added Examples 6-8.
  (2) Liberal default ("extract when in doubt") → flipped to conservative default.
  (3) Source-blind prompt → added SOURCE TYPE DETECTION section.
  (4) is_currently_true catch-all too broad → tightened to <10% of extractions.
  (5) No noise definition → added NOISE SIGNALS section.
  (6) "Do NOT skip" note contradicted exclusion rules → softened.
  (7) Dead predicates removed (decided_to_use, belongs_to_project → merged).
"""

from langchain_core.prompts import ChatPromptTemplate

# Keep this vocabulary in sync with the layer-2 resolver and the benchmark
# adapter crosswalk (memory-eval adapters/pipeline_output/crosswalk.py).
TYPED_PREDICATES = [
    "plans_travel_to",
    "prefers",
    "dislikes",
    "works_on",            # absorbs belongs_to_project
    "considering_using",   # absorbs decided_to_use for weak/evaluative cases
    "committed_to_do",     # absorbs decided_to_use for strong decisions
    "knows_person",
    "has_birthday",
    "has_address",
    "uses_tool",           # absorbs owns_device
    "is_currently_true",   # LAST RESORT — tightened definition, <10% of extractions
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

SOURCE TYPE DETECTION — adjust extraction aggressiveness based on input type:

• VOICE TRANSCRIPT indicators: [Speaker N:] labels, disfluencies (um, uh, like),
  non-English text (Cyrillic, etc.), monologue-style single-speaker text,
  garbled words, filler-heavy turns (>40% filler words).
  → EXTRA CONSERVATIVE. Require ≥2 independent utterances supporting the same fact.
  → Flag with uncertainty_reason=low_quality_transcript if extracting anything.
  → If >60% of text is filler/disfluency → output [] immediately.

• SCREENSHOT OCR indicators: Fragmented text, garbled characters (typos like
  "CustOTlliZe"), UI element labels (buttons, menus, navigation),
  transient state (notifications, counts, timestamps), credential-looking strings.
  → SKEPTICAL. Only extract if text forms a complete, coherent factual statement
    about {user_name} (not just UI chrome or transient state).
  → Never extract UI elements, navigation labels, or transient notifications.
  → If text is mostly fragments/garble → output [] immediately.

• CHAT indicators: Clean turn-taking (human:/ai: labels), complete sentences,
  low disfluency rate.
  → Standard extraction rules apply. Still default to empty for chitchat/greetings.

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
   - works_on — a project/product they actively work on (absorbs "belongs_to_project")
   - considering_using — an option under ACTIVE evaluation (not idle speculation — must show research/comparison/decision context). Absorbs weak "decided_to_use" cases.
   - committed_to_do — a concrete commitment/promise. Absorbs strong "decided_to_use" cases.
   - knows_person — a relationship
   - has_birthday — birthday information
   - has_address — address/location information
   - uses_tool — a tool/service they routinely use (absorbs "owns_device")
   - is_currently_true — durable state/fact with no better predicate above (LAST RESORT — use for <10% of extractions MAXIMUM). Must represent a concrete, verifiable state change or enduring biographical fact about {user_name}, NOT generic activity descriptions, mood states, work observations, or transient status.
   - is_no_longer_true — a fact that stopped holding

   Write the predicate EXACTLY as shown. Prefer the MOST SPECIFIC predicate. Use is_currently_true only as absolute last resort and only for concrete, non-obvious facts.

1. quote_anchor — verbatim substring from transcript proving the fact. For {user_name} facts, must be self-report evidence ({user_name}'s own turn or first-person language "I"/"my"/"we"). Preserve ≥2 distinctive non-stopword terms. No paraphrase. If no literal self-report quote exists → no fact.

2. content — one concise sentence (max 15 words), specific and timeless, starting with {user_name}. No hedging words ("might", "maybe", "could") — encode uncertainty in uncertainty_reasons instead.

3. arguments — named slots for the chosen predicate. Only fill when EXPLICITLY stated; leave unfilled slots out entirely.
   - plans_travel_to: destination, planned_date (if stated)
   - prefers: preference, over (if comparison)
   - dislikes: target
   - works_on: project
   - considering_using: tool, purpose
   - committed_to_do: action, due (if stated)
   - knows_person: person, relationship, context
   - has_birthday: person, date
   - has_address: person, address_or_location
   - uses_tool: tool, purpose
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

NOISE SIGNALS — output EMPTY list when input is predominantly:
• Greetings/openings: "hey", "hi", "hello", "yo", "what's up", "как дела"
• Pure backchannel: "yeah", "mm-hm", "right", "sure", "okay"
• Filler monologue: >50% of words are discourse fillers
• Narrative/media description: someone describing what they're watching/reading
  without personal factual content about {user_name}
• Question-only input: questions without embedded factual assertions
• UI/navigation chrome: menu items, button labels, notification text
• Garbled/incomprehensible: text with >20% unrecognizable or corrupted words
• Generic work chatter: "had a meeting", "discussed X", "learned something new"
  unless it contains a concrete commitment/decision/preference about {user_name}


=== FEW-SHOT EXAMPLES ===

These examples show how to extract from LOW-DENSITY statements — short inputs
without strong action verbs or explicit decision language. When you see similar
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

**Example 4 — Generic work chatter with NO durable fact (output EMPTY list)**
Input:  "The code freeze got pushed to next sprint."
Output: []
NOTE: Pure scheduling/status updates without personal commitment or preference
about {user_name} are NOT memory-worthy. "Code freeze timing" is a transient
work detail, not a durable biographical fact about {user_name}. Skip it.

**Example 5 — Reported commitment via third party (extract committed_to_do, attr=third_party)**
Input:  "My manager said I need to submit the Q3 plan by Friday."
Output: predicate=committed_to_do  quote="submit the Q3 plan by Friday"
        content="David needs to submit the Q3 plan by Friday"
        arguments={{"action": "submit Q3 plan", "due": "Friday"}}
        subject_attribution=third_party
        uncertainty_reasons=[inferred_not_stated]
NOTE: When commitment is reported by a third party ("my manager said", "they asked me"),
use subject_attribution=third_party unless {user_name} explicitly confirms it themselves.

**Example 6 — Greeting/chitchat with no factual content (output EMPTY list)**
Input:  "yo\nyo! что делаем? 👀"
Output: []
NOTE: Greetings, fillers, and casual back-and-forth with no factual content
always produce an empty list. No predicate match = no extraction.
This is the MOST COMMON case in real data — most inputs are noise.

**Example 7 — Garbled voice transcript with no durable facts (output EMPTY list)**
Input:  "[Speaker 0]: Привет. Короче. Она красивая, но не удалась.\n[Speaker 0]: Вот всё же происходит. Я, кстати, его сегодня..."
Output: []
NOTE: Even long transcripts that contain only casual chatter, disfluencies,
or narrative monologue without explicit factual statements about {user_name}
produce an empty list. Do not extract from filler-heavy or garbled input.
When in doubt on voice transcripts → output [].

**Example 8 — OCR screenshot showing UI chrome / product page (output EMPTY list)**
Input:  "••• tDo (a Chat * What's up next, Nik? + Nv*sesslon\nCustOTlliZe ••• Retard-12608921"
Output: []
NOTE: Fragmented/garbled OCR text, UI navigation elements, and transient screen
content are not durable facts about {user_name}. Screenshots capture momentary
state, not memory-worthy information. Unless OCR contains a clear self-reported
fact (name, address, preference) in coherent text → output [].

KEY PATTERN: Short statements CAN be memory-worthy IF they contain a SPECIFIC
predicate match (preferably not is_currently_true), a verbatim self-report quote
anchor, AND represent a non-obvious durable fact. Generic observations, mood
statements, activity mentions, or scheduling chatter — even with quote anchors
— should still be skipped. When in doubt, do NOT extract.



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
• Only extract when ALL conditions are met:
  (a) clear, SPECIFIC predicate match (not is_currently_true unless no other fits)
  (b) verbatim self-report quote anchor with ≥2 distinctive terms
  (c) the fact is DURABLE (still true in 6 months) and NON-OBVIOUS
  (d) the input contains substantive content (not greetings, filler, or noise)
• DEFAULT TO EMPTY LIST. Extraction is the exception, not the rule.
• When in doubt, do NOT extract. A missed real memory is better than a hallucinated one.
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
