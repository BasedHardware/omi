"""Deterministic quality policy shared by shadow planning and effect validation."""

from collections import Counter
import re
import unicodedata

from models.dream_agent import Plan

# Code-configurable threshold; no rollout/environment switch changes admission.
MIN_SUMMARY_TRANSCRIPT_WORDS = 40
FEEDBACK_PER_PASS = 1


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
        reason = None
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
    return plan.model_copy(update={'edits': edits, 'feedback': feedback})


def cap_feedback(feedback, *, usage_sink):
    extra = max(0, len(feedback) - FEEDBACK_PER_PASS)
    if extra:
        counts = Counter(usage_sink.get('rejected', {}))
        counts['feedback_cap'] += extra
        usage_sink['rejected'] = dict(counts)
    return feedback[:FEEDBACK_PER_PASS]
