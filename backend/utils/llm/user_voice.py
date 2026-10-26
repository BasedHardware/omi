"""How the user writes to one person, so drafts sent as them sound like them.

``propose_message`` opens the compose sheet with a body the chat model wrote. The
words then read like Omi rather than like the user, and the user either rewrites
them or sends something that reads like AI to a friend. This module builds a
small, code-only profile of the user's own voice toward ONE person and uses it in
two places, neither of which adds a model call:

1. ``profile_prompt_block`` is attached to the ``search_contacts`` result for a
   contact that matches a known person, which is the moment the model is about to
   draft the message (see ``utils.device_tools``).
2. ``polish_draft`` deterministically fixes the marks a model still gets wrong
   (how the last line ends, how many "!") before the compose sheet opens. It never
   changes words.

Sources are only the user's own lines:

- written: messages the user wrote to that person, where the platform can read
  them (``user_written_lines``; none by default). These are the best evidence of
  how the user texts someone and win for every measure once there are enough.
- spoken: transcript segments with ``is_user`` in conversations where that person
  is a tagged speaker. These carry length, greetings, language mix and examples.
- typed: messages the user typed to Omi. Speech-to-text inserts its own
  punctuation, so without written lines, endings, "!" and emoji are measured on
  typed lines when there are enough of them, and on all lines otherwise.

Questions are left out of the ending shares: a question ends with "?" because of
what it says, not how the person writes, and someone who mostly asks Omi things
would otherwise look like they end every line with "?".

Reciprocity: people answer in kind -- an emoji with an emoji, a "!" with a "!", a
language with that language -- far more often than their base rate. ``fit_mirror``
measures that on the same exchanges (the other person's message, then the user's
reply; spoken turns give length and script only) and ``reply_target`` turns it into
an aim for this one reply. ``infer_register`` tells work from personal with Omi's own
conversation categories for that person, else the work words in their exchanges.

Locked, discarded and deleted conversations are never read. The feature is
opt-in (``assistant_settings.drafts.user_voice``); the profile is cached for
seven days, encrypted with the user's key like other user content.
"""

import json
import logging
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from pydantic import BaseModel, Field

import database.chat as chat_db
import database.conversations as conversations_db
import database.users as users_db
from database.redis_db import r as redis_client
from utils.encryption import decrypt, encrypt

logger = logging.getLogger(__name__)

USER_VOICE_CACHE_TTL_SECONDS = 7 * 24 * 3600
USER_VOICE_PROFILE_VERSION = 5

# Below this many of the user's own lines a profile is noise; the prompt block
# then says so instead of inventing a style.
USER_VOICE_MIN_LINES = 8
# Endings and "!" come from typed lines only when there are at least this many.
USER_VOICE_MIN_TYPED_LINES = 12
# A greeting is worth naming only when the user opens this often (percent).
GREETING_MIN_PERCENT = 15

# Bounded reads: one page of recent conversations and recent chat messages.
USER_VOICE_MAX_CONVERSATIONS = 200
USER_VOICE_MAX_TYPED_MESSAGES = 200
USER_VOICE_MAX_LINES = 150
USER_VOICE_MAX_EXAMPLES = 5
USER_VOICE_MAX_EXAMPLE_CHARS = 140

# Real exchanges (their message -> the user's reply) kept for few-shot examples.
USER_VOICE_MAX_EXCHANGES = 120
USER_VOICE_MAX_EXCHANGE_CHARS = 200
# Examples shown per draft: the ones closest to what they just said, plus the newest.
USER_VOICE_SHOTS = 8
USER_VOICE_RECENT_SHOTS = 3
# Lines of the open thread shown with the draft.
USER_VOICE_MAX_THREAD = 8
# A short line the user sends this person again and again ("okk", "Yes yes").
STOCK_REPLY_MAX_CHARS = 14
STOCK_REPLY_MIN_COUNT = 2
USER_VOICE_MAX_STOCK = 6

# An ending the user uses less often than this (percent) counts as "never".
RARE_ENDING_PERCENT = 5

_EMOJI_RE = re.compile('[\U0001f300-\U0001faff☀-➿\U0001f1e6-\U0001f1ff]')
_URL_RE = re.compile(r'https?://\S+')
_BANG_RE = re.compile('[!！]')
_LAUGH_RE = re.compile(r'(haha+|hehe+|lol|lmao|哈哈+)$', re.IGNORECASE)
_STRETCH_RE = re.compile(r'([^\W\d_])\1{2,}|\bokk+\b', re.IGNORECASE)
_GREETING_RE = re.compile(
    r'^(hi|hey|hello|yo|dear|good morning|morning|嗨|哈喽|你好|hola|bonjour|ciao)\b',
    re.IGNORECASE,
)
_SCRIPT_NAMES = {
    'LATIN': 'latin',
    'CJK': 'han',
    'HIRAGANA': 'kana',
    'KATAKANA': 'kana',
    'HANGUL': 'hangul',
    'CYRILLIC': 'cyrillic',
    'ARABIC': 'arabic',
    'DEVANAGARI': 'devanagari',
    'HEBREW': 'hebrew',
    'GREEK': 'greek',
    'THAI': 'thai',
}
# Scripts whose sentences end with full-width marks.
_FULL_WIDTH_SCRIPTS = frozenset({'han', 'kana'})
_ENDING_WORDS = {
    'none': 'no punctuation',
    '.': 'a period',
    '!': '"!"',
    '?': 'a question mark',
    'emoji': 'an emoji',
    'laugh': 'a laugh (haha)',
    'ellipsis': '"..."',
}


class VoiceExchange(BaseModel):
    them: str
    me: str


class VoiceMirror(BaseModel):
    """How this person writes to the user, and how the user's reply follows what they just sent.

    Fitted on the same (their message -> the user's reply) exchanges. Per message, people
    tend to answer an emoji with an emoji, a "!" with a "!" and a language with that
    language far more often than their base rate; reply length follows the other person
    mostly across people (already in the profile), so it moves a draft only as far as the
    fitted slope says. Spoken exchanges carry length and script only: speech-to-text
    writes the marks.
    """

    exchanges: int = 0
    marks_measured: bool = False
    their_median_chars: int = 0
    their_emoji_rate: int = 0
    their_exclamation_rate: int = 0
    # Percent of the user's replies with the mark, when their message had it / did not.
    emoji_if_they: int = 0
    emoji_if_not: int = 0
    exclamation_if_they: int = 0
    exclamation_if_not: int = 0
    # Percent of replies in the same main script as their message.
    same_script: int = 0
    # Slope of log(reply length) on log(their length), clamped to [-1, 1].
    length_slope: float = 0.0
    user_emoji: list[str] = Field(default_factory=list)


class ReactionHabit(BaseModel):
    """How often the user answers this person with a tapback / emoji reaction, and which.

    Fitted per run of their messages (they finish, the user answers): ``rate`` is the
    percent of runs the user reacted to, ``kinds`` the percent of those reactions by
    kind. Measured on 1,806 held-out answer moments of one real user, the person's own
    rate is the only signal that helps (message content added nothing), so this stays a
    per-person habit, not a classifier.
    """

    runs: int = 0
    rate: int = 0
    reply_rate: int = 0
    kinds: dict[str, int] = Field(default_factory=dict)
    favourite: Optional[str] = None


class ReplyTarget(BaseModel):
    chars: int
    emoji: bool
    emoji_percent: int
    exclamation: str  # 'one' | 'rare' | 'none'
    exclamation_percent: int
    script: Optional[str] = None
    script_percent: int = 0
    their_chars: int = 0
    their_emoji: bool = False
    their_exclamation: bool = False


class UserVoiceProfile(BaseModel):
    version: int = USER_VOICE_PROFILE_VERSION
    person_id: str
    person_name: str
    built_at: datetime
    lines: int = 0
    spoken_lines: int = 0
    typed_lines: int = 0
    # Percent of measured lines, by how the line ends.
    endings: dict[str, int] = Field(default_factory=dict)
    exclamation_rate: int = 0
    exclamations_per_line: float = 0.0
    emoji_rate: int = 0
    # Percent of lines by their main script, e.g. {'latin': 70, 'han': 30}. Lines,
    # not letters: one Han character carries about what a Latin word does.
    scripts: dict[str, int] = Field(default_factory=dict)
    written_lines: int = 0
    # Percent of lines that stretch a word ("okk", "cominggg", "heyyy").
    stretch_rate: int = 0
    greeting_rate: int = 0
    lowercase_start_rate: int = 0
    median_chars: int = 0
    p90_chars: int = 0
    greetings: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    # How the user answered this person before, oldest first (written source only).
    exchanges: list[VoiceExchange] = Field(default_factory=list)
    reply_median_chars: int = 0
    stock_replies: list[str] = Field(default_factory=list)
    mirror: Optional[VoiceMirror] = None
    # 'work' | 'personal' | None, and why (conversation categories, or work words).
    voice_register: Optional[str] = None
    voice_register_reason: str = ''
    # Words and short phrases the user uses far more than the people who write to them.
    phrases: list[str] = Field(default_factory=list)
    reactions: Optional[ReactionHabit] = None
    # What the person said last, set per turn by the contact seam; never cached.
    incoming: str = Field(default='', exclude=True)

    @property
    def is_reliable(self) -> bool:
        return self.lines >= USER_VOICE_MIN_LINES


class PolishResult(BaseModel):
    text: str
    changes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Measuring lines (pure)
# ---------------------------------------------------------------------------


_ATTACHMENT_RE = re.compile(r'\[(image|photo|video|attachment)[^\]]*\]|[\ufffc\ufffd]', re.IGNORECASE)


def _clean(text: Any) -> str:
    return ' '.join(_ATTACHMENT_RE.sub('', _URL_RE.sub('', str(text or ''))).split())


def line_ending(text: str) -> Optional[str]:
    """How a line ends: '.', '!', '?', 'ellipsis', 'emoji', 'laugh' or 'none'."""
    stripped = _clean(text)
    if not stripped:
        return None
    if stripped.endswith(('...', '…')):
        return 'ellipsis'
    last = stripped[-1]
    if _EMOJI_RE.match(last) or unicodedata.category(last) == 'So':
        return 'emoji'
    if last in '.。':
        return '.'
    if last in '!！':
        return '!'
    if last in '?？':
        return '?'
    if _LAUGH_RE.search(stripped):
        return 'laugh'
    return 'none'


def letter_scripts(text: str) -> Counter:
    counts: Counter = Counter()
    for char in text:
        if not char.isalpha():
            continue
        name = unicodedata.name(char, '')
        counts[_SCRIPT_NAMES.get(name.split(' ', 1)[0], 'other')] += 1
    return counts


def _dominant_script(text: str) -> Optional[str]:
    counts = letter_scripts(text)
    return counts.most_common(1)[0][0] if counts else None


def _percent(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def _quantile(sorted_values: list[int], q: float) -> int:
    if not sorted_values:
        return 0
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def build_profile(
    person_id: str,
    person_name: str,
    spoken_lines: Iterable[str],
    typed_lines: Iterable[str],
    *,
    written_lines: Iterable[str] = (),
    exchanges: Iterable[tuple[str, str]] = (),
    spoken_exchanges: Iterable[tuple[str, str]] = (),
    categories: Iterable[str] = (),
    thread: Iterable[dict] = (),
    now: Optional[datetime] = None,
) -> UserVoiceProfile:
    """Build the profile from the user's own lines, oldest first."""
    spoken = [line for line in (_clean(t) for t in spoken_lines) if line][-USER_VOICE_MAX_LINES:]
    typed = [line for line in (_clean(t) for t in typed_lines) if line][-USER_VOICE_MAX_LINES:]
    written = [line for line in (_clean(t) for t in written_lines) if line][-USER_VOICE_MAX_LINES:]
    everything = written + spoken + typed
    profile = UserVoiceProfile(
        person_id=person_id,
        person_name=person_name,
        built_at=now or datetime.now(timezone.utc),
        lines=len(written) + len(spoken),
        spoken_lines=len(spoken),
        typed_lines=len(typed),
        written_lines=len(written),
    )
    if not everything:
        return profile

    # Marks: what the user wrote to this person when there is enough of it; else
    # typed lines, because STT punctuates for the user; else everything.
    if len(written) >= USER_VOICE_MIN_LINES:
        marked = written
    elif len(typed) >= USER_VOICE_MIN_TYPED_LINES:
        marked = typed
    else:
        marked = everything
    statements = [line for line in marked if line_ending(line) != '?'] or marked
    endings = Counter(e for e in (line_ending(line) for line in statements) if e)
    bang_lines = sum(1 for line in marked if _BANG_RE.search(line))
    bangs = sum(len(_BANG_RE.findall(line)) for line in marked)
    emoji_lines = sum(1 for line in marked if _EMOJI_RE.search(line))
    profile.endings = {k: _percent(v, len(statements)) for k, v in endings.most_common()}
    profile.exclamation_rate = _percent(bang_lines, len(marked))
    profile.exclamations_per_line = round(bangs / len(marked), 2)
    profile.emoji_rate = _percent(emoji_lines, len(marked))

    # Everything else is about this person: their lines, or all lines if none yet.
    personal = (written if len(written) >= USER_VOICE_MIN_LINES else written + spoken) or everything
    scripts = Counter(s for s in (_dominant_script(line) for line in personal) if s)
    profile.scripts = {k: _percent(v, len(personal)) for k, v in scripts.most_common() if _percent(v, len(personal))}
    profile.stretch_rate = _percent(sum(1 for line in personal if _STRETCH_RE.search(line)), len(personal))

    latin_lines = [line for line in personal if _dominant_script(line) == 'latin']
    if len(latin_lines) >= 5:
        profile.lowercase_start_rate = _percent(sum(1 for line in latin_lines if line[0].islower()), len(latin_lines))

    lengths = sorted(len(line) for line in personal)
    profile.median_chars = _quantile(lengths, 0.5)
    profile.p90_chars = _quantile(lengths, 0.9)

    greeted = [m.group(1).lower() for m in (_GREETING_RE.match(line) for line in personal) if m]
    profile.greeting_rate = _percent(len(greeted), len(personal))
    profile.greetings = [g for g, _ in Counter(greeted).most_common(3)]

    seen: set[str] = set()
    examples: list[str] = []
    for line in reversed(personal):
        if len(line) > USER_VOICE_MAX_EXAMPLE_CHARS or len(line) < 4 or line.casefold() in seen:
            continue
        seen.add(line.casefold())
        examples.append(line)
        if len(examples) == USER_VOICE_MAX_EXAMPLES:
            break
    profile.examples = examples

    kept = []
    for them, me in exchanges:
        them, me = _clean(them), _clean(me)
        if them and me and len(me) <= USER_VOICE_MAX_EXCHANGE_CHARS:
            kept.append(VoiceExchange(them=them[:USER_VOICE_MAX_EXCHANGE_CHARS], me=me))
    profile.exchanges = kept[-USER_VOICE_MAX_EXCHANGES:]
    if profile.exchanges:
        profile.reply_median_chars = _quantile(sorted(len(e.me) for e in profile.exchanges), 0.5)

    short = Counter()
    form: dict[str, str] = {}
    # Replies when there are exchanges (the same lines, each once), else everything written to them.
    for line in [e.me for e in profile.exchanges] or personal:
        if len(line) <= STOCK_REPLY_MAX_CHARS and line_ending(line) != '?':
            key = line.casefold().rstrip('.!！。')
            short[key] += 1
            form[key] = line  # the newest spelling
    profile.stock_replies = [form[k] for k, n in short.most_common(USER_VOICE_MAX_STOCK) if n >= STOCK_REPLY_MIN_COUNT]

    written_pairs = [(e.them, e.me) for e in profile.exchanges]
    spoken_pairs = [(_clean(a), _clean(b)) for a, b in spoken_exchanges]
    spoken_pairs = [(a, b) for a, b in spoken_pairs if a and b]
    profile.mirror = fit_mirror(written_pairs, marks=True) if len(written_pairs) >= USER_VOICE_MIN_LINES else (
        fit_mirror(spoken_pairs, marks=False) if len(spoken_pairs) >= USER_VOICE_MIN_LINES else None
    )
    profile.voice_register, profile.voice_register_reason = infer_register(categories, written_pairs or spoken_pairs)
    their_lines = [a for a, _ in written_pairs or spoken_pairs]
    profile.phrases = signature_phrases(written + typed if len(written) >= USER_VOICE_MIN_LINES else everything, their_lines)
    profile.reactions = fit_reactions(thread)
    return profile


# ---------------------------------------------------------------------------
# Signature phrases and reactions (pure)
# ---------------------------------------------------------------------------

USER_VOICE_MAX_PHRASES = 6
PHRASE_MIN_LINES = 3
# How much more often the user says it than the other side (as a ratio of line shares).
PHRASE_MIN_RATIO = 2.5
_PHRASE_STOP = frozenset(
    "the a an and or but so to of in on at for with is are was were be been it its it's i i'm im you your "
    "that this what just like yeah yes ok okay no not do did don't can can't will my me we they he she "
    "know want think get got go going really all one good would could should have has had there here when "
    "how why who then than also more some any our us him her them his their from about up out if as by "
    "today tomorrow time day work school".split()
)
# A single word counts only when it is stretched ("yeees", "okkk") or far more the user's than the other side's.
PHRASE_WORD_MIN_RATIO = 6.0
_WORD_RE = re.compile(r"[^\W\d_][\w'\u2019]*|[\u4e00-\u9fff]")


def _phrase_grams(line: str) -> set[str]:
    words = [w.replace('\u2019', "'") for w in _WORD_RE.findall(line.casefold())]
    grams: set[str] = set()
    for n in (1, 2, 3):
        for i in range(len(words) - n + 1):
            chunk = words[i : i + n]
            if all(w in _PHRASE_STOP for w in chunk):
                continue
            han = all(re.fullmatch('[\u4e00-\u9fff]', w) for w in chunk)
            if n == 1 and (han or len(chunk[0]) < 3):
                continue
            grams.add(''.join(chunk) if han else ' '.join(chunk))
    return grams


def signature_phrases(user_lines: Iterable[str], their_lines: Iterable[str] = ()) -> list[str]:
    """Words and phrases that mark the user's voice ("high key", "yeees", "no hurry").

    Counted per line (a phrase repeated in one line counts once) against what the other
    side writes, so shared topic words ("dinner" in a thread about dinner) drop out;
    a longer phrase wins over the words inside it.
    """
    mine = [_clean(t) for t in user_lines if _clean(t)]
    theirs = [_clean(t) for t in their_lines if _clean(t)]
    if len(mine) < USER_VOICE_MIN_LINES:
        return []
    a: Counter = Counter(g for line in mine for g in _phrase_grams(line))
    b: Counter = Counter(g for line in theirs for g in _phrase_grams(line))
    scored = []
    for gram, n in a.items():
        if n < PHRASE_MIN_LINES:
            continue
        ratio = (n / len(mine)) / ((b[gram] + 0.5) / max(len(theirs), 1))
        if theirs and ratio < PHRASE_MIN_RATIO:
            continue
        if ' ' not in gram and not _STRETCH_RE.search(gram) and (not theirs or ratio < PHRASE_WORD_MIN_RATIO):
            continue
        scored.append((math.log(ratio + 1) * math.log(n + 1) if theirs else n, gram))
    # A phrase that carries most uses of its words stands for them ("high key", not "high").
    kept_grams = {g for _, g in scored}
    scored = [
        (score, gram)
        for score, gram in scored
        if not any(gram != longer and gram in longer and a[longer] >= 0.7 * a[gram] for longer in kept_grams)
    ]
    picked: list[str] = []
    for _, gram in sorted(scored, reverse=True):
        if any(gram in p or p in gram for p in picked):
            continue
        picked.append(gram)
        if len(picked) == USER_VOICE_MAX_PHRASES:
            break
    return picked


REACTION_MIN_RUNS = 8
# Offer a reaction for this person only when the user reacts to most of their runs.
REACTION_SUGGEST_PERCENT = 40


def fit_reactions(thread: Iterable[dict]) -> Optional[ReactionHabit]:
    """The user's reaction habit with this person, from a thread with reaction items.

    ``thread`` is oldest first, ``{'is_user', 'text'}`` plus, for a reaction the user
    left, ``{'is_user': True, 'reaction': 'love'|'like'|'laugh'|'emphasize'|'question'|'dislike'|<emoji>}``.
    A platform that cannot see reactions sends none and gets no habit.
    """
    items = [t for t in thread or () if isinstance(t, dict)]
    if not any(t.get('reaction') for t in items):
        return None
    runs = reacted = replied = 0
    kinds: Counter = Counter()
    i = 0
    while i < len(items):
        if items[i].get('is_user'):
            i += 1
            continue
        while i < len(items) and not items[i].get('is_user'):
            i += 1  # their run
        answer = []
        while i < len(items) and items[i].get('is_user'):
            answer.append(items[i])
            i += 1
        if not answer:
            break  # the open run: not answered yet
        runs += 1
        tap = next((a['reaction'] for a in answer if a.get('reaction')), None)
        if tap:
            reacted += 1
            kinds[str(tap)] += 1
        if any(_clean(a.get('text')) and not a.get('reaction') for a in answer):
            replied += 1
    if runs < REACTION_MIN_RUNS:
        return None
    habit = ReactionHabit(runs=runs, rate=_percent(reacted, runs), reply_rate=_percent(replied, runs))
    habit.kinds = {k: _percent(v, reacted) for k, v in kinds.most_common(4)} if reacted else {}
    habit.favourite = kinds.most_common(1)[0][0] if reacted else None
    return habit


def suggest_reaction(profile: Optional[UserVoiceProfile]) -> Optional[str]:
    """The reaction to offer with this reply, when the user usually reacts to this person."""
    habit = profile.reactions if profile else None
    if not habit or not habit.favourite or habit.rate < REACTION_SUGGEST_PERCENT:
        return None
    return habit.favourite


# ---------------------------------------------------------------------------
# Reciprocity and register (pure)
# ---------------------------------------------------------------------------

# Below this many replies to messages with a mark, the "if they" rate leans on the base rate.
_MIRROR_PRIOR = 2
EMOJI_REPLY_PERCENT = 30
EXCLAMATION_ONE_PERCENT = 40
EXCLAMATION_NONE_PERCENT = 8
SAME_SCRIPT_PERCENT = 70


def _reply_script(text: str) -> Optional[str]:
    """A message's script for answering in kind: any full-width script wins (one Han word in an
    English-heavy line still makes it a Chinese message), else the dominant one."""
    counts = letter_scripts(text)
    full = [s for s in counts if s in _FULL_WIDTH_SCRIPTS]
    return max(full, key=counts.get) if full else (counts.most_common(1)[0][0] if counts else None)


def _marks(text: str) -> tuple[int, bool, bool, Optional[str]]:
    return len(text), bool(_EMOJI_RE.search(text)), bool(_BANG_RE.search(text)), _reply_script(text)


def fit_mirror(pairs: list[tuple[str, str]], *, marks: bool) -> Optional[VoiceMirror]:
    """Fit how the user's reply follows the other person's message, from real exchanges."""
    rows = [(_marks(them), _marks(me), me) for them, me in pairs if them and me]
    n = len(rows)
    if n < USER_VOICE_MIN_LINES:
        return None

    def conditional(index: int) -> tuple[int, int]:
        base = sum(1 for _, m, _ in rows if m[index]) / n
        def smoothed(group: list) -> int:
            return round(100 * (sum(1 for _, m, _ in group if m[index]) + _MIRROR_PRIOR * base) / (len(group) + _MIRROR_PRIOR))
        return smoothed([r for r in rows if r[0][index]]), smoothed([r for r in rows if not r[0][index]])

    lt = [math.log(t[0] + 1) for t, _, _ in rows]
    lm = [math.log(m[0] + 1) for _, m, _ in rows]
    mt, mm = sum(lt) / n, sum(lm) / n
    var = sum((x - mt) ** 2 for x in lt)
    cov = sum((x - mt) * (y - mm) for x, y in zip(lt, lm))
    scripted = [(t[3], m[3]) for t, m, _ in rows if t[3] and m[3]]
    mirror = VoiceMirror(
        exchanges=n,
        marks_measured=marks,
        their_median_chars=_quantile(sorted(t[0] for t, _, _ in rows), 0.5),
        same_script=_percent(sum(1 for a, b in scripted if a == b), len(scripted)),
        length_slope=round(max(-1.0, min(1.0, cov / var)), 2) if var else 0.0,
    )
    if marks:
        mirror.their_emoji_rate = _percent(sum(1 for t, _, _ in rows if t[1]), n)
        mirror.their_exclamation_rate = _percent(sum(1 for t, _, _ in rows if t[2]), n)
        mirror.emoji_if_they, mirror.emoji_if_not = conditional(1)
        mirror.exclamation_if_they, mirror.exclamation_if_not = conditional(2)
        used = Counter(ch for _, _, me in rows for ch in _EMOJI_RE.findall(me))
        mirror.user_emoji = [e for e, _ in used.most_common(4)]
    return mirror


def reply_target(profile: Optional[UserVoiceProfile], incoming: str) -> Optional[ReplyTarget]:
    """What this reply should look like, from what they just sent and the fitted mirroring."""
    mirror = profile.mirror if profile else None
    text = _clean(incoming)
    if mirror is None or not text:
        return None
    chars, emoji, bang, script = _marks(text)
    base = profile.reply_median_chars or profile.median_chars or 20
    slope = max(0.0, min(1.0, mirror.length_slope))
    ratio = max(0.6, min(1.6, (max(1, chars) / max(1, mirror.their_median_chars)) ** slope))
    target = ReplyTarget(
        chars=max(2, round(base * ratio)),
        emoji=False,
        emoji_percent=0,
        exclamation='rare',
        exclamation_percent=0,
        their_chars=chars,
        their_emoji=emoji,
        their_exclamation=bang,
    )
    if mirror.marks_measured:
        target.emoji_percent = mirror.emoji_if_they if emoji else mirror.emoji_if_not
        target.emoji = target.emoji_percent >= EMOJI_REPLY_PERCENT
        target.exclamation_percent = mirror.exclamation_if_they if bang else mirror.exclamation_if_not
        if target.exclamation_percent >= EXCLAMATION_ONE_PERCENT:
            target.exclamation = 'one'
        elif target.exclamation_percent < EXCLAMATION_NONE_PERCENT:
            target.exclamation = 'none'
    if script and mirror.same_script >= SAME_SCRIPT_PERCENT:
        target.script, target.script_percent = script, mirror.same_script
    return target


# Omi's own conversation categories (models.conversation_enums.CategoryEnum) that mark a work relationship.
WORK_CATEGORIES = frozenset({'work', 'business', 'entrepreneurship', 'finance', 'legal', 'economics', 'technology', 'design'})
PERSONAL_CATEGORIES = frozenset(
    {'personal', 'social', 'family', 'romantic', 'parenting', 'entertainment', 'sports', 'music', 'travel', 'health', 'inspiration'}
)
WORK_SHARE_PERCENT = 20
_WORK_WORDS_RE = re.compile(
    r'\b(invoice|payment|contract|client|interview|recruit\w*|resume|deadline|deliverable|meeting|office|project|'
    r'specs?|salary|offer|report|schedule|candidates?|website)\b|会议|會議|合同|报告|報告|客户|網站|网站',
    re.IGNORECASE,
)


def infer_register(categories: Iterable[str], pairs: list[tuple[str, str]]) -> tuple[Optional[str], str]:
    """'work' or 'personal' for this person: Omi's conversation categories first, then work words."""
    cats = [str(c).lower() for c in categories if c]
    work = sum(1 for c in cats if c in WORK_CATEGORIES)
    personal = sum(1 for c in cats if c in PERSONAL_CATEGORIES)
    if work + personal >= 3:
        share = _percent(work, work + personal)
        if share >= 60:
            return 'work', f'{share}% of your conversations with them are work'
        if share <= 40:
            return 'personal', f'{100 - share}% of your conversations with them are personal'
    if pairs:
        share = _percent(sum(1 for a, b in pairs if _WORK_WORDS_RE.search(a) or _WORK_WORDS_RE.search(b)), len(pairs))
        return ('work', f'work words in {share}% of your exchanges') if share >= WORK_SHARE_PERCENT else (
            'personal',
            f'work words in only {share}% of your exchanges',
        )
    return None, ''


def _grams(text: str) -> set[str]:
    """Character bigrams, case-folded: works the same for Latin and Han text."""
    t = ''.join(ch for ch in text.casefold() if ch.isalnum() or ch == ' ')
    return {t[i : i + 2] for i in range(len(t) - 1)} if len(t) > 1 else {t} if t else set()


def pick_shots(profile: UserVoiceProfile, incoming: str = '', k: int = USER_VOICE_SHOTS) -> list[VoiceExchange]:
    """Past exchanges to show: the closest to what they just said, plus the newest; oldest first."""
    pool = profile.exchanges
    if not pool:
        return []
    chosen = set(range(max(0, len(pool) - USER_VOICE_RECENT_SHOTS), len(pool)))
    wanted = _grams(incoming)
    if wanted:
        def score(i: int) -> float:
            have = _grams(pool[i].them)
            return len(wanted & have) / (len(wanted | have) or 1)

        for i in sorted(range(len(pool)), key=score, reverse=True):
            if len(chosen) >= k:
                break
            chosen.add(i)
    else:
        chosen = set(range(max(0, len(pool) - k), len(pool)))
    return [pool[i] for i in sorted(chosen)]


# ---------------------------------------------------------------------------
# Using the profile (pure)
# ---------------------------------------------------------------------------


def _rare_endings(profile: UserVoiceProfile) -> list[str]:
    return [k for k in ('.', '!') if profile.endings.get(k, 0) < RARE_ENDING_PERCENT]


def allowed_exclamations(profile: Optional[UserVoiceProfile]) -> int:
    if profile is None or not profile.is_reliable:
        return 1
    if profile.exclamation_rate < RARE_ENDING_PERCENT:
        return 0
    return 2 if profile.exclamations_per_line > 1.2 else 1


def profile_prompt_block(
    profile: Optional[UserVoiceProfile], incoming: str = '', thread: Iterable[dict] = ()
) -> str:
    """Instructions for the drafting model; empty when there is no profile.

    ``thread`` is the open conversation with this person, oldest first, as
    ``{'is_user': bool, 'text': str}`` (written source only); ``incoming`` is what
    they said last, used to pick the closest past exchanges.
    """
    if profile is None:
        return ''
    name = profile.person_name
    if not profile.is_reliable:
        return (
            f"Draft to {name} as the user. Few of the user's own lines with {name} are on record, "
            "so keep it short and plain, like a text, not a letter."
        )
    lines = [
        f"Write the message as the user writes to {name} (from {profile.lines} of the user's own lines "
        "with them). Copy this voice, not a generic assistant voice:"
    ]
    if profile.scripts:
        mix = ', '.join(f'{script} {pct}%' for script, pct in profile.scripts.items())
        main_script, main_pct = next(iter(profile.scripts.items()))
        advice = (
            f'write in {main_script} script unless the user asked otherwise'
            if main_pct >= 50
            else 'either is natural with them; follow the language the user used in this request'
        )
        lines.append(f'- lines by script: {mix}; {advice}')
    ends = ', '.join(f'{_ENDING_WORDS.get(k, k)} {v}%' for k, v in list(profile.endings.items())[:3])
    rare = [_ENDING_WORDS[k] for k in _rare_endings(profile)]
    lines.append(f'- lines end with: {ends}' + (f"; almost never {' or '.join(rare)}" if rare else ''))
    limit = allowed_exclamations(profile)
    lines.append(f'- "!" in {profile.exclamation_rate}% of lines; use at most {limit}')
    lines.append(f'- emoji in {profile.emoji_rate}% of lines' + ('; use none' if profile.emoji_rate == 0 else ''))
    if profile.lowercase_start_rate >= 60:
        lines.append(f'- starts lines lowercase ({profile.lowercase_start_rate}%)')
    if profile.stretch_rate >= 10:
        lines.append(
            f'- stretches a word ("okk", "heyyy") in {profile.stretch_rate}% of lines; most lines have none, '
            'so at most one stretched word and only where the replies below would'
        )
    lines.append(
        f'- length: usually about {profile.median_chars} characters (90% under {profile.p90_chars}); '
        'as short as the user would send it, often a fragment, never padded with extra pleasantries'
    )
    if profile.greetings and profile.greeting_rate >= GREETING_MIN_PERCENT:
        lines.append(f"- opens with a greeting in {profile.greeting_rate}% of lines: {', '.join(profile.greetings)}")
    else:
        lines.append('- almost never opens with a greeting or their name; start with the point')
    if profile.examples:
        quoted = ' / '.join(f'"{e}"' for e in profile.examples)
        lines.append(f'- the user\'s own recent lines (style only, never copy facts from them): {quoted}')
    if profile.phrases:
        quoted = ' / '.join(f'"{e}"' for e in profile.phrases)
        lines.append(f'- words and phrases that are the user\'s own (use one only where it fits naturally): {quoted}')
    if profile.stock_replies:
        quoted = ' / '.join(f'"{e}"' for e in profile.stock_replies)
        lines.append(f'- short replies the user sends {name} again and again: {quoted}')
    shots = pick_shots(profile, incoming)
    if shots:
        lines.append(
            f'- how the user actually answered {name} before (copy the wording, slang, spelling, '
            'length and language of these replies; never their facts):'
        )
        lines.extend(f'    {name}: {e.them}  ->  user: {e.me}' for e in shots)
    tail = [t for t in thread if isinstance(t, dict) and _clean(t.get('text'))][-USER_VOICE_MAX_THREAD:]
    if tail:
        lines.append('- the open thread, oldest first (reply to the last message):')
        lines.extend(f"    {'user' if t.get('is_user') else name}: {_clean(t.get('text'))}" for t in tail)
    aim = reply_target(profile, incoming)
    target = aim.chars if aim else (profile.reply_median_chars or profile.median_chars)
    lines.append(
        "- the user's request gives the MEANING, not the words: its wording is an assistant's, so do not "
        f'reuse it; say it the way the user would to {name}, with the plain everyday words, slang and '
        f'spelling of the replies above, about {target} characters, nothing added (no explanations, '
        'no extra pleasantries, no "already"/"just"/"really" padding)'
    )
    if profile.voice_register == 'work':
        lines.append(
            f'- register: work ({profile.voice_register_reason}): practical and direct, the point first; no pet '
            'names or in-jokes; warmth only the way the replies above show it'
        )
    elif profile.voice_register == 'personal':
        lines.append(
            f'- register: personal ({profile.voice_register_reason}): the casual voice of the replies above; '
            'pet names, slang and stretched words only the ones they use'
        )
    mirror = profile.mirror
    if aim and mirror:
        said = f'{aim.their_chars} characters' + (', an emoji' if aim.their_emoji else '') + (', "!"' if aim.their_exclamation else '')
        parts = [f'- match {name} the way the user does (fitted on {mirror.exchanges} real replies): they just sent {said}']
        if mirror.marks_measured:
            if aim.emoji:
                mine = f" ({' '.join(mirror.user_emoji)})" if mirror.user_emoji else ''
                parts.append(f'one emoji of the user\'s own fits{mine}: they answer like this {aim.emoji_percent}% of the time')
            else:
                parts.append(f'no emoji (the user adds one {aim.emoji_percent}% of the time here)')
            if aim.exclamation == 'one':
                parts.append(f'one "!" fits ({aim.exclamation_percent}% of replies here)')
            elif aim.exclamation == 'none':
                parts.append(f'no "!" ({aim.exclamation_percent}%)')
        if aim.script:
            parts.append(f'answer in {aim.script} script like their message ({aim.script_percent}% of the time)')
        lines.append('; '.join(parts))
    habit = profile.reactions
    tap = suggest_reaction(profile)
    if habit and tap:
        only = 100 - habit.reply_rate
        lines.append(
            f'- the user also reacts to {name}\'s last message in {habit.rate}% of answers, mostly "{tap}"'
            + (f', and answers with the reaction alone {only}% of the time' if only >= 10 else '')
            + '; offer that reaction to the user alongside the draft (the compose sheet cannot leave it)'
        )
    return '\n'.join(lines)


def polish_draft(text: str, profile: Optional[UserVoiceProfile]) -> PolishResult:
    """Fix marks toward the user's voice. Never changes, adds or drops words."""
    result = PolishResult(text=text or '')
    if not result.text.strip() or profile is None or not profile.is_reliable:
        return result
    draft = result.text.strip()
    full_width = _dominant_script(draft) in _FULL_WIDTH_SCRIPTS

    # 1. "!" count: keep the last ones, calm the earlier ones to a stop.
    allowed = allowed_exclamations(profile)
    count = len(_BANG_RE.findall(draft))
    if count > allowed:
        surplus = count - allowed

        def calm(match: re.Match) -> str:
            nonlocal surplus
            if surplus <= 0:
                return match.group(0)
            surplus -= 1
            rest = draft[match.end() :]
            if rest.strip() and not _BANG_RE.sub('', rest).strip():
                return ''  # part of a final "!!" run whose last mark stays
            if not rest.strip():
                # The last "!" becomes the user's usual stop to this person, if they use one.
                if profile.endings.get('.', 0) < RARE_ENDING_PERCENT:
                    return ''
                return '\u3002' if full_width else '.'
            return '，' if match.group(0) == '！' or full_width else '.'

        draft = _BANG_RE.sub(calm, draft)
        result.changes.append(f'"!" {count} -> {allowed}')

    # 2. The last line ends the way the user ends lines to this person. Only a
    #    short single-line text: an email keeps its full stops.
    if '\n' not in draft and len(draft) < 300:
        ending = line_ending(draft)
        if ending == '.' and profile.endings.get('.', 0) < RARE_ENDING_PERCENT:
            preferred = next((k for k in profile.endings if k in ('none', '!')), 'none')
            if preferred == '!' and len(_BANG_RE.findall(draft)) >= allowed:
                preferred = 'none'
            replacement = '' if preferred == 'none' else ('！' if full_width else '!')
            draft = re.sub(r'[.。]\s*$', replacement, draft)
            result.changes.append(f'last "." -> {"no mark" if preferred == "none" else repr(replacement)}')

    result.text = draft.strip()
    return result


def match_person(contact_name: str, people: Iterable[dict]) -> Optional[dict]:
    """The one Omi person a device contact refers to, or None when unsure.

    Omi people are usually named the way the user says them ("Ada"), contacts by
    full name ("Ada Lovelace"). Exact full-name matches win; otherwise a unique
    first-name match. Two candidates means we do not guess.
    """
    wanted = ' '.join(str(contact_name or '').split()).casefold()
    if not wanted:
        return None
    named = [p for p in people if p.get('name') and not p.get('is_dismissed')]
    exact = [p for p in named if ' '.join(p['name'].split()).casefold() == wanted]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    first = wanted.split(' ', 1)[0]
    by_first = [p for p in named if ' '.join(p['name'].split()).casefold() == first]
    return by_first[0] if len(by_first) == 1 else None


# ---------------------------------------------------------------------------
# Reading the user's lines and the cache (IO)
# ---------------------------------------------------------------------------


def is_user_voice_enabled(uid: str) -> bool:
    settings = users_db.get_assistant_settings(uid) or {}
    drafts = settings.get('drafts')
    return isinstance(drafts, dict) and drafts.get('user_voice') is True


def user_lines_with_person(conversations: Iterable[dict], person_id: str) -> list[str]:
    """The user's own segments in conversations where ``person_id`` speaks, oldest first."""
    lines: list[tuple[Any, float, str]] = []
    for conversation in conversations:
        if conversation.get('is_locked') or conversation.get('discarded') or conversation.get('deleted'):
            continue
        segments = conversation.get('transcript_segments') or []
        if not any(s.get('person_id') == person_id and not s.get('is_user') for s in segments):
            continue
        started = conversation.get('started_at') or conversation.get('created_at') or ''
        for segment in segments:
            if segment.get('is_user') and segment.get('text'):
                lines.append((str(started), float(segment.get('start') or 0), segment['text']))
    lines.sort(key=lambda item: (item[0], item[1]))
    return [text for _, _, text in lines]


def _with_person(conversations: Iterable[dict], person_id: str) -> list[dict]:
    keep = []
    for conversation in conversations:
        if conversation.get('is_locked') or conversation.get('discarded') or conversation.get('deleted'):
            continue
        segments = conversation.get('transcript_segments') or []
        if any(s.get('person_id') == person_id and not s.get('is_user') for s in segments):
            keep.append(conversation)
    return keep


def spoken_exchanges_with_person(conversations: Iterable[dict], person_id: str) -> list[tuple[str, str]]:
    """(what that person said, what the user said next) turns in conversations with them, oldest first."""
    pairs: list[tuple[Any, tuple[str, str]]] = []
    for conversation in _with_person(conversations, person_id):
        started = str(conversation.get('started_at') or conversation.get('created_at') or '')
        segments = sorted(conversation.get('transcript_segments') or [], key=lambda s: float(s.get('start') or 0))
        for prev, seg in zip(segments, segments[1:]):
            if seg.get('is_user') and not prev.get('is_user') and prev.get('person_id') == person_id:
                if prev.get('text') and seg.get('text'):
                    pairs.append((started, (prev['text'], seg['text'])))
    pairs.sort(key=lambda item: item[0])
    return [pair for _, pair in pairs][-USER_VOICE_MAX_EXCHANGES:]


def categories_with_person(conversations: Iterable[dict], person_id: str) -> list[str]:
    """Omi's own category for each conversation with that person."""
    out = []
    for conversation in _with_person(conversations, person_id):
        category = (conversation.get('structured') or {}).get('category')
        if category:
            out.append(str(getattr(category, 'value', category)))
    return out


def typed_user_lines(messages: Iterable[dict]) -> list[str]:
    """What the user typed to Omi, oldest first (newest-first pages are reversed)."""
    typed = [
        m.get('text') or ''
        for m in messages
        if m.get('sender') == 'human' and (m.get('type') or 'text') == 'text' and m.get('text')
    ]
    return list(reversed(typed))


def user_written_lines(uid: str, person: dict) -> list[str]:
    """Messages the user wrote to this person, oldest first, where the platform can read them.

    Omi has no such source today (iOS gives apps no access to sent messages), so this
    returns nothing; a client that can read them with the user's permission (Android
    SMS, macOS Messages) fills it, and the profile prefers it over everything else.
    Text the assistant drafted must not be passed: it is not the user's voice.
    """
    return []


def user_written_exchanges(uid: str, person: dict) -> list[tuple[str, str]]:
    """Past (their message, the user's reply) pairs with this person, oldest first.

    Same source and rules as ``user_written_lines``: empty unless the platform can
    read the user's sent messages, and never text the assistant drafted.
    """
    return []


def user_written_thread(uid: str, person: dict) -> list[dict]:
    """The thread with this person, oldest first, as ``{'is_user', 'text'}``; empty by default.

    Reactions the user left come as their own items, ``{'is_user': True, 'reaction': kind}``
    (see ``fit_reactions``); the profile prompt shows only the text items.
    """
    return []


def _cache_key(uid: str, person_id: str) -> str:
    return f'user_voice:{uid}:{person_id}'


def _read_cached(uid: str, person_id: str) -> Optional[UserVoiceProfile]:
    raw = redis_client.get(_cache_key(uid, person_id))
    if not raw:
        return None
    try:
        data = json.loads(decrypt(raw.decode() if isinstance(raw, bytes) else raw, uid))
        profile = UserVoiceProfile.model_validate(data)
    except Exception:
        return None
    return profile if profile.version == USER_VOICE_PROFILE_VERSION else None


def _write_cached(uid: str, profile: UserVoiceProfile) -> None:
    payload = encrypt(profile.model_dump_json(), uid)
    redis_client.setex(_cache_key(uid, profile.person_id), USER_VOICE_CACHE_TTL_SECONDS, payload)


def invalidate_user_voice(uid: str, person_id: str) -> None:
    redis_client.delete(_cache_key(uid, person_id))


def get_user_voice_profile(uid: str, person: dict) -> UserVoiceProfile:
    """The cached profile for this person, rebuilt when missing or a week old."""
    person_id = person['id']
    cached = _read_cached(uid, person_id)
    if cached is not None:
        return cached
    conversations = conversations_db.get_conversations(uid, limit=USER_VOICE_MAX_CONVERSATIONS)
    messages = chat_db.get_messages(uid, limit=USER_VOICE_MAX_TYPED_MESSAGES)
    profile = build_profile(
        person_id,
        person.get('name') or '',
        user_lines_with_person(conversations, person_id),
        typed_user_lines(messages),
        written_lines=user_written_lines(uid, person),
        exchanges=user_written_exchanges(uid, person),
        spoken_exchanges=spoken_exchanges_with_person(conversations, person_id),
        categories=categories_with_person(conversations, person_id),
        thread=user_written_thread(uid, person),
    )
    _write_cached(uid, profile)
    return profile


# ---------------------------------------------------------------------------
# The propose_message seam
# ---------------------------------------------------------------------------

# A contact search can return many people; only the first few get a profile.
USER_VOICE_MAX_CONTACTS = 3


def handle_key(handle: Any) -> Optional[str]:
    """Compare phone numbers by their last ten digits and emails case-insensitively."""
    value = str(handle or '').strip()
    if '@' in value:
        return value.casefold()
    digits = re.sub(r'\D', '', value)
    return digits[-10:] if len(digits) >= 7 else None


def _contact_handles(contact: dict) -> list[str]:
    raw = [contact.get('preferred_messaging_handle')]
    for field in ('phone_numbers', 'email_addresses'):
        raw.extend(entry.get('value') for entry in contact.get(field) or [] if isinstance(entry, dict))
    return [key for key in (handle_key(h) for h in raw) if key]


def annotate_contacts_with_voice(uid: str, result: dict) -> dict[str, UserVoiceProfile]:
    """Attach ``user_voice`` to contacts that are known people; return profiles by handle.

    Runs on the ``search_contacts`` result, so the guidance reaches the model in
    the same turn, just before it writes the ``propose_message`` body.
    """
    contacts = result.get('contacts') if result.get('ok') else None
    if not contacts or not is_user_voice_enabled(uid):
        return {}
    people = users_db.get_people(uid)
    voices: dict[str, UserVoiceProfile] = {}
    for contact in contacts[:USER_VOICE_MAX_CONTACTS]:
        if not isinstance(contact, dict):
            continue
        person = match_person(contact.get('name') or '', people)
        if person is None:
            continue
        profile = get_user_voice_profile(uid, person)
        thread = user_written_thread(uid, person)
        incoming = ' / '.join(_clean(t.get('text')) for t in _last_run(thread))
        contact['user_voice'] = profile_prompt_block(profile, incoming, thread)
        profile = profile.model_copy(update={'incoming': incoming})
        for key in _contact_handles(contact):
            voices[key] = profile
    return voices


def _last_run(thread: list[dict]) -> list[dict]:
    """Their messages since the user last wrote."""
    run: list[dict] = []
    for item in reversed(thread or []):
        if not isinstance(item, dict) or item.get('is_user'):
            break
        run.insert(0, item)
    return run


def profile_for_recipients(voices: dict[str, UserVoiceProfile], to: Iterable[str]) -> Optional[UserVoiceProfile]:
    """The profile for a one-person message; a group message is left as written."""
    found = {id(p): p for p in (voices.get(handle_key(h) or '') for h in to or []) if p is not None}
    recipients = [h for h in to or [] if str(h).strip()]
    if len(found) != 1 or len(recipients) != 1:
        return None
    return next(iter(found.values()))
