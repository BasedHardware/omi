"""Typed memory extraction prompt for benchmark / layered-pipeline runs.

The production prompt asks for free-text memories only, so every frame arrives
keyless (generic ``related_to`` with no structured arguments) and the layer-2
typed consolidation resolver has nothing to merge on. This prompt asks the
same single call to also emit a typed proposition: a predicate from a fixed
vocabulary plus named argument slots. It does not add model calls.
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

IDENTITY RULES (CRITICAL):
• Never create new family members without EXPLICIT evidence ("This is my daughter Sarah", "My son's name is...")
• Recognize nicknames — don't create new people (common nicknames like "Buddy", "Junior" are likely existing family members)
• Verify name spellings against existing memories before creating new entries
• Never use "User" — always use {user_name}
• If uncertain about a person's identity, DO NOT extract the memory

EXTRACT a fact when it is durable context about {user_name}: preferences and dislikes, decisions and commitments, projects and tools, relationships, plans, addresses/birthdays, changes of state ("no longer..."). Skip media/news narration that is not about {user_name}, generic world knowledge, and pure scheduling chatter.

FOR EVERY FACT, FILL THE TYPED FIELDS:

0. quote_anchor — copy the exact source sentence or clause that proves the fact into the quote_anchor field. It MUST be a verbatim substring from the transcript, not a paraphrase. For any fact about {user_name}, the quote_anchor must be self-report evidence: either {user_name}'s own speaker turn or a literal clause containing first-person language ("I", "my", "we", "our") that directly asserts the fact. The final content must preserve at least 2 distinctive non-stopword terms from that quote. If you cannot copy a literal self-report quote anchor for a user fact, output no fact.

1. content — one concise sentence (max 15 words), specific and timeless, starting with {user_name} when about them. Do not paraphrase beyond what the quote_anchor directly states.

2. predicate — EXACTLY ONE of:
   - plans_travel_to — a trip or relocation plan. arguments: destination, planned_date (if stated)
   - prefers — a stable preference. arguments: preference, over (if a comparison)
   - dislikes — a stable dislike. arguments: target
   - works_on — a project/product they actively work on. arguments: project
   - decided_to_use — a decision in favor of a tool/approach. arguments: tool, purpose
   - considering_using — an option under consideration, not decided. arguments: tool, purpose
   - committed_to_do — a concrete commitment/promise. arguments: action, due (if stated)
   - knows_person — a relationship. arguments: person, relationship, context
   - has_birthday — arguments: person, date
   - has_address — arguments: person, address_or_location
   - uses_tool — a tool/service they use routinely. arguments: tool, purpose
   - belongs_to_project — an artifact/person belongs to a project. arguments: member, project
   - is_currently_true — durable state/fact with no better predicate above. arguments: topic
   - is_no_longer_true — a fact that stopped holding (supersession/contradiction). arguments: topic, replaced_by (if stated)

   Prefer the MOST SPECIFIC predicate. Use is_currently_true only as a last resort.

3. arguments — the named slots listed for the predicate, as short literal strings. Only fill argument slots when value is EXPLICITLY stated in conversation; leave unfilled slots out entirely rather than guessing.

4. subject_attribution — "user" ONLY if the fact is about {user_name} AND the quote_anchor is self-report evidence from {user_name} (actor-authored or first-person wording). Use "third_party" if about someone else; use "assistant_suggested" if an assistant/AI/team member proposed it or if the quote lacks first-person confirmation. Facts with assistant_suggested are normally not durable memories; only emit them when needed to preserve a reviewable contradiction/update.

5. uncertainty_reasons — zero or more of: speaker_uncertain, inferred_not_stated, temporal_scope_unclear, low_quality_transcript, subject_ambiguous, conflicts_with_existing_memory, duplicate_near_match. Use them honestly; an uncertain fact WITH reasons is better than a dropped fact or a confidently wrong one.

6. category — "interesting" only for external wisdom from others with attribution; otherwise "system".

------------------------------------------------------------------------------
ANTI-HALLUCINATION GUARDRAILS
------------------------------------------------------------------------------

NEVER EXTRACT (Absolute Rules):
1. NEWS & ANNOUNCEMENTS: Product releases, acquisitions, feature launches, company news
   ❌ "Company X acquired startup Y" / "OpenAI released a new model" / "Apple announced..."

2. GENERAL KNOWLEDGE: Science facts, geography, statistics not about the user
   ❌ "Light travels at 186,000 miles per second" / "Certain plants are toxic to pets"

3. PRODUCT DOCUMENTATION: How features work, product capabilities, technical specs
   ❌ "Feature X enables automated workflows" / "The API can process documents"

4. CUSTOMER/COMPANY FACTS: Unless user is directly involved with specific outcome
   ❌ "Acme Corp is evaluating new software" / "BigCo delayed their rollout"

5. INTERNAL METRICS: Survey rates, deal sizes, percentages, team statistics
   ❌ "Team survey response rate is 83%" / "Average deal size is $30K"

6. ORG RESTRUCTURING: Team moves, role changes, temporary assignments
   ❌ "{user_name} is merging teams" / "The marketing team is moving to..."

7. COLLEAGUE FACTS WITHOUT RELATIONSHIP: Must state how they relate to user
   ❌ "Alex is a senior engineer at the company" (no relationship to user)
   ✅ "Alex reports to {user_name} and leads the backend team" (relationship stated)

8. GENERIC RELATIONSHIPS: "Has a friend named X" without meaningful context
   ❌ "{user_name} has a friend named Mike" (no context = useless)
   ✅ "Mike is {user_name}'s running partner who they train with for marathons" (specific context)

9. UNCONFIRMED OWNERSHIP / GROUP ATTRIBUTION: Do not turn group plans, team chatter, assistant suggestions, or another speaker's statement into a personal fact about {user_name} unless {user_name} explicitly confirms it in first person.
   ❌ Team says "we might use Linear" → "{user_name} uses Linear"
   ❌ Assistant says "You could try Notion" → "{user_name} uses Notion"
   ✅ {user_name} says "I decided to use Linear for roadmap planning" → extract decided_to_use

STRICT EXCLUSION RULES — DO NOT extract if memory is:

Trivial Personal Preferences:
❌ "Likes coffee" / "Enjoys reading" / "Prefers the color blue"
❌ "Went to the gym" / "Had lunch with a friend"
❌ "Watched a movie last night" / "Listened to music"

Generic Activities or Events:
❌ "Attended a meeting" / "Went to a conference"
❌ "Traveled to New York" (unless there's remarkable context)
❌ "Worked on a project" (unless specific and notable)

Common Knowledge or Obvious Facts:
❌ "Exercise is good for health"
❌ "Important to save money"
❌ "JavaScript is used for web development"
❌ "Automation saves time" / "AI needs development" / "Robots are hard to build"

Vague or Generic Statements:
❌ "Had an interesting conversation"
❌ "Learned something new"
❌ "Feeling motivated"
❌ "Expressed concern about X" / "Discussed Y" / "Mentioned Z"
❌ "Thinks X is important" / "Believes Y" / "Feels Z"

Low-Impact Observations:
❌ "It's been a busy week"
❌ "The office is crowded today"
❌ "Coffee shop was noisy"

Already Obvious from Context:
❌ "Uses a computer for work" (if user is a software engineer)
❌ "Has meetings regularly" (if user is in a corporate job)

Skills — Prefer Achievements Over Tool Lists:
✅ "{user_name} uses Python for data analysis and automation scripts" (specific use case)
✅ "{user_name} built a real-time notification system using WebSockets and Redis" (applied expertise)
❌ "{user_name} knows programming" (too vague — which languages? for what?)
❌ "{user_name} has technical skills" (meaningless without specifics)

BANNED LANGUAGE — DO NOT USE IN content:
• Hedging words: "likely", "possibly", "seems to", "appears to", "may be", "might", "maybe", "could", "perhaps"
• Filler phrases: "indicating a...", "suggesting a...", "reflecting a...", "showcasing"
• Transient verbs: "is working on", "is building", "is developing", "is testing", "is focusing on"
• Org change verbs: "is merging", "is reorganizing", "is restructuring"

If you find yourself using these words in the final content, the memory is too uncertain or transient — DO NOT extract. Exception: if {user_name} explicitly says a first-person consideration or plan ("I might switch to Raycast", "we are considering Linear", "I plan to move to Berlin"), extract it with predicate considering_using, committed_to_do, or plans_travel_to, preserve the literal quote_anchor, and put the uncertainty in uncertainty_reasons instead of the content.

DATE AND TIME HANDLING:
• NEVER use vague time references like "Thursday", "next week", "tomorrow", "Monday"
• These become meaningless after a few days and make memories useless
• Memories should be TIMELESS — they're for long-term context, not scheduling
• If conversation mentions a scheduled event with a specific time:
  - DO NOT create a memory about it (handled by action items/calendar events separately)
  - Instead, extract the timeless context: relationships, roles, preferences, facts
• Focus on "who" and "what", not "when"
• Examples:
  ✅ "Mike Johnson is head of enterprise sales"
  ✅ "Rachel prefers Google Slides for client presentations"
  ❌ "Client meeting on Thursday at 2pm" (temporal, not a memory)

LOGIC CHECK (Sanity Test):
Before extracting, verify the fact is logically possible:
• Age math: Don't claim 40 years work experience for someone who appears to be ~40
• Family consistency: Don't create children that contradict existing family structure
• Location consistency: Don't claim multiple contradictory home locations
• Career consistency: Don't claim conflicting job titles or employers simultaneously

If a fact seems mathematically impossible or contradicts existing memories, DO NOT extract.

BEFORE YOU OUTPUT — MANDATORY DOUBLE-CHECK:
For EACH fact you're about to extract, verify it does NOT match these patterns:
❌ "{user_name} expressed [feeling/opinion] about X" → DELETE THIS
❌ "{user_name} discussed X" or "talked about Y" → DELETE THIS
❌ "{user_name} mentioned that [obvious fact]" → DELETE THIS
❌ "{user_name} thinks/believes/feels X" → DELETE THIS
❌ A group/team/assistant statement rewritten as {user_name}'s personal preference, tool use, or commitment without a first-person confirmation quote → DELETE THIS
❌ Any fact whose key nouns/verbs are synonyms or inferences rather than words present in its quote anchor → DELETE THIS
❌ Any fact about {user_name} whose quote_anchor is not actor-authored and does not contain first-person confirmation language ("I", "my", "we", "our") → DELETE THIS

If a fact matches ANY of the above patterns, REMOVE it from your output.

CONSOLIDATION CHECK (Before Creating New Fact):
When you're about to extract a fact about a topic that already has existing memories:
1. CHECK: Does a fact about this topic/person already exist?
2. IF YES: Is new info significant enough to warrant separate fact, or would it fragment the topic?
3. PREFER: Fewer, richer facts over many fragmented ones about the same subject

Example — if existing memories already include:
- "{user_name} uses AWS for cloud hosting"
- "{user_name} deploys apps on AWS"

DON'T add: "{user_name} uses AWS Lambda" (fragmented, same topic)
Instead: Skip it — avoid creating more fragments about the same topic.

DEDUPLICATION:
• Scan the existing memories below. Do not re-emit a semantically identical fact.
• DO emit updates and contradictions of existing memories (use is_no_longer_true or the specific predicate, plus conflicts_with_existing_memory).
• ABSOLUTELY FORBIDDEN to add a fact if it is IDENTICAL or SEMANTICALLY REDUNDANT to an existing one.
  - Existing: "Likes coffee" → New: "Enjoys drinking coffee" ⇒ REJECT (Redundant)
• EXCEPTION FOR UPDATES / CHANGES:
  - If a new fact CONTRADICTS or UPDATES an existing one, YOU MUST ADD IT.
  - Existing: "Likes ice cream" → New: "Hates ice cream" ⇒ ADD IT (Update/Change)
  - Existing: "Works at Google" → New: "Left Google and joined OpenAI" ⇒ ADD IT (Update)

QUALITY:
• Each fact must stand alone and still make sense in 6 months.
• No hedging filler in content ("seems to", "might be") — encode doubt in uncertainty_reasons instead.
• Third-party private facts (health, relationships of others) are allowed but MUST carry subject_attribution="third_party".

OUTPUT LIMITS (These are MAXIMUMS, not targets):
• Extract AT MOST 2-3 facts total per conversation (most will have 0-2)
• Many conversations will result in 0 facts — this is NORMAL and EXPECTED
• Better to extract 0 facts than to include low-quality ones
• When in doubt, DON'T extract — be conservative and selective
• DEFAULT TO EMPTY LIST — only extract if facts are truly exceptional

QUALITY OVER QUANTITY:
• Most conversations have 0 extractable facts — this is completely fine
• If ambiguous whether something is worth extracting, choose: EMPTY LIST over low-quality facts
• Only extract facts if they're genuinely useful for future context

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
            '    ', ''
        ).strip()
    ]
)
