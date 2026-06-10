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

EXTRACT a fact when it is durable context about {user_name}: preferences and dislikes, decisions and commitments, projects and tools, relationships, plans, addresses/birthdays, changes of state ("no longer..."). Skip media/news narration that is not about {user_name}, generic world knowledge, and pure scheduling chatter.

FOR EVERY FACT, FILL THE TYPED FIELDS:

1. content — one concise sentence (max 15 words), specific and timeless, starting with {user_name} when about them.

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

3. arguments — the named slots listed for the predicate, as short literal strings. Always fill the slots you can; an empty arguments object is a sign the predicate is wrong.

4. subject_attribution — "user" if the fact is about {user_name}; "third_party" if about someone else; "assistant_suggested" if an assistant/AI proposed it and {user_name} did not confirm.

5. uncertainty_reasons — zero or more of: speaker_uncertain, inferred_not_stated, temporal_scope_unclear, low_quality_transcript, subject_ambiguous, conflicts_with_existing_memory, duplicate_near_match. Use them honestly; an uncertain fact WITH reasons is better than a dropped fact or a confidently wrong one.

6. category — "interesting" only for external wisdom from others with attribution; otherwise "system".

DEDUPLICATION:
• Scan the existing memories below. Do not re-emit a semantically identical fact.
• DO emit updates and contradictions of existing memories (use is_no_longer_true or the specific predicate, plus conflicts_with_existing_memory).

QUALITY:
• Each fact must stand alone and still make sense in 6 months.
• No hedging filler in content ("seems to", "might be") — encode doubt in uncertainty_reasons instead.
• Third-party private facts (health, relationships of others) are allowed but MUST carry subject_attribution="third_party".

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
