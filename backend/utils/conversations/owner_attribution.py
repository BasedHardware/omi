"""Source-cluster evidence is the authority for owner-attributed memory writes."""

from dataclasses import dataclass, field
from collections.abc import Mapping
import re
from typing import Any, Literal, Optional, Sequence

from config.refactor_modes import default_on

OwnerTrust = Literal["unique_owner", "no_owner", "multi_owner", "no_speaker_ids"]
ClusterKey = tuple[Optional[str], Any]
OWNER_MATCH_SOURCES = frozenset(('conversation_voice', 'speaker_evidence_v2'))


def _field(row: Any, key: str, default: Any = None) -> Any:
    return row.get(key, default) if isinstance(row, Mapping) else getattr(row, key, default)


def speaker_cluster_key(segment: Any) -> Optional[ClusterKey]:
    """Return the scope-qualified cluster identity, or None when it is not evidence.

    Numeric ``speaker_id`` values are conversation-local and can repeat across
    ``speaker_id_scope`` values after a merge. A TranscriptSegment that only
    materialized ``speaker_id`` from the SPEAKER_00 default is not a cluster.
    """
    if _field(segment, "_speaker_id_synthesized", False):
        return None
    speaker_id = _field(segment, "speaker_id")
    if speaker_id is None:
        return None
    return (_field(segment, "speaker_id_scope"), speaker_id)


def count_speaker_ids(segments: Any) -> tuple[int, int]:
    """Return distinct cluster counts and clusters flagged as the account owner."""
    distinct: set[ClusterKey] = set()
    owner: set[ClusterKey] = set()
    for segment in segments:
        key = speaker_cluster_key(segment)
        if key is None:
            continue
        distinct.add(key)
        if getattr(segment, "is_user", False):
            owner.add(key)
    return len(distinct), len(owner)


@dataclass(frozen=True)
class OwnerAttributionEvidence:
    distinct_speaker_ids: int
    owner_speaker_ids: int
    owner_cluster_id: Optional[ClusterKey]
    trust: OwnerTrust

    @classmethod
    def from_segments(cls, segments: Sequence[Any]) -> "OwnerAttributionEvidence":
        distinct, owners = count_speaker_ids(segments)
        trust: OwnerTrust = (
            "no_speaker_ids"
            if distinct == 0
            else "no_owner" if owners == 0 else "multi_owner" if owners > 1 else "unique_owner"
        )
        cluster: Optional[ClusterKey] = None
        if trust == "unique_owner":
            for segment in segments:
                if not getattr(segment, "is_user", False):
                    continue
                key = speaker_cluster_key(segment)
                if key is not None:
                    cluster = key
                    break
        return cls(distinct, owners, cluster, trust)


def may_attribute_to_owner(evidence: OwnerAttributionEvidence, *, segment: Any = None) -> bool:
    """Admit a user fact, or bind a quote only to the uniquely identified owner cluster.

    Legacy transcripts without cluster evidence fail closed. Segment labels alone
    cannot override the conversation's evidence, including for quote promotion.
    """
    return evidence.trust == "unique_owner" and (
        segment is None or speaker_cluster_key(segment) == evidence.owner_cluster_id
    )


def confident_owner_segments(segments: Sequence[Any]) -> list[Any]:
    """Memory input requires a positive identity decision, never a legacy boolean.

    Keep the full transcript for notes/playback. Only this derived input is
    narrowed. Ambiguous multi-owner clusters and a carried ``is_user`` without
    a current user decision do not authorize memory formation. An explicit
    manual label is a positive owner decision too.
    """
    roles = speaker_role_projection(segments)
    if roles is not None:
        return [row for row in segments if roles.for_segment(row).role == 'primary_user']
    # TranscriptSegment supplies status='user' for a legacy is_user payload.
    # That compatibility default is not an identity decision. Require the
    # producer's positive-match provenance (or the explicit manual authority).
    trusted = [
        segment
        for segment in segments
        if getattr(segment, 'is_user', False)
        and not getattr(segment, 'person_id', None)
        and (
            getattr(segment, 'speaker_label_source', None) == 'manual'
            or (
                getattr(segment, 'speaker_identity_status', None) == 'user'
                and getattr(segment, 'speaker_match_source', None) in OWNER_MATCH_SOURCES
                and getattr(segment, 'speaker_label_source', None) != 'carried'
            )
        )
    ]
    # An unproven legacy boolean on another voice must not veto a real manual
    # confirmation. Ambiguity is measured across trusted owner decisions only.
    evidence = OwnerAttributionEvidence.from_segments(trusted)
    return [segment for segment in trusted if may_attribute_to_owner(evidence, segment=segment)]


@dataclass(frozen=True)
class SpeakerRole:
    role: Literal['primary_user', 'other', 'unknown'] = 'unknown'
    person_id: Optional[str] = None
    display_name: Optional[str] = None

    def name(self, owner_name: str, names: Mapping[str, str]) -> Optional[str]:
        value = owner_name if self.role == 'primary_user' else names.get(self.person_id or '') or self.display_name
        return ' '.join(value.split()) if value else None


UNKNOWN_ROLE = SpeakerRole()
OWNER_ROLE = SpeakerRole('primary_user')


@dataclass(frozen=True)
class SpeakerRoleMap:
    """Prompt-only identities; a manual excerpt never labels its unconfirmed siblings."""

    rows: tuple[Any, ...]
    roles: tuple[SpeakerRole, ...]
    clusters: Mapping[ClusterKey, SpeakerRole]
    _by_identity: Mapping[int, SpeakerRole] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, '_by_identity', {id(row): role for row, role in zip(self.rows, self.roles)})

    def for_segment(self, segment: Any) -> SpeakerRole:
        # Identity matters for segment-only manual authority. Do not fall back
        # to a numeric cluster for a row outside the supplied evidence.
        return self._by_identity.get(id(segment), UNKNOWN_ROLE)


def _positive_owner(row: Any) -> bool:
    return bool(
        _field(row, 'is_user', False)
        and not _field(row, 'person_id')
        and (
            _field(row, 'speaker_label_source') == 'manual'
            or (
                _field(row, 'speaker_identity_status') == 'user'
                and _field(row, 'speaker_match_source') in OWNER_MATCH_SOURCES
                and _field(row, 'speaker_label_source') != 'carried'
            )
        )
    )


def speaker_role_map(
    segments: Sequence[Any], *, evidence: Any = None, resolution_available: bool = True
) -> SpeakerRoleMap:
    """Resolve scoped owner/contact roles without IO, environment reads or mutation.

    A positive owner decision needs a real scoped cluster and no second positive
    owner cluster. Contradictory labels make the cluster unbound. Explicit manual
    authority applies only to that row; it does not turn the rest of a voice into
    the owner. Legacy/carried booleans are never positive owner evidence.
    """
    rows = tuple(segments)
    groups: dict[ClusterKey, list[Any]] = {}
    for row in rows:
        key = speaker_cluster_key(row)
        if key is not None:
            groups.setdefault(key, []).append(row)
    owners = {key for key, members in groups.items() if any(_positive_owner(row) for row in members)}
    contact_evidence: dict[str, SpeakerRole] = {}
    if resolution_available and evidence is not None and _field(evidence, 'status') != 'unavailable':
        for cluster in _field(evidence, 'clusters', ()):
            eligible = [
                candidate
                for candidate in _field(cluster, 'candidates', ())
                if _field(candidate, 'label_eligible', False) and _field(candidate, 'band') != 'unknown'
            ]
            best = max(eligible, key=lambda candidate: _field(candidate, 'probability', 0), default=None)
            if best is None or _field(best, 'band') != 'confident' or _field(best, 'person_id') == 'owner':
                continue
            if _field(best, 'source') not in ('voice', 'channel', 'near_field', 'manual'):
                continue
            for sid in _field(cluster, 'segment_ids', ()):
                if _field(best, 'source') == 'manual' and sid not in (_field(best, 'segment_ids') or ()):
                    continue
                contact_evidence[sid] = SpeakerRole('other', _field(best, 'person_id'), _field(best, 'name'))

    def claim(row: Any) -> SpeakerRole:
        manual = _field(row, 'speaker_label_source') == 'manual'
        if _positive_owner(row) and len(owners) == 1 and (resolution_available or manual):
            return OWNER_ROLE
        if _field(row, 'person_id') and not _field(row, 'is_user', False) and (resolution_available or manual):
            person_id = str(_field(row, 'person_id'))
            candidate = contact_evidence.get(_field(row, 'id'))
            if candidate and candidate.person_id != person_id and not manual:
                return UNKNOWN_ROLE
            return SpeakerRole('other', person_id, candidate.display_name if candidate else _field(row, 'person_name'))
        if not _field(row, 'is_user', False) and not manual:
            return contact_evidence.get(_field(row, 'id'), UNKNOWN_ROLE)
        return UNKNOWN_ROLE

    clusters: dict[ClusterKey, SpeakerRole] = {}
    for key, members in groups.items():
        claims = {claim(row) for row in members}
        clusters[key] = next(iter(claims)) if len(claims) == 1 else UNKNOWN_ROLE
    roles = []
    for row in rows:
        key = speaker_cluster_key(row)
        role = clusters.get(key, UNKNOWN_ROLE) if key is not None else UNKNOWN_ROLE
        if key is not None and _field(row, 'speaker_label_source') == 'manual':
            role = claim(row)
        roles.append(role)
    return SpeakerRoleMap(rows, tuple(roles), clusters)


def speaker_role_projection(
    segments: Sequence[Any], *, evidence: Any = None, resolution_available: bool = True
) -> Optional[SpeakerRoleMap]:
    """The single default-on rollback boundary for derived role consumers."""
    return (
        speaker_role_map(segments, evidence=evidence, resolution_available=resolution_available)
        if default_on('SPEAKER_ROLE_PROJECTION_ENABLED')
        else None
    )


def normalized_evidence_quote(value: str) -> str:
    return re.sub(r'[\W_]+', ' ', str(value or '').casefold()).strip()


def grounded_quote_segments(quotes: Sequence[str], segments: Sequence[Any]) -> Optional[list[Any]]:
    """Every quote must have exactly one source row, including repeated text."""
    matched = []
    for quote in quotes:
        normalized = normalized_evidence_quote(quote)
        candidates = [
            row
            for row in segments
            if normalized and f' {normalized} ' in f" {normalized_evidence_quote(_field(row, 'text', ''))} "
        ]
        if len(candidates) != 1:
            return None
        matched.append(candidates[0])
    return matched or None


def owner_spoken_for_quotes(quotes: Sequence[str], segments: Sequence[Any]) -> bool:
    matched = grounded_quote_segments(quotes, segments)
    if not matched:
        return False
    roles = speaker_role_projection(segments)
    if roles is not None:
        return all(roles.for_segment(row).role == 'primary_user' for row in matched)
    evidence = OwnerAttributionEvidence.from_segments(segments)
    return all(may_attribute_to_owner(evidence, segment=row) for row in matched)


def quote_source_attribution(
    quotes: Sequence[str], segments: Sequence[Any]
) -> Literal['user_spoken', 'third_party', 'unknown']:
    """Resolve utterance authorship independently of the extracted subject."""
    matched = grounded_quote_segments(quotes, segments)
    roles = speaker_role_projection(segments)
    if not matched or roles is None:
        return 'user_spoken' if owner_spoken_for_quotes(quotes, segments) else 'unknown'
    sources = {roles.for_segment(row).role for row in matched}
    if sources == {'primary_user'}:
        return 'user_spoken'
    return 'third_party' if sources == {'other'} else 'unknown'


def explicitly_self_referential(quotes: Sequence[str], segments: Sequence[Any]) -> bool:
    """A conservative sufficient signal, never a language-based rejection rule.

    Other languages stay retained with unknown aboutness unless a later semantic
    authority resolves them. A speaker identity alone cannot establish a subject.
    """
    matched = grounded_quote_segments(quotes, segments)
    if not matched or any(
        normalized_evidence_quote(quote) != normalized_evidence_quote(_field(row, 'text', ''))
        for quote, row in zip(quotes, matched)
    ):
        # A first-person fragment inside the owner's report of another person's
        # words is not an explicit self-reference by the owner.
        return False
    return all(
        re.match(
            r"\s*i(?:['’]m\b|\s+(?:am|was|have|own|live|prefer|want|need|will|plan|work|feel)\b)", quote, re.IGNORECASE
        )
        for quote in quotes
    )
