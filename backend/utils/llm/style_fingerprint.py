"""
Corpus-derived texting-style fingerprint.

Everything here is measured from the USER'S OWN messages. There are deliberately
NO hardcoded word lists — no banned slang, no allowed slang, no "AI-tell" phrases.
Those never generalize: "bet"/"lol"/"fr" are correct for a casual texter and wrong
for a formal one; "certainly" is fine for a formal writer and wrong for a terse one.
So the only things this module asserts as hard style facts are objective,
per-user statistics (does THIS user capitalize? does THIS user use emoji?). All
word-choice / register / "sounds like an AI" judgment is left to the self-selection
judge in reply_draft.py, which is handed the user's real samples and decides
relative to them.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import FrozenSet, List, Tuple

# Emoji + common pictographic/symbol/variation-selector ranges. Used only to
# COUNT emoji in text; never to inject or forbid any specific character.
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"  # symbols & pictographs, supplemental, extended-A
    "\U0001f000-\U0001f0ff"  # mahjong/dominoes/cards
    "\U00002600-\U000027bf"  # misc symbols + dingbats
    "\U0001f1e6-\U0001f1ff"  # regional indicators (flags)
    "←-⇿"  # arrows
    "⬀-⯿"  # misc symbols & arrows
    "️"  # variation selector-16 (emoji presentation)
    "⃣"  # combining enclosing keycap
    "]"
)


def _tokenize_words(text):
    """Word tokens across scripts. A token is a run of letters (Unicode category L) and
    their combining marks (category M) — so accented/decomposed Latin AND Indic/Thai/
    Arabic (where vowel signs attach to a base letter) stay as one word — with internal
    apostrophes kept for contractions. Category-based rather than a regex because
    Python's stdlib `re` has no Unicode-property classes, so `[^\\W\\d_]` would drop
    combining marks (Mn/Mc) and split those words. (A prior ASCII-only `[A-Za-z']+`
    matched nothing in non-Latin scripts, collapsing whole messages to 1 word.)"""
    words = []
    cur = []
    for ch in text or "":
        if unicodedata.category(ch)[0] in ("L", "M"):
            cur.append(ch)
        elif ch in "'’" and cur:  # internal apostrophe (don't, y'all)
            cur.append(ch)
        elif cur:
            words.append("".join(cur))
            cur = []
    if cur:
        words.append("".join(cur))
    return words


# Em dash, en dash, or a double-hyphen used as a dash. One of the loudest "AI
# tells" — but still judged corpus-relatively: only forbidden for users whose own
# messages never use it.
_EM_DASH_RE = re.compile(r"[—–]|--")

# Below this many samples we don't trust the measured capitalization/emoji habit
# enough to hard-fail a candidate on it; cold-start neutral rules govern instead.
MIN_SAMPLES_FOR_HARD_FAIL = 5


def has_em_dash(text: str) -> bool:
    return bool(_EM_DASH_RE.search(text or ""))


@dataclass
class StyleFingerprint:
    sample_count: int
    lowercase_ratio: float  # fraction of alpha-starting samples that start lowercase
    uses_capitalization: bool  # False => the user habitually texts in all-lowercase
    emoji_rate: float  # emoji per message
    uses_emoji: bool  # the user actually uses emoji
    avg_words: float
    word_band: Tuple[int, int]  # (p10, p90) words per message, clamped >= 1
    terminal_punct_rate: float  # fraction of samples ending in . ! or ?
    ends_with_period_rate: float  # fraction ending specifically in '.'
    median_words: int = 1  # typical (p50) words per message — the length target
    short_reply_rate: float = 0.0  # fraction of the user's messages that are <= 2 words
    uses_em_dash: bool = False  # the user actually uses em/en dashes or --
    vocabulary: FrozenSet[str] = field(default_factory=frozenset)  # user's own words (informational only)
    cold_start: bool = False


def count_emojis(text: str) -> int:
    return len(_EMOJI_RE.findall(text or ""))


def _percentile(sorted_vals: List[int], pct: float) -> int:
    """Nearest-rank percentile on an already-sorted, non-empty list."""
    if not sorted_vals:
        return 0
    idx = int(round((pct / 100.0) * (len(sorted_vals) - 1)))
    idx = max(0, min(idx, len(sorted_vals) - 1))
    return sorted_vals[idx]


def _starts_lowercase(text: str) -> bool:
    """True if the first alphabetic character is lowercase. Non-alpha leads are
    skipped so an opening emoji/number/punctuation doesn't mask the letter case."""
    for ch in text:
        if ch.isalpha():
            return ch.islower()
    return False


def _starts_uppercase(text: str) -> bool:
    for ch in text:
        if ch.isalpha():
            return ch.isupper()
    return False


def compute_fingerprint(samples: List[str]) -> StyleFingerprint:
    """Measure how this user texts from their own outgoing messages."""
    cleaned = [s.strip() for s in (samples or []) if s and s.strip()]
    n = len(cleaned)
    if n == 0:
        return StyleFingerprint(
            sample_count=0,
            lowercase_ratio=0.0,
            uses_capitalization=True,  # neutral default: assume normal capitalization
            emoji_rate=0.0,
            uses_emoji=False,
            avg_words=0.0,
            word_band=(1, 1),
            terminal_punct_rate=0.0,
            ends_with_period_rate=0.0,
            vocabulary=frozenset(),
            cold_start=True,
        )

    alpha_leading = [s for s in cleaned if any(c.isalpha() for c in s)]
    lower_leads = sum(1 for s in alpha_leading if _starts_lowercase(s))
    lowercase_ratio = (lower_leads / len(alpha_leading)) if alpha_leading else 0.0

    total_emoji = sum(count_emojis(s) for s in cleaned)
    emoji_rate = total_emoji / n

    word_counts = sorted(len(_tokenize_words(s)) or 1 for s in cleaned)
    avg_words = sum(word_counts) / n
    word_band = (max(1, _percentile(word_counts, 10)), max(1, _percentile(word_counts, 90)))
    median_words = max(1, _percentile(word_counts, 50))
    short_reply_rate = sum(1 for w in word_counts if w <= 2) / n

    terminal = sum(1 for s in cleaned if s[-1] in ".!?")
    periods = sum(1 for s in cleaned if s[-1] == ".")

    vocabulary = frozenset(w.lower() for s in cleaned for w in _tokenize_words(s))

    return StyleFingerprint(
        sample_count=n,
        lowercase_ratio=lowercase_ratio,
        uses_capitalization=lowercase_ratio < 0.5,
        emoji_rate=emoji_rate,
        # `>=` so a user exactly at the threshold (e.g. 1 emoji in 20 messages) counts
        # as using emoji — otherwise style_hard_fails would reject their emoji drafts
        # with "never uses emoji", contradicting their own sampled corpus.
        uses_emoji=emoji_rate >= 0.05,
        avg_words=avg_words,
        word_band=word_band,
        median_words=median_words,
        short_reply_rate=short_reply_rate,
        terminal_punct_rate=terminal / n,
        ends_with_period_rate=periods / n,
        uses_em_dash=any(has_em_dash(s) for s in cleaned),
        vocabulary=vocabulary,
        cold_start=False,
    )


def render_fingerprint_lines(fp: StyleFingerprint) -> str:
    """Human-readable style summary for the drafting prompt. Describes the user's
    measured habits; lists NO example words."""
    if fp.cold_start:
        return (
            "- No writing samples yet: write neutral, plain, correctly-capitalized English. "
            "Keep it short and human, but do NOT adopt slang, all-lowercase, or emoji."
        )
    cap = (
        "writes in all lowercase — do the same, do NOT capitalize the first letter"
        if not fp.uses_capitalization
        else "uses normal sentence capitalization — capitalize the first letter and 'I'"
    )
    if fp.uses_emoji:
        emoji = f"sometimes uses emoji (~{fp.emoji_rate:.1f} per message) — matching that rate is fine"
    else:
        emoji = "never uses emoji — do NOT add any emoji"
    lo, hi = fp.word_band
    # Lead with the TYPICAL (median) length, not the p90 max, so drafts target the user's habit and
    # don't drift toward the long end. Surface the short-reply tendency generically (from their data).
    # Descriptive, not prescriptive: report the user's real range so the model can size the reply to
    # the moment (short for a quick reaction, longer for a real message) — never a hard "keep it short".
    if fp.short_reply_rate >= 0.4:
        length = (
            f"this user texts SHORT — about {fp.median_words} word(s) typical and {round(fp.short_reply_rate * 100)}% "
            f"of their messages are 1-2 words. Keep replies this short: a word or a brief phrase. EVEN when "
            f"answering a real question that has several specifics to give, stay terse — a short lowercase "
            f"phrase or a quick comma list of the real things, never polished prose or a paragraph. Match "
            f"their brevity; don't pad and don't inflate"
        )
    else:
        length = (
            f"messages are typically about {fp.median_words} words (range {lo}-{hi}) — size the reply to the moment, "
            f"short for a quick reaction and fuller for a real message; don't pad and don't force it short"
        )
    end_punct = (
        "usually ends sentences with punctuation" if fp.terminal_punct_rate > 0.5 else "usually skips end punctuation"
    )
    dash = (
        "sometimes uses dashes"
        if fp.uses_em_dash
        else "NEVER uses em dashes (—), en dashes (–), or -- : do NOT use them"
    )
    return "\n".join(
        [
            f"- Capitalization: {cap}",
            f"- Emoji: {emoji}",
            f"- Length: {length}",
            f"- Punctuation: {end_punct}; use only the punctuation their samples show — {dash}",
            "- Vocabulary: use only words, abbreviations, and slang that appear in their samples "
            "above; do NOT introduce any word or register their own messages don't already show.",
        ]
    )


def style_hard_fails(draft: str, fp: StyleFingerprint) -> List[str]:
    """Objective, corpus-derived reasons a candidate contradicts how this user
    texts. Only binary style facts measured from the user's own samples — never a
    judgment about specific words. Empty list => no hard style violation.

    Skipped entirely when there isn't enough evidence (cold start / few samples);
    the neutral cold-start prompt rules cover that case instead.
    """
    fails: List[str] = []
    text = (draft or "").strip()
    if not text:
        return fails
    if fp.cold_start or fp.sample_count < MIN_SAMPLES_FOR_HARD_FAIL:
        return fails

    if not fp.uses_emoji and count_emojis(text) > 0:
        fails.append("added emoji, but this user never uses emoji")

    if not fp.uses_em_dash and has_em_dash(text):
        fails.append("uses an em dash / --, but this user never does (classic AI tell)")

    if fp.uses_capitalization and _starts_lowercase(text):
        fails.append("starts lowercase, but this user capitalizes normally")
    elif not fp.uses_capitalization and _starts_uppercase(text):
        fails.append("starts capitalized, but this user texts in all-lowercase")

    return fails


def length_soft_fail(draft: str, fp: StyleFingerprint) -> bool:
    """Soft signal: draft length far outside the user's usual band. A legitimately
    longer/shorter reply is common, so this is advisory (widened band), not a hard fail."""
    if fp.cold_start:
        return False
    words = len(_tokenize_words(draft or "")) or 1
    lo, hi = fp.word_band
    return words < max(1, lo // 2) or words > hi * 3
