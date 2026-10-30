"""A tiny local model that rewrites a ``propose_message`` draft in the user's own words.

``user_voice.profile_prompt_block`` steers the big chat model toward the user's voice,
and ``polish_draft`` fixes marks in code, but the wording stays an assistant's ("I've
arrived" where the user writes "im here!"). This stage hands the finished draft, the
user's own past texts to that person and what that person just said to a small model
(Qwen3-0.6B, optionally with a LoRA adapter trained on the user's own sent messages)
that rewrites the words only. A code guard then refuses any rewrite that changes the
meaning -- a number, link, name or negation that is lost or added, a different
language, a length far from the draft -- and the draft goes out as before.

Where it runs: an OpenAI-compatible chat endpoint the operator configures
(``USER_VOICE_REPHRASER_URL``, e.g. ``mlx_lm.server`` or ``llama-server`` on the
user's own machine). Unset means off: no call, the draft is only polished. The engine
gets one short request with a hard timeout and fails open.

Measured on one real user's held-out texts (``backend/evals/user_voice/README.md``).
"""

import logging
import os
import re
from typing import Callable, Iterable, Optional

import httpx
from pydantic import BaseModel, Field

from utils.llm.user_voice import (
    UserVoiceProfile,
    _clean,
    _dominant_script,
    pick_shots,
    polish_draft,
)

logger = logging.getLogger(__name__)

REPHRASER_URL_ENV = 'USER_VOICE_REPHRASER_URL'
REPHRASER_MODEL_ENV = 'USER_VOICE_REPHRASER_MODEL'
REPHRASER_TIMEOUT_SECONDS = 4.0
REPHRASER_MAX_TOKENS = 80
REPHRASER_EXAMPLES = 8
REPHRASER_MAX_DRAFT_CHARS = 300
# A rewrite outside this share of the draft's length is a different message.
MIN_LENGTH_RATIO = 0.2
MAX_LENGTH_RATIO = 2.5
COPY_MIN_CHARS = 25

SYSTEM = (
    "Rewrite the draft so it reads like the user texting this person. Keep the meaning, names and numbers; "
    "change only the wording, length, punctuation and casing."
)


class RephraseResult(BaseModel):
    text: str
    engine: str = 'none'  # 'none' | 'local'
    rejected: Optional[str] = None
    # Set only when the engine failed (timeout, HTTP, parse); a guard refusal is not a failure.
    engine_error: Optional[str] = None
    changes: list[str] = Field(default_factory=list)


def _examples(profile: UserVoiceProfile, incoming: str) -> list[str]:
    """The user's replies closest to what they just said, then the newest lines."""
    picked = [e.me for e in pick_shots(profile, incoming, k=REPHRASER_EXAMPLES // 2)]
    for line in reversed(profile.examples):
        if len(picked) >= REPHRASER_EXAMPLES:
            break
        if line not in picked:
            picked.append(line)
    return picked[:REPHRASER_EXAMPLES]


def rephrase_messages(profile: UserVoiceProfile, draft: str, incoming: str = '') -> list[dict]:
    """The chat request for the rephraser; the same shape the adapter was trained on."""
    shown = '\n'.join('- ' + _clean(e) for e in _examples(profile, incoming))
    phrases = ('\nPhrases the user often uses: ' + ', '.join(profile.phrases)) if profile.phrases else ''
    user = (
        f"The user's past texts to this person:\n{shown}{phrases}\n"
        f"They said: {_clean(incoming)[-300:]}\nDraft: {draft}\nRewrite:"
    )
    return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]


# ---------------------------------------------------------------------------
# The meaning guard (pure)
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r'\d+(?:[:.,]\d+)*')
_URL_RE = re.compile(r'https?://\S+')
_NEGATION_RE = re.compile(
    r"\b(not|no|nope|never|nothing|nobody|cannot|cant|wont|dont|didnt|isnt|arent|wasnt|doesnt|havent)\b|n['’]t\b|[不没别]",
    re.I,
)
_NAME_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{1,}(?:'s)?)\b")
_NOT_NAMES = frozenset({'I', "I'm", "I'll", "I've", 'OK', 'Ok', 'Omg', 'Lol'})


def _names(text: str, known: Iterable[str] = ()) -> set[str]:
    found = {m.group(1).removesuffix("'s") for m in _NAME_RE.finditer(text)}
    return {n.casefold() for n in found if n not in _NOT_NAMES} | {k.casefold() for k in known if k and k in text}


def _clean_output(text: str) -> str:
    text = re.sub(r'<think>.*?</think>', '', text or '', flags=re.S).strip()
    text = re.sub(r'^(rewrite|rewritten|message)\s*:\s*', '', text, flags=re.I).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"“”\'':
        text = text[1:-1].strip()
    return text


# A small model at temperature 0 can loop: "Omgggg..." x60, "the journal of the journal", "放洗衣篮放洗衣篮".
_LONG_RUN_RE = re.compile(r'(.)\1{9,}')
_LOOP_RE = re.compile(r'\b(\w+(?:\s+\w+)+)\s+\1\b|([\u3400-\u9fff]{3,})\2')
_ECHO_RE = re.compile(r'\b(\w+) of the \1\b', re.I)


def _repeats(text: str) -> bool:
    """A loop, not a laugh: "哈哈哈哈" and "hahaha" stay; a repeated phrase or a 10+ letter run does not."""
    loops = any(len(set(m.group(1) or m.group(2))) > 1 for m in _LOOP_RE.finditer(text))
    return bool(_LONG_RUN_RE.search(text) or loops or _ECHO_RE.search(text))


def _key(text: str) -> str:
    return re.sub(r'[\W_]+', '', text.casefold())


def guard(draft: str, candidate: str, people: Iterable[str] = (), shown: Iterable[str] = ()) -> Optional[str]:
    """Why the rewrite must not replace the draft, or None when it keeps the meaning.

    ``shown`` are the user's past lines the rephraser saw: a small model sometimes
    answers with one of them instead of rewriting the draft (longer lines only).
    """
    if not candidate.strip():
        return 'empty'
    # Short stock replies ("okk im here") are often exactly what the user sends again.
    if (
        len(candidate) > COPY_MIN_CHARS
        and _key(candidate) != _key(draft)
        and _key(candidate) in {_key(s) for s in shown}
    ):
        return 'copied a past line'
    if '\n' in candidate.strip() and '\n' not in draft.strip():
        return 'extra lines'
    if _repeats(candidate) and not _repeats(draft):
        return 'repeats itself'
    ratio = len(candidate) / max(len(draft), 1)
    if ratio < MIN_LENGTH_RATIO or ratio > MAX_LENGTH_RATIO:
        return f'length x{ratio:.1f}'
    if sorted(_NUMBER_RE.findall(draft)) != sorted(_NUMBER_RE.findall(candidate)):
        return 'numbers changed'
    if set(_URL_RE.findall(draft)) != set(_URL_RE.findall(candidate)):
        return 'link changed'
    if bool(_NEGATION_RE.search(draft)) != bool(_NEGATION_RE.search(candidate)):
        return 'negation changed'
    lost = _names(draft, people) - {w.casefold() for w in re.findall(r"[^\W\d_]+", candidate)}
    if lost:
        return 'name dropped'
    added = _names(candidate, people) - {w.casefold() for w in re.findall(r"[^\W\d_]+", draft)}
    if added:
        return 'name added'
    a, b = _dominant_script(draft), _dominant_script(candidate)
    if a and b and a != b:
        return 'language changed'
    return None


# ---------------------------------------------------------------------------
# The engine seam
# ---------------------------------------------------------------------------

Complete = Callable[[list[dict]], str]


def configured() -> bool:
    return bool(os.getenv(REPHRASER_URL_ENV))


def _local_server_complete(messages: list[dict]) -> str:
    """One chat completion from the operator's OpenAI-compatible endpoint."""
    url = os.environ[REPHRASER_URL_ENV].rstrip('/') + '/chat/completions'
    body = {
        # mlx_lm.server applies its --adapter-path only to 'default_model'; naming the model loads it bare.
        'model': os.getenv(REPHRASER_MODEL_ENV, 'default_model'),
        'messages': messages,
        'max_tokens': REPHRASER_MAX_TOKENS,
        'temperature': 0,
        # Qwen3 hybrid models: answer directly.
        'chat_template_kwargs': {'enable_thinking': False},
    }
    response = httpx.post(url, json=body, timeout=REPHRASER_TIMEOUT_SECONDS, follow_redirects=False)
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']


def rephrase_draft(
    draft: str,
    profile: Optional[UserVoiceProfile],
    incoming: str = '',
    *,
    complete: Optional[Complete] = None,
) -> RephraseResult:
    """Rewrite the draft in the user's words when a rephraser is configured, then polish.

    Never raises: any engine error, timeout or guard refusal keeps the draft as it was
    (polished), and ``rejected`` says why.
    """
    result = RephraseResult(text=draft or '')
    if not result.text.strip() or profile is None or not profile.is_reliable:
        return result
    engine = complete or (_local_server_complete if configured() else None)
    text = result.text
    if engine is not None and len(text) <= REPHRASER_MAX_DRAFT_CHARS:
        try:
            candidate = _clean_output(engine(rephrase_messages(profile, text, incoming)))
            reason = guard(text, candidate, [profile.person_name], _examples(profile, incoming))
            if reason is None:
                if candidate != text:
                    result.changes.append('rephrased')
                text, result.engine = candidate, 'local'
            else:
                result.rejected = reason
        except Exception as error:  # fail open: the draft is only polished
            result.rejected = result.engine_error = type(error).__name__
            logger.info('User voice rephraser unavailable: %s', type(error).__name__)
    polished = polish_draft(text, profile)
    result.text = polished.text
    result.changes.extend(polished.changes)
    return result
