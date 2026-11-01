"""Strict constructor frozen from main 0d8e1258, before E1."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PreE1ProjectionBinding:
    """Immutable intake metadata; never inferred from a GPU result body.

    Stored as ``jobs[segment_id].projection_binding``. Every sibling names the
    same bounded complete ``segment_ids`` set. Result-log entries additionally
    carry ``previous_segment_id`` (null at the start of an owner log), so
    projection can preserve the committed capture order under concurrent pumps.
    """

    owner_id: str
    job_id: str
    content_id: str
    segment_ids: tuple[str, ...]
    source: str = 'omi'
    client_device_id: str | None = None
    client_platform: str | None = None
    is_locked: bool = False
    private_cloud_sync_enabled: bool = False
    data_protection_level: str = 'enhanced'
    target_conversation_id: str | None = None
    run_token: str | None = None
    run_epoch: int | None = None
    privacy_generation: int = 0
    language: str | None = None
    record_origin: bool = False
    native_record: bool = False

    def __post_init__(self):
        # Firestore caps transaction writes at 500; completion reads all siblings.
        if not self.owner_id or not self.job_id or not self.content_id:
            raise ValueError('projection requires owner, job and content identities')
        if not 1 <= len(self.segment_ids) <= 128 or len(set(self.segment_ids)) != len(self.segment_ids):
            raise ValueError('projection requires 1..128 unique sibling segments')
        for value in (self.owner_id, self.job_id, self.content_id, *self.segment_ids):
            if '/' in value or not value or len(value.encode()) > 256:
                raise ValueError('projection identities must be bounded document IDs')
        if self.data_protection_level not in {'standard', 'enhanced'}:
            raise ValueError('unsupported projection protection level')
        if (self.run_token is None) != (self.run_epoch is None):
            raise ValueError('projection run token and epoch must be paired')
        if self.privacy_generation < 0:
            raise ValueError('invalid privacy generation')
