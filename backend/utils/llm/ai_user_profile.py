"""Backend-owned synthesis of the desktop AI user profile.

Desktop clients used to carry both prompt stages themselves and run them through
Anthropic Haiku chat completions. The prompts, the model, the two-stage flow and the
character cap now live here, behind ``get_llm('memories')``, so Mac and Windows produce
the same document from the same routing.

Inspired by the ContextAgent paper (arXiv:2505.14668): a once-daily, LLM-synthesized
"what we know about this user" document injected as grounding context into other AI
pipelines — not a raw memories list.
"""

from typing import Any, List, Optional, cast

from pydantic import BaseModel, Field

from utils.llm.usage_tracker import Features, track_usage
from .clients import get_llm
import logging

logger = logging.getLogger(__name__)

# Hard safety-truncate cap on a synthesized profile. The prompts ask for <2000 chars;
# the enforced ceiling is generous so a slight overshoot is not cut mid-sentence.
MAX_PROFILE_CHARS = 10_000

MAX_LINES_PER_SOURCE = 500
MAX_LINE_CHARS = 1_000
MAX_PAST_PROFILES = 5

SOURCE_ORDER = ('memories', 'tasks', 'goals', 'conversations', 'messages')

_SOURCE_HEADERS = {
    'memories': 'Memories about the user',
    'tasks': 'Recent tasks',
    'goals': 'Active goals',
    'conversations': 'Recent conversations (past 7 days)',
    'messages': 'Recent AI chat messages',
}

_STAGE1_SYSTEM_PROMPT = """You are generating a structured user profile that will be injected as context into AI pipelines (task extraction, goal extraction, memory extraction) that analyze the user's screen and audio activity.

OUTPUT FORMAT:
- A flat list of factual statements, one per line, prefixed with "- "
- Each statement must be a concrete fact directly supported by the provided data
- No prose, no paragraphs, no headers, no markdown formatting
- No adjectives like "passionate", "dedicated", "impressive"
- Write in third person ("User works at...", not "You work at...")

WHAT TO INCLUDE (only if clearly supported by the data):
- Full name, role, company, industry
- Current projects and what tools/apps they use for each
- Key people they interact with (names, roles, relationship)
- Active goals and their progress
- Recurring meetings, deadlines, routines
- Communication platforms they use (Slack, email, iMessage, etc.)
- Technical stack, programming languages, frameworks
- Topics they frequently discuss or research
- Pending tasks and commitments to others
- Time zone, work schedule patterns

CRITICAL RULES:
- ONLY include facts that are directly evidenced in the provided data
- If a category has no supporting data, skip it entirely — do not guess or infer
- Do NOT hallucinate names, roles, companies, or relationships not present in the data
- Do NOT add personality descriptions or subjective assessments
- When uncertain, omit rather than speculate
- NEVER fabricate email addresses, phone numbers, URLs, or contact information
- If you cannot find a piece of information verbatim in the data, do not include it

The output MUST be under 2000 characters total."""

_STAGE2_SYSTEM_PROMPT = """You are merging a newly generated user profile with historical profiles to create one holistic, up-to-date user profile. This profile is injected as context into AI pipelines (task extraction, goal extraction, memory extraction) that analyze the user's screen and audio activity.

OUTPUT FORMAT:
- A flat list of factual statements, one per line, prefixed with "- "
- Each statement must be a concrete fact
- No prose, no paragraphs, no headers, no markdown formatting
- No adjectives or subjective assessments
- Write in third person

MERGE RULES:
- The NEW profile reflects today's data and takes priority for current state
- Past profiles provide historical context — retain facts that are still relevant
- If a fact from the past contradicts the new profile, use the new one
- Remove outdated information (completed tasks, past deadlines, old routines)
- Keep stable facts (name, role, company, key relationships, tech stack)
- Accumulate knowledge: if past profiles mention people, projects, or patterns not in today's data, keep them if they seem ongoing
- Do NOT hallucinate — only include facts present in the provided profiles
- Do NOT add commentary about changes or evolution over time

The output MUST be under 2000 characters total."""

_STAGE1_USER_PREAMBLE = """Generate a factual user profile from the following data. Output a flat list of concrete facts (one per line, prefixed with "- "). This profile will be used as context for AI pipelines that analyze the user's screen and audio activity to extract tasks, goals, and memories. Focus on facts that help identify who is who, what projects are active, and what the user's current priorities are. Under 2000 characters."""

_STAGE2_USER_PREAMBLE = """Merge the following into one holistic user profile. Under 2000 characters."""


class ProfileSources(BaseModel):
    memories: List[str] = Field(default_factory=list)
    tasks: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    conversations: List[str] = Field(default_factory=list)
    messages: List[str] = Field(default_factory=list)

    def cleaned(self) -> "ProfileSources":
        def clean(lines: List[str]) -> List[str]:
            return [line.strip()[:MAX_LINE_CHARS] for line in lines if line.strip()][:MAX_LINES_PER_SOURCE]

        return ProfileSources(
            memories=clean(self.memories),
            tasks=clean(self.tasks),
            goals=clean(self.goals),
            conversations=clean(self.conversations),
            messages=clean(self.messages),
        )

    def lines_for(self, source: str) -> List[str]:
        return cast(List[str], getattr(self, source))

    def total_items(self) -> int:
        return sum(len(self.lines_for(source)) for source in SOURCE_ORDER)

    def used_source_names(self) -> List[str]:
        return [source for source in SOURCE_ORDER if self.lines_for(source)]


class ProfileSynthesis(BaseModel):
    profile_text: str
    data_sources_used: List[str]
    item_count: int


def _stage1_user_prompt(sources: ProfileSources) -> str:
    sections = [
        f"## {_SOURCE_HEADERS[source]}\n" + "\n".join(sources.lines_for(source))
        for source in SOURCE_ORDER
        if sources.lines_for(source)
    ]
    return f"{_STAGE1_USER_PREAMBLE}\n\n" + "\n\n".join(sections)


def _stage2_user_prompt(fresh_profile: str, past_profiles: List[str]) -> str:
    past_section = "\n\n".join(f"--- Profile {i + 1} ---\n{text}" for i, text in enumerate(past_profiles))
    return (
        f"{_STAGE2_USER_PREAMBLE}\n\n"
        "=== NEW PROFILE (generated today from latest data) ===\n"
        f"{fresh_profile}\n\n"
        "=== PAST PROFILES (oldest to newest, up to 5) ===\n"
        f"{past_section}"
    )


def _invoke(uid: str, system_prompt: str, user_prompt: str) -> str:
    with track_usage(uid, Features.MEMORIES):
        response = get_llm('memories').invoke([("system", system_prompt), ("human", user_prompt)])
    return cast(str, cast(Any, response).content or "").strip()


def enforce_char_cap(text: str, cap: int = MAX_PROFILE_CHARS) -> str:
    if len(text) <= cap:
        return text
    return text[:cap].rstrip()


def synthesize_ai_user_profile(
    uid: str,
    sources: ProfileSources,
    *,
    past_profiles: Optional[List[str]] = None,
) -> Optional[ProfileSynthesis]:
    """Two-stage AI user profile synthesis through get_llm('memories') (OpenRouter Luna).

    Stage 1 synthesizes today's profile from the raw source lines; stage 2 consolidates it
    with up to five past profiles (oldest first) so knowledge accumulates. Returns ``None``
    when the model call fails or returns nothing, so callers keep the previous profile
    rather than storing an empty one.
    """
    cleaned = sources.cleaned()
    item_count = cleaned.total_items()
    if item_count == 0:
        return None

    past = [p.strip() for p in (past_profiles or []) if p.strip()][:MAX_PAST_PROFILES]

    try:
        profile_text = _invoke(uid, _STAGE1_SYSTEM_PROMPT, _stage1_user_prompt(cleaned))
        if not profile_text:
            logger.error("AI user profile stage 1 returned empty content for uid=%s", uid)
            return None
        if past:
            consolidated = _invoke(uid, _STAGE2_SYSTEM_PROMPT, _stage2_user_prompt(profile_text, past))
            if consolidated:
                profile_text = consolidated
            else:
                logger.warning("AI user profile stage 2 returned empty content for uid=%s; keeping stage 1", uid)
    except Exception:
        logger.exception("Error synthesizing AI user profile for uid=%s", uid)
        return None

    return ProfileSynthesis(
        profile_text=enforce_char_cap(profile_text),
        data_sources_used=cleaned.used_source_names(),
        item_count=item_count,
    )
