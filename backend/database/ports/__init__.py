"""Storage-neutral domain contracts. Import adapters explicitly at the composition boundary."""

from .base import CommitFence, MutationConflict, Page, RevisionConflict, SpaceId, SpaceStore, SpaceTx
from .folders import FolderCreate, FolderEntity, FolderUpdate, FoldersRepo, FoldersTx
from .people import GenerationFence, PeopleRepo, PeopleTx, PersonDraft, PersonEntity

__all__ = [
    'MutationConflict',
    'Page',
    'RevisionConflict',
    'SpaceId',
    'SpaceStore',
    'SpaceTx',
    'FolderCreate',
    'FolderEntity',
    'FolderUpdate',
    'FoldersRepo',
    'FoldersTx',
    'GenerationFence',
    'PeopleRepo',
    'PeopleTx',
    'PersonDraft',
    'PersonEntity',
]

from .action_items import (
    TaskRelationshipConflictError,
    ActionItemEntity,
    ActionItemDraft,
    ActionItemTransactionLimitError,
    TaskRelationshipRule,
    ActionItemsTx,
    ActionItemsRepo,
)

__all__ += [
    'TaskRelationshipConflictError',
    'ActionItemEntity',
    'ActionItemDraft',
    'ActionItemTransactionLimitError',
    'TaskRelationshipRule',
    'ActionItemsTx',
    'ActionItemsRepo',
]

from .goals import (
    GoalStoreError,
    GoalNotFoundError,
    GoalConflictError,
    GoalValidationError,
    GoalEntity,
    GoalCreate,
    GoalUpdate,
    GoalProgressEventEntity,
    GoalsTx,
    GoalsRepo,
)

__all__ += [
    'GoalStoreError',
    'GoalNotFoundError',
    'GoalConflictError',
    'GoalValidationError',
    'GoalEntity',
    'GoalCreate',
    'GoalUpdate',
    'GoalProgressEventEntity',
    'GoalsTx',
    'GoalsRepo',
]

from .workstreams import (
    WorkstreamStoreError,
    WorkstreamNotFoundError,
    WorkstreamConflictError,
    WorkstreamGenerationMismatchError,
    WorkstreamEntity,
    WorkstreamCreate,
    WorkstreamUpdate,
    WorkstreamEventEntity,
    ArtifactDescriptorEntity,
    ContinuationCheckpointEntity,
    WorkstreamsTx,
    WorkstreamsRepo,
)

__all__ += [
    'WorkstreamStoreError',
    'WorkstreamNotFoundError',
    'WorkstreamConflictError',
    'WorkstreamGenerationMismatchError',
    'WorkstreamEntity',
    'WorkstreamCreate',
    'WorkstreamUpdate',
    'WorkstreamEventEntity',
    'ArtifactDescriptorEntity',
    'ContinuationCheckpointEntity',
    'WorkstreamsTx',
    'WorkstreamsRepo',
]

__all__ += ['CommitFence']
