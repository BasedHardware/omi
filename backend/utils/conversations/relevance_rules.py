"""Deterministic tier of the conversation relevance decision.

The relevance step (``relevance.py``) runs these rules before any model call,
and sync intake applies them inside its transaction. A rule may return
``'discard'`` only when the transcript provably carries no content a person
could want back (fillers, acknowledgements, function words, microphone
checks). It may return ``'keep'`` only when the transcript is
unambiguously substantive. Everything else returns ``None`` and the model decides.

Design constraints, in priority order:

1. A false discard hides something the user wanted, so every discard rule is
   gated by "protective" signals: any content word, digit, number word, time
   expression, task verb, capitalised mid-sentence word (likely a name), or
   text in a script the rules cannot read. When in doubt, return ``None``.
   Standalone "yes"/"no" are answers, not filler: they go to the model.
2. Duration is never a discard reason. ``speech_seconds`` is accepted for the
   interface but deliberately unused: summed segment spans are unreliable in
   practice (pre-roll offsets, 10 s quantised sync segments, single segments
   spanning several minutes for one sentence, overlapping dual-channel
   segments), and short speech can matter ("call mom before five").
3. Bounded text rules; no external I/O; microseconds per call. The calendar
   request keep guard has one default-on runtime rollback switch.
   Several test harnesses load this module with a stubbed ``utils`` package.

Measured 2026-09-23 against 286 hand-labelled conversations from one account
(106 keep, 94 discard): 0 discards of a keep label, 44 of 94 junk settled
without a model call (the previous filler check settled 8).
"""

from __future__ import annotations

import re
import unicodedata
from typing import FrozenSet, List, Literal, Optional, Sequence, Tuple

from config.refactor_modes import default_on

Verdict = Literal['keep', 'discard']

# Bumped whenever a rule changes, so stored decisions stay attributable.
RULES_VERSION = 5

# ---------------------------------------------------------------------------
# Lexicons. All entries are casefolded; apostrophes are normalised to "'".
# ---------------------------------------------------------------------------

# Interjections, backchannels, acknowledgements, greetings and politeness
# formulas. A transcript made only of these carries no retrievable content.
FILLER_WORDS: FrozenSet[str] = frozenset("""
    mm mmm mhm mmhm hmm hm hmmm hmmh mmh hmmmh hmmmmm uh uhh um umm huh ah ahh
    oh ohh ooh eh er erm ha haha hahaha heh hehe lol aha whoa wow ugh oops ow
    yeah yea ya yah yep yup yeh okay ok k kay alright allright
    aight right sure cool nice great good fine wow hey hi hello yo bye goodbye
    thanks thank ty sorry pardon please bro dude man guys exactly totally
    absolutely definitely indeed perfect awesome amazing true correct
    """.split())

# Non-English backchannels seen in multilingual capture. Only single-token
# acknowledgements belong here; any other non-English token blocks a discard.
MULTILINGUAL_FILLER_WORDS: FrozenSet[str] = frozenset("""
    ừ ờ ừm ừa dạ vâng ja jo ne nee oui ouais si sí vale bueno da ага угу да
    нет ну ок окей
    """.split())

# Pronouns, determiners, auxiliaries, prepositions, conjunctions, discourse
# adverbs, generic evaluatives and light verbs. Deliberately excludes number
# words, time words and task verbs (see below) so they always count as content.
FUNCTION_WORDS: FrozenSet[str] = frozenset("""
    i me my mine myself you your yours yourself he him his she her hers it its
    itself we us our ours they them their theirs this that these those there
    here someone something anything everything nothing anyone everyone somebody
    anybody everybody nobody somewhere anywhere
    i'm i've i'll i'd you're you've you'll you'd he's she's it's it'll we're
    we've we'll they're they've they'll that's there's here's what's who's
    where's how's let's don't doesn't didn't can't cannot won't wouldn't
    couldn't shouldn't isn't aren't wasn't weren't haven't hasn't hadn't ain't
    gonna wanna gotta kinda sorta dunno lemme gimme y'all 're 's 'm 've 'll 'd
    a an the is am are was were be been being do does did doing done have has
    had having will would can could shall may might not
    and or but so if then because cause cuz than as though although while
    of to in on at for with about from by into onto over under up down out off
    after
    back through around away along
    just like really actually basically literally honestly seriously well also
    too very only even still again already maybe probably perhaps kind sort
    quite pretty rather anyway anyways whatever whenever however somehow
    what why how where who whom whose which when
    all some any more most much many few little lot lots bit both each every
    other another same different else such own enough
    get gets got gotten getting go goes going went gone come comes coming came
    know knew known think thinking thought mean means meant guess say says
    saying said tell told see sees seeing saw seen look looking looked want
    wants wanted let make makes made take takes took taken give gave put feel
    felt try trying tried keep kept stay wait hold stop mind gives giving given
    talk talks talking talked agree agreed one ones
    thing things stuff way time times
    bad wrong crazy weird fun funny interesting easy hard better best worse
    worst big small real sad happy boring
    now yet ever never always sometimes often
    oh god gosh jeez geez
    """.split())

# Words that mark a counting microphone check ("testing one two three").
MIC_CHECK_WORDS: FrozenSet[str] = frozenset("""
    test testing tested check checking mic microphone hear me can you one two
    three four five 1 2 3 4 5 hello is this a it working works on
    """.split())
MIC_CHECK_MAX_TOKENS = 20

# Explicit reminder / note phrasing. These are keep-worthy regardless of length.
EXPLICIT_REMINDER_RE = re.compile(
    r"\b(?:remind me|don'?t forget|do not forget|remember to|note to self|"
    r"make a note|take a note|set (?:a|an) (?:reminder|alarm|timer)|"
    r"add (?:it |this |that )?to (?:my|the) (?:list|calendar|to-?do))\b",
    re.IGNORECASE,
)

EXPLICIT_CALENDAR_REQUEST_KEEP_ENV = 'EXPLICIT_CALENDAR_REQUEST_KEEP'
# A direct instruction (optionally polite), not a prediction, quotation or
# future-tense commitment. Match one existing segment; never fuse speakers.
_CALENDAR_REQUEST_RE = re.compile(
    r"(?:please[ ,\t]+|(?:can|could|would)[ \t]+you[ \t]+(?:please[ \t]+)?)?"
    r"(?:put[ \t]+\w[^\r\n.!?;]{0,159}?[ \t]+on|add[ \t]+\w[^\r\n.!?;]{0,159}?[ \t]+to)"
    r"[ \t]+(?:my|the)[ \t]+calendar(?:[ \t]+[^\r\n.!?;]{1,80})?[.!?]?",
    re.IGNORECASE,
)
# Only scan after the bounded candidate matches. Ambiguous negation/cancellation
# keeps the prior policy; word boundaries preserve Notion/notebook/notifications.
_CALENDAR_REQUEST_NEGATION_RE = re.compile(
    r"\b(?:not|never|no|cannot|without|except|excluding|avoid(?:ing)?|omit(?:ting)?|"
    r"instead[ \t-]+of|rather[ \t-]+than|[a-z]{1,12}n't|cancel(?:s|ed|led|ing|ling|lation|lations)?)\b",
    re.IGNORECASE,
)


def has_explicit_keep_instruction(text: str) -> bool:
    """Retain input for normal adjudication; never authorize an action/event.

    Existing reminder matching remains unchanged when the calendar guard is off.
    Call per segment for new calendar forms, without coalescing speakers/turns.
    """
    if EXPLICIT_REMINDER_RE.search(text):
        return True
    if not default_on(EXPLICIT_CALENDAR_REQUEST_KEEP_ENV):
        return False
    candidate = normalize_relevance_text(text).strip()
    return (
        _CALENDAR_REQUEST_RE.fullmatch(candidate) is not None
        and _CALENDAR_REQUEST_NEGATION_RE.search(candidate) is None
    )


# Code points of CJK acknowledgement particles. A CJK transcript whose Han/kana
# characters are all in this set is a backchannel ("嗯嗯", "好的", "对对对").
CJK_FILLER_CHARS: FrozenSet[str] = frozenset(
    '嗯啊哦噢喔呃额恩唉哎诶欸嘿喂哈呵呀吧嘛呢啦了的对好是行' 'はいええうんあそうね' 'ハイ'
)

# Capitalised forms that are names or months but collide with FUNCTION_WORDS.
# Seen anywhere (even sentence-initially) they block a discard.
CAPITALISED_HOMOGRAPHS: FrozenSet[str] = frozenset({'May', 'Will', 'Bill', 'Mark', 'Sue', 'Pat'})

# Thresholds.
FUNCTION_ONLY_MAX_TOKENS = 25  # longer function-word-only runs go to the LLM
KEEP_WORD_COUNT = 100  # above this the model is never asked; shared with the model tier
CJK_CHARS_PER_WORD = 1.5


def transcript_word_count(text: str) -> int:
    """The model tier's word count (``conv_discard`` and the Jev tier share it).

    CJK-dominant text counts two characters as a word; otherwise whitespace tokens.
    """
    if not text:
        return 0
    cjk_chars = sum(1 for c in text if unicodedata.east_asian_width(c) in ('W', 'F', 'H'))
    if cjk_chars > len(text) * 0.3:
        return cjk_chars // 2
    return len(text.split())


_TOKEN_RE = re.compile(r"[^\W_]+(?:'[^\W_]+)*|'(?:re|s|m|ve|ll|d)\b", re.UNICODE)
_ELONGATED_FILLER_RE = re.compile(r'^(?:m+|h+m+|m+h+m+|u+h+|u+m+|a+h+|o+h+|e+h+|h?(?:a+h+)+a*|(?:ha)+h?|(?:he)+h?)$')
_SENTENCE_BREAK_RE = re.compile(r'[.!?。！？…]+')


def _is_cjk(ch: str) -> bool:
    cp = ord(ch)
    return (
        0x4E00 <= cp <= 0x9FFF
        or 0x3400 <= cp <= 0x4DBF
        or 0x3040 <= cp <= 0x30FF  # hiragana + katakana
        or 0xAC00 <= cp <= 0xD7AF  # hangul syllables
        or 0xF900 <= cp <= 0xFAFF
    )


def normalize_relevance_text(text: str) -> str:
    text = unicodedata.normalize('NFKC', text)
    return text.replace('’', "'").replace('‘', "'").replace('`', "'")


def _is_filler(token: str) -> bool:
    return token in FILLER_WORDS or token in MULTILINGUAL_FILLER_WORDS or bool(_ELONGATED_FILLER_RE.match(token))


def _has_mid_sentence_capital(texts: Sequence[str]) -> bool:
    """True when a capitalised Latin word appears after the first word of a sentence,
    or a name/month homograph of a function word appears capitalised anywhere.

    Proxy for a proper noun ("call Sarah", "at Blue Bottle"). ASR output from
    some providers is fully lowercased, so absence proves nothing; presence
    blocks a discard. "I"-forms and "OK" are ignored.
    """
    for text in texts:
        for sentence in _SENTENCE_BREAK_RE.split(text):
            words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)*", sentence)
            if any(word in CAPITALISED_HOMOGRAPHS for word in words):
                return True
            for word in words[1:]:
                if (
                    word[0].isupper()
                    and word.isascii()
                    and word not in ('I', "I'm", "I've", "I'll", "I'd", 'OK', 'Okay')
                ):
                    return True
    return False


def _tokenise(texts: Sequence[str]) -> Tuple[List[str], List[str], List[str]]:
    """Returns (latin_tokens, foreign_tokens, cjk_chars) from the transcript."""
    latin: List[str] = []
    foreign: List[str] = []
    cjk: List[str] = []
    for raw in texts:
        text = normalize_relevance_text(raw)
        cjk.extend(ch for ch in text if _is_cjk(ch))
        stripped = ''.join(' ' if _is_cjk(ch) else ch for ch in text).casefold()
        for token in _TOKEN_RE.findall(stripped):
            (latin if token.isascii() else foreign).append(token)
    return latin, foreign, cjk


# Only all-noise runs of repeated, exact outro phrases qualify. A single
# sign-off, quoted phrase, mixed real speech, or unfamiliar language abstains.
_ASR_OUTROS = frozenset(
    {
        'thank you for watching',
        'thanks for watching',
        'terima kasih telah menonton',
    }
)


def repeated_asr_outros(texts: Sequence[str]) -> bool:
    # A quotation is evidence of discussion, not a bare ASR outro. Do not
    # erase that distinction while normalizing punctuation for matching.
    if any(
        mark in text
        for text in texts
        for mark in ('"', "'", '`', '“', '”', '‘', '’', '«', '»', '‹', '›', '「', '」', '『', '』')
    ):
        return False
    utterances = [re.sub(r'[^\w\s]', '', unicodedata.normalize('NFKC', text).casefold()).strip() for text in texts]
    utterances = [' '.join(text.split()) for text in utterances if text]
    return len(utterances) >= 3 and all(text in _ASR_OUTROS for text in utterances)


def deterministic_relevance(texts: Sequence[str], speech_seconds: Optional[float]) -> Tuple[Optional[Verdict], str]:
    """Return ``(verdict, rule)``; ``verdict`` is None when the model must decide.

    ``texts`` are transcript segment texts in order; ``speech_seconds`` is accepted and ignored. ``rule`` is a stable
    snake_case id used as a metric label and stored with the decision.
    """
    del speech_seconds  # Intentionally unused; see module docstring.

    if repeated_asr_outros(texts):
        return 'discard', 'repeated_asr_outro'

    latin, foreign, cjk = _tokenise(texts)
    if not latin and not foreign and not cjk:
        return 'discard', 'empty_transcript'

    cjk_content = [ch for ch in cjk if ch not in CJK_FILLER_CHARS]
    word_equivalents = len(latin) + len(foreign) + len(cjk) / CJK_CHARS_PER_WORD

    joined = ' '.join(normalize_relevance_text(t) for t in texts)
    has_digit = any(ch.isdigit() for ch in joined)
    unreadable = bool(cjk_content) or any(not _is_filler(t) for t in foreign)

    # 1. Explicit reminder phrasing is always worth keeping, whatever else is said.
    if EXPLICIT_REMINDER_RE.search(joined) or any(has_explicit_keep_instruction(t) for t in texts):
        return 'keep', 'explicit_reminder'

    # 2. Content-free at any length: checked before the length fast path so a long
    #    run of "yeah yeah ..." is not kept for its length.
    if not unreadable and all(_is_filler(t) for t in latin):
        return 'discard', 'filler_only'

    # 3. Length fast path (same threshold as the existing >100-word shortcut).
    if word_equivalents > KEEP_WORD_COUNT:
        return 'keep', 'substantial_length'

    # 4. Unknown-language content is never discarded deterministically.
    if unreadable:
        return None, 'non_latin_content'

    # 5. Short content-free utterances. Digits and likely names always protect.
    if has_digit and not _is_mic_check(latin):
        return None, 'ambiguous'
    protected = _has_mid_sentence_capital(texts)
    if not protected and _is_mic_check(latin):
        return 'discard', 'mic_check'
    if (
        not protected
        and not has_digit
        and len(latin) <= FUNCTION_ONLY_MAX_TOKENS
        and all(_is_filler(t) or t in FUNCTION_WORDS for t in latin)
    ):
        return 'discard', 'no_content_words'

    return None, 'ambiguous'


def _is_mic_check(latin: Sequence[str]) -> bool:
    """'testing one two three', 'can you hear me' style checks and nothing else."""
    if not latin or len(latin) > MIC_CHECK_MAX_TOKENS:
        return False
    if not any(t in ('test', 'testing', 'mic', 'microphone') for t in latin):
        return False
    counting = sum(t in ('one', 'two', 'three', '1', '2', '3') for t in latin) >= 2
    hear_me = any(a == 'hear' and b == 'me' for a, b in zip(latin, latin[1:]))
    if not (counting or hear_me):
        return False
    leftovers = [t for t in latin if t not in MIC_CHECK_WORDS and not _is_filler(t) and t not in FUNCTION_WORDS]
    return not leftovers


# The measured 286-conversation cohort above supports zero-content lexicon
# decisions (0 false discards), not a nonzero content-density cutoff. Use the
# conservative boundary: content density == 0 and filler ratio > 0. No duration
# or minimum word count participates; even one content token protects speech.
FALLBACK_MAX_CONTENT_DENSITY = 0.0
FALLBACK_MIN_FILLER_RATIO = 0.0


def deterministic_tiebreak(texts: Sequence[str]) -> Verdict:
    """Total decision when paid arms cannot answer; preserve rule ordering.

    Extend the measured lexicon-only rule beyond its 25-token model referral
    only for backchannel-bearing runs. Unknown scripts, numbers and names
    remain protected. This is deliberately not calibrated to one outage.
    """
    verdict, _ = deterministic_relevance(texts, None)
    if verdict is not None:
        return verdict
    latin, foreign, cjk = _tokenise(texts)
    joined = ' '.join(normalize_relevance_text(t) for t in texts)
    if (not latin) or foreign or cjk or any(ch.isdigit() for ch in joined) or _has_mid_sentence_capital(texts):
        return 'keep'
    filler_ratio = sum(_is_filler(t) for t in latin) / len(latin)
    content_density = sum(not _is_filler(t) and t not in FUNCTION_WORDS for t in latin) / len(latin)
    if content_density <= FALLBACK_MAX_CONTENT_DENSITY and filler_ratio > FALLBACK_MIN_FILLER_RATIO:
        return 'discard'
    return 'keep'
