"""One declaration per capability kind; shared dispatch contains no kind chains."""

from dataclasses import dataclass
from importlib import import_module


def _call(module, name, *args, **kwargs):
    return getattr(import_module(module), name)(*args, **kwargs)


@dataclass(frozen=True)
class Kind:
    validation: str
    application: str = 'apply_fields'
    patcher: str | None = None
    schema_rule: str = 'edit'
    default_policy: str = 'auto'
    key_rule: str = 'default'
    view_rule: str = 'default'
    allowed_fields: tuple[str, ...] = ()
    collections: tuple[str, ...] = ()
    tool: str = 'propose_edit'
    # Named deterministic checks. Unused until a verifier chain includes them.
    # None of these kinds are deterministic-sufficient: a passing check cannot
    # auto-apply on its own.
    verifier_checks: tuple[str, ...] = ()
    deterministic_sufficient: bool = False
    dream_only: bool = False

    def validate(self, *args, **kwargs):
        return _call('utils.agent_capabilities.tools', self.validation, *args, **kwargs)

    def apply(self, *args, **kwargs):
        return _call('utils.agent_capabilities.tools', self.application, *args, **kwargs)

    def patch(self, *args, **kwargs):
        return _call('utils.agent_capabilities.tools', self.patcher, *args, **kwargs)

    def schema(self, edit):
        return _call('utils.agent_capabilities.kind_schema', self.schema_rule, edit)

    def key(self, edit, records):
        return _call('utils.agent_capabilities.kind_keys', self.key_rule, edit, records)

    def undo(self, uid, change_id, undone=True):
        return _call('database.review_changes', 'set_undone', uid, change_id, undone)

    def change_view(self, edit, records):
        return _call('utils.agent_capabilities.kind_views', self.view_rule, edit, records)


KINDS = {
    'spelling': Kind(
        'validate_spelling', 'apply_spelling', 'patch_spelling', key_rule='spelling', verifier_checks=('spelling',)
    ),
    'title': Kind(
        'validate_summary',
        patcher='patch_summary',
        allowed_fields=('structured.title', 'user_title'),
        collections=('conversations',),
    ),
    'overview': Kind(
        'validate_summary',
        patcher='patch_summary',
        allowed_fields=('structured.overview', 'structured.sections', 'structured.note_claims'),
        collections=('conversations',),
    ),
    'memory': Kind('validate_memory', 'apply_memory', default_policy='suggest', key_rule='memory'),
    'resolve_required_memory': Kind(
        'validate_required_intake', 'apply_required_intake', schema_rule='required_intake', dream_only=True
    ),
    'merge_memories': Kind(
        'validate_memory',
        'apply_memory_merge',
        schema_rule='memory_merge',
        key_rule='merge_memory',
        view_rule='merge_memory',
    ),
    'retire_memory': Kind('validate_hygiene', 'apply_hygiene', schema_rule='hygiene', key_rule='hygiene'),
    'supersede_memory': Kind('validate_hygiene', 'apply_hygiene', schema_rule='hygiene', key_rule='hygiene'),
    'merge_people': Kind('validate_entity', 'apply_people', key_rule='merge', view_rule='merge_people'),
    'entity_summary': Kind(
        'validate_entity',
        'apply_entity',
        default_policy='suggest',
        allowed_fields=('summary', 'updated_at'),
        collections=('entity_pages',),
    ),
    'close_task': Kind(
        'validate_task',
        patcher='patch_task',
        default_policy='suggest',
        allowed_fields=('status', 'completed', 'completed_at'),
        collections=('action_items',),
    ),
    'dismiss_person': Kind(
        'validate_cleanup',
        'apply_cleanup',
        schema_rule='retire',
        key_rule='retire',
        allowed_fields=('is_dismissed', 'dismissed_at', 'updated_at'),
        collections=('people',),
    ),
    'merge_tasks': Kind(
        'validate_cleanup',
        'apply_cleanup',
        schema_rule='merge',
        key_rule='merge',
        allowed_fields=('status', 'completed', 'completed_at', 'deleted', 'superseded_by', 'updated_at'),
        collections=('action_items',),
    ),
    'retire_task': Kind(
        'validate_cleanup',
        'apply_cleanup',
        schema_rule='retire',
        key_rule='retire',
        allowed_fields=('status', 'completed', 'completed_at', 'deleted', 'superseded_by', 'updated_at'),
        collections=('action_items',),
    ),
    'merge_conversations': Kind(
        'validate_cleanup',
        'apply_cleanup',
        schema_rule='merge',
        key_rule='merge',
        allowed_fields=('dream_duplicate_of', 'dream_duplicate'),
        collections=('conversations',),
        verifier_checks=('duplicate_capture',),
    ),
    'set_language': Kind(
        'validate_cleanup',
        'apply_cleanup',
        schema_rule='language',
        allowed_fields=('language',),
        collections=('conversations',),
        verifier_checks=('language',),
    ),
}
KINDS['vocabulary'] = Kind(
    'validate_vocabulary',
    'apply_vocabulary_entry',
    schema_rule='term',
    key_rule='vocabulary',
    allowed_fields=('source',),
    collections=('dream_vocabulary',),
    tool='learn_term',
)
ALL_EDIT_KINDS = {name: spec for name, spec in KINDS.items() if spec.tool == 'propose_edit'}
EDIT_KINDS = {name: spec for name, spec in ALL_EDIT_KINDS.items() if not spec.dream_only}
AUTO = frozenset(name for name, spec in KINDS.items() if spec.default_policy == 'auto')


def get_kind(name):
    from utils.agent_capabilities.errors import ToolError

    if name not in KINDS:
        raise ToolError('agent_unknown_edit_kind', field='kind', expected='A registered capability kind')
    return KINDS[name]


def journal_fields():
    """Allowed patch surface derives from each capability declaration."""
    fields = {}
    for spec in KINDS.values():
        for collection in spec.collections:
            fields.setdefault(collection, set()).update(spec.allowed_fields)
    # Existing non-Harness operations retain their journal contract here.
    fields.setdefault('conversations', set()).update({'transcript_segments', 'manual_speaker_assignments'})
    fields.setdefault('people', set()).update({'name', 'aliases', 'organization', 'subtitle'})
    fields['knowledge_nodes'] = {
        'label',
        'label_lower',
        'aliases',
        'aliases_lower',
        'merged_entity_ids',
        'redirect_entity_id',
    }
    return fields
