"""Reduce a bounded Home cohort to content-free observations and review prompts."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from config.episodes import home_step_projection_enabled
from config.summary_guarantee import deadline_seconds
from models.conversation_emoji import DEFAULT_EMOJI, NEUTRAL_EMOJI
from utils.conversations import home_step, summary_delivery, transcribing_hold
from utils.conversations.fragment_visibility import (
    held_for_notes,
    is_completed_below_floor,
    is_completed_rule_discard,
    is_settling_fragment,
)
from utils.conversations.home_titles import is_fallback_title, summary_owed
from utils.enrichment import age_gate
from utils.home_feed import card_content
from utils.summary_quality import safe_body
from utils.sync import bridge_pending

STATUSES = ('completed', 'in_progress', 'processing', 'merging', 'failed')
LANES = ('batch_live_v1', 'batch_sync_v1')

# Read card text only after the protection check at the same snapshot.
CARD_FIELDS = (
    'user_title',
    'user_overview',
    'structured.title',
    'structured.gist',
    'structured.overview',
    'structured.emoji',
    'structured.title_provenance',
)

METADATA_FIELDS = tuple(
    dict.fromkeys(
        (
            *(name for name in transcribing_hold.READ_FIELDS if name != 'user_title'),
            'started_at',
            'finished_at',
            'data_protection_level',
            'private_cloud_sync_enabled',
            'uses_custom_stt',
            'processing_state',
            'terminal_no_derived_effects',
            'client_processing',
            'deferred',
            'deleted',
            'discarded',
            'recording',
            'home_hidden',
            'dream_duplicate_of',
            'sync_merged_into',
            'sync_bridge_pending',
            'sync_relevance',
            'sync_processing_hold.held',
            'sync_processing_hold.last_content_at',
            'v3_derived',
            'has_photos',
            'record_transcription_empty',
            'record_audio_partial',
            'record_audio_closed',
            'server_batch_audio_start',
            'server_batch_audio_end',
            'starred',
            'folder_user_set',
            'sync_relevance_user_kept',
            'relevance_decision.verdict',
            'relevance_decision.reason',
            'relevance_decision.decided_by',
            'summary_title_provenance',
            'structured.title_provenance',
            'summary_output_present',
            'summary_completed_at',
            'notes_written_at',
            'summary_due_at',
            'summary_first_pending_at',
            'summary_blocked_reason',
            'summary_retryable',
            'home_content_invalidated',
        )
    )
)

MIN_REPORT_OWNERS = 5
REPEATED_CARDS = 3
ROW_CATEGORIES = (
    'terminal_without_derivatives',
    'protected_or_unknown',
    'hidden_by_design',
    'in_progress',
    'display_unknown',
    'processing',
    'classified_captures',
)


@dataclass(frozen=True)
class Symptom:
    denominator: str
    stage: str
    description: str
    drill_down: str


SYMPTOMS = {
    'capture_not_completed': Symptom(
        'in_progress',
        'capture_seal',
        'A finished capture still appears unfinished after two hours.',
        'Compare capture-end and seal/finalization receipts.',
    ),
    'transcript_wait_expired': Symptom(
        'transcript_expected',
        'batch_transcription',
        'The transcription wait expired without a batch transcript receipt.',
        'Compare seal, batch job, and transcript projection outcomes.',
    ),
    'notes_not_scheduled': Symptom(
        'notes_expected',
        'summary_admission',
        'Speech landed without a notes delivery receipt or a scheduled notes deadline.',
        'Check missing-debt eligibility and summary admission outcomes.',
    ),
    'notes_outside_repair_window': Symptom(
        'notes_expected',
        'summary_delivery',
        'Notes are missing and the capture is past automatic repair age.',
        'Review older cohorts separately from bounded repair candidates.',
    ),
    'notes_overdue': Symptom(
        'notes_expected',
        'summary_delivery',
        'Notes are still missing after their scheduled deadline.',
        'Check debt age, capacity, and summary repair outcomes.',
    ),
    'processing_expired': Symptom(
        'processing',
        'conversation_finalization',
        'A processing or merging capture exceeded the Home waiting limit.',
        'Check lifecycle and projection outcome metrics.',
    ),
    'capture_failed': Symptom(
        'classified_captures',
        'conversation_finalization',
        'A capture could not produce a ready Home card.',
        'Check the terminal capture, transcription, and finalization outcome counts.',
    ),
    'ready_card_blank': Symptom(
        'ready_cards',
        'home_presentation',
        'A ready card has neither a readable title nor a preview.',
        'Compare the Home step and the card fields returned by the list reader.',
    ),
    'ready_title_missing': Symptom(
        'ready_cards',
        'home_presentation',
        'A ready card has no readable title.',
        'Check title provenance and the Home title projection.',
    ),
    'ready_title_generic': Symptom(
        'ready_cards',
        'notes_title',
        'A ready card has a generated fallback title.',
        'Compare fallback-title rates with notes completion.',
    ),
    'summary_without_preview': Symptom(
        'summary_receipted_cards',
        'home_presentation',
        'A ready card has a summary receipt but no preview line.',
        'Check preview projection and section-only summary output.',
    ),
    'ready_emoji_missing': Symptom(
        'ready_cards',
        'home_presentation',
        'A ready card has no stored display emoji.',
        'Compare the notes output with the product emoji default.',
    ),
    'ready_emoji_default': Symptom(
        'summary_receipted_cards',
        'notes_emoji',
        'A summarized card uses a default or neutral emoji.',
        'Track repeated defaults as a quality signal. The neutral emoji can be intentional.',
    ),
}


def _has_text(value):
    return isinstance(value, str) and bool(value.strip())


def positive_revision(value):
    return type(value) is int and value > 0


def _presented(row, step, now):
    manual_title = row.get('user_title')
    structured = row.get('structured')
    if _has_text(manual_title):
        row = {**row, 'structured': {**(structured or {}), 'title': manual_title}}
    projected = transcribing_hold.project({**row, 'home_step': step}, now=now, home_list=True)
    return card_content.content(projected, 'conversation')


def hidden_by_metadata(row):
    return any(
        row.get(key)
        for key in (
            'deleted',
            'discarded',
            'recording',
            'home_hidden',
            'sync_merged_into',
            'dream_duplicate_of',
            'v3_derived',
        )
    )


def _hidden_by_rules(row):
    return bridge_pending.hidden(row) or is_completed_rule_discard(row) or is_completed_below_floor(row)


def needs_title_for_visibility(row):
    return _hidden_by_rules(row) or is_settling_fragment(row, show_held=True)


def hidden_for_review(row, *, show_held=False):
    # Keep lifecycle failures observable while honoring the list's discard,
    # bridge and settling policies. V3-owned products are outside this cohort.
    return (
        hidden_by_metadata(row)
        or _hidden_by_rules(row)
        or (is_settling_fragment(row, show_held=show_held) and not transcribing_hold.applies(row, stored=True))
    )


def protected_for_review(row):
    return (
        row.get('data_protection_level') not in {'standard', 'enhanced'}
        or row.get('is_locked')
        or row.get('private_cloud_sync_enabled') is not True
        or row.get('uses_custom_stt')
        or row.get('deferred')
        or row.get('processing_state') == 'local_pending'
        or row.get('terminal_no_derived_effects')
        or row.get('client_processing')
    )


def inspect_row(row, *, now: datetime) -> tuple[set[str], set[str]]:
    """Return fixed enums only. Receipt absence and observed display gaps are distinct."""
    metrics = {'rows'}
    findings = set()
    if row.get('terminal_no_derived_effects'):
        return metrics | {'terminal_without_derivatives'}, findings
    if protected_for_review(row):
        return metrics | {'protected_or_unknown'}, findings
    if row.get('home_health_visibility_unknown'):
        return metrics | {'display_unknown'}, findings
    if hidden_for_review(row, show_held=True):
        return metrics | {'hidden_by_design'}, findings
    status = row.get('status')
    finished = card_content.utc(row.get('finished_at'))
    age = now - finished if finished else timedelta(0)
    if status == 'in_progress':
        metrics.add('in_progress')
        if age >= timedelta(hours=2):
            findings.add('capture_not_completed')
        return metrics, findings

    # Match the legacy list reader. Prepared Home, device grouping and legacy
    # transcripts lacking a projection receipt are outside this observation.
    if not isinstance(row.get('structured'), dict) and row.get('structured') is not None:
        return metrics | {'display_unknown'}, findings
    step = home_step.classify(row, show_held=True)
    if step == home_step.NOISE:
        return metrics | {'hidden_by_design'}, findings
    if status in ('processing', 'merging'):
        metrics.add('processing')
        if step == home_step.FAILED:
            findings.add('processing_expired')
        return metrics, findings
    metrics.add('classified_captures')
    if status == 'failed' or step == home_step.FAILED:
        findings.add('capture_failed')
    if step is None and not home_step_projection_enabled():
        metrics.add('home_step_unavailable')
    empty_receipt = row.get('record_transcription_empty')
    if empty_receipt:
        metrics.add('transcript_empty_receipt_present')
    landed = positive_revision(row.get('record_projection_revision')) and not empty_receipt
    if status == 'completed' and (landed or transcribing_hold.applies(row, stored=True)):
        metrics.add('transcript_expected')
        if not landed and (step == home_step.FAILED or transcribing_hold.failed(row)):
            findings.add('transcript_wait_expired')
    if not landed and status == 'completed':
        metrics.add('transcript_receipt_absent')

    summary = bool(row.get('summary_output_present') or row.get('summary_completed_at'))
    if summary:
        metrics.add('summary_receipted')
    elif row.get('summary_blocked_reason'):
        metrics.add('notes_blocked')
    elif step == home_step.WRITING_NOTES and not summary_owed(row) and held_for_notes(row, now=now.timestamp()):
        metrics.update({'notes_expected', 'notes_pending'})
    elif row.get('summary_output_present') is not False:
        metrics.add('summary_receipt_unknown')
    elif (
        status == 'completed'
        and landed
        and row.get('has_content') is True
        and not row.get('record_upload_failed')
        and not row.get('summary_retryable')
        and row.get('finalization_status') not in {'blocked_byok', 'dead_letter'}
        and not summary_delivery.intentional_short_clip_minimum(row)
        and row.get('user_title') is None
        and row.get('user_overview') is None
        and not summary_delivery.present(row.get('structured'))
        and not safe_body((row.get('structured') or {}).get('gist')).strip()
    ):
        metrics.add('notes_expected')
        due = row.get('summary_due_at')
        if age_gate.expired(
            {'first_pending_at': row.get('summary_first_pending_at')}, row.get('created_at'), now=now.timestamp()
        ):
            findings.add('notes_outside_repair_window')
        elif summary_owed(row):
            if type(due) in (int, float) and due <= now.timestamp():
                findings.add('notes_overdue')
            else:
                metrics.add('notes_pending')
        elif row.get('notes_written_at'):
            metrics.add('notes_attempt_without_delivery_receipt')
        elif age >= timedelta(seconds=deadline_seconds()):
            findings.add('notes_not_scheduled')
        else:
            metrics.add('notes_pending')
    if step != home_step.READY:
        return metrics, findings

    card = _presented(row, step, now)
    metrics.add('ready_cards')
    title, preview, emoji = card['title'], card['preview'], card['emoji']
    if not _has_text(title):
        findings.add('ready_title_missing')
        if not _has_text(preview):
            findings.add('ready_card_blank')
    elif is_fallback_title(title) and not _has_text(row.get('user_title')):
        findings.add('ready_title_generic')
    if not _has_text(emoji):
        findings.add('ready_emoji_missing')
    if summary:
        metrics.add('summary_receipted_cards')
        if not _has_text(preview):
            findings.add('summary_without_preview')
        if emoji in {DEFAULT_EMOJI, NEUTRAL_EMOJI}:
            findings.add('ready_emoji_default')
    return metrics, findings


@dataclass
class Review:
    """Hold transient owner counts solely to suppress small and repeated-symptom cells."""

    counts: Counter = field(default_factory=Counter)
    owners: set = field(default_factory=set)
    affected: dict = field(default_factory=lambda: defaultdict(Counter))
    denominators: dict = field(default_factory=lambda: defaultdict(set))

    def observe(self, owner, row, *, now):
        metrics, findings = inspect_row(row, now=now)
        self.owners.add(owner)
        self.counts.update(metrics)
        for metric in metrics:
            self.denominators[metric].add(owner)
        for symptom in findings:
            self.affected[symptom][owner] += 1
        return findings

    def receipt(self):
        if len(self.owners) < MIN_REPORT_OWNERS:
            return {'suppressed': True, 'metrics': {}, 'feedback': []}
        feedback = []
        for key, symptom in SYMPTOMS.items():
            owners = self.affected[key]
            # Zeroes on an observable population are useful for before/after.
            if len(self.denominators[symptom.denominator]) < MIN_REPORT_OWNERS or (
                owners and len(owners) < MIN_REPORT_OWNERS
            ):
                continue
            repeated = sum(value >= REPEATED_CARDS for value in owners.values())
            feedback.append(
                {
                    'issue_key': key,
                    'stage': symptom.stage,
                    'observation': symptom.description,
                    'investigate': symptom.drill_down,
                    'affected_rows': sum(owners.values()),
                    'observable_rows': self.counts[symptom.denominator],
                    'affected_owners': len(owners),
                    'owners_with_repeated_symptom': repeated if repeated >= MIN_REPORT_OWNERS else None,
                }
            )
        metrics = {
            key: value for key, value in sorted(self.counts.items()) if len(self.denominators[key]) >= MIN_REPORT_OWNERS
        }
        if any(0 < len(self.denominators[key]) < MIN_REPORT_OWNERS for key in ROW_CATEGORIES):
            metrics.pop('rows', None)
        return {'suppressed': False, 'metrics': metrics, 'feedback': feedback}
