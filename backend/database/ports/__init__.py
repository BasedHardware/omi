"""Storage-neutral domain contracts. Import adapters explicitly at the composition boundary."""

from .base import MutationConflict, Page, RevisionConflict, SpaceId, SpaceStore, SpaceTx
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
