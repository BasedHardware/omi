"""Deterministic quality policy shared by shadow planning and effect validation."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
import re
import unicodedata

from models.dream_agent import Plan

# Code-configurable threshold; no rollout/environment switch changes admission.
MIN_SUMMARY_TRANSCRIPT_WORDS = 40
FEEDBACK_PER_PASS = 1
MIN_RETIRE_TASK_DAYS = 7
SPELLING_COLLECTIONS = {'conversations', 'people', 'memories', 'memory_items'}


def timestamp(value):
    """Storage datetimes and ISO strings share UTC semantics; unknown times cannot authorize edits."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def task_rejection(edit, row, records, *, now=None):
    if edit.kind not in {'close_task', 'retire_task'}:
        return None
    times = [timestamp(row.get(field)) for field in ('created_at', 'updated_at') if row.get(field) is not None]
    if not times or any(time is None for time in times):
        return 'stale_task_evidence'
    latest = max(time for time in times if time is not None)
    sources = {edit.target}
    if row.get('conversation_id'):
        sources.add('conversations/' + row['conversation_id'].removeprefix('conversations/'))
    for source in row.get('provenance') or []:
        if source.get('kind') == 'conversation':
            sources.add('conversations/' + source['id'])
    for ref in edit.evidence:
        if ref in sources or ref not in records:
            continue
        evidence = records[ref]
        # Creation/capture time, not a later metadata refresh of an old conversation.
        time = timestamp(evidence.get('created_at') or evidence.get('timestamp') or evidence.get('updated_at'))
        if time is not None and time > latest:
            break
    else:
        return 'stale_task_evidence'
    if edit.kind == 'retire_task':
        created = timestamp(row.get('created_at'))
        if created is None or (now or datetime.now(timezone.utc)) - created <= timedelta(days=MIN_RETIRE_TASK_DAYS):
            return 'task_too_recent'
    return None


def spelling_rejection(edit):
    if edit.kind != 'spelling':
        return None
    collection, separator, key = edit.target.partition('/')
    if collection not in SPELLING_COLLECTIONS or not separator or not key or '/' in key:
        return 'bad_target'
    return None


@lru_cache(maxsize=1)
def common_words():
    return frozenset((Path(__file__).parent / 'data' / 'common_english_words.txt').read_text(encoding='utf-8').split())


def vocabulary_rejection(term):
    word = term.spelling.strip().lower()
    if term.kind == 'jargon' and re.fullmatch(r'[a-z]+', word) and word in common_words():
        return 'common_word'
    return None


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c)).replace(
        'đ', 'd'
    )


def tokens(text):
    return re.findall(r'[^\W_]+', normalized(text))


PLACEHOLDER = re.compile(
    r'\b(?:missing|untitled|unknown|no (?:content|discernible|speech|transcript|information)|'
    r'not available|not enough|insufficient|empty|no (?:meaningful|clear|useful)|n a|this conversation|the conversation|'
    r'(?:title|overview|summary) (?:added|updated|generated|created)|'
    r'(?:title|overview|summary) (?:is|was|has)|'
    r'khong (?:co|ro|biet|du|xac dinh)|chua (?:co|xac dinh)|thieu (?:tieu de|noi dung)|'
    r'cuoc (?:tro chuyen|hoi thoai) nay)\b|'
    r'^(?:conversation|conversations|cuoc tro chuyen|cuoc hoi thoai)$'
)
LANGUAGE = re.compile(
    r'\b(?:language(?:s)?|translation|translat\w*|non english|nonenglish|bilingual|multilingual|'
    r'english|vietnamese|code switch\w*|mixed (?:speech|tongue\w*)|'
    r'ngon ngu|chuyen ngu|dich|tieng (?:anh|viet)|song ngu|da ngu|tron tieng|xen ke)\b'
)
NON_FAILURE = re.compile(
    r'\b(?:(?:is|are|was|were|remains?|appears?|looks?|seems?) '
    r'(?:(?:fully|entirely|already|completely|perfectly|all) )?'
    r'(?:fine|accurate|correct|valid|ok|okay|good|working correctly)|'
    r'no (?:issues?|errors?|problems?|defects?|failures?|edits?)|'
    r'nothing (?:is wrong|needs (?:editing|fixing|correction))|all good|'
    r'(?:does not|do not|doesn t|don t) (?:require|need) (?:any )?'
    r'(?:edits?|changes?|corrections?|fixes?)|'
    r'accurately (?:captures?|reflects?|transcribes?)|'
    r'khong co (?:van de|loi|sai sot)|'
    r'khong (?:can|yeu cau) (?:bat ky )?(?:chinh sua|sua doi|sua|thay doi)|'
    r'(?:moi thu|tat ca) (?:deu )?(?:on|tot|dung)|'
    r'(?:ban chep|ban ghi|noi dung|loi noi) (?:hoan toan )?(?:chinh xac|dung)|'
    r'(?:la|van|deu|hoan toan) (?:chinh xac|on|dung))\b|'
    r'^(?:fine|accurate|correct|valid|ok|okay|chinh xac)\b'
)
RECORD_REF = re.compile(
    r'\b[a-z_]+/[0-9a-f-]{8,}\b|' r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
    re.IGNORECASE,
)


def summary_rejection(edit, row, *, min_words=None):
    if edit.kind not in {'title', 'overview'}:
        return None
    current = (row.get('structured') or {}).get(edit.kind) or ''
    has_content = bool(current) if edit.kind == 'title' else bool(current.strip())
    if has_content or (edit.kind == 'title' and row.get('user_title')):
        return 'nonempty_field'
    # Sections can be the visible overview even when its compatibility field is blank.
    if edit.kind == 'overview' and (row.get('structured') or {}).get('sections'):
        return 'nonempty_field'
    speech = ' '.join((s.get('text') or '') for s in row.get('transcript_segments') or [])
    if len(tokens(speech)) < (MIN_SUMMARY_TRANSCRIPT_WORDS if min_words is None else min_words):
        return 'insufficient_speech'
    after_words = tokens(edit.after)
    if len(after_words) < (3 if edit.kind == 'title' else 8) or PLACEHOLDER.search(' '.join(after_words)):
        return 'placeholder'
    if edit.kind == 'title' and not set(after_words).intersection(tokens(speech)):
        return 'ungrounded'
    if edit.kind == 'overview':
        # render_sections_markdown emits ## heading and a blank line; the notes prompt requires - bullets.
        # Require at least one complete section, and no prose preceding the first heading.
        if not re.fullmatch(r'## [^\n]+\n\n- \S[\s\S]*', edit.after.strip()):
            return 'overview_format'
    return None


def feedback_rejection(feedback):
    if (
        feedback.failure_class in {'success', 'none', 'ok'}
        or feedback.severity == 'info'
        or NON_FAILURE.search(' '.join(tokens(feedback.reproduction)))
    ):
        return 'not_a_failure'
    text = ' '.join((feedback.component, feedback.failure_class, feedback.reproduction))
    if LANGUAGE.search(' '.join(tokens(text))):
        return 'language_not_defect'
    if RECORD_REF.search(feedback.reproduction):
        return 'ref_leak'
    return None


def filter_plan(plan: Plan, records, *, usage_sink=None):
    """Drop unsafe proposals before any report persistence; diagnostics contain counts only."""
    rejected = Counter()
    edits = []
    for edit in plan.edits:
        reason = spelling_rejection(edit)
        if edit.kind in {'close_task', 'retire_task'}:
            reason = (
                'invalid_evidence'
                if edit.target not in records or any(ref not in records for ref in edit.evidence)
                else task_rejection(edit, records[edit.target], records)
            )
        if edit.kind in {'title', 'overview'}:
            reason = (
                'invalid_evidence'
                if edit.target not in records or any(ref not in records for ref in edit.evidence)
                else summary_rejection(edit, records[edit.target])
            )
        if reason:
            rejected[reason] += 1
        else:
            edits.append(edit)
    vocabulary = []
    for term in plan.vocabulary:
        reason = vocabulary_rejection(term)
        if reason:
            rejected[reason] += 1
        else:
            vocabulary.append(term)
    feedback = []
    for item in plan.feedback:
        reason = feedback_rejection(item)
        if reason:
            rejected[reason] += 1
        else:
            feedback.append(item)
    if usage_sink is not None:
        counts = Counter(usage_sink.get('rejected', {}))
        counts.update(rejected)
        usage_sink['rejected'] = dict(counts)
    return plan.model_copy(update={'edits': edits, 'vocabulary': vocabulary, 'feedback': feedback})


def cap_feedback(feedback, *, usage_sink):
    extra = max(0, len(feedback) - FEEDBACK_PER_PASS)
    if extra:
        counts = Counter(usage_sink.get('rejected', {}))
        counts['feedback_cap'] += extra
        usage_sink['rejected'] = dict(counts)
    return feedback[:FEEDBACK_PER_PASS]
