"""Dream-owned profile v2: ref-grounded lines and a deterministic render (shadow only).

The profile never owns a fact: every line cites one to three records from the
owner's stores, and a people line must also cite an owner-side record so no
third-party-only fact is rendered (INV-MEM-6). Line 1 of the render is always the
owner's name from the user document, never model output, because
``database.auth`` parses the first profile line as the owner's name. The render is
byte-stable (fixed section order, sorted lines, no timestamps) so prompt caches
that will carry it survive unchanged weeks. Nothing reads this field yet.
"""

import hashlib
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from models.dream_edit import Strict

SECTION_IDS = ('identity', 'work', 'projects', 'people', 'routines', 'preferences', 'goals')
MAX_SECTIONS = 8
MAX_LINES = 60
MAX_LINES_PER_SECTION = 12
MAX_RENDER_CHARS = 6000
RENDERER_VERSION = 1

SectionId = Literal['identity', 'work', 'projects', 'people', 'routines', 'preferences', 'goals']


class ProfileLineOp(Strict):
    op: Literal['add', 'update', 'drop']
    line_id: str = Field(default='', max_length=64, description='Existing line id; required for update and drop.')
    section: SectionId
    text: str = Field(default='', max_length=200, description='Third person, one fact; required for add/update.')
    refs: list[str] = Field(default_factory=list, max_length=3, description='1-3 refs from the supplied corpus.')


class ProfileLine(Strict):
    id: str = Field(min_length=1, max_length=64)
    text: str = Field(min_length=1, max_length=200)
    refs: list[str] = Field(min_length=1, max_length=3)
    pinned: bool = False
    updated_at: str = ''
    run_id: str = ''


class ProfileSection(Strict):
    id: SectionId
    lines: list[ProfileLine] = Field(default_factory=list, max_length=MAX_LINES_PER_SECTION)


class RenderedProfile(Strict):
    profile_text: str
    renderer_version: int = RENDERER_VERSION
    rendered_at: str = ''
    source_stamp: str = ''


class ProfileV2(Strict):
    schema_version: int = 2
    identity_name: str = ''
    sections: list[ProfileSection] = Field(default_factory=list, max_length=MAX_SECTIONS)
    rendered: RenderedProfile | None = None


def _collection(ref: str) -> str:
    return ref.split('/', 1)[0]


def line_id(run_id: str, section: str, text: str) -> str:
    return str(uuid5(NAMESPACE_URL, run_id + ':' + section + ':' + hashlib.sha256(text.encode()).hexdigest()[:8]))


def _grounded(op: ProfileLineOp, corpus_refs: set[str]) -> bool:
    if not 1 <= len(op.refs) <= 3 or any(ref not in corpus_refs for ref in op.refs):
        return False
    if op.section == 'people':
        # A people line must also cite something the owner said or holds.
        return any(_collection(ref) != 'people' for ref in op.refs)
    return True


def apply_ops(
    previous: ProfileV2 | None, ops: list[ProfileLineOp], *, run_id: str, now: str, corpus_refs: set[str]
) -> tuple[ProfileV2, dict[str, int]]:
    """Apply validated line ops; invalid ops are dropped and counted, never raised."""
    counts = {'add': 0, 'update': 0, 'drop': 0, 'rejected': 0, 'identity_ignored': 0}
    sections = {section.id: list(section.lines) for section in (previous.sections if previous else [])}
    for op in ops:
        if op.section == 'identity':
            # The identity line is the user-doc name; models never write it.
            counts['identity_ignored'] += 1
            continue
        lines = sections.setdefault(op.section, [])
        index = next((i for i, line in enumerate(lines) if line.id == op.line_id), None) if op.line_id else None
        if op.op == 'drop':
            if index is None or lines[index].pinned:
                counts['rejected'] += 1
                continue
            lines.pop(index)
            counts['drop'] += 1
            continue
        text = ' '.join(op.text.split())
        if not text or not _grounded(op, corpus_refs):
            counts['rejected'] += 1
            continue
        if op.op == 'update':
            if index is None or lines[index].pinned:
                counts['rejected'] += 1
                continue
            lines[index] = ProfileLine(id=lines[index].id, text=text, refs=op.refs, updated_at=now, run_id=run_id)
            counts['update'] += 1
            continue
        if len(lines) >= MAX_LINES_PER_SECTION or sum(len(rows) for rows in sections.values()) >= MAX_LINES:
            counts['rejected'] += 1
            continue
        lines.append(
            ProfileLine(id=line_id(run_id, op.section, text), text=text, refs=op.refs, updated_at=now, run_id=run_id)
        )
        counts['add'] += 1
    ordered = [ProfileSection(id=section, lines=sections[section]) for section in SECTION_IDS if sections.get(section)][
        :MAX_SECTIONS
    ]
    return ProfileV2(sections=ordered), counts


def render(
    profile: ProfileV2, *, identity_name: str, corpus_refs: set[str], rendered_at: str, section_digests: dict[str, str]
) -> tuple[RenderedProfile, int]:
    """Byte-stable text; returns (rendered, stale_line_count). Ungrounded lines are excluded."""
    name = ' '.join(str(identity_name or '').split()) or 'The owner'
    out = [f'- {name}']
    stale = 0
    cited: set[str] = set()
    for section_id in SECTION_IDS:
        section = next((section for section in profile.sections if section.id == section_id), None)
        if section is None:
            continue
        for line in sorted(section.lines, key=lambda row: row.id):
            if any(ref not in corpus_refs for ref in line.refs):
                stale += 1
                continue
            out.append(f'- {line.text}')
            cited.update(line.refs)
    text = '\n'.join(out)
    if len(text) > MAX_RENDER_CHARS:
        # Deterministic: drop whole trailing lines, never cut mid-line.
        kept = []
        for row in out:
            if len('\n'.join([*kept, row])) > MAX_RENDER_CHARS:
                break
            kept.append(row)
        text = '\n'.join(kept)
    stamp_parts = sorted({section_digests.get(_section_of(ref), '') for ref in cited})
    stamp = hashlib.sha256('|'.join(stamp_parts).encode()).hexdigest()
    return RenderedProfile(profile_text=text, rendered_at=rendered_at, source_stamp=stamp), stale


_COLLECTION_SECTION = {
    'people': 'people',
    'action_items': 'tasks',
    'memory_items': 'memories',
    'memories': 'memories',
    'conversations': 'conversations',
}


def _section_of(ref: str) -> str:
    return _COLLECTION_SECTION.get(_collection(ref), 'other')


def to_doc(profile: ProfileV2, rendered: RenderedProfile, identity_name: str) -> dict[str, Any]:
    return {
        **profile.model_dump(mode='json', exclude={'rendered', 'identity_name'}),
        'identity_name': identity_name,
        'rendered': rendered.model_dump(mode='json'),
    }


def from_doc(doc: Any) -> ProfileV2 | None:
    if not isinstance(doc, dict):
        return None
    try:
        # Side metadata (rendered, notes, run_started_at, ...) lives beside the schema fields.
        fields = set(ProfileV2.model_fields) - {'rendered'}
        return ProfileV2.model_validate({key: value for key, value in doc.items() if key in fields})
    except Exception:
        return None
