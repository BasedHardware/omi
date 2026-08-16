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
    "works_on",  # absorbs belongs_to_project
    "considering_using",  # absorbs decided_to_use for weak/evaluative cases
    "committed_to_do",  # absorbs decided_to_use for strong decisions
    "knows_person",
    "has_birthday",
    "has_address",
    "uses_tool",  # absorbs owns_device
    "is_currently_true",  # PRIMARY predicate for voice/transcript sources (~30% of extractions); use for biographical identity, ongoing states, location/residence, visa/status, family relationships, health, travel history when no more specific predicate fits
    "is_no_longer_true",
    "credential_detected",  # credentials, passwords, PII, auth material (OCR/security sources)
    "sensitive_info_visible",  # sensitive but non-credential info (emails, personal identifiers)
]


def render_source_guidance(source_type: str) -> str:
    """Render source-aware extraction guidance from a declared source_type.

    This REPLACES the v3 'SOURCE TYPE DETECTION' heuristic section.
    Instead of guessing from text patterns, we receive the definitive source type
    and emit precise behavioral instructions.

    Backward compatible: if source_type is unknown/empty, returns neutral guidance
    that tells the model to use standard rules (no suppression).
    """
    from utils.memory_ingestion.models import SourceTypeConfig, SourceStrength

    config = SourceTypeConfig.REGISTRY.get(source_type)
    if not config:
        return (
            "Source type: UNKNOWN.\n"
            "Apply standard extraction rules. Default to conservative: "
            "when in doubt, do not extract."
        )

    parts = [f"Source type: {config.label} (signal strength: {config.strength.value})."]

    if config.strength == SourceStrength.HIGH:
        parts.append(
            "HIGH CONFIDENCE SOURCE. Extract when both conditions are met:\n"
            "  (a) clear, SPECIFIC predicate match (is_currently_true for state facts is fine)\n"
            "  (b) verbatim self-report quote anchor OR qualifying assistant_suggested quote evidence described below\n"
            "Do NOT suppress clear user claims or specific grounded assistant_suggested observations from this source."
        )
    elif config.strength == SourceStrength.MEDIUM:
        parts.append(
            "MEDIUM CONFIDENCE SOURCE (e.g., voice transcript). Extract liberally:\n"
            "  (a) clear predicate match — is_currently_true is EXPECTED and PRIMARY for biographical facts\n"
            "  (b) verbatim quote anchor\n"
            "  (c) content is substantive (not filler/chitchat)\n"
            "For voice transcripts: extract ALL distinct biographical facts (origin, visa status,\n"
            "family, health, religion, location, work arrangement). Each fact gets its own frame.\n"
            "3-6+ frames from one session is NORMAL when multiple topics are covered.\n"
            "Apply only light skepticism for garbled or sparse input."
        )
    elif config.strength == SourceStrength.LOW:
        parts.append("LOW CONFIDENCE SOURCE — extract liberally, filter in post-processing.")
        if config.requires_corroboration:
            parts.append(
                "  Prefer facts with ≥2 independent utterances, but do NOT suppress"
                " single-mention facts that are specific and verifiable."
            )
        parts.append(
            "  Extract any plausible memory-worthy fact. Prefer false positives over"
            " false negatives — the post-processing stack will deduplicate and filter."
            "  Only skip content that is pure noise/gibberish with zero factual signal."
        )
    else:
        parts.append("Apply standard extraction rules with conservative default.")

    if config.confidence_cap < 1.0:
        parts.append(f"  Confidence cap: {config.confidence_cap} for extractions from this source.")

    if config.guidance_notes:
        parts.append(config.guidance_notes)

    return "\n".join(parts)


typed_extract_memories_prompt = ChatPromptTemplate.from_messages(  # type: ignore[reportUnknownMemberType]  # langchain from_messages stub has Unknown type args
    ['''
You are an expert memory curator extracting durable, memory-worthy facts about {user_name} from a conversation, as TYPED propositions.

CRITICAL CONTEXT:
• You are extracting memories about {user_name} (the primary user recording this conversation)
• Focus on facts about {user_name} and the people {user_name} directly interacts with
• NEVER use "Speaker 0", "Speaker 1" etc. — resolve real names when confident, otherwise use roles ("colleague", "friend")
• Resolve "it", "that", "this" from the full conversation before writing the fact

SOURCE SIGNAL: {source_guidance}

This source type is DECLARED (not inferred from text). Follow the above guidance
precisely. Do NOT attempt to re-detect or second-guess the source type from text
patterns like [Speaker N:] labels or disfluencies — the signal quality is already
characterized above.

ASSISTANT-TURN ATTRIBUTION FOR CHAT SOURCES:
• human/user-authored turns are direct evidence about {user_name}.
• ai/assistant/model-authored turns are CONTEXTUAL evidence only. Extract from them
  only when they describe a SPECIFIC, PERSONALIZED, GROUNDED observation or
  recommendation about {user_name}'s current task, tool, form, setting, or situation.
• Valid assistant_suggested evidence names concrete user-specific details, e.g.
  "working on the congressional casework form for your USCIS case" or
  "set 1440x900 on your MacBook Pro".
• NEVER extract generic assistant filler as user memory: praise, encouragement,
  "back to work" nudges, "keep pushing Omi features", "what's next", app-switch
  reminders ("back to Telegram/Discord/X"), generic productivity reminders,
  name-only mentions ("Nik"), or broad guesses about what {user_name} is doing.
• Test: if the assistant sentence could be sent to any Omi user as motivation or
  a generic reminder, output [] for that sentence. If it identifies a concrete
  personal object/task/tool/setting grounded in the visible/chat context, extract
  with subject_attribution=assistant_suggested.

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
   - is_currently_true — durable state/fact with no better predicate above (use for biographical identity, ongoing states, location/residence, visa/immigration status, family relationships, health diagnoses, travel history, religion, nationality, work arrangement like WFH). This is the PRIMARY predicate for voice/transcript sources where most facts are state descriptions rather than actions. Represents ~30% of extractions for those sources.
   - is_no_longer_true — a fact that stopped holding
   - credential_detected — credentials, passwords, PII, or auth material visible on screen (OCR/security sources)
   - sensitive_info_visible — sensitive but non-credential info visible (email addresses, personal identifiers)

   Write the predicate EXACTLY as shown. Prefer the MOST SPECIFIC predicate. For voice/transcript sources, is_currently_true is expected and normal — use it freely for biographical/state facts. For chat sources, prefer action predicates when available.

1. quote_anchor — verbatim substring from transcript proving the fact. For direct {user_name} facts, prefer self-report evidence ({user_name}'s own turn or first-person language "I"/"my"/"we"). Preserve ≥2 distinctive non-stopword terms. No paraphrase. If no literal quote evidence exists → no fact.
   **ASSISTANT-SUGGESTED EXCEPTION:** For chat sources only, assistant-authored quote evidence is allowed when it is specific, personalized, and grounded in the user's visible/current context. Mark subject_attribution=assistant_suggested. Do NOT use generic assistant praise, nudges, reminders, or app-switch chatter as quote evidence.
   **OCR/security source EXCEPTION:** For credential_detected, sensitive_info_visible, and is_currently_true (when describing visible PII/passwords/credentials on screen), accept UI text fragments as evidence — a visible email address, password field, login prompt, or keychain dialog IS the evidence. No first-person language required for security-relevant OCR extractions only.

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

4. subject_attribution — "user" if fact is about {user_name} AND quote_anchor is self-report. Use "third_party" for others; use "assistant_suggested" ONLY for qualifying chat assistant-authored observations/recommendations described in the ASSISTANT-TURN ATTRIBUTION rules.

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
• Generic assistant-authored encouragement, praise, productivity nudges, app-switch reminders, or broad activity guesses rewritten as durable {user_name} facts
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
• UI/navigation chrome: menu items, button labels, notification text (EXCEPT login forms, password fields, email addresses, keychain dialogs, credential managers — those ARE extractable with credential_detected/sensitive_info_visible)
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
BUT: If the same transcript contains clear biographical facts (origin, family
status, visa, health, location, tools used, projects) → DO extract those as
is_currently_true. Only output [] when there are ZERO extractable facts.

**Example 7b — Voice transcript with multiple biographical facts (extract MULTIPLE is_currently_true)**
Input:  "[Speaker 0]: I'm from rural Russia, near Japan. Moved to Moscow later.\\n[Speaker 0]: I got an O-1 visa after applying five times.\\n[Speaker 0]: I'm Orthodox Christian, like people in Ethiopia.\\n[Speaker 0]: I work from home, no office."
Output: predicate=is_currently_true  quote="from rural Russia, near Japan"
        content="Alex is originally from rural Russia near Japan"
        arguments={{"topic": "originally from rural Russia near Japan"}}
        subject_attribution=user
---
Output: predicate=is_currently_true  quote="moved to Moscow"
        content="Alex moved to Moscow, Russia"
        arguments={{"topic": "moved to Moscow, Russia"}}
        subject_attribution=user
---
Output: predicate=is_currently_true  quote="O-1 visa"
        content="Alex has O-1 visa status"
        arguments={{"topic": "O-1 visa status"}}
        subject_attribution=user
---
Output: predicate=is_currently_true  quote="Orthodox Christian"
        content="Alex is Orthodox Christian"
        arguments={{"topic": "Orthodox Christian"}}
        subject_attribution=user
---
Output: predicate=is_currently_true  quote="work from home, no office"
        content="Alex works from home"
        arguments={{"topic": "works from home"}}
        subject_attribution=user
NOTE: Voice transcripts often contain MULTIPLE biographical facts in one session.
Extract EACH distinct fact as its own is_currently_true frame. Do NOT consolidate
different facts into one frame, and do NOT skip facts just because there are many.
Biographical identity facts, visa/status, origin, religion, family, health, and
work arrangement are ALWAYS worth extracting when clearly stated by {user_name}.
A single voice session can (and should) produce 3-6+ is_currently_true frames when
the conversation covers multiple biographical topics.

**Example 7c — Voice transcript with family/health biographical facts (extract is_currently_true)**
Input:  "[Speaker 0]: My father was diagnosed with cancer last month.\\n[Speaker 0]: I have a paternal half-brother — my dad recently had a baby.\\n[Speaker 0]: I've been on a green card for about 2 years now."
Output: predicate=is_currently_true  quote="father was diagnosed with cancer"
        content="Alex's father was diagnosed with cancer"
        arguments={{"topic": "father diagnosed with cancer"}}
        subject_attribution=user
        importance=high
---
Output: predicate=is_currently_true  quote="paternal half-brother"
        content="Alex has a paternal half-brother (father recently had baby)"
        arguments={{"topic": "has paternal half-brother"}}
        subject_attribution=user
---
Output: predicate=is_currently_true  quote="green card for about 2 years"
        content="Alex has been pursuing green card process for approximately 2 years"
        arguments={{"topic": "pursuing green card process"}}
        subject_attribution=user
NOTE: Family relationships and health diagnoses are HIGH-VALUE biographical facts.
Always extract these with is_currently_true when {user_name} states them explicitly,
even from voice transcripts. Set importance=high for serious health diagnoses
(family or self). These facts are exactly what is_currently_true is designed for.

**Example 8 — OCR screenshot showing UI chrome / product page with NO credentials (output EMPTY list)**
Input:  "••• tDo (a Chat * What's up next, Nik? + Nv*sesslon\nCustOTlliZe ••• Retard-12608921"
Output: []
NOTE: Fragmented/garbled OCR text, UI navigation elements, and transient screen
content are not durable facts about {user_name}. Screenshots capture momentary
state, not memory-worthy information. Unless OCR contains a clear self-reported
fact (name, address, preference) in coherent text → output [].
**BUT: If OCR shows passwords, email addresses, login prompts, keychain dialogs,
credential fields, or other security-sensitive material visible on screen →
EXTRACT with credential_detected or sensitive_info_visible. See Example 11.**

**Example 9 — Work chatter that SOUNDS factual but is NOT durable (output EMPTY list)**
Input:  "[Speaker 0]: We're committing to hire 10 engineers this quarter, "
        "and I'm going to lead the Omi wearable to GPT integration. "
        "[Speaker 0]: The goal is full-time offers for all interns by September."
Output: []
NOTE: Work discussions contain action verbs ('committing', 'lead', 'goal') that
MIMIC durable fact patterns. These are NOT memory-worthy because:
  (a) They describe team/company objectives, not {user_name}'s personal facts
  (b) They lack the specificity of a personal preference, relationship, or biographical detail
  (c) They are context-bound to a specific work project/quarter
Even with SPECIFIC numbers (10 engineers, September) and ACTION verbs (commit, lead)
  → output [] if the fact is about work deliverables, not {user_name} personally.
The key test: "Will this still be a true fact about ME in 6 months?" If no → skip.

KEY PATTERN: Short statements CAN be memory-worthy IF they contain a SPECIFIC
predicate match (is_currently_true is PERFECTLY VALID for voice biographical facts),
a verbatim self-report quote anchor, AND represent a non-obvious durable fact.
Generic observations, mood statements, activity mentions, or scheduling chatter —
even with quote anchors — should still be skipped. When in doubt for voice transcripts
with biographical content → extract (don't suppress). When in doubt for trivial chatter
→ skip.

**Example 10 — Casual chat with first-person commitment (extract committed_to_do)**
Input:  "human: Can you make me a snake game, and just, like, launch it once done?\nhuman: Yo, yo. How's going?\nai: Your trial has ended."
Output: predicate=committed_to_do  quote="make me a snake game, and just, like, launch it once done"
        content="David committed to making a snake game and launching it when done"
        arguments={{\"action\": \"make a snake game and launch it\"}}
        subject_attribution=user
NOTE: Chat exchanges often bury commitments in casual, chatty language ('make me',
'like', 'yo'). A first-person action request IS a commitment even when surrounded
by filler. Extract when {user_name} explicitly requests or commits to an action,
regardless of how casual the surrounding chat is. Skip the greeting/filler turns
('Yo', 'How's going') — only extract the substantive turn.

**Example 10a — Assistant-only generic Omi nudge (output EMPTY list)**
Input:  "ai: Solid progress today, Nik. Keep pushing those Omi features forward — your task list is waiting."
Output: []
NOTE: Generic assistant praise, encouragement, and productivity nudges are NOT
source evidence for durable facts. Do not extract works_on(Omi), uses_tool(task list),
or name facts from assistant motivational filler.

**Example 10a.2 — Assistant-only app switch reminder (output EMPTY list)**
Input:  "ai: Back to Telegram, Nik — looks like you still have Omi messages to handle."
Output: []
NOTE: App-switch reminders and broad guesses about current activity are not durable
memories. Do not extract uses_tool(Telegram), works_on(Omi), or name facts unless
{user_name}'s own turn or a specific grounded assistant observation supports them.

**Example 10a.3 — Assistant-only browsing/activity chatter (output EMPTY list)**
Input:  "ai: Looks like you're browsing movies, Nik. Want to get back to what matters?"
Output: []
NOTE: Assistant observations about transient browsing, generic refocus prompts, or
name-only mentions are not memory-worthy. Output [] unless the assistant identifies
a concrete personal task/tool/setting like a form, credential screen, or specific
user-requested configuration.

**Example 10b — AI-observed user activity from chat context (extract with assistant_suggested)**
Input:  "human: Yo yo yo. can i help you?\nai: haha I think you meant to ask *me* if I can help *you* 😄\n\nlooks like you're working on the congressional casework form for your USCIS case — filling it out on Velázquez's site. need help with anything specific on that?"
Output: predicate=works_on  quote="working on the congressional casework form for your USCIS case"
        content="David works on congressional casework form for USCIS case"
        arguments={{\"project\": "congressional casework form for USCIS case"}}
        subject_attribution=assistant_suggested
NOTE: When the AI assistant observes {user_name} doing something specific and
personally meaningful (NOT generic work chatter, praise, or refocus reminders),
extract it with subject_attribution=assistant_suggested. The key distinction:
  - ✅ EXTRACT: "looks like you're working on [specific personal form/case/task]" → works_on
  - ✅ EXTRACT: "for your MacBook Pro, set [specific setting]" → prefers/uses_tool
  - ❌ SKIP: "back to Telegram/Discord/X", "keep pushing Omi", "good job debugging" → generic assistant chatter
  - ❌ SKIP: "looks like you're browsing movies" → transient activity
The observation must name a SPECIFIC personal object/task/tool setting, not a vague
work summary, app reminder, or motivational line. Personal administrative tasks
(forms, cases, applications) ARE extractable.

**Example 10c — First-person tool usage mentioned casually in chat (extract uses_tool)**
Input:  "human: Omi, я вот играю в Rust, и короче у меня вот типа видишь, вот такой вот туман типа.\nai: Это TAA + depth of field в Rust."
Output: predicate=uses_tool  quote="играю в Rust"
        content="David uses Rust (video game)"
        arguments={{\\"tool\\": \\"Rust (video game)\\"}}
        subject_attribution=user
NOTE: First-person statements about tools/games/apps in ANY language (including
non-English) are extractable. Look for \"{user_name} plays/uses/играет в [tool]\"
patterns even when buried in troubleshooting or casual chat. The language of
the input doesn't matter — extract the fact if the semantic signal is clear.
Profanity and informal language surrounding the fact do NOT invalidate extraction.

**Example 10d — AI-observed user preference from chat (extract prefers, attr=assistant_suggested)**
Input:  "human: У меня MacBook, какой? Pro, нахуй, который, типа, сколько там? 14 дюймов? Вот. Какое мне resolution ставить?\nai: MacBook Pro 14\" — нативное 3024x1964. Из того что видишь в списке — ставь **1440x900**, это самое близкое к нормальному соотношению сторон."
Output: predicate=uses_tool  quote="У меня MacBook, какой? Pro"
        content="David uses a MacBook Pro 14-inch"
        arguments={{\\"tool\\": \\"MacBook Pro 14-inch\\"}}
        subject_attribution=user
---
Output: predicate=prefers  quote="ставь 1440x900"
        content="David prefers 1440x900 screen resolution for gaming"
        arguments={{\\"preference\\": \\"1440x900 screen resolution\\", \\"context\\": \\"gaming on MacBook Pro\\"}}
        subject_attribution=assistant_suggested
NOTE: When the chat contains MULTIPLE extractable facts (device ownership +
a specific setting/preference), extract EACH as a separate frame. The AI's
recommendation about a specific setting value IS extractable as a preference
(assistant_suggested) when it's a personalized response to {user_name}'s question.
Device ownership comes from {user_name}'s own words; preferences can come from
either speaker when they're specific to {user_name}'s situation.

**Example 10e — Multi-fact chat with commitment + biographical state (extract BOTH)**
Input:  "human: I need to change my company interest to receive email on this that i have been stable, which you currently can see on my screen. can you do all these 13 actions, basically, and make sure that my address is updated everywhere?\nhuman: hi"
Output: predicate=committed_to_do  quote="make sure that my address is updated everywhere"
        content="David committed to updating address everywhere across multiple services"
        arguments={{\\"action\\": \\"update address everywhere across multiple services\\"}}
        subject_attribution=user
---
Output: predicate=is_currently_true  quote="i have been stable"
        content="David has been stable at current company"
        arguments={{\\"topic\\": \\"stable at current company\\"}}
        subject_attribution=user
NOTE: Long chat messages often contain MULTIPLE facts buried together. Extract
EACH distinct fact separately: action commitments get committed_to_do, durable
state facts get is_currently_true. Don't stop after extracting the most obvious
fact — scan the entire message for all extractable signals.

**Example 11 — OCR screenshot with visible credentials / security material (EXTRACT)**
Output: predicate=sensitive_info_visible  quote="kodjirna33@gmail.com"
        content="Nikita Shevchenko's email address (kodjirna33@gmail.com) is visible on screen"
        subject_attribution=user
NOTE: OCR screenshots that show email addresses, login fields, password prompts,
keychain dialogs, API keys, or other security-sensitive material ARE memory-worthy.
These represent credential/PII exposure events that should be recorded even though
the source is OCR (low signal). Use credential_detected for passwords/auth material,
sensitive_info_visible for emails/personal identifiers. The visible UI text itself
serves as evidence — no first-person quote needed for security-relevant OCR extractions.

**Example 12 — Garbled OCR with keychain/password dialog (EXTRACT credential_detected)**
Input:  "curltywantsto useyour confSdentlDI\nInformation stored In-Chrorne Safe Stornp- In\nyour keyohaln.\nTo allow this, 8nt•rth8 4login' k•ychain password.\nPa5wmrd..\nAW MIow\nDery\nIr*W"
Output: predicate=credential_detected  quote="keychain password"
        content="Password field or keychain credential prompt is visible on screen"
        subject_attribution=user
NOTE: Even heavily garbled OCR text that contains 'password', 'keychain', 'login',
'credential', or masked characters (•••, ****) indicates a security-sensitive
screen. ALWAYS extract these — do not return [] just because text is garbled.
The presence of ANY security keyword in OCR overrides the garbled-text → [] rule.

**Example 13 — Garbled OCR with encryption password / SSH credentials (EXTRACT)**
Input:  "Enteryour encryption password\nkodjima33@gm8il.¢om\nEneryptAMV&&WQ\nContinu•\nForgot pAssword?\n*****\nV8uIts\nsThp\nHosts\nmacos\nkodjimB33"
Output: predicate=credential_detected  quote="encryption password"
        content="Encryption password or SSH credential material is visible on screen (Termius context)"
        arguments={{"topic": "Termius encryption password / SSH credentials"}}
        subject_attribution=user
NOTE: SSH clients (Termius), terminal hosts, and encryption setup screens showing
passwords, hostnames, or usernames are credential extraction targets. Even when
the email/hostname is OCR-garbled (gm8il.¢om instead of gmail.com), the STRUCTURE
(email@domain format + 'encryption password' label) is enough to extract.

**Example 14 — Garbled OCR with sign-in page / email field (EXTRACT sensitive_info_visible)**
Input:  "hatGPT\nChatGPT\nSlgnln-C\nChatGPT\n+ Ask G¢mlnl\nch8tgpt.com\nClaudè Ik4CPI\nExlensions\nnl Nule5\nTTF\nRec"
Output: predicate=sensitive_info_visible  quote="Sign in"
        content="Login or sign-in page with email address field is visible on screen"
        subject_attribution=user
uncertainty_reasons=[low_quality_transcript]
NOTE: Sign-in pages, login forms, and authentication UI elements visible in
screenshots are extractable even from noisy OCR. Use sensitive_info_visible
for login/sign-in contexts where an email or identifier may be present but
is too garbled to read precisely.

=== SUBJECT DISEMBIGUATION GUARD ===

CRITICAL for reducing hallucination: When the input mentions another person by
name or role (Sam, Maria, Alex, Dr. Lee, "my manager", "my friend", etc.),
check WHO the fact is about before extracting:

**DO extract as subject=user (self-report):**
|- "I had coffee with Maria" → knows_person(Maria) [user is subject]
|- "My manager asked me to submit the plan" → committed_to_do(submit plan)
  [action is on user, even if triggered by someone else]
|- "I prefer oat milk" → prefers(oat milk) [clear first-person]

**DO NOT extract as subject=user (fact is about someone else):**
|- "Sam is moving offices" → SKIP or subject_attribution=third_party
  [Sam is the grammatical subject, not user]
|- "My friend prefers tea over coffee" → SKIP or subject_attribution=third_party
  [friend is the one with the preference]
|- "Alex said he'll handle the review" → SKIP
  [Alex's commitment, not user's]

**VOICE TRANSCRIPT MULTI-SPEAKER RULE — VIOLATION = HALLUCINATION:**
When input contains multiple speakers (SPEAKER 0, SPEAKER 1, SPEAKER 2, etc.),
ONLY extract facts where {user_name} (SPEAKER 0 / primary speaker) is the explicit subject.
Facts about other speakers' preferences, tools, work, or plans are NOT about {user_name}
→ output [] for those. A transcript mentioning "SPEAKER 2 uses Chrome" tells you nothing
about {user_name} → SKIP entirely.

⚠️ EXTRACTING A SPEAKER_N FACT AS IF IT WERE ABOUT {user_name} IS A HALLUCINATION.
This is the #1 source of voice FPs. Every time you extract a fact about SPEAKER 1/2/3+
and attribute it to {user_name}, you are hallucinating. When you see another speaker's
name/role as the grammatical subject, that fact is NOT about {user_name}. No exceptions.
If 100% of facts in a transcript are about other speakers → output [] for the entire transcript.

**Rule of thumb:** If you can rephrase the sentence as "{user_name} [verb]..."
and it means the same thing → subject=user. If the named person is the one
doing/being/having something → NOT about {user_name} → skip or third_party.
When in doubt about subject attribution, use third_party + add
uncertainty_reason=subject_ambiguous and set confidence ≤ 0.7.


=== PREDICATE DISAMBIGUATION RULES ===

Pick the MOST SPECIFIC predicate. Common mis-mappings that cause errors:

• "founder / creator / co-founder of X" → knows_person(person=X), NOT works_on.
  [Founding a relationship, not working on a project]
• "uses / owns / has a [device]" (MacBook, iPhone, monitor) → uses_tool, NOT is_currently_true.
  [Device ownership is a tool-use fact, not a generic state]
• "leading / heading X project" → works_on(X), NOT knows_person.
  [Project leadership = working on the project]
• "meeting with / talking to [person]" → knows_person if relationship context, else SKIP.
  [One-time meetings without enduring relationship context are not memory-worthy]
• "going to / traveling to [place]" → plans_travel_to, NOT is_currently_true.
  [Travel plans have their own predicate — do NOT degrade to is_currently_true]

When two predicates could fit, ALWAYS pick the more specific one. is_currently_true
is the PRIMARY predicate for voice/transcript sources (expected ~30% of extractions).
For chat sources, prefer action predicates. is_currently_true is correct and expected
for: biographical facts (origin, nationality, religion), visa/immigration status,
residence/location, family relationships, health conditions, work arrangements (WFH),
travel history, and any durable state that doesn't fit a more specific action predicate.
Do NOT degrade travel plans or device ownership to is_currently_true — those have
their own predicates. But for everything else that is a state rather than an action,
is_currently_true is the RIGHT choice, not a last resort.


=== EXTRACTION CONSOLIDATION RULE ===

ONE factual statement = ONE frame maximum. Never split one fact into multiple frames:
• ❌ "Applying for green card" → 3 separate frames (application, card, status)
• ✅ "Applying for green card" → 1 frame with the complete thought
• ❌ "Committed to $100K ARR by June" → 2 frames ($100K ARR, June deadline)
• ✅ "Committed to $100K ARR by June" → 1 frame with full commitment

EXCEPTION for voice transcripts: Different biographical facts SHOULD be separate
frames. "I'm from Russia. I have an O-1 visa. My father has cancer." → 3 frames,
not 1. Each distinct topic (origin, visa, family health) deserves its own frame.
Only consolidate when the SAME fact is stated multiple ways.

If you find yourself extracting 10+ frames from a single short transcript,
review whether some are trivial. But 3-6 is_currently_true frames from a rich
voice conversation covering multiple biographical topics is NORMAL and EXPECTED.
Prefer complete coverage of distinct facts over aggressive consolidation.


UNIVERSAL RULES (all sources):
• Each fact must be DURABLE (still true in 6 months) and NON-OBVIOUS
• Never extract greetings, pure backchannel, or question-only input
• HIGH signal sources (chat, conversation): Do NOT suppress clear user claims
• LOW signal sources (ambient voice, OCR): Default to [] UNLESS the content contains credentials, PII, passwords, email addresses, login fields, or other security-sensitive material visible on screen — extract those with credential_detected or sensitive_info_visible
• ⚠️ OCR SECURITY OVERRIDE: For screenshot_ocr source, if ANY security pattern is present (password, keychain, login, sign-in, email@domain, ••• masking, credential manager, SSH host/username, encryption password, [SECURITY_OCR_ALERT] marker), you MUST extract. The garbled text quality is NOT a valid reason to return [] for security-sensitive OCR. This rule takes priority over Example 8's "garbled → []" guidance.

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
'''.replace(' ', '').strip()]
)
